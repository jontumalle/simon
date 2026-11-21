"""Vertex AI Gen AI Evaluation Service & Offline Rubric Runner for Simon Managed Agents.

Evaluates any Simon Managed Agent (or all agents via `--all-agents`) against its
3-layer rubrics in `data/evals/<agent>_rubrics.json` and golden cases in
`data/evals/<agent>_eval_cases.json`:
  - Layer 1: Deterministic hard code gates (contract, URL hygiene, zero telemetry leak)
  - Layer 2: Process & skill trajectory rubrics (simon-db, youtube, music, field-reporting, etc.)
  - Layer 3: Output quality & safety rubrics (zero ranking, grounding, attribution, brief fit, prompt injection)

Usage:
  # Run offline baseline for all agents with rubrics
  python3 -m simon.vertex_eval --all-agents --mode offline --save-local

  # Run offline baseline for one specific agent
  python3 -m simon.vertex_eval --agent discovery-scout --mode offline --save-local

  # Run live Vertex AI Gen AI Evaluation Service
  python3 -m simon.vertex_eval \
    --agent discovery-scout \
    --mode vertex \
    --project gemini4nyc26nyc-2203 \
    --region us-east1 \
    --push-url https://simon-staging-139550420825.us-east1.run.app
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest
import uuid

from .db_tools import REPORT_FORBIDDEN_KEYS, get_agent_document, list_agent_documents, save_agent_document
from .store import SimonStore, create_store

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = REPO_ROOT / "data" / "evals"
RUBRICS_PATH = EVALS_DIR / "discovery_rubrics.json"
EVAL_CASES_PATH = EVALS_DIR / "discovery_eval_cases.json"
DEMO_HANDOFF_PATH = REPO_ROOT / "examples" / "discovery_handoff_demo.json"

VERIFY_SCRIPT_DIR = REPO_ROOT / "agents" / "discovery-scout" / "skills" / "music" / "scripts"
if str(VERIFY_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_SCRIPT_DIR))

from verify_handoff import clean_and_dedupe_handoff  # noqa: E402

RANKING_PRAISE_RE = re.compile(
    r"\b(#1|top pick|best|strong fit|strong candidate|standout|recommended|score|8/10|9/10|10/10)\b",
    re.IGNORECASE,
)

# Map canonical agent slug -> rubric file prefix (handles discovery-scout -> discovery_rubrics.json)
AGENT_FILE_ALIASES = {
    "discovery-scout": "discovery",
    "simon-discovery-scout": "discovery",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_agent_slug(agent: str) -> str:
    slug = (agent or "discovery-scout").strip().lower()
    if slug.startswith("simon-"):
        slug = slug[len("simon-"):]
    return slug


def _resolve_rubrics_path(agent: str = "discovery-scout") -> Path:
    slug = _normalize_agent_slug(agent)
    candidates = [
        EVALS_DIR / f"{slug}_rubrics.json",
        EVALS_DIR / f"{AGENT_FILE_ALIASES.get(slug, slug)}_rubrics.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"No rubric file found for agent '{agent}' in {EVALS_DIR}")


def _resolve_cases_path(agent: str = "discovery-scout") -> Optional[Path]:
    slug = _normalize_agent_slug(agent)
    candidates = [
        EVALS_DIR / f"{slug}_eval_cases.json",
        EVALS_DIR / f"{AGENT_FILE_ALIASES.get(slug, slug)}_eval_cases.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def list_available_eval_agents() -> List[Dict[str, Any]]:
    """Discover all agents with rubric specs under data/evals/*_rubrics.json."""
    agents: List[Dict[str, Any]] = []
    if not EVALS_DIR.is_dir():
        return agents
    for path in sorted(EVALS_DIR.glob("*_rubrics.json")):
        if path.name == "agent_rubrics_template.json":
            continue
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        agent_id = str(spec.get("agent_id") or "")
        slug = _normalize_agent_slug(agent_id or path.name.replace("_rubrics.json", ""))
        rubric_count = sum(len(layer.get("rubrics") or []) for layer in (spec.get("layers") or []))
        agents.append(
            {
                "slug": slug,
                "agent_id": agent_id or f"simon-{slug}",
                "rubric_set_id": spec.get("rubric_set_id") or f"{slug}-v1",
                "stage": spec.get("stage") or "unknown",
                "rubric_count": rubric_count,
                "skills_covered": spec.get("skills_covered") or [],
                "rubrics_file": str(path.relative_to(REPO_ROOT)),
            }
        )
    return agents


def load_agent_rubrics(agent: str = "discovery-scout") -> Dict[str, Any]:
    """Load canonical rubric definitions for a specific agent."""
    path = _resolve_rubrics_path(agent)
    return json.loads(path.read_text(encoding="utf-8"))


def load_discovery_rubrics(path: Path = RUBRICS_PATH) -> Dict[str, Any]:
    """Backward-compatible loader for discovery-scout rubrics."""
    if not path.is_file():
        raise FileNotFoundError(f"Rubric spec not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _has_forbidden_telemetry(obj: Any) -> List[str]:
    found: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in REPORT_FORBIDDEN_KEYS:
                found.append(k)
            found.extend(_has_forbidden_telemetry(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_has_forbidden_telemetry(item))
    return sorted(set(found))


def _load_golden_samples(agent: str = "discovery-scout") -> List[Dict[str, Any]]:
    """Build evaluation samples for an agent from its golden eval cases file."""
    slug = _normalize_agent_slug(agent)
    samples: List[Dict[str, Any]] = []

    if slug == "discovery-scout" and DEMO_HANDOFF_PATH.is_file():
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        samples.append(
            {
                "case_id": "golden_demo_handoff",
                "source": "golden_dataset",
                "brief": handoff.get("search_brief") or "Find emerging NYC solo vocalists.",
                "output": handoff,
                "handoff": handoff,
                "report": {
                    "report_id": "rep_golden_demo",
                    "agent_name": "Discovery Scout 01",
                    "stage": "discovery",
                    "status": "completed",
                    "headline": f"Found {len(handoff.get('leads') or [])} verified vocalists across active sources.",
                    "steps": [
                        {"phase": "looking_at", "title": "Pulled discovered_sources from simon-db"},
                        {"phase": "finding", "title": "Collected candidate leads across channels"},
                        {"phase": "analysis", "title": "Ran verify_handoff.py and deduplicated leads"},
                    ],
                },
                "expected_valid": True,
                "context": "Pulled discovered_sources via simon-db, inspected YouTube live sessions and DIY venue calendars via channel-videos and url_context, ran verify_handoff.py.",
            }
        )

    cases_path = _resolve_cases_path(slug)
    if cases_path and cases_path.is_file():
        cases_data = json.loads(cases_path.read_text(encoding="utf-8"))
        raw_cases: List[Dict[str, Any]] = []
        if isinstance(cases_data, list):
            raw_cases = [c for c in cases_data if isinstance(c, dict)]
        elif isinstance(cases_data, dict):
            for key in ("cases", "eval_cases", "golden_cases", "handoff_contract_cases"):
                val = cases_data.get(key)
                if isinstance(val, list):
                    raw_cases.extend(c for c in val if isinstance(c, dict))

        for idx, case in enumerate(raw_cases):
            payload = case.get("output") or case.get("payload") or case.get("handoff")
            if not isinstance(payload, dict):
                continue
            samples.append(
                {
                    "case_id": str(case.get("id") or case.get("case_id") or f"{slug}_case_{idx + 1}"),
                    "source": "golden_dataset",
                    "brief": str(
                        case.get("brief")
                        or case.get("prompt")
                        or payload.get("search_brief")
                        or f"{slug} evaluation case"
                    ),
                    "output": payload,
                    "handoff": payload if slug == "discovery-scout" else None,
                    "report": case.get("report"),
                    "expected_valid": bool(case.get("expected_valid", True)),
                    "context": str(case.get("context") or case.get("notes") or f"Golden eval case for {slug}."),
                }
            )
    return samples


def _parse_json_output_text(raw: Any) -> Dict[str, Any]:
    """Parse a dict or JSON/fenced-JSON string from an agent trace output."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("\n", 1)
        if len(parts) == 2:
            s = parts[1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def _trace_matches_agent(slug: str, doc: Dict[str, Any]) -> bool:
    """Return True if an agent_run or agent_report belongs to the normalized agent slug."""
    if not slug:
        return True
    agent_id = str(doc.get("agent_id") or doc.get("agent_name") or "").lower()
    stage = str(doc.get("stage") or "").lower()
    if slug in agent_id or slug.replace("-", " ") in agent_id:
        return True
    if slug == "discovery-scout" and stage == "discovery":
        return True
    return False


def list_evaluable_traces(
    store: Optional[SimonStore],
    agent: Optional[str] = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """List real recorded traces (`agent_runs` and `agent_reports`) selectable in `/evals`."""
    if store is None:
        return []
    slug = _normalize_agent_slug(agent) if agent else ""
    traces: List[Dict[str, Any]] = []
    seen: set = set()

    for coll in ("agent_runs", "agent_reports"):
        rows = list_agent_documents(store, coll, limit=max(limit, 50))
        for row in rows:
            doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
            if not isinstance(doc, dict):
                continue
            if slug and not _trace_matches_agent(slug, doc):
                continue
            tid = str(
                doc.get("agent_run_id")
                or doc.get("report_id")
                or row.get("doc_id")
                or doc.get("_doc_id")
                or ""
            ).strip()
            if not tid or (coll, tid) in seen:
                continue
            seen.add((coll, tid))
            steps = doc.get("steps") or doc.get("trace") or []
            status = str(doc.get("status") or "unknown")
            brief = str(
                doc.get("assignment")
                or doc.get("target")
                or doc.get("brief")
                or doc.get("headline")
                or ""
            ).strip()
            output_obj = _parse_json_output_text(doc.get("output") or doc.get("output_text"))
            created_at = str(doc.get("created_at") or doc.get("updated_at") or row.get("updated_at") or "")
            label_brief = (brief[:68] + "…") if len(brief) > 68 else (brief or tid)
            traces.append(
                {
                    "trace_id": tid,
                    "collection": coll,
                    "agent_id": str(doc.get("agent_id") or doc.get("agent_name") or slug or "unknown"),
                    "status": status,
                    "step_count": len(steps) if isinstance(steps, list) else 0,
                    "has_output": bool(output_obj),
                    "brief": brief,
                    "created_at": created_at,
                    "label": f"[{coll[:-1]}] {tid} · {status} · {len(steps) if isinstance(steps, list) else 0} steps · {label_brief}",
                }
            )

    traces.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    return traces[:limit]


def _load_single_trace_sample(
    store: Optional[SimonStore],
    trace_id: str,
    trace_collection: Optional[str] = None,
    agent: str = "discovery-scout",
) -> List[Dict[str, Any]]:
    """Load one specific recorded trace (`agent_runs` or `agent_reports`) as an eval sample."""
    if store is None:
        raise ValueError("A store is required to evaluate a specific trace_id.")
    slug = _normalize_agent_slug(agent)
    collections = (
        [trace_collection]
        if trace_collection in ("agent_runs", "agent_reports")
        else ["agent_runs", "agent_reports"]
    )
    found_doc: Optional[Dict[str, Any]] = None
    found_coll: str = ""
    for coll in collections:
        row = get_agent_document(store, coll, trace_id)
        if isinstance(row, dict):
            found_doc = row.get("data") if isinstance(row.get("data"), dict) else row
            found_coll = coll
            break
    if not found_doc:
        raise ValueError(f"Trace '{trace_id}' not found in {', '.join(collections)}.")

    steps = found_doc.get("steps") or found_doc.get("trace") or []
    output_obj = _parse_json_output_text(found_doc.get("output") or found_doc.get("output_text"))
    steps_summary = "\n".join(
        f"[{s.get('index', idx + 1)}:{s.get('phase') or s.get('type') or 'step'}] "
        f"{s.get('title') or ''} {s.get('preview') or s.get('finding') or ''}"
        for idx, s in enumerate(steps)
        if isinstance(s, dict)
    )
    return [
        {
            "case_id": trace_id,
            "source": f"trace:{found_coll}:{trace_id}",
            "brief": str(
                found_doc.get("assignment")
                or found_doc.get("target")
                or found_doc.get("brief")
                or output_obj.get("search_brief")
                or f"Trace {trace_id}"
            ),
            "output": output_obj,
            "handoff": output_obj if slug == "discovery-scout" else None,
            "report": found_doc if found_coll == "agent_reports" else None,
            "trace_status": str(found_doc.get("status") or ""),
            "trace_steps": steps if isinstance(steps, list) else [],
            "expected_valid": True,
            "context": steps_summary or f"Recorded {found_coll} trace {trace_id}.",
        }
    ]


def _load_live_report_samples(
    store: Optional[SimonStore],
    agent: str = "discovery-scout",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Load recent Scouting Reports (`agent_reports`) for an agent from Firestore/SQLite."""
    if store is None:
        return []
    slug = _normalize_agent_slug(agent)
    rows = list_agent_documents(store, "agent_reports", limit=limit)
    samples: List[Dict[str, Any]] = []
    for row in rows:
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict):
            continue
        agent_name = str(doc.get("agent_name") or doc.get("agent_id") or "").lower()
        stage = str(doc.get("stage") or "").lower()
        if slug == "discovery-scout":
            if stage and stage != "discovery":
                continue
        else:
            if slug.replace("-", " ") not in agent_name and slug not in agent_name:
                continue
        output = doc.get("output") if isinstance(doc.get("output"), dict) else None
        if not output:
            continue
        steps_summary = "; ".join(
            f"[{s.get('phase', 'step')}] {s.get('title', '')}: {s.get('finding', '')}"
            for s in (doc.get("steps") or [])
            if isinstance(s, dict)
        )
        samples.append(
            {
                "case_id": str(doc.get("report_id") or doc.get("_doc_id") or f"report_{len(samples) + 1}"),
                "source": "live_reports",
                "brief": str(doc.get("brief") or output.get("search_brief") or f"Live {slug} run"),
                "output": output,
                "handoff": output if slug == "discovery-scout" else None,
                "report": doc,
                "expected_valid": True,
                "context": steps_summary or "Live agent_report from Simon platform.",
            }
        )
    return samples


def _extract_urls(obj: Any) -> List[str]:
    urls: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and (k == "url" or k.endswith("_url") or v.startswith(("http://", "https://"))):
                urls.append(v)
            else:
                urls.extend(_extract_urls(v))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(_extract_urls(item))
    return urls


def _evaluate_deterministic_gates(
    agent: str,
    rubrics_spec: Dict[str, Any],
    samples: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run Layer 1 hard code gates across all samples for an agent."""
    slug = _normalize_agent_slug(agent)
    valid_samples = [s for s in samples if s.get("expected_valid", True)]
    if not valid_samples:
        valid_samples = samples

    gate_layer = next(
        (l for l in (rubrics_spec.get("layers") or []) if l.get("layer_id") == "layer_1_code_gates"),
        {"rubrics": []},
    )
    gate_rubrics = gate_layer.get("rubrics") or []
    passes_by_id: Dict[str, int] = {r["id"]: 0 for r in gate_rubrics}
    case_results: List[Dict[str, Any]] = []

    for s in valid_samples:
        output = s.get("output") or s.get("handoff") or {}
        report = s.get("report")
        trace_status = str(s.get("trace_status") or "").lower()
        case_failures: List[str] = []

        # Discovery-specific contract check vs generic non-empty JSON object check
        if trace_status in ("incomplete", "failed", "error"):
            contract_ok = False
            contract_err = f"Trace did not complete (status={trace_status})"
        elif slug == "discovery-scout":
            cleaned, errors = clean_and_dedupe_handoff(output, verify_oembed=False)
            contract_ok = len(errors) == 0 and bool(cleaned.get("leads"))
            contract_err = "; ".join(errors[:2]) if errors else ""
        else:
            contract_ok = isinstance(output, dict) and len(output) > 0
            contract_err = "Empty or non-object JSON output" if not contract_ok else ""

        urls = _extract_urls(output)
        block_soundcloud = slug == "discovery-scout"
        urls_ok = all(
            u.strip().lower().startswith(("http://", "https://"))
            and (not block_soundcloud or "soundcloud.com" not in u.lower())
            for u in urls
        )
        leaks = _has_forbidden_telemetry(report) if isinstance(report, dict) else []
        leaks_ok = len(leaks) == 0
        out_text = json.dumps(output, ensure_ascii=False)
        no_ranking_ok = not bool(RANKING_PRAISE_RE.search(out_text))

        for r in gate_rubrics:
            rid = r["id"]
            if "contract" in rid or "schema" in rid or "json" in rid or "cap" in rid or "shortlist" in rid:
                ok = contract_ok
                if not ok:
                    case_failures.append(f"{rid}: {contract_err or 'contract check failed'}")
            elif "url" in rid or "link" in rid:
                ok = urls_ok
                if not ok:
                    case_failures.append(f"{rid}: invalid or blocked URL detected")
            elif "leak" in rid or "telemetry" in rid or "sys" in rid:
                ok = leaks_ok
                if not ok:
                    case_failures.append(f"{rid}: leaked {', '.join(leaks)}")
            elif "rank" in rid or "score" in rid or "objective" in rid:
                ok = no_ranking_ok
                if not ok:
                    case_failures.append(f"{rid}: subjective or ranking language detected")
            else:
                ok = contract_ok
                if not ok:
                    case_failures.append(f"{rid}: prerequisite contract check failed")
            if ok:
                passes_by_id[rid] += 1

        passed_all = len(case_failures) == 0
        case_results.append(
            {
                "case_id": s["case_id"],
                "source": s["source"],
                "brief": s["brief"],
                "passed": passed_all,
                "score": 1.0 if passed_all else 0.0,
                "rationale": (
                    "Passed all Layer 1 hard gates."
                    if passed_all
                    else " | ".join(case_failures[:3])
                ),
            }
        )

    total = max(1, len(valid_samples))
    dims: List[Dict[str, Any]] = []
    for r in gate_rubrics:
        rid = r["id"]
        passed_n = passes_by_id.get(rid, 0)
        dims.append(
            {
                "rubric_id": rid,
                "name": r["name"],
                "layer": "layer_1_code_gates",
                "skill": r.get("skill", "SYSTEM.md"),
                "scale": r.get("scale", "pass_fail"),
                "score": round(passed_n / total, 4),
                "raw_score": passed_n,
                "max_score": total,
                "passed": passed_n == total,
                "detail": f"{passed_n}/{total} valid sample(s) passed {r['name']}.",
            }
        )
    return dims, case_results


def _evaluate_offline_rubrics(
    agent: str,
    rubrics_spec: Dict[str, Any],
    samples: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Heuristic offline scoring for Layer 2 & Layer 3 rubrics when Vertex AI is not invoked."""
    valid_samples = [s for s in samples if s.get("expected_valid", True)] or samples
    total = max(1, len(valid_samples))
    dims: List[Dict[str, Any]] = []

    for layer in rubrics_spec.get("layers") or []:
        layer_id = layer["layer_id"]
        if layer_id == "layer_1_code_gates":
            continue
        for rubric in layer.get("rubrics") or []:
            rid = rubric["id"]
            max_s = float(rubric.get("max_score") or (2.0 if rubric.get("scale") == "0_to_2" else (5.0 if rubric.get("scale") == "1_to_5" else 1.0)))
            accum = 0.0
            for s in valid_samples:
                output = s.get("output") or s.get("handoff") or {}
                report = s.get("report") or {}
                ctx = str(s.get("context") or "").lower()
                out_str = json.dumps(output, ensure_ascii=False)
                steps = report.get("steps") or []
                phases = {st.get("phase") for st in steps if isinstance(st, dict)}
                headline = str(report.get("headline") or "")

                if "field_news" in rid or "report" in rid:
                    if {"looking_at", "finding", "analysis"}.issubset(phases) and headline:
                        accum += max_s
                    elif headline or steps:
                        accum += max_s * 0.65
                    else:
                        accum += max_s * 0.5
                elif "channel_mix" in rid:
                    leads = output.get("leads") or []
                    channels = {
                        seed.get("source_channel")
                        for lead in leads
                        if isinstance(lead, dict)
                        for seed in (lead.get("seed_sources") or [])
                        if isinstance(seed, dict) and seed.get("source_channel")
                    }
                    accum += max_s if len(channels) >= 2 else (max_s * 0.5 if len(channels) == 1 else 0.0)
                elif "new_sources" in rid:
                    accum += max_s if output.get("discovered_sources") else 0.0
                elif "zero_ranking" in rid:
                    violated = bool(RANKING_PRAISE_RE.search(out_str + " " + headline))
                    accum += 0.0 if violated else max_s
                elif "db" in rid:
                    if "simon_db.py list" in ctx or "discovered_sources" in ctx:
                        accum += max_s
                    elif "simon-db" in ctx or "simon_db" in ctx:
                        accum += max_s * 0.5
                    else:
                        accum += 0.0
                elif "yt_quota" in rid or "youtube" in rid:
                    if "channel-videos" in ctx or "youtube_api.py video" in ctx:
                        accum += max_s
                    elif "youtube_api.py search" in ctx:
                        accum += max_s * 0.5
                    else:
                        accum += 0.0
                else:
                    # Do NOT award fake 100% for LLM-judge rubrics in offline mode.
                    accum += 0.0

            avg_raw = round(accum / total, 3)
            norm = round(min(1.0, max(0.0, avg_raw / max_s)), 4)
            threshold = float(layer.get("pass_threshold") or 0.75)
            is_llm_only = not any(
                tok in rid
                for tok in ("field_news", "report", "channel_mix", "new_sources", "zero_ranking", "db", "yt_quota", "youtube")
            )
            dims.append(
                {
                    "rubric_id": rid,
                    "name": rubric["name"],
                    "layer": layer_id,
                    "skill": rubric.get("skill", "SYSTEM.md"),
                    "scale": rubric.get("scale", "pass_fail"),
                    "score": norm,
                    "raw_score": avg_raw,
                    "max_score": max_s,
                    "passed": False if is_llm_only else (norm >= threshold),
                    "detail": (
                        "Requires Vertex AI LLM judge (--mode vertex); not auto-passed offline."
                        if is_llm_only
                        else f"Offline deterministic check avg {avg_raw}/{max_s:g} across {total} sample(s)."
                    ),
                }
            )
    return dims


def _evaluate_with_vertex_ai(
    rubrics_spec: Dict[str, Any],
    samples: List[Dict[str, Any]],
    project: str,
    region: str,
    experiment_name: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """Run Layer 2 & Layer 3 custom pointwise rubrics via Vertex AI Gen AI Evaluation Service."""
    try:
        import pandas as pd  # type: ignore
        import vertexai  # type: ignore
        from vertexai.evaluation import EvalTask, PointwiseMetric, PointwiseMetricPromptTemplate  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Vertex AI Evaluation SDK not installed. Install with: "
            "pip install 'google-cloud-aiplatform[evaluation]' pandas"
        ) from exc

    vertexai.init(project=project, location=region)

    valid_samples = [s for s in samples if s.get("expected_valid", True)] or samples
    rows = [
        {
            "case_id": s["case_id"],
            "prompt": s["brief"],
            "context": s.get("context") or "",
            "response": json.dumps(
                {"output": s.get("output") or s.get("handoff"), "report": s.get("report")},
                ensure_ascii=False,
            ),
        }
        for s in valid_samples
    ]
    eval_df = pd.DataFrame(rows)

    metrics = []
    rubric_lookup: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for layer in rubrics_spec.get("layers") or []:
        if layer["layer_id"] == "layer_1_code_gates":
            continue
        for rubric in layer.get("rubrics") or []:
            template = rubric.get("vertex_prompt_template")
            if not template:
                continue
            rid = rubric["id"]
            rubric_lookup[rid] = (layer, rubric)
            metrics.append(
                PointwiseMetric(
                    metric=rid,
                    metric_prompt_template=PointwiseMetricPromptTemplate(
                        criteria={rid: rubric["criteria"]},
                        rating_rubric={
                            str(k): str(v)
                            for k, v in (
                                rubric.get("levels")
                                or {"0": "Fails criteria", str(rubric.get("max_score", 1)): "Meets criteria"}
                            ).items()
                        },
                        instruction=template,
                    ),
                )
            )

    eval_task = EvalTask(
        dataset=eval_df,
        metrics=metrics,
        experiment=experiment_name,
    )
    result = eval_task.evaluate()
    summary = getattr(result, "summary_metrics", {}) or {}
    metrics_table = getattr(result, "metrics_table", None)

    dims: List[Dict[str, Any]] = []
    for rid, (layer, rubric) in rubric_lookup.items():
        max_s = float(rubric.get("max_score") or 1.0)
        mean_val = summary.get(f"{rid}/mean")
        if mean_val is None and metrics_table is not None and f"{rid}/score" in metrics_table.columns:
            mean_val = float(metrics_table[f"{rid}/score"].dropna().mean())
        raw_score = round(float(mean_val), 3) if mean_val is not None else 0.0
        norm = round(min(1.0, max(0.0, raw_score / max_s)), 4)
        threshold = float(layer.get("pass_threshold") or 0.75)
        dims.append(
            {
                "rubric_id": rid,
                "name": rubric["name"],
                "layer": layer["layer_id"],
                "skill": rubric.get("skill", "SYSTEM.md"),
                "scale": rubric.get("scale", "pass_fail"),
                "score": norm,
                "raw_score": raw_score,
                "max_score": max_s,
                "passed": norm >= threshold,
                "detail": f"Vertex AI Judge mean {raw_score}/{max_s:g} across {len(valid_samples)} sample(s).",
            }
        )

    vertex_case_updates: List[Dict[str, Any]] = []
    if metrics_table is not None:
        for idx, row in metrics_table.iterrows():
            case_id = str(valid_samples[idx]["case_id"]) if idx < len(valid_samples) else f"case_{idx}"
            explanations = []
            for rid in rubric_lookup:
                exp_col = f"{rid}/explanation"
                if exp_col in row and row[exp_col]:
                    explanations.append(f"{rid}: {str(row[exp_col])[:140]}")
            vertex_case_updates.append(
                {
                    "case_id": case_id,
                    "rationale": " | ".join(explanations[:3]) or "Evaluated via Vertex AI Gen AI Evaluation Service.",
                }
            )

    console_url = (
        f"https://console.cloud.google.com/vertex-ai/experiments/locations/{region}"
        f"/experiments/{experiment_name}/runs?project={project}"
    )
    return dims, vertex_case_updates, console_url


def run_agent_eval(
    agent: str = "discovery-scout",
    mode: str = "offline",
    sample_source: str = "mixed",
    store: Optional[SimonStore] = None,
    project: Optional[str] = None,
    region: Optional[str] = None,
    trigger: str = "cli",
    git_sha: Optional[str] = None,
    trace_id: Optional[str] = None,
    trace_collection: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the 3-layer eval for any Simon agent and return a canonical SimonEvalRun dict."""
    slug = _normalize_agent_slug(agent)
    rubrics_spec = load_agent_rubrics(slug)
    samples: List[Dict[str, Any]] = []
    effective_sample_source = sample_source
    if trace_id:
        samples = _load_single_trace_sample(
            store=store,
            trace_id=trace_id,
            trace_collection=trace_collection,
            agent=slug,
        )
        effective_sample_source = f"trace:{trace_id}"
    else:
        if sample_source in ("live_reports", "mixed"):
            samples.extend(_load_live_report_samples(store, agent=slug, limit=10))
        if sample_source in ("golden_dataset", "mixed") or not samples:
            samples.extend(_load_golden_samples(agent=slug))

    gate_dims, case_results = _evaluate_deterministic_gates(slug, rubrics_spec, samples)
    passed_gates = all(d["passed"] for d in gate_dims)

    eval_run_id = f"eval_{uuid.uuid4().hex[:10]}"
    gcp_project = project or os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "gemini4nyc26nyc-2203"
    gcp_region = region or os.environ.get("GCP_REGION") or "us-east1"
    experiment_name: Optional[str] = f"simon-{slug}-eval-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    vertex_console_url: Optional[str] = None
    notes: Optional[str] = None

    if mode == "vertex":
        vertex_dims, vertex_updates, vertex_console_url = _evaluate_with_vertex_ai(
            rubrics_spec=rubrics_spec,
            samples=samples,
            project=gcp_project,
            region=gcp_region,
            experiment_name=experiment_name,
        )
        all_dims = gate_dims + vertex_dims
        updates_by_id = {u["case_id"]: u["rationale"] for u in vertex_updates}
        for cr in case_results:
            if cr["case_id"] in updates_by_id:
                cr["rationale"] = f"{cr['rationale']} | Vertex AI: {updates_by_id[cr['case_id']]}"
        runner = "hybrid_vertex_offline"
    else:
        offline_dims = _evaluate_offline_rubrics(slug, rubrics_spec, samples)
        all_dims = gate_dims + offline_dims
        runner = "offline_baseline"
        experiment_name = None
        notes = f"Ran Layer 1 hard gates + Layer 2/3 offline heuristic checks for {slug}."

    overall = round(sum(d["score"] for d in all_dims) / max(1, len(all_dims)), 4)
    if not passed_gates:
        status = "failed"
    elif overall >= 0.8:
        status = "passed"
    else:
        status = "warning"

    return {
        "eval_run_id": eval_run_id,
        "agent_id": rubrics_spec.get("agent_id", f"simon-{slug}"),
        "rubric_set_id": rubrics_spec.get("rubric_set_id", f"{slug}-v1"),
        "runner": runner,
        "mode": mode,
        "trigger": trigger,
        "status": status,
        "overall_score": overall,
        "passed_gates": passed_gates,
        "sample_count": len(samples),
        "sample_source": effective_sample_source,
        "git_sha": git_sha or os.environ.get("GITHUB_SHA"),
        "gcp_project": gcp_project,
        "gcp_region": gcp_region,
        "vertex_experiment": experiment_name,
        "vertex_console_url": vertex_console_url,
        "created_at": _utc_now_iso(),
        "dimensions": all_dims,
        "case_results": case_results,
        "notes": notes,
    }


def run_discovery_eval(
    mode: str = "offline",
    sample_source: str = "mixed",
    store: Optional[SimonStore] = None,
    project: Optional[str] = None,
    region: Optional[str] = None,
    trigger: str = "cli",
    git_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """Backward-compatible wrapper for running discovery-scout evals."""
    return run_agent_eval(
        agent="discovery-scout",
        mode=mode,
        sample_source=sample_source,
        store=store,
        project=project,
        region=region,
        trigger=trigger,
        git_sha=git_sha,
    )


def push_eval_run(eval_run: Dict[str, Any], push_url: str, token: Optional[str] = None) -> Dict[str, Any]:
    """POST an eval_run scorecard to Simon's platform API (`POST /api/eval-runs`)."""
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
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to push eval_run to {endpoint} ({exc.code}): {body}") from exc


def format_markdown_summary(eval_run: Dict[str, Any]) -> str:
    """Format a GitHub Actions step summary table for an eval run."""
    lines = [
        f"## {eval_run['agent_id']} Eval (`{eval_run['eval_run_id']}`)",
        "",
        f"- **Mode / Runner:** `{eval_run['mode']}` (`{eval_run['runner']}`)",
        f"- **Status:** **{eval_run['status'].upper()}** · **Overall Score:** `{eval_run['overall_score'] * 100:.1f}%` · **Hard Gates:** `{'PASS' if eval_run['passed_gates'] else 'FAIL'}`",
        f"- **Samples:** `{eval_run['sample_count']}` (`{eval_run['sample_source']}`)",
    ]
    if eval_run.get("vertex_console_url"):
        lines.append(f"- **Vertex AI Experiment:** [Open in Google Cloud Console]({eval_run['vertex_console_url']})")
    lines.extend(
        [
            "",
            "| Layer | Rubric | Skill | Score | Pass | Detail |",
            "| :--- | :--- | :--- | :---: | :---: | :--- |",
        ]
    )
    for d in eval_run.get("dimensions") or []:
        badge = "PASS" if d.get("passed") else "FAIL"
        lines.append(
            f"| `{d.get('layer')}` | {d.get('name')} | `{d.get('skill')}` | `{d.get('score', 0) * 100:.0f}%` | {badge} | {d.get('detail', '')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Simon Managed Agent rubrics (Offline or Vertex AI).")
    parser.add_argument("--agent", default="discovery-scout", help="Target agent slug (default: discovery-scout).")
    parser.add_argument("--all-agents", action="store_true", help="Run evals across all agents with rubric specs.")
    parser.add_argument("--mode", choices=["offline", "vertex"], default="offline")
    parser.add_argument("--sample-source", choices=["golden_dataset", "live_reports", "mixed"], default="mixed")
    parser.add_argument("--project", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--trigger", default="cli")
    parser.add_argument("--save-local", action="store_true", help="Save eval_run(s) into configured local/Firestore store.")
    parser.add_argument("--push-url", default=None, help="Platform URL to POST eval_run (e.g. https://simon-staging-...run.app).")
    parser.add_argument("--out", default=None, help="Optional JSON output file path.")
    parser.add_argument("--summary-md", default=None, help="Optional Markdown summary path (e.g. $GITHUB_STEP_SUMMARY).")
    parser.add_argument("--fail-on-gate", action="store_true", help="Exit non-zero if Layer 1 hard gates fail.")
    args = parser.parse_args(argv)

    store = create_store() if args.save_local or args.sample_source in ("live_reports", "mixed") else None
    target_slugs = [a["slug"] for a in list_available_eval_agents()] if args.all_agents else [_normalize_agent_slug(args.agent)]

    runs: List[Dict[str, Any]] = []
    any_gate_failed = False
    for slug in target_slugs:
        eval_run = run_agent_eval(
            agent=slug,
            mode=args.mode,
            sample_source=args.sample_source,
            store=store,
            project=args.project,
            region=args.region,
            trigger=args.trigger,
        )
        runs.append(eval_run)
        if not eval_run["passed_gates"]:
            any_gate_failed = True
        if args.save_local and store is not None:
            save_agent_document(store, "eval_runs", eval_run)
        if args.push_url:
            token = os.environ.get("SIMON_AGENT_DB_TOKEN", "").strip() or None
            push_eval_run(eval_run, args.push_url, token=token)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = runs if args.all_agents else runs[0]
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md = "\n".join(format_markdown_summary(r) for r in runs)
    if args.summary_md:
        with open(args.summary_md, "a", encoding="utf-8") as fh:
            fh.write(md)

    print(md)
    if args.fail_on_gate and any_gate_failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
