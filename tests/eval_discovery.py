"""Baseline evaluation harness for Simon's Discovery Scout (simon-discovery-scout + YouTubeConnector).

Usage:
  # Run offline baseline scorecard against golden fixtures (CI-safe, no API calls)
  python3 tests/eval_discovery.py

  # Run as standard unittest suite
  python3 -m unittest tests/eval_discovery.py -v

  # Run live eval against Gemini Discovery Managed Agent + public YouTubeConnector
  python3 tests/eval_discovery.py --live --brief "Find singers who reinterpret familiar songs through phrasing."
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import unittest
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from simon.deploy import compile_agent_package
from simon.gemini import Gemini
from simon.scout import DEFAULT_TASTE_BRIEF, load_dotenv_if_present, run_live_scout
from simon.store import SimonStore
from simon.youtube import (
    YouTubeConnector,
    canonical_watch_url,
    extract_video_id,
    infer_performer_and_attribution,
    normalize_artist_key,
)

VERIFY_SCRIPT_DIR = REPO_ROOT / "agents" / "discovery-scout" / "skills" / "music" / "scripts"
if str(VERIFY_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_SCRIPT_DIR))

from verify_handoff import clean_and_dedupe_handoff  # noqa: E402

EVAL_DATASET_PATH = REPO_ROOT / "data" / "evals" / "discovery_eval_cases.json"
DEMO_HANDOFF_PATH = REPO_ROOT / "examples" / "discovery_handoff_demo.json"


@dataclass
class CheckResult:
    dimension: str
    case_id: str
    passed: bool
    detail: str = ""


@dataclass
class EvalReport:
    mode: str
    checks: List[CheckResult] = field(default_factory=list)

    def add(self, dimension: str, case_id: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(dimension=dimension, case_id=case_id, passed=passed, detail=detail))

    def summary_by_dimension(self) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, List[CheckResult]] = {}
        for chk in self.checks:
            grouped.setdefault(chk.dimension, []).append(chk)
        out: Dict[str, Dict[str, Any]] = {}
        for dim, items in grouped.items():
            passed = sum(1 for item in items if item.passed)
            total = len(items)
            out[dim] = {
                "passed": passed,
                "total": total,
                "score": round(passed / total, 4) if total else 0.0,
                "failures": [
                    {"case_id": item.case_id, "detail": item.detail}
                    for item in items
                    if not item.passed
                ],
            }
        return out

    @property
    def overall_score(self) -> float:
        if not self.checks:
            return 0.0
        return round(sum(1 for c in self.checks if c.passed) / len(self.checks), 4)

    def format_table(self) -> str:
        lines = [
            f"Discovery Agent Baseline Eval ({self.mode})",
            "=" * 64,
            f"{'Dimension':<34} {'Pass':>6} {'Total':>6} {'Score':>8}",
            "-" * 64,
        ]
        for dim, stats in self.summary_by_dimension().items():
            pct = f"{stats['score'] * 100:5.1f}%"
            lines.append(f"{dim:<34} {stats['passed']:>6} {stats['total']:>6} {pct:>8}")
        lines.append("-" * 64)
        total_pass = sum(1 for c in self.checks if c.passed)
        lines.append(
            f"{'OVERALL':<34} {total_pass:>6} {len(self.checks):>6} {self.overall_score * 100:5.1f}%"
        )
        failures = [c for c in self.checks if not c.passed]
        if failures:
            lines.append("")
            lines.append("Failures:")
            for fail in failures:
                lines.append(f"  - [{fail.dimension}] {fail.case_id}: {fail.detail}")
        return "\n".join(lines)


class EvalYouTubeConnector(YouTubeConnector):
    """Deterministic YouTubeConnector for offline pipeline evals."""

    CATALOG = {
        "3-K26i1go0s": {
            "video_id": "3-K26i1go0s",
            "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
            "title": "Olivia Dean - Wish I Didn't Miss You (Angie Stone) | Mahogany Session",
            "channel": "Mahogany",
        },
        "BcQnHzrc24Y": {
            "video_id": "BcQnHzrc24Y",
            "url": "https://www.youtube.com/watch?v=BcQnHzrc24Y",
            "title": "Olivia Dean - Love Me Not in the Live Lounge",
            "channel": "BBCRadio1VEVO",
        },
        "RXwE1G7_U9M": {
            "video_id": "RXwE1G7_U9M",
            "url": "https://www.youtube.com/watch?v=RXwE1G7_U9M",
            "title": "YEBBA - My Mind | Sofar NYC",
            "channel": "Sofar Sounds",
        },
        "XIIYcEz1u28": {
            "video_id": "XIIYcEz1u28",
            "url": "https://www.youtube.com/watch?v=XIIYcEz1u28",
            "title": "Acantha Lang at Sofar Sounds NYC",
            "channel": "Hiddentravel",
        },
    }

    def verify_oembed(self, url: str) -> Optional[Dict[str, str]]:
        vid = extract_video_id(url)
        return self.CATALOG.get(vid or "")

    def search_public_videos(self, query: str, max_results: int = 6) -> List[Dict[str, str]]:
        if "Olivia Dean" in query:
            return [
                {
                    "video_id": "BcQnHzrc24Y",
                    "url": "https://www.youtube.com/watch?v=BcQnHzrc24Y",
                    "title": "Olivia Dean - Love Me Not in the Live Lounge",
                    "channel": "BBCRadio1VEVO",
                    "duration": "3:18",
                    "query_used": query,
                }
            ]
        if "YEBBA" in query or "Acantha Lang" in query:
            return []
        return [
            {
                "video_id": "3-K26i1go0s",
                "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                "title": "Olivia Dean - Wish I Didn't Miss You (Angie Stone) | Mahogany Session",
                "channel": "Mahogany",
                "duration": "3:50",
                "query_used": query,
            },
            {
                "video_id": "RXwE1G7_U9M",
                "url": "https://www.youtube.com/watch?v=RXwE1G7_U9M",
                "title": "YEBBA - My Mind | Sofar NYC",
                "channel": "Sofar Sounds",
                "duration": "6:10",
                "query_used": query,
            },
            {
                "video_id": "XIIYcEz1u28",
                "url": "https://www.youtube.com/watch?v=XIIYcEz1u28",
                "title": "Acantha Lang at Sofar Sounds NYC",
                "channel": "Hiddentravel",
                "duration": "2:38",
                "query_used": query,
            },
        ][:max_results]


class ScenarioGemini:
    """Deterministic Gemini stub injecting a scenario's discovery payload."""

    discovery_agent = "simon-discovery-scout (offline-eval)"
    synthesis_agent = "simon-synthesis-scout (offline-eval)"
    audio_model = "gemini-4-hydrogen"

    def __init__(self, agent_output: Dict[str, Any]):
        self._agent_output = agent_output

    def discover_youtube_leads(self, taste_brief: str, target_artist: Optional[str] = None) -> Dict[str, Any]:
        return {
            "interaction_id": "eval-disc-001",
            "duration_ms": 120,
            "steps": [{"index": 1, "type": "model_output", "preview": "Scenario discovery payload"}],
            "data": self._agent_output,
        }

    def evaluate_youtube_clip(self, taste_brief, stage_name, video_url, title="", channel=""):
        return {
            "interaction_id": f"eval-clip-{extract_video_id(video_url)}",
            "duration_ms": 95,
            "evaluated_model": self.audio_model,
            "data": {
                "recording_context": "live",
                "recording_context_notes": "Single-room acoustic live capture.",
                "observations": [
                    {
                        "timestamp": "1:10",
                        "dimension": "phrasing",
                        "musical_choice": f"{stage_name} reshapes the vocal phrasing behind the beat.",
                    }
                ],
            },
        }

    def synthesize_shortlist(self, taste_brief, leads, clip_evidence):
        return {
            "interaction_id": "eval-synth-001",
            "duration_ms": 110,
            "steps": [],
            "data": {"synthesis_summary": "Eval synthesis pass", "assessments": [], "shortlist": []},
        }


