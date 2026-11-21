"""Option C Label-Signing Recall Evaluation Runner for Simon Discovery Scout.

Evaluates Discovery Scout outputs (local handoff JSONs, SQLite/Firestore leads &
agent_reports, or live staging API leads) against the 10-artist benchmark in
`data/evals/label_signing_recall_eval.json`:
  - Layer 1 Hard Gates:
      * gate_benchmark_integrity (canonical YouTube URLs, <=100k metrics, zero brief leakage)
      * gate_seed_source_coverage (all in-map overlapping_seed_sources exist & are active)
  - Layer 3 Recall Dimensions:
      * recall_in_map (6 NYC/session-overlapping label signings)
      * recall_out_of_map (4 out-of-map cold-discovery label signings)
      * recall_overall (all 10 label signings)

Emits a canonical `SimonEvalRun` scorecard (`data/evals/eval_run_schema.json`)
compatible with `/evals` and `POST /api/eval-runs`.

Usage:
  python3 -m simon.recall_eval --save-local --out local/evals/discovery-label-recall-latest.json
  python3 -m simon.recall_eval --source-url https://simon-staging-139550420825.us-east1.run.app
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest
import uuid

from .db_tools import list_agent_documents
from .store import SimonStore, create_store

REPO_ROOT = Path(__file__).resolve().parents[1]
RECALL_BENCHMARK_PATH = REPO_ROOT / "data" / "evals" / "label_signing_recall_eval.json"
SEED_SOURCES_PATH = REPO_ROOT / "data" / "reference" / "discovery_sources_seed.json"

YT_WATCH_RE = re.compile(r"^https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})$")
YT_ID_EXTRACT_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/diacritics, and collapse punctuation for robust artist matching."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()
    if cleaned.startswith("the "):
        cleaned = cleaned[4:].strip()
    return cleaned


def extract_youtube_ids(text_or_urls: Iterable[str]) -> Set[str]:
    ids: Set[str] = set()
    for item in text_or_urls:
        if not item:
            continue
        for match in YT_ID_EXTRACT_RE.finditer(str(item)):
            ids.add(match.group(1))
    return ids


def load_recall_benchmark(path: Path = RECALL_BENCHMARK_PATH) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Recall benchmark not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_seed_sources(path: Path = SEED_SOURCES_PATH) -> Dict[str, Dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Seed sources not found at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(src["source_id"]): src
        for src in (raw.get("sources") or [])
        if isinstance(src, dict) and src.get("source_id")
    }


def validate_benchmark_integrity(benchmark: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Check canonical YouTube URLs, metric bounds (200-100k), and zero brief leakage."""
    errors: List[str] = []
    artists = benchmark.get("artists") or []
    if not artists:
        return False, ["Benchmark has no artists."]

    artist_names = [str(a.get("stage_name") or "") for a in artists]
    label_names = [str(a.get("label") or "") for a in artists]

    for a in artists:
        aid = str(a.get("id") or a.get("stage_name") or "unknown")
        bucket = a.get("bucket")
        if bucket not in ("in_map", "out_of_map"):
            errors.append(f"{aid}: invalid bucket '{bucket}'")
        metrics = a.get("metrics") or {}
        subs = metrics.get("youtube_subscribers")
        if subs is not None and not (200 <= int(subs) <= 100000):
            errors.append(f"{aid}: youtube_subscribers={subs} outside [200, 100000]")
        spotify = metrics.get("spotify_monthly_listeners_approx")
        if spotify is not None and int(spotify) > 100000:
            errors.append(f"{aid}: spotify_monthly_listeners_approx={spotify} exceeds 100000")
        videos = metrics.get("sample_videos") or []
        if not videos:
            errors.append(f"{aid}: missing sample_videos")
        for v in videos:
            url = str(v.get("url") or "")
            if not YT_WATCH_RE.match(url):
                errors.append(f"{aid}: non-canonical YouTube URL '{url}'")

    # Ensure recommended briefs do not leak artist names or record label names.
    for b in benchmark.get("recommended_run_briefs") or []:
        bid = str(b.get("brief_id") or "brief")
        text_norm = normalize_name(str(b.get("search_brief") or ""))
        for name in artist_names:
            nn = normalize_name(name)
            if nn and nn in text_norm:
                errors.append(f"{bid}: leaks artist name '{name}'")
        for lbl in label_names:
            # Check primary label token before parentheses/slashes
            primary = lbl.split("(")[0].split("/")[0].strip()
            ln = normalize_name(primary)
            if ln and len(ln) >= 4 and ln in text_norm:
                errors.append(f"{bid}: leaks label name '{primary}'")

    return len(errors) == 0, errors