def load_eval_dataset(path: Path = EVAL_DATASET_PATH) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def score_discovery_agent_output(
    report: EvalReport,
    agent_data: Dict[str, Any],
    leads: List[Dict[str, Any]],
    case_prefix: str = "live",
) -> None:
    """Reusable contract & hygiene grader for both offline scenarios and live runs."""
    queries = [q for q in (agent_data.get("search_queries") or []) if isinstance(q, str) and q.strip()]
    report.add(
        "contract_validity",
        f"{case_prefix}_has_search_queries",
        len(queries) >= 1,
        f"search_queries count={len(queries)}",
    )
    report.add(
        "contract_validity",
        f"{case_prefix}_has_discovery_summary",
        isinstance(agent_data.get("discovery_summary"), str) and bool(agent_data.get("discovery_summary", "").strip()),
        "discovery_summary missing or empty",
    )

    all_links = [url for lead in leads for url in lead.get("source_links", [])]
    non_canonical = [
        url for url in all_links if not url.startswith("https://www.youtube.com/watch?v=")
    ]
    report.add(
        "url_hygiene",
        f"{case_prefix}_all_links_canonical_youtube",
        len(all_links) > 0 and len(non_canonical) == 0,
        f"non_canonical={non_canonical}",
    )
    soundcloud_links = [url for url in all_links if "soundcloud.com" in url.lower()]
    report.add(
        "url_hygiene",
        f"{case_prefix}_zero_soundcloud_links",
        len(soundcloud_links) == 0,
        f"soundcloud_links={soundcloud_links}",
    )

    keys = [normalize_artist_key(lead.get("stage_name", "")) for lead in leads]
    report.add(
        "dedup_and_grouping",
        f"{case_prefix}_zero_duplicate_artist_keys",
        len(keys) == len(set(keys)),
        f"keys={keys}",
    )

    valid_statuses = all(lead.get("attribution_status") in ("verified", "uncertain") for lead in leads)
    report.add(
        "contract_validity",
        f"{case_prefix}_valid_attribution_statuses",
        len(leads) > 0 and valid_statuses,
        f"statuses={[lead.get('attribution_status') for lead in leads]}",
    )


def run_offline_baseline_eval(dataset_path: Path = EVAL_DATASET_PATH) -> EvalReport:
    data = load_eval_dataset(dataset_path)
    report = EvalReport(mode="offline_baseline")
    connector = YouTubeConnector()

    # 1. URL hygiene cases
    for case in data.get("url_hygiene_cases", []):
        cid = case["id"]
        try:
            canon = canonical_watch_url(case["input_url"])
            valid = True
        except ValueError:
            canon = None
            valid = False
        passed = valid == case["expected_valid"] and canon == case["expected_canonical"]
        report.add(
            "url_hygiene",
            cid,
            passed,
            f"got valid={valid} canon={canon!r}, expected valid={case['expected_valid']} canon={case['expected_canonical']!r}",
        )

    # 2. Attribution accuracy cases
    for case in data.get("attribution_cases", []):
        cid = case["id"]
        stage_name, status, _ = infer_performer_and_attribution(case["title"], case["channel"])
        passed = (
            stage_name == case["expected_stage_name"]
            and status == case["expected_status"]
        )
        report.add(
            "attribution_accuracy",
            cid,
            passed,
            f"got ({stage_name!r}, {status!r}), expected ({case['expected_stage_name']!r}, {case['expected_status']!r})",
        )

    # 3. Grouping & deduplication cases
    for case in data.get("grouping_cases", []):
        cid = case["id"]
        leads = connector.group_videos_into_leads(case["videos"])
        lead_count = len(leads)
        unique_links = len(leads[0]["source_links"]) if leads else 0
        status = leads[0]["attribution_status"] if leads else None
        passed = (
            lead_count == case["expected_lead_count"]
            and unique_links == case["expected_unique_links"]
            and status == case["expected_status"]
        )
        report.add(
            "dedup_and_grouping",
            cid,
            passed,
            f"got count={lead_count} links={unique_links} status={status!r}, expected count={case['expected_lead_count']} links={case['expected_unique_links']} status={case['expected_status']!r}",
        )

    # 4. End-to-end discovery + second-take pipeline scenarios
    for scenario in data.get("pipeline_scenarios", []):
        sid = scenario["id"]
        store = SimonStore(":memory:")
        run = run_live_scout(
            brief_prompt=scenario["brief"],
            store=store,
            gemini=ScenarioGemini(scenario["agent_output"]),
            youtube=EvalYouTubeConnector(),
            max_leads=scenario["max_leads"],
            max_second_takes=scenario["max_second_takes"],
        )
        leads_dicts = [lead.to_dict() for lead in run.artist_leads]
        score_discovery_agent_output(report, scenario["agent_output"], leads_dicts, case_prefix=sid)

        exp = scenario["expected"]
        all_urls = {url for lead in run.artist_leads for url in lead.source_links}
        leaked = [u for u in exp.get("must_exclude_urls", []) if u in all_urls]
        report.add(
            "url_hygiene",
            f"{sid}_excludes_dead_and_disallowed_urls",
            len(leaked) == 0,
            f"leaked={leaked}",
        )
        report.add(
            "contract_validity",
            f"{sid}_matches_target_lead_count",
            len(run.artist_leads) == exp["lead_count"],
            f"got {len(run.artist_leads)}, expected {exp['lead_count']}",
        )

        uncertain_actual = {
            lead.stage_name for lead in run.artist_leads if lead.attribution_status == "uncertain"
        }
        report.add(
            "attribution_accuracy",
            f"{sid}_flags_expected_uncertain_leads",
            set(exp["expected_uncertain_artists"]).issubset(uncertain_actual),
            f"got uncertain={sorted(uncertain_actual)}, expected subset={exp['expected_uncertain_artists']}",
        )

        clips_by_artist: Dict[str, List[str]] = {}
        for clip in run.clip_evidence:
            clips_by_artist.setdefault(clip.stage_name, []).append(clip.source_url)

        for artist in exp.get("expected_multi_clip_artists", []):
            urls = clips_by_artist.get(artist, [])
            report.add(
                "second_take_coverage",
                f"{sid}_second_take_added_{normalize_artist_key(artist)}",
                len(urls) >= 2 and len(urls) == len(set(urls)),
                f"artist={artist} evaluated_urls={urls}",
            )
        for artist in exp.get("expected_single_clip_artists", []):
            assess = next((a for a in run.assessments if a.stage_name == artist), None)
            report.add(
                "second_take_coverage",
                f"{sid}_single_clip_flag_preserved_{normalize_artist_key(artist)}",
                assess is not None and assess.single_clip_flag is True,
                f"artist={artist} single_clip_flag={getattr(assess, 'single_clip_flag', None)}",
            )

    # 5. Stage 1 DiscoveryHandoff v1.0.0 contract & sandbox verifier evals
    demo_handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
    cleaned_demo, demo_errors = clean_and_dedupe_handoff(demo_handoff, verify_oembed=False)
    report.add(
        "handoff_contract_v1",
        "demo_handoff_passes_strict_v1_schema",
        len(demo_errors) == 0 and len(cleaned_demo.get("leads", [])) >= 1,
        f"errors={demo_errors}",
    )

    subjective_handoff = {
        "contract_version": "1.0.0",
        "run_id": "run_eval_subj",
        "search_brief": "NYC vocalists",
        "requested_count": 1,
        "leads": [
            {
                "lead_id": "lead_01",
                "stage_name": "Test Singer",
                "seed_sources": [
                    {"url": "https://www.youtube.com/watch?v=3-K26i1go0s", "source_channel": "youtube_live_session"}
                ],
                "attribution_status": "verified",
                "context_snippet": "#1 top pick, score: 9/10 strongest fit for NYC.",
            }
        ],
        "discovered_sources": [],
    }
    _, subj_errors = clean_and_dedupe_handoff(subjective_handoff, verify_oembed=False)
    report.add(
        "handoff_contract_v1",
        "rejects_subjective_ranking_and_scores",
        any("ranking/scoring" in err for err in subj_errors),
        f"errors={subj_errors}",
    )

    multi_channel_dup_handoff = {
        "contract_version": "1.0.0",
        "run_id": "run_eval_dedup",
        "search_brief": "NYC vocalists",
        "requested_count": 1,
        "leads": [
            {
                "lead_id": "lead_01",
                "stage_name": "The Velvet Echo",
                "seed_sources": [
                    {"url": "https://youtu.be/3-K26i1go0s?t=15", "source_channel": "youtube_live_session"}
                ],
                "attribution_status": "verified",
                "context_snippet": "Live room performance on YouTube.",
            },
            {
                "lead_id": "lead_02",
                "stage_name": "Velvet Echo",
                "seed_sources": [
                    {"url": "https://www.arlenesgrocerynyc.com/calendar", "source_channel": "diy_venue_calendar"}
                ],
                "attribution_status": "uncertain",
                "context_snippet": "Listed on Arlene's Grocery calendar.",
            },
        ],
        "discovered_sources": [
            {
                "url": "https://www.arlenesgrocerynyc.com/calendar",
                "source_channel": "diy_venue_calendar",
                "title_or_node": "Arlene's Grocery",
                "why_useful": "LES emerging vocal showcase calendar.",
                "discovered_by": "stage_1_discovery",
            }
        ],
    }
    cleaned_dup, dup_errors = clean_and_dedupe_handoff(multi_channel_dup_handoff, verify_oembed=False)
    merged_leads = cleaned_dup.get("leads", [])
    report.add(
        "handoff_contract_v1",
        "merges_cross_channel_duplicate_leads_and_canonicalizes_urls",
        (
            len(dup_errors) == 0
            and len(merged_leads) == 1
            and len(merged_leads[0]["seed_sources"]) == 2
            and merged_leads[0]["seed_sources"][0]["url"] == "https://www.youtube.com/watch?v=3-K26i1go0s"
            and merged_leads[0]["attribution_status"] == "uncertain"
        ),
        f"errors={dup_errors} merged={merged_leads}",
    )

    extra_key_handoff = dict(demo_handoff)
    extra_key_handoff["unexpected_rank_field"] = 1
    _, extra_errors = clean_and_dedupe_handoff(extra_key_handoff, verify_oembed=False)
    report.add(
        "handoff_contract_v1",
        "rejects_additional_properties_on_handoff",
        any("additionalProperties=false" in err for err in extra_errors),
        f"errors={extra_errors}",
    )

    # 6. Managed Agent package compilation & mount checks (agents/discovery-scout)
    pkg = compile_agent_package(REPO_ROOT / "agents" / "discovery-scout")
    payload = pkg["payload"]
    inline_targets = {
        s.get("target") or s.get("path")
        for s in payload.get("base_environment", {}).get("sources", [])
        if s.get("type") == "inline"
    }
    required_mounts = {
        ".agents/AGENTS.md",
        ".agents/skills/music/SKILL.md",
        ".agents/skills/music/scripts/verify_handoff.py",
        ".agents/skills/simon-db/SKILL.md",
        ".agents/skills/simon-db/scripts/simon_db.py",
    }
    report.add(
        "agent_package_compile",
        "mounts_layer1_layer2_verifier_and_simon_db",
        required_mounts.issubset(inline_targets),
        f"missing={sorted(required_mounts - inline_targets)}",
    )
    env_vars = payload.get("base_environment", {}).get("env", {})
    report.add(
        "agent_package_compile",
        "configures_domain_db_url_and_token_budget",
        (
            env_vars.get("SIMON_DOMAIN") == "music"
            and bool(env_vars.get("SIMON_DB_URL"))
            and bool(payload.get("agent_config", {}).get("max_total_tokens"))
        ),
        f"env={env_vars} agent_config={payload.get('agent_config')}",
    )

    return report