def validate_seed_source_coverage(
    benchmark: Dict[str, Any],
    seed_sources: Dict[str, Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Verify every in_map artist references active source_ids present in discovery_sources_seed.json."""
    errors: List[str] = []
    for a in benchmark.get("artists") or []:
        if a.get("bucket") != "in_map":
            continue
        aid = str(a.get("id") or a.get("stage_name"))
        overlaps = a.get("overlapping_seed_sources") or []
        if not overlaps:
            errors.append(f"{aid}: in_map artist has no overlapping_seed_sources")
            continue
        for sid in overlaps:
            src = seed_sources.get(sid)
            if src is None:
                errors.append(f"{aid}: unknown seed source '{sid}'")
            elif src.get("status") != "active":
                errors.append(f"{aid}: seed source '{sid}' status is '{src.get('status')}' (expected active)")
    return len(errors) == 0, errors


def extract_observed_leads_from_payloads(payloads: Iterable[Dict[str, Any]]) -> Tuple[Set[str], Set[str], Set[str]]:
    """Collect normalized stage names, YouTube video IDs, and channel handles from leads/handoffs/reports."""
    names: Set[str] = set()
    video_ids: Set[str] = set()
    handles: Set[str] = set()

    def _ingest_lead(lead: Dict[str, Any]) -> None:
        for key in ("stage_name", "name", "artist_name", "subject_name"):
            val = lead.get(key)
            if isinstance(val, str) and val.strip():
                names.add(normalize_name(val))
        urls: List[str] = []
        for src in lead.get("seed_sources") or []:
            if isinstance(src, dict) and src.get("url"):
                urls.append(str(src["url"]))
        for link in lead.get("links") or lead.get("video_urls") or []:
            urls.append(str(link))
        if lead.get("url"):
            urls.append(str(lead["url"]))
        video_ids.update(extract_youtube_ids(urls))
        for u in urls:
            m = re.search(r"youtube\.com/(@[A-Za-z0-9._-]+)", u, re.IGNORECASE)
            if m:
                handles.add(m.group(1).lower())

    for obj in payloads:
        if not isinstance(obj, dict):
            continue
        doc = obj.get("data") if isinstance(obj.get("data"), dict) else obj
        if isinstance(doc.get("output"), dict):
            doc = doc["output"]
        if isinstance(doc.get("leads"), list):
            for lead in doc["leads"]:
                if isinstance(lead, dict):
                    _ingest_lead(lead)
        elif any(k in doc for k in ("stage_name", "artist_name", "subject_name")):
            _ingest_lead(doc)

    return names, video_ids, handles


def fetch_staging_leads(base_url: str, token: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch live leads & agent_reports from a Simon platform instance."""
    collected: List[Dict[str, Any]] = []
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for endpoint_path in (f"/api/agent-db/leads?limit={limit}", f"/api/agent-db/agent_reports?limit={limit}"):
        url = base_url.rstrip("/") + endpoint_path
        req = urlrequest.Request(url, headers=headers, method="GET")
        try:
            with urlrequest.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("documents") or data.get("items") or data.get("reports") or []
                if isinstance(rows, list):
                    collected.extend(r for r in rows if isinstance(r, dict))
        except (urlerror.HTTPError, urlerror.URLError, TimeoutError, ValueError):
            continue
    return collected


def run_recall_eval(
    *,
    benchmark_path: Path = RECALL_BENCHMARK_PATH,
    seed_sources_path: Path = SEED_SOURCES_PATH,
    handoff_payloads: Optional[List[Dict[str, Any]]] = None,
    store: Optional[SimonStore] = None,
    source_url: Optional[str] = None,
    source_token: Optional[str] = None,
    trigger: str = "cli",
    git_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Option C label-signing recall eval and return a canonical SimonEvalRun dict."""
    benchmark = load_recall_benchmark(benchmark_path)
    seed_sources = load_seed_sources(seed_sources_path)

    integrity_ok, integrity_errors = validate_benchmark_integrity(benchmark)
    coverage_ok, coverage_errors = validate_seed_source_coverage(benchmark, seed_sources)
    passed_gates = integrity_ok and coverage_ok

    # Gather candidate discovery outputs from explicit payloads, local/Firestore store, and/or staging URL.
    payloads: List[Dict[str, Any]] = list(handoff_payloads or [])
    sample_source = "golden_dataset"
    if store is not None:
        for coll in ("leads", "discovery_handoffs", "agent_reports"):
            docs = list_agent_documents(store, coll, limit=100)
            if docs:
                payloads.extend(docs)
                sample_source = "mixed" if handoff_payloads else "live_reports"
    if source_url:
        remote_docs = fetch_staging_leads(source_url, token=source_token)
        if remote_docs:
            payloads.extend(remote_docs)
            sample_source = "live_reports"

    observed_names, observed_vids, observed_handles = extract_observed_leads_from_payloads(payloads)

    in_map_hits = 0
    in_map_total = 0
    out_map_hits = 0
    out_map_total = 0
    case_results: List[Dict[str, Any]] = []

    for artist in benchmark.get("artists") or []:
        bucket = str(artist.get("bucket") or "in_map")
        stage_name = str(artist.get("stage_name") or "")
        norm_target = normalize_name(stage_name)
        metrics = artist.get("metrics") or {}
        target_vids = extract_youtube_ids(v.get("url", "") for v in (metrics.get("sample_videos") or []))
        target_handle = str(metrics.get("youtube_channel_handle") or "").lower()

        matched_by: List[str] = []
        if norm_target and norm_target in observed_names:
            matched_by.append("stage_name")
        if target_vids & observed_vids:
            matched_by.append("youtube_video_id")
        if target_handle and target_handle in observed_handles:
            matched_by.append("youtube_handle")

        hit = bool(matched_by)
        if bucket == "in_map":
            in_map_total += 1
            if hit:
                in_map_hits += 1
        else:
            out_map_total += 1
            if hit:
                out_map_hits += 1

        case_results.append(
            {
                "case_id": str(artist.get("id") or stage_name),
                "source": bucket,
                "brief": f"{stage_name} ({artist.get('label', 'unknown label')} · {artist.get('origin', '')})",
                "passed": hit,
                "score": 1.0 if hit else 0.0,
                "rationale": (
                    f"Matched via {', '.join(matched_by)}"
                    if hit
                    else f"Not yet surfaced in evaluated leads (bucket={bucket}, yt_subs={metrics.get('youtube_subscribers')})"
                ),
            }
        )

    in_map_score = round(in_map_hits / max(1, in_map_total), 4)
    out_map_score = round(out_map_hits / max(1, out_map_total), 4)
    overall_recall = round((in_map_hits + out_map_hits) / max(1, in_map_total + out_map_total), 4)

    dimensions: List[Dict[str, Any]] = [
        {
            "rubric_id": "gate_benchmark_integrity",
            "name": "Benchmark Metric & Leak-Free Integrity",
            "layer": "layer_1_code_gates",
            "skill": "source-discovery",
            "scale": "pass_fail",
            "score": 1.0 if integrity_ok else 0.0,
            "raw_score": 1.0 if integrity_ok else 0.0,
            "max_score": 1.0,
            "passed": integrity_ok,
            "detail": "All 10 artists canonical & <=100k; 0 brief leaks." if integrity_ok else "; ".join(integrity_errors[:3]),
        },
        {
            "rubric_id": "gate_seed_source_coverage",
            "name": "In-Map Seed Source Coverage",
            "layer": "layer_1_code_gates",
            "skill": "simon-db",
            "scale": "pass_fail",
            "score": 1.0 if coverage_ok else 0.0,
            "raw_score": 1.0 if coverage_ok else 0.0,
            "max_score": 1.0,
            "passed": coverage_ok,
            "detail": f"All {in_map_total} in-map artists map to active seeded sources." if coverage_ok else "; ".join(coverage_errors[:3]),
        },
        {
            "rubric_id": "recall_in_map",
            "name": "In-Map Label Signing Recall (6 NYC/Session)",
            "layer": "layer_3_quality_safety",
            "skill": "music",
            "scale": "0_to_1",
            "score": in_map_score,
            "raw_score": float(in_map_hits),
            "max_score": float(in_map_total),
            "passed": in_map_score >= 0.5,
            "detail": f"{in_map_hits}/{in_map_total} in-map label signings surfaced.",
        },
        {
            "rubric_id": "recall_out_of_map",
            "name": "Out-of-Map Cold Discovery Recall (4 Global)",
            "layer": "layer_3_quality_safety",
            "skill": "source-discovery",
            "scale": "0_to_1",
            "score": out_map_score,
            "raw_score": float(out_map_hits),
            "max_score": float(out_map_total),
            "passed": out_map_score >= 0.25,
            "detail": f"{out_map_hits}/{out_map_total} out-of-map cold-discovery signings surfaced.",
        },
        {
            "rubric_id": "recall_overall",
            "name": "Combined Label Signing Recall (10 Total)",
            "layer": "layer_3_quality_safety",
            "skill": "music",
            "scale": "0_to_1",
            "score": overall_recall,
            "raw_score": float(in_map_hits + out_map_hits),
            "max_score": float(in_map_total + out_map_total),
            "passed": overall_recall >= 0.4,
            "detail": f"{in_map_hits + out_map_hits}/{in_map_total + out_map_total} total signings surfaced across {len(payloads)} evaluated docs.",
        },
    ]

    overall_score = round(sum(d["score"] for d in dimensions) / len(dimensions), 4)
    if not passed_gates:
        status = "failed"
    elif overall_recall >= 0.4:
        status = "passed"
    else:
        status = "warning"

    return {
        "eval_run_id": f"eval_recall_{uuid.uuid4().hex[:8]}",
        "agent_id": "simon-discovery-scout",
        "rubric_set_id": "discovery-label-recall-v1",
        "runner": "offline_baseline",
        "mode": "offline",
        "trigger": trigger,
        "status": status,
        "overall_score": overall_score,
        "passed_gates": passed_gates,
        "sample_count": in_map_total + out_map_total,
        "sample_source": sample_source,
        "git_sha": git_sha or os.environ.get("GITHUB_SHA"),
        "gcp_project": os.environ.get("GOOGLE_CLOUD_PROJECT", "gemini4nyc26nyc-2203"),
        "gcp_region": os.environ.get("GOOGLE_CLOUD_REGION", "us-east1"),
        "vertex_experiment": None,
        "vertex_console_url": None,
        "created_at": _utc_now_iso(),
        "dimensions": dimensions,
        "case_results": case_results,
        "notes": (
            f"Option C recall check against {benchmark_path.name}: "
            f"in_map={in_map_hits}/{in_map_total}, out_of_map={out_map_hits}/{out_map_total}, "
            f"evaluated_docs={len(payloads)}."
        ),
    }


def push_eval_run(eval_run: Dict[str, Any], push_url: str, token: Optional[str] = None) -> Dict[str, Any]:
    endpoint = push_url.rstrip("/") + "/api/eval-runs"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urlrequest.Request(
        endpoint,
        data=json.dumps(eval_run).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_recall_markdown(eval_run: Dict[str, Any]) -> str:
    lines = [
        f"## Simon Discovery Scout · Label-Signing Recall Eval (`{eval_run['eval_run_id']}`)",
        "",
        f"- **Status:** **{eval_run['status'].upper()}** · **Hard Gates:** `{'PASS' if eval_run['passed_gates'] else 'FAIL'}` · **Score:** `{eval_run['overall_score'] * 100:.1f}%`",
        f"- **Notes:** {eval_run.get('notes', '')}",
        "",
        "| Layer | Metric | Score | Pass | Detail |",
        "| :--- | :--- | :---: | :---: | :--- |",
    ]
    for d in eval_run.get("dimensions") or []:
        lines.append(
            f"| `{d['layer']}` | {d['name']} | `{d['score'] * 100:.0f}%` | {'PASS' if d['passed'] else 'FAIL'} | {d['detail']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Score Discovery Scout recall against Option C label signings.")
    parser.add_argument("--benchmark", type=Path, default=RECALL_BENCHMARK_PATH)
    parser.add_argument("--handoff-file", type=Path, action="append", default=[], help="Optional DiscoveryHandoff JSON file(s) to score.")
    parser.add_argument("--source-url", default=None, help="Optional Simon staging URL to pull live leads/reports from.")
    parser.add_argument("--save-local", action="store_true", help="Save SimonEvalRun into local/Firestore eval_runs.")
    parser.add_argument("--push-url", default=None, help="Optional Simon platform URL to POST the scorecard to /api/eval-runs.")
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON output snapshot path.")
    parser.add_argument("--fail-on-gate", action="store_true", help="Exit 1 if Layer 1 benchmark/source gates fail.")
    args = parser.parse_args(argv)

    handoffs: List[Dict[str, Any]] = []
    for hf in args.handoff_file:
        handoffs.append(json.loads(hf.read_text(encoding="utf-8")))

    store = create_store() if args.save_local else None
    token = os.environ.get("SIMON_AGENT_DB_TOKEN", "").strip() or None
    eval_run = run_recall_eval(
        benchmark_path=args.benchmark,
        handoff_payloads=handoffs,
        store=store,
        source_url=args.source_url,
        source_token=token,
    )

    if args.save_local and store is not None:
        store.save_document("eval_runs", eval_run["eval_run_id"], eval_run)

    if args.push_url:
        push_eval_run(eval_run, args.push_url, token=token)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(eval_run, indent=2) + "\n", encoding="utf-8")

    print(format_recall_markdown(eval_run))
    if args.fail_on_gate and not eval_run["passed_gates"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