def run_live_discovery_eval(brief_prompt: str, max_leads: int = 4) -> EvalReport:
    """Run a live eval against Gemini.discover_youtube_leads + YouTubeConnector."""
    load_dotenv_if_present()
    gm = Gemini()
    yt = YouTubeConnector()
    report = EvalReport(mode=f"live ({gm.discovery_agent})")

    disc_res = gm.discover_youtube_leads(brief_prompt)
    disc_data = disc_res.get("data", {})
    queries = [str(q).strip() for q in (disc_data.get("search_queries") or []) if str(q).strip()]

    discovered: List[Dict[str, str]] = []
    seen_urls = set()
    for cand in disc_data.get("candidate_videos") or []:
        if not isinstance(cand, dict) or not cand.get("url"):
            continue
        oe = yt.verify_oembed(str(cand["url"]))
        if not oe or oe["url"] in seen_urls:
            continue
        seen_urls.add(oe["url"])
        discovered.append({
            "video_id": oe["video_id"],
            "url": oe["url"],
            "title": oe["title"] or str(cand.get("title", "")),
            "channel": oe["channel"] or str(cand.get("channel", "")),
            "stage_name": str(cand.get("stage_name", "")).strip(),
            "attribution_status": str(cand.get("attribution_status", "")).strip(),
            "attribution_notes": str(cand.get("attribution_notes", "")).strip(),
            "query_used": "managed_agent_direct",
        })

    for query in queries[:3]:
        for vid in yt.search_public_videos(query, max_results=4):
            if vid["url"] in seen_urls:
                continue
            oe = yt.verify_oembed(vid["url"])
            if not oe:
                continue
            seen_urls.add(oe["url"])
            vid["title"] = oe["title"] or vid["title"]
            vid["channel"] = oe["channel"] or vid["channel"]
            discovered.append(vid)

    leads = yt.group_videos_into_leads(discovered)[:max_leads]
    score_discovery_agent_output(report, disc_data, leads, case_prefix="live")
    report.add(
        "contract_validity",
        "live_returned_at_least_one_verified_lead",
        len(leads) >= 1,
        f"leads_found={[l['stage_name'] for l in leads]}",
    )
    return report


class DiscoveryBaselineEvalTests(unittest.TestCase):
    def test_offline_discovery_baseline_eval_suite(self) -> None:
        report = run_offline_baseline_eval()
        failures = [c for c in report.checks if not c.passed]
        self.assertEqual(
            failures,
            [],
            msg="Discovery baseline eval failures:\n" + report.format_table(),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Simon Discovery Agent baseline evals.")
    parser.add_argument("--live", action="store_true", help="Run live discovery eval against Gemini + YouTube.")
    parser.add_argument("--brief", default=DEFAULT_TASTE_BRIEF, help="Taste brief for --live mode.")
    parser.add_argument("--max-leads", type=int, default=4, help="Max leads for --live mode.")
    parser.add_argument("--json", action="store_true", help="Emit JSON scorecard instead of ASCII table.")
    args = parser.parse_args()

    report = (
        run_live_discovery_eval(brief_prompt=args.brief, max_leads=args.max_leads)
        if args.live
        else run_offline_baseline_eval()
    )

    if args.json:
        print(
            json.dumps(
                {
                    "mode": report.mode,
                    "overall_score": report.overall_score,
                    "dimensions": report.summary_by_dimension(),
                },
                indent=2,
            )
        )
    else:
        print(report.format_table())

    return 0 if report.overall_score == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
