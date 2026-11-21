"""Discovery Scouting Landing Page (/discovery) & Live Agent Traces (/traces) UI + API helpers.

Connects Simon's Discovery Source Registry (`data/reference/discovery_sources_seed.json` +
`discovered_sources` in simon-db), Managed Agent fleet orchestration (`simon/fleet.py`),
and strict `DiscoveryHandoff v1.0.0` contract validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from .db_tools import (
    get_agent_document,
    list_agent_documents,
    sanitize_agent_report,
    save_agent_document,
)
from .fleet import (
    TERMINAL_STATUSES,
    _http_json,
    dispatch_fleet,
    poll_interaction,
    resolve_discovery_agent_id,
)
from .store import SimonStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SEED_PATH = REPO_ROOT / "data" / "reference" / "discovery_sources_seed.json"
DEMO_HANDOFF_PATH = REPO_ROOT / "examples" / "discovery_handoff_demo.json"
VERIFY_SCRIPT_DIR = REPO_ROOT / "agents" / "discovery-scout" / "skills" / "music" / "scripts"
if str(VERIFY_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_SCRIPT_DIR))

from verify_handoff import clean_and_dedupe_handoff  # noqa: E402

DEFAULT_DISCOVERY_BRIEF = (
    "Find emerging NYC solo vocalists performing stripped-back live soul, R&B, or indie sets."
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_source_registry(store: SimonStore) -> Dict[str, Any]:
    """Load seeded reference sources merged with any newly discovered sources in simon-db."""
    sources: List[Dict[str, Any]] = []
    seen_urls = set()

    if SOURCE_SEED_PATH.is_file():
        seed_payload = json.loads(SOURCE_SEED_PATH.read_text(encoding="utf-8"))
        for src in seed_payload.get("sources", []):
            url = str(src.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append(src)

    # Merge any live discovered_sources saved via simon-db
    db_docs = list_agent_documents(store, "discovered_sources", limit=100)
    for row in db_docs:
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict):
            continue
        url = str(doc.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(
            {
                "source_id": str(doc.get("source_id") or doc.get("_doc_id") or f"db_{uuid.uuid4().hex[:8]}"),
                "name": str(doc.get("name") or doc.get("title_or_node") or url),
                "url": url,
                "source_channel": str(doc.get("source_channel") or "other"),
                "source_type": str(doc.get("source_type") or "discovered"),
                "location": doc.get("location") or {"scope": "global", "city": None, "area": None, "country": None},
                "genre_tags": doc.get("genre_tags") or ["all"],
                "career_tier": str(doc.get("career_tier") or "mixed"),
                "access_method": str(doc.get("access_method") or "public_web"),
                "why_useful": str(doc.get("why_useful") or "Discovered by Simon agent."),
                "discovered_by": str(doc.get("discovered_by") or "stage_1_discovery"),
                "status": str(doc.get("status") or "active"),
                "notes": doc.get("notes"),
                "last_checked_at": doc.get("last_checked_at"),
            }
        )

    channels = sorted({s.get("source_channel", "other") for s in sources})
    cities = sorted({(s.get("location") or {}).get("city") or "Global" for s in sources})
    tiers = sorted({s.get("career_tier", "mixed") for s in sources})
    return {
        "count": len(sources),
        "channels": channels,
        "cities": cities,
        "tiers": tiers,
        "sources": sources,
    }


def _partition_sources(sources: List[Dict[str, Any]], agent_count: int) -> List[List[Dict[str, Any]]]:
    """Distribute selected sources evenly across N discovery agents."""
    n = max(1, min(int(agent_count), 10))
    buckets: List[List[Dict[str, Any]]] = [[] for _ in range(n)]
    for idx, src in enumerate(sources):
        buckets[idx % n].append(src)
    # If user requested more agents than sources, replicate sources round-robin so every agent has work
    for idx in range(n):
        if not buckets[idx] and sources:
            buckets[idx].append(sources[idx % len(sources)])
    return buckets


def _extract_findings_from_handoff(output_json: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(output_json, dict):
        return []
    findings: List[Dict[str, Any]] = []
    for lead in output_json.get("leads") or []:
        if not isinstance(lead, dict):
            continue
        seeds = lead.get("seed_sources") or []
        first_seed = seeds[0] if seeds and isinstance(seeds[0], dict) else {}
        item = {
            "lead_id": str(lead.get("lead_id") or ""),
            "title": str(lead.get("stage_name") or lead.get("lead_id") or "Unnamed Subject"),
            "summary": str(lead.get("context_snippet") or first_seed.get("notes") or "Discovered lead."),
            "source_name": str(first_seed.get("seed_query_or_venue_node") or first_seed.get("source_channel") or ""),
            "source_channel": str(first_seed.get("source_channel") or ""),
            "url": str(first_seed.get("url") or ""),
            "attribution_status": str(lead.get("attribution_status") or ""),
        }
        findings.append({k: v for k, v in item.items() if v})
    return findings


def _human_steps_for_worker(
    worker: Dict[str, Any],
    brief: str,
    mode: str,
) -> List[Dict[str, Any]]:
    """Build clean human-first Field News steps (looking_at / finding / analysis) with zero telemetry."""
    assigned = worker.get("assigned_sources") or []
    src_names = ", ".join(s.get("name", "source") for s in assigned[:3]) or "assigned sources"
    status = str(worker.get("status") or "in_progress")
    findings = _extract_findings_from_handoff(worker.get("output_json"))
    now = _utc_now_iso()

    if status == "completed":
        names_preview = ", ".join(f["title"] for f in findings[:3]) or "no verified leads"
        return [
            {
                "step_number": 1,
                "phase": "looking_at",
                "title": f"Scanning {src_names}",
                "looking_at": f"Inspecting {src_names} against brief: {brief}",
                "finding": f"Checked {len(assigned)} assigned source(s) for active vocalists and public clips.",
                "analysis": "Focused on objective public bills and verifiable artist attribution.",
                "status": "done",
                "updated_at": now,
            },
            {
                "step_number": 2,
                "phase": "finding",
                "title": f"Discovered {len(findings)} subject(s)",
                "looking_at": f"Cross-checking public seed links from {src_names}",
                "finding": f"Found {len(findings)} distinct lead(s): {names_preview}.",
                "analysis": "Each subject has at least one public seed link with clear context.",
                "status": "done",
                "updated_at": now,
            },
            {
                "step_number": 3,
                "phase": "analysis",
                "title": "Verified & deduplicated leads",
                "looking_at": "Checking attribution, URL hygiene, and unranked neutrality",
                "finding": (
                    "All leads passed DiscoveryHandoff v1.0.0 checks."
                    if worker.get("contract_valid")
                    else "Completed with contract notes to review."
                ),
                "analysis": (
                    "Zero scoring or ranking applied; ready for Stage 2 investigation."
                    if worker.get("contract_valid")
                    else "; ".join(worker.get("contract_errors") or ["Review output payload."])
                ),
                "status": "done" if worker.get("contract_valid") else "blocked",
                "updated_at": now,
            },
            {
                "step_number": 4,
                "phase": "saved",
                "title": "Scouting report & output stored",
                "looking_at": "Final DiscoveryHandoff output contract",
                "finding": f"Stored {len(findings)} lead(s) and full structured output for review.",
                "analysis": "Available now in Scouting Reports.",
                "status": "done",
                "updated_at": now,
            },
        ]

    if status in ("failed", "cancelled", "incomplete", "budget_exceeded", "error"):
        return [
            {
                "step_number": 1,
                "phase": "looking_at",
                "title": f"Blocked while scouting {src_names}",
                "looking_at": f"Assigned to inspect {src_names}",
                "finding": "Run stopped before producing a complete scouting report.",
                "analysis": str(worker.get("error") or f"Status: {status}"),
                "status": "blocked",
                "updated_at": now,
            }
        ]

    # Active / in-motion live worker before completion
    raw_steps = worker.get("steps") or []
    step_count = len(raw_steps)
    steps: List[Dict[str, Any]] = [
        {
            "step_number": 1,
            "phase": "looking_at",
            "title": f"Inspecting {src_names}",
            "looking_at": f"Reviewing {src_names} for: {brief}",
            "finding": (
                f"Active in the field ({step_count} research action(s) underway)."
                if step_count
                else "Scout launched and opening assigned sources."
            ),
            "analysis": "Gathering objective public leads and verifying source URLs.",
            "status": "active",
            "updated_at": now,
        }
    ]
    if step_count >= 2:
        steps[0]["status"] = "done"
        steps.append(
            {
                "step_number": 2,
                "phase": "finding",
                "title": "Pulling candidate subjects & seed links",
                "looking_at": f"Checking public listings and channels across {src_names}",
                "finding": "Collecting artist names, live clip links, and venue/channel context.",
                "analysis": "Filtering out duplicates and verifying public attribution before saving.",
                "status": "active",
                "updated_at": now,
            }
        )
    return steps


def _sync_worker_agent_report(
    store: SimonStore,
    batch_id: str,
    brief: str,
    worker: Dict[str, Any],
    mode: str,
) -> Dict[str, Any]:
    """Create or update the human-first `agent_reports` record for a discovery worker."""
    idx = int(worker.get("index", 0))
    report_id = str(worker.get("report_id") or f"rep_{batch_id}_w{idx + 1}")
    worker["report_id"] = report_id
    agent_name = f"Discovery Scout {idx + 1:02d}"
    assigned_sources = [
        {
            "source_id": str(s.get("source_id") or ""),
            "name": str(s.get("name") or ""),
            "url": str(s.get("url") or ""),
            "source_channel": str(s.get("source_channel") or ""),
            "city": str(s.get("city") or ""),
        }
        for s in (worker.get("assigned_sources") or [])
    ]
    assigned_sources = [{k: v for k, v in item.items() if v} for item in assigned_sources]

    existing_doc = get_agent_document(store, "agent_reports", report_id)
    existing = (
        existing_doc.get("data")
        if isinstance(existing_doc, dict) and isinstance(existing_doc.get("data"), dict)
        else (existing_doc if isinstance(existing_doc, dict) else None)
    )

    raw_status = str(worker.get("status") or "in_progress")
    if raw_status == "completed":
        rep_status = "completed"
    elif raw_status in ("failed", "cancelled", "incomplete", "budget_exceeded", "error"):
        rep_status = "blocked"
    elif existing and existing.get("steps"):
        rep_status = "in_motion"
    else:
        rep_status = "in_motion" if (worker.get("steps") or mode == "live") else "starting"

    extracted_findings = _extract_findings_from_handoff(worker.get("output_json"))
    existing_findings = list(existing.get("findings") or []) if existing else []
    findings = extracted_findings or existing_findings

    # Preserve agent-authored Field News steps if the agent wrote them directly via field_report.py
    existing_steps = list(existing.get("steps") or []) if existing else []
    fallback_steps = _human_steps_for_worker(worker, brief, mode)
    if existing_steps and any(s.get("looking_at") or s.get("finding") for s in existing_steps):
        steps = existing_steps
        if rep_status == "completed" and not any(s.get("phase") == "saved" for s in steps):
            steps.append(fallback_steps[-1])
    else:
        steps = fallback_steps

    src_names = ", ".join(s.get("name", "source") for s in assigned_sources[:2]) or "assigned sources"
    if rep_status == "completed":
        default_headline = f"Found {len(findings)} verified lead(s) across {src_names}."
        current_focus = "Report completed"
    elif rep_status == "blocked":
        default_headline = f"Scout blocked while inspecting {src_names}."
        current_focus = str(worker.get("error") or "Needs attention")
    else:
        default_headline = f"Scouting {src_names} for matching vocalists."
        current_focus = steps[-1].get("looking_at") or f"Inspecting {src_names}"

    now = _utc_now_iso()
    report_payload: Dict[str, Any] = {
        "contract_version": "1.0.0",
        "report_id": report_id,
        "batch_id": batch_id,
        "agent_name": agent_name,
        "stage": "discovery",
        "brief": brief,
        "assigned_sources": assigned_sources,
        "status": rep_status,
        "headline": (existing.get("headline") if existing and rep_status != "completed" and existing.get("headline") else default_headline),
        "current_focus": current_focus,
        "steps": steps,
        "findings": findings,
        "output": worker.get("output_json") if worker.get("output_json") is not None else (existing.get("output") if existing else None),
        "archived": bool((existing or {}).get("archived", False)),
        "archived_at": (existing or {}).get("archived_at"),
        "created_at": str((existing or {}).get("created_at") or worker.get("created_at") or now),
        "updated_at": str(worker.get("updated_at") or now),
    }
    clean_report = sanitize_agent_report(report_payload)
    save_agent_document(store, "agent_reports", clean_report, doc_id=report_id)
    return clean_report


def backfill_historical_reports(store: SimonStore, limit: int = 50) -> int:
    """Idempotently project legacy `fleet_runs` discovery batches into human-first `agent_reports`.

    Never overwrites or un-archives reports that already exist in `agent_reports`.
    """
    existing_rows = list_agent_documents(store, "agent_reports", limit=500)
    existing_ids = set()
    for row in existing_rows:
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if isinstance(doc, dict) and doc.get("report_id"):
            existing_ids.add(str(doc["report_id"]))

    created = 0
    fleet_docs = list_agent_documents(store, "fleet_runs", limit=limit)
    for row in fleet_docs:
        batch = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(batch, dict):
            continue
        workers = batch.get("workers")
        if not isinstance(workers, list) or not workers:
            continue
        batch_id = str(batch.get("batch_id") or batch.get("_doc_id") or "").strip()
        if not batch_id:
            continue
        brief = str(batch.get("search_brief") or DEFAULT_DISCOVERY_BRIEF)
        mode = str(batch.get("mode") or "live")
        batch_created = batch.get("created_at")
        batch_updated = batch.get("updated_at") or batch_created
        for idx, worker in enumerate(workers):
            if not isinstance(worker, dict):
                continue
            w_copy = dict(worker)
            w_copy.setdefault("index", idx)
            report_id = str(w_copy.get("report_id") or f"rep_{batch_id}_w{idx + 1}")
            if report_id in existing_ids:
                continue
            w_copy["report_id"] = report_id
            if batch_created and not w_copy.get("created_at"):
                w_copy["created_at"] = batch_created
            if batch_updated and not w_copy.get("updated_at"):
                w_copy["updated_at"] = batch_updated
            _sync_worker_agent_report(store, batch_id=batch_id, brief=brief, worker=w_copy, mode=mode)
            existing_ids.add(report_id)
            created += 1
    return created


def archive_agent_reports(
    store: SimonStore,
    report_ids: Optional[List[str]] = None,
    batch_id: Optional[str] = None,
    archived: bool = True,
) -> Dict[str, Any]:
    """Soft-archive (Clear / Start Over) or restore `agent_reports` without deleting history."""
    backfill_historical_reports(store)
    target_ids = {str(rid).strip() for rid in (report_ids or []) if str(rid).strip()}
    docs = list_agent_documents(store, "agent_reports", limit=500)
    now = _utc_now_iso()
    updated = 0
    for row in docs:
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict) or not doc.get("report_id"):
            continue
        rid = str(doc["report_id"])
        if target_ids and rid not in target_ids:
            continue
        if batch_id and doc.get("batch_id") != batch_id:
            continue
        if bool(doc.get("archived", False)) == bool(archived):
            continue
        clean = sanitize_agent_report(doc)
        clean["archived"] = bool(archived)
        clean["archived_at"] = now if archived else None
        save_agent_document(store, "agent_reports", clean, doc_id=rid)
        updated += 1
    return {"ok": True, "updated_count": updated, "archived": bool(archived)}


def list_agent_reports(
    store: SimonStore,
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List human-first AgentReport documents with all telemetry stripped."""
    backfill_historical_reports(store)
    docs = list_agent_documents(store, "agent_reports", limit=max(limit, 200))
    reports: List[Dict[str, Any]] = []
    for row in docs:
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict) or not doc.get("report_id"):
            continue
        clean = sanitize_agent_report(doc)
        if not include_archived and bool(clean.get("archived", False)):
            continue
        if batch_id and clean.get("batch_id") != batch_id:
            continue
        if status and clean.get("status") != status:
            continue
        if stage and clean.get("stage") != stage:
            continue
        reports.append(clean)
    reports.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    return reports[:limit]


def get_agent_report(store: SimonStore, report_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single human-first AgentReport with all telemetry stripped."""
    row = get_agent_document(store, "agent_reports", report_id)
    if not isinstance(row, dict):
        return None
    doc = row.get("data") if isinstance(row.get("data"), dict) else row
    if not isinstance(doc, dict):
        return None
    return sanitize_agent_report(doc)


def list_investigator_dossiers(
    store: SimonStore,
    lead_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List stored Stage 2 investigator dossiers with all telemetry keys stripped."""
    docs = list_agent_documents(store, "investigator_dossiers", limit=max(limit, 100))
    dossiers: List[Dict[str, Any]] = []
    for row in docs:
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict):
            continue
        clean = sanitize_agent_report(doc)
        if lead_id and clean.get("lead_id") != lead_id and clean.get("_doc_id") != lead_id:
            continue
        dossiers.append(clean)
    dossiers.sort(
        key=lambda d: str(d.get("updated_at") or d.get("_saved_at") or d.get("created_at") or ""),
        reverse=True,
    )
    return dossiers[:limit]


def list_discovery_leads(
    store: SimonStore,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List verified/discovered leads from `leads` and `discovery_handoffs`, deduplicated and sanitized."""
    leads_out: List[Dict[str, Any]] = []
    seen_keys = set()

    def _add_lead(raw: Dict[str, Any], handoff_meta: Optional[Dict[str, Any]] = None) -> None:
        if not isinstance(raw, dict):
            return
        lead_id = str(raw.get("lead_id") or raw.get("_doc_id") or "").strip()
        stage_name = str(raw.get("stage_name") or "").strip()
        if not lead_id and not stage_name:
            return
        dedupe_key = (lead_id or stage_name).lower()
        if dedupe_key in seen_keys:
            return
        seen_keys.add(dedupe_key)
        item = dict(raw)
        if handoff_meta:
            item.setdefault("run_id", handoff_meta.get("run_id"))
            item.setdefault("search_brief", handoff_meta.get("search_brief"))
            item.setdefault("discovered_at", handoff_meta.get("generated_at"))
        leads_out.append(sanitize_agent_report(item))

    for row in list_agent_documents(store, "leads", limit=max(limit, 100)):
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if isinstance(doc, dict):
            _add_lead(doc)

    for row in list_agent_documents(store, "discovery_handoffs", limit=50):
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict):
            continue
        meta = {
            "run_id": doc.get("run_id"),
            "search_brief": doc.get("search_brief"),
            "generated_at": doc.get("generated_at") or doc.get("_saved_at"),
        }
        for lead in doc.get("leads") or []:
            if isinstance(lead, dict):
                _add_lead(lead, handoff_meta=meta)

    return leads_out[:limit]


def _validate_handoff_payload(output_json: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(output_json, dict):
        return {"valid": False, "errors": ["No JSON DiscoveryHandoff payload returned yet."], "lead_count": 0}
    cleaned, errors = clean_and_dedupe_handoff(output_json, verify_oembed=False)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "lead_count": len(cleaned.get("leads", [])),
        "cleaned": cleaned if not errors else output_json,
    }


def _build_simulated_worker(
    worker_index: int,
    run_id: str,
    brief: str,
    leads_per_agent: int,
    assigned_sources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Produce a realistic, contract-valid DiscoveryHandoff v1.0.0 worker result for instant UI testing."""
    demo_leads_pool: List[Dict[str, Any]] = []
    if DEMO_HANDOFF_PATH.is_file():
        demo = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        demo_leads_pool = demo.get("leads", [])

    primary_src = assigned_sources[0]
    src_channel = primary_src.get("source_channel", "youtube_live_session")
    if src_channel == "musicbrainz":
        src_channel = "other"

    leads: List[Dict[str, Any]] = []
    for k in range(leads_per_agent):
        if demo_leads_pool and src_channel == "youtube_live_session":
            base = demo_leads_pool[(worker_index + k) % len(demo_leads_pool)]
            leads.append(
                {
                    "lead_id": f"lead_w{worker_index + 1}_{k + 1:02d}",
                    "stage_name": base["stage_name"],
                    "seed_sources": [
                        {
                            "url": base["seed_sources"][0]["url"],
                            "source_channel": "youtube_live_session",
                            "seed_query_or_venue_node": primary_src["name"],
                            "discovered_at": _utc_now_iso(),
                            "notes": f"Simulated discovery from {primary_src['name']}.",
                        }
                    ],
                    "attribution_status": base.get("attribution_status", "verified"),
                    "context_snippet": base.get("context_snippet")
                    or f"Live vocal video listed under {primary_src['name']}.",
                }
            )
        else:
            sample_names = [
                "Maya Vance",
                "Soraia Bell",
                "Devon K.",
                "Nadia Solis",
                "Tessa Morales",
                "Eliot Gray",
                "Kira Osei",
                "Jules Navarro",
            ]
            artist = sample_names[(worker_index * 3 + k) % len(sample_names)]
            leads.append(
                {
                    "lead_id": f"lead_w{worker_index + 1}_{k + 1:02d}",
                    "stage_name": artist,
                    "seed_sources": [
                        {
                            "url": primary_src["url"],
                            "source_channel": src_channel,
                            "seed_query_or_venue_node": primary_src["name"],
                            "discovered_at": _utc_now_iso(),
                            "notes": f"Listed on {primary_src['name']} ({(primary_src.get('location') or {}).get('city') or 'Global'}).",
                        }
                    ],
                    "attribution_status": "verified" if src_channel == "bandcamp_local_arrival" else "uncertain",
                    "context_snippet": (
                        f"Listed on {primary_src['name']} ({src_channel}) matching brief constraints."
                    ),
                }
            )

    handoff = {
        "contract_version": "1.0.0",
        "run_id": f"{run_id}_w{worker_index + 1}",
        "search_brief": brief,
        "requested_count": leads_per_agent,
        "generated_at": _utc_now_iso(),
        "leads": leads,
        "discovered_sources": [
            {
                "url": primary_src["url"],
                "source_channel": primary_src.get("source_channel", "other"),
                "title_or_node": primary_src["name"],
                "why_useful": primary_src.get("why_useful") or "Active discovery source.",
                "discovered_by": "stage_1_discovery",
            }
        ],
    }
    validation = _validate_handoff_payload(handoff)
    return {
        "index": worker_index,
        "worker_id": f"agent_{worker_index + 1:02d}",
        "interaction_id": f"sim-{run_id}-w{worker_index + 1}",
        "status": "completed",
        "duration_ms": 840 + worker_index * 210,
        "assigned_sources": [
            {
                "source_id": s["source_id"],
                "name": s["name"],
                "url": s["url"],
                "source_channel": s["source_channel"],
                "city": (s.get("location") or {}).get("city") or "Global",
            }
            for s in assigned_sources
        ],
        "steps": [
            {
                "index": 1,
                "type": "tool_call",
                "tools": ["code_execution"],
                "preview": "python3 .agents/skills/simon-db/scripts/simon_db.py list discovered_sources --limit 50",
            },
            {
                "index": 2,
                "type": "tool_call",
                "tools": ["google_search", "url_context"],
                "preview": f"Scanned {len(assigned_sources)} assigned source(s): {', '.join(s['name'] for s in assigned_sources)}",
            },
            {
                "index": 3,
                "type": "tool_call",
                "tools": ["code_execution"],
                "preview": f"python3 .agents/skills/music/scripts/verify_handoff.py -> ok=true, lead_count={len(leads)}",
            },
            {
                "index": 4,
                "type": "model_output",
                "preview": f"Emitted DiscoveryHandoff v1.0.0 with {len(leads)} unranked lead(s).",
            },
        ],
        "output_json": validation.get("cleaned", handoff),
        "output_text": json.dumps(validation.get("cleaned", handoff), indent=2),
        "contract_valid": validation["valid"],
        "contract_errors": validation["errors"],
        "lead_count": validation["lead_count"],
        "error": None,
    }


def dispatch_discovery_batch(
    store: SimonStore,
    source_ids: List[str],
    brief: str,
    leads_per_agent: int = 2,
    agent_count: Optional[int] = None,
    live: bool = False,
    api_key: Optional[str] = None,
    request_fn: Callable[..., Tuple[int, Dict[str, Any]]] = _http_json,
) -> Dict[str, Any]:
    """Dispatch N Stage 1 Discovery agents across selected sources and persist batch state."""
    registry = load_source_registry(store)
    by_id = {s["source_id"]: s for s in registry["sources"]}
    selected = [by_id[sid] for sid in source_ids if sid in by_id]
    if not selected:
        raise ValueError("Select at least one valid source from the Source Registry.")

    clean_brief = (brief or DEFAULT_DISCOVERY_BRIEF).strip()
    n_leads = max(1, min(int(leads_per_agent or 2), 10))
    n_agents = max(1, min(int(agent_count or len(selected)), 10))
    partitions = _partition_sources(selected, n_agents)

    batch_id = f"disc_{uuid.uuid4().hex[:10]}"
    agent_id = resolve_discovery_agent_id()
    created_at = _utc_now_iso()

    workers: List[Dict[str, Any]] = []

    if not live:
        for idx, assigned in enumerate(partitions):
            worker = _build_simulated_worker(idx, batch_id, clean_brief, n_leads, assigned)
            worker["report_id"] = f"rep_{batch_id}_w{idx + 1}"
            workers.append(worker)
            if worker["contract_valid"] and isinstance(worker.get("output_json"), dict):
                try:
                    save_agent_document(store, "discovery_handoffs", worker["output_json"])
                except ValueError:
                    pass
            _sync_worker_agent_report(store, batch_id, clean_brief, worker, mode="simulated")
        mode = "simulated"
    else:
        assignments = [
            {
                "run_id": f"{batch_id}_w{idx + 1}",
                "report_id": f"rep_{batch_id}_w{idx + 1}",
                "batch_id": batch_id,
                "agent_name": f"Discovery Scout {idx + 1:02d}",
                "search_brief": clean_brief,
                "requested_count": n_leads,
                "assigned_sources": [
                    {
                        "source_id": s["source_id"],
                        "name": s["name"],
                        "url": s["url"],
                        "source_channel": s["source_channel"],
                        "location": s.get("location"),
                        "why_useful": s.get("why_useful"),
                    }
                    for s in assigned
                ],
            }
            for idx, assigned in enumerate(partitions)
        ]
        prompt_template = (
            "Run Stage 1 Discovery for this JSON assignment:\n{target}\n\n"
            "Focus specifically on the `assigned_sources` list provided above. "
            "Follow your Layer 1 SYSTEM.md, `source-discovery`, `field-reporting`, and Layer 2 `music` SKILL.md steps:\n"
            "1. While working, post live human-first Field News updates (`looking_at`, `finding`, `analysis`) "
            "using `.agents/skills/field-reporting/scripts/field_report.py step` with your `report_id` and `batch_id` "
            "(never include interaction_id or raw metadata).\n"
            "2. Run `verify_handoff.py`, save `discovery_handoffs`, `leads`, and any newly discovered `discovered_sources` to `simon-db`.\n"
            "3. Call `field_report.py finish --report-id <report_id> --headline \"...\" --output @/workspace/out/handoff_verified.json`.\n"
            "4. Return ONLY the verified DiscoveryHandoff v1.0.0 JSON object."
        )
        fleet_res = dispatch_fleet(
            agent_id=agent_id,
            assignments=assignments,
            prompt_template=prompt_template,
            max_concurrency=min(n_agents, 5),
            wait=False,
            dry_run=False,
            api_key=api_key,
            request_fn=request_fn,
        )
        for idx, fw in enumerate(fleet_res["workers"]):
            assigned = partitions[idx]
            out_json = fw.get("output_json")
            validation = _validate_handoff_payload(out_json) if fw.get("status") == "completed" else None
            worker = {
                "index": idx,
                "worker_id": f"agent_{idx + 1:02d}",
                "report_id": f"rep_{batch_id}_w{idx + 1}",
                "interaction_id": fw.get("interaction_id"),
                "environment_id": fw.get("environment_id"),
                "status": fw.get("status", "in_progress"),
                "duration_ms": fw.get("duration_ms", 0),
                "assigned_sources": [
                    {
                        "source_id": s["source_id"],
                        "name": s["name"],
                        "url": s["url"],
                        "source_channel": s["source_channel"],
                        "city": (s.get("location") or {}).get("city") or "Global",
                    }
                    for s in assigned
                ],
                "steps": fw.get("steps") or [],
                "output_json": validation.get("cleaned", out_json) if validation else out_json,
                "output_text": fw.get("output_text"),
                "contract_valid": validation["valid"] if validation else None,
                "contract_errors": validation["errors"] if validation else [],
                "lead_count": validation["lead_count"] if validation else 0,
                "error": fw.get("error"),
            }
            workers.append(worker)
            _sync_worker_agent_report(store, batch_id, clean_brief, worker, mode="live")
        mode = "live"

    batch_doc = {
        "batch_id": batch_id,
        "kind": "discovery_batch",
        "mode": mode,
        "agent_id": agent_id,
        "search_brief": clean_brief,
        "leads_per_agent": n_leads,
        "agent_count": n_agents,
        "selected_source_ids": [s["source_id"] for s in selected],
        "created_at": created_at,
        "updated_at": created_at,
        "workers": workers,
    }
    save_agent_document(store, "fleet_runs", batch_doc, doc_id=batch_id)
    return batch_doc


def list_discovery_batches(store: SimonStore, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent discovery batches saved in fleet_runs."""
    rows = list_agent_documents(store, "fleet_runs", limit=limit)
    out: List[Dict[str, Any]] = []
    for row in rows:
        data = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(data, dict) or data.get("kind") != "discovery_batch":
            continue
        workers = data.get("workers") or []
        completed = sum(1 for w in workers if w.get("status") == "completed")
        failed = sum(1 for w in workers if w.get("status") in ("failed", "error", "timeout", "cancelled"))
        total_leads = sum(int(w.get("lead_count") or 0) for w in workers)
        out.append(
            {
                "batch_id": data.get("batch_id") or data.get("_doc_id"),
                "mode": data.get("mode"),
                "agent_id": data.get("agent_id"),
                "search_brief": data.get("search_brief"),
                "agent_count": len(workers),
                "completed": completed,
                "failed": failed,
                "in_progress": max(0, len(workers) - completed - failed),
                "total_leads": total_leads,
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            }
        )
    return out


def _count_batch_steps(batch: Dict[str, Any]) -> int:
    return sum(len(w.get("steps") or []) for w in (batch.get("workers") or []))


def _batch_has_active_workers(batch: Dict[str, Any]) -> bool:
    for w in batch.get("workers") or []:
        st = str(w.get("status") or "")
        if w.get("interaction_id") and st not in TERMINAL_STATUSES and st != "error":
            return True
    return False


def _poll_batch_once(
    store: SimonStore,
    batch: Dict[str, Any],
    batch_id: str,
    api_key: Optional[str] = None,
    request_fn: Callable[..., Tuple[int, Dict[str, Any]]] = _http_json,
) -> bool:
    changed = False
    for worker in batch.get("workers") or []:
        status = str(worker.get("status") or "")
        interaction_id = worker.get("interaction_id")
        if not interaction_id or status in TERMINAL_STATUSES or status == "error":
            continue
        try:
            polled = poll_interaction(interaction_id, api_key=api_key, request_fn=request_fn)
        except Exception as exc:  # noqa: BLE001
            worker["error"] = str(exc)
            continue

        prev_steps = len(worker.get("steps") or [])
        new_steps = polled.get("steps") or []
        if polled["status"] != status or len(new_steps) != prev_steps:
            changed = True

        worker["status"] = polled["status"]
        if polled.get("environment_id"):
            worker["environment_id"] = polled["environment_id"]
        if new_steps:
            worker["steps"] = new_steps
        if polled.get("error"):
            worker["error"] = polled["error"]

        if polled["status"] == "completed":
            worker["output_text"] = polled.get("output_text")
            validation = _validate_handoff_payload(polled.get("output_json"))
            worker["output_json"] = validation.get("cleaned", polled.get("output_json"))
            worker["contract_valid"] = validation["valid"]
            worker["contract_errors"] = validation["errors"]
            worker["lead_count"] = validation["lead_count"]
            changed = True
            if validation["valid"] and isinstance(worker["output_json"], dict):
                try:
                    save_agent_document(store, "discovery_handoffs", worker["output_json"])
                except ValueError:
                    pass

        _sync_worker_agent_report(
            store,
            batch_id=batch_id,
            brief=str(batch.get("search_brief") or DEFAULT_DISCOVERY_BRIEF),
            worker=worker,
            mode=str(batch.get("mode") or "live"),
        )

    if changed:
        batch["updated_at"] = _utc_now_iso()
        save_agent_document(store, "fleet_runs", batch, doc_id=batch_id)
    return changed


def refresh_discovery_batch(
    store: SimonStore,
    batch_id: str,
    api_key: Optional[str] = None,
    request_fn: Callable[..., Tuple[int, Dict[str, Any]]] = _http_json,
    wait: bool = False,
    since_steps: int = -1,
    timeout_s: float = 15.0,
    poll_interval_s: float = 1.5,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Optional[Dict[str, Any]]:
    """Fetch a batch from fleet_runs and poll/long-poll Gemini for any in-progress live workers."""
    found = get_agent_document(store, "fleet_runs", batch_id)
    if not isinstance(found, dict):
        return None
    batch = found.get("data") if isinstance(found.get("data"), dict) else found
    if batch.get("mode") != "live":
        batch["total_steps"] = _count_batch_steps(batch)
        return batch

    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        changed = _poll_batch_once(store, batch, batch_id, api_key=api_key, request_fn=request_fn)
        total_steps = _count_batch_steps(batch)
        batch["total_steps"] = total_steps
        if not wait:
            break
        if changed or (since_steps >= 0 and total_steps > since_steps):
            break
        if not _batch_has_active_workers(batch):
            break
        if time.monotonic() >= deadline:
            break
        sleep_fn(poll_interval_s)

    return batch


_NAV_CSS = """
  .nav-sections { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .nav-group {
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    padding: 5px 8px; border-radius: 12px; border: 1px solid var(--border);
    background: rgba(25, 31, 46, 0.72);
  }
  .nav-group-label {
    font-size: 0.68rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); padding: 0 7px 0 4px; border-right: 1px solid var(--border);
  }
  .nav-group.stage-discovery .nav-group-label { color: var(--accent); }
  .nav-group.stage-investigation .nav-group-label { color: var(--teal); }
  .nav-group a {
    padding: 6px 11px; border-radius: 8px; font-weight: 600; font-size: 0.84rem;
    border: 1px solid transparent; background: transparent; color: var(--muted);
    text-decoration: none;
  }
  .nav-group a:hover { color: var(--text); text-decoration: none; border-color: var(--border); background: var(--panel-2); }
  .nav-group.stage-discovery a.active {
    background: var(--amber-bg); border-color: var(--accent); color: var(--accent);
  }
  .nav-group.stage-investigation a.active {
    background: var(--teal-bg); border-color: var(--teal); color: var(--teal);
  }
"""


def render_top_nav(active_path: str) -> str:
    """Render the shared two-section top navigation (Discovery vs Investigation)."""
    def _link(href: str, label: str, elem_id: str = "") -> str:
        cls = ' class="active"' if active_path == href else ""
        id_attr = f' id="{elem_id}"' if elem_id else ""
        return f'<a href="{href}"{id_attr}{cls}>{label}</a>'

    discovery_links = "".join(
        [
            _link("/discovery", "1. Discovery Dashboard"),
            _link("/field-news", "2. Field News", "tracesNavLink"),
            _link("/reports", "3. Scouting Reports", "reportsNavLink"),
        ]
    )
    investigation_links = "".join(
        [
            _link("/investigate", "4. Investigator Desk"),
            _link("/", "5. Vocal Studio"),
        ]
    )
    return (
        '<nav class="nav-sections" aria-label="Simon Pipeline Navigation">'
        '<div class="nav-group stage-discovery">'
        '<span class="nav-group-label">Discovery</span>'
        f"{discovery_links}"
        "</div>"
        '<div class="nav-group stage-investigation">'
        '<span class="nav-group-label">Investigation</span>'
        f"{investigation_links}"
        "</div>"
        "</nav>"
    )


_SHARED_CSS = (
    """
  :root {
    --bg: #0b0d12; --panel: #131722; --panel-2: #191f2e; --border: #262f45;
    --text: #eef2ff; --muted: #9aa5c4; --accent: #f59e0b; --accent-hover: #fbbf24;
    --teal: #2dd4bf; --warn: #fb7185; --blue: #60a5fa;
    --amber-bg: rgba(245, 158, 11, 0.13); --teal-bg: rgba(45, 212, 191, 0.12);
    --warn-bg: rgba(251, 113, 133, 0.14); --blue-bg: rgba(96, 165, 250, 0.14);
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; color: var(--text); font-family: var(--sans); line-height: 1.5;
    background: radial-gradient(circle at top right, #172036 0%, var(--bg) 52%);
  }
  a { color: var(--teal); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .wrap { max-width: 1280px; margin: 0 auto; padding: 24px 22px 64px; }
  header {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
    gap: 16px; border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 22px;
  }
  .brand h1 { margin: 0; font-size: 1.65rem; letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }
  .brand p { margin: 5px 0 0; color: var(--muted); font-size: 0.92rem; }
  .nav { display: flex; gap: 8px; flex-wrap: wrap; }
  .nav a {
    padding: 8px 14px; border-radius: 10px; font-weight: 600; font-size: 0.88rem;
    border: 1px solid var(--border); background: var(--panel-2); color: var(--muted);
  }
  .nav a.active { background: var(--amber-bg); border-color: var(--accent); color: var(--accent); }
  .nav a:hover { color: var(--text); text-decoration: none; border-color: var(--accent); }
  .pill {
    display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 999px;
    font-size: 0.74rem; font-weight: 600; border: 1px solid var(--border); background: var(--panel-2); color: var(--muted);
  }
  .pill.ok { color: var(--teal); border-color: rgba(45,212,191,0.4); background: var(--teal-bg); }
  .pill.warn { color: var(--warn); border-color: rgba(251,113,133,0.4); background: var(--warn-bg); }
  .pill.amber { color: var(--accent); border-color: rgba(245,158,11,0.4); background: var(--amber-bg); }
  .pill.blue { color: var(--blue); border-color: rgba(96,165,250,0.4); background: var(--blue-bg); }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
    padding: 18px 20px; margin-bottom: 20px; box-shadow: 0 10px 28px rgba(0,0,0,0.24);
  }
  .section-head {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
    margin: 0 0 14px;
  }
  .section-head h2 { margin: 0; font-size: 1.08rem; }
  input, select, textarea {
    background: #0d1018; color: var(--text); border: 1px solid var(--border);
    border-radius: 9px; padding: 8px 11px; font-family: inherit; font-size: 0.88rem;
  }
  textarea { width: 100%; min-height: 64px; resize: vertical; }
  input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent); }
  .btn {
    background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
    border-radius: 9px; padding: 8px 14px; font-size: 0.85rem; font-weight: 600; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px;
  }
  .btn:hover { border-color: var(--accent); text-decoration: none; }
  .btn.primary {
    background: var(--accent); color: #111318; border-color: var(--accent); font-weight: 800; padding: 10px 18px;
  }
  .btn.primary:hover { background: var(--accent-hover); }
  .btn:disabled { opacity: 0.55; cursor: wait; }
  .banner { padding: 10px 14px; border-radius: 10px; margin-bottom: 16px; font-size: 0.88rem; display: none; }
  .banner.info { display: block; background: var(--amber-bg); border: 1px solid var(--accent); color: #fde68a; }
  .banner.err { display: block; background: var(--warn-bg); border: 1px solid var(--warn); color: #fecdd3; }
  .source-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(265px, 1fr)); gap: 10px;
    max-height: 360px; overflow-y: auto; padding-right: 4px;
  }
  .source-item {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 11px;
    padding: 11px 13px; cursor: pointer; transition: border-color 0.12s ease, background 0.12s ease;
  }
  .source-item:hover { border-color: var(--muted); }
  .source-item.selected { border-color: var(--accent); background: rgba(245, 158, 11, 0.09); }
  .source-title { font-weight: 700; font-size: 0.9rem; margin-bottom: 4px; display: flex; justify-content: space-between; gap: 6px; }
  .source-why { font-size: 0.8rem; color: var(--muted); margin-top: 6px; }
  .worker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
  .worker-card {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 12px; padding: 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .lead-box {
    background: #0d1018; border: 1px solid var(--border); border-radius: 9px; padding: 10px 12px;
  }
  .mono { font-family: var(--mono); font-size: 0.78rem; color: var(--muted); }
  pre.json-view {
    background: #090b10; border: 1px solid var(--border); border-radius: 9px; padding: 12px;
    overflow-x: auto; font-family: var(--mono); font-size: 0.76rem; color: #cbd5e1; max-height: 280px;
  }
  .step-row {
    background: #0d1018; border-left: 3px solid var(--accent); border-radius: 6px;
    padding: 8px 11px; margin-bottom: 8px; font-size: 0.84rem;
  }
  .kv-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(175px, 1fr)); gap: 8px;
  }
  .kv-cell {
    background: #0d1018; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  }
  .kv-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 700; }
  .kv-val { font-size: 0.86rem; font-weight: 600; margin-top: 2px; word-break: break-word; }
"""
    + _NAV_CSS
)


DISCOVERY_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · Stage 1 Discovery &amp; Source Orchestrator</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill amber">1. Discovery Dashboard</span></h1>
        <p>Decide what you want to scout: set your brief, pick active sources, dispatch scouts, and follow their live progress in <strong>Field News</strong>.</p>
      </div>
      {render_top_nav("/discovery")}
    </header>

    <div id="banner" class="banner"></div>

    <section class="card">
      <div class="section-head">
        <h2>1. Select Discovery Sources <span id="selectedBadge" class="pill amber">0 selected</span></h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <select id="channelFilter"><option value="">All channels</option></select>
          <select id="cityFilter"><option value="">All locations</option></select>
          <select id="tierFilter"><option value="">All tiers</option></select>
          <button class="btn" type="button" id="selectQuickBtn">Quick Pick: 3 NYC Active</button>
          <button class="btn" type="button" id="clearSelBtn">Clear</button>
        </div>
      </div>
      <div id="sourceGrid" class="source-grid"></div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>2. Orchestrate Discovery Fleet</h2>
        <span id="agentIdBadge" class="pill blue">simon-discovery-scout</span>
      </div>
      <label for="briefInput" style="display:block; font-weight:600; font-size:0.86rem; margin-bottom:6px;">Search Brief</label>
      <textarea id="briefInput">{DEFAULT_DISCOVERY_BRIEF}</textarea>
      <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; margin-top:14px;">
        <div style="display:flex; flex-wrap:wrap; gap:14px; align-items:center;">
          <label style="font-size:0.86rem;">
            Discovery Agents:
            <input type="number" id="agentCountInput" min="1" max="10" value="3" style="width:68px; margin-left:6px;" />
          </label>
          <label style="font-size:0.86rem;">
            Leads / Agent (N):
            <input type="number" id="leadsPerAgentInput" min="1" max="10" value="2" style="width:68px; margin-left:6px;" />
          </label>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.86rem; cursor:pointer;">
            <input type="checkbox" id="liveToggle" />
            <span>Dispatch Live Managed Agents</span>
          </label>
        </div>
        <div style="display:flex; gap:10px; align-items:center;">
          <button id="dispatchBtn" class="btn primary" type="button">Send Discovery Agents</button>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>3. Per-Agent Contract Outputs (<code>DiscoveryHandoff v1.0.0</code>)</h2>
        <div style="display:flex; gap:8px; align-items:center;">
          <span id="batchStatusBadge" class="pill">No batch dispatched yet</span>
          <a id="openTracesBtn" class="btn" href="/traces" style="display:none;">Track Live Traces →</a>
        </div>
      </div>
      <div id="outputsContainer" class="worker-grid">
        <div class="mono">Select sources above and click <strong>Send Discovery Agents</strong> to see each agent's contract output here.</div>
      </div>
    </section>
  </div>

  <script>
    let allSources = [];
    const selectedIds = new Set();
    let activeBatchId = null;
    let pollTimer = null;

    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
    function showBanner(msg, kind) {{
      const b = el('banner');
      if (!msg) {{ b.style.display = 'none'; return; }}
      b.textContent = msg; b.className = 'banner ' + (kind || 'info'); b.style.display = 'block';
    }}

    function renderSources() {{
      const ch = el('channelFilter').value;
      const city = el('cityFilter').value;
      const tier = el('tierFilter').value;
      const filtered = allSources.filter((s) => {{
        const sCity = (s.location && s.location.city) || 'Global';
        if (ch && s.source_channel !== ch) return false;
        if (city && sCity !== city) return false;
        if (tier && s.career_tier !== tier) return false;
        return true;
      }});
      el('sourceGrid').innerHTML = filtered.map((s) => {{
        const isSel = selectedIds.has(s.source_id);
        const sCity = (s.location && s.location.city) || 'Global';
        const statusCls = s.status === 'active' ? 'ok' : 'warn';
        return `
          <div class="source-item ${{isSel ? 'selected' : ''}}" data-id="${{esc(s.source_id)}}">
            <div class="source-title">
              <span>${{isSel ? '☑ ' : '☐ '}}${{esc(s.name)}}</span>
              <span class="pill ${{statusCls}}">${{esc(s.status)}}</span>
            </div>
            <div style="display:flex; gap:5px; flex-wrap:wrap;">
              <span class="pill blue">${{esc(s.source_channel)}}</span>
              <span class="pill">${{esc(sCity)}}</span>
              <span class="pill">${{esc(s.career_tier)}}</span>
            </div>
            <div class="source-why">${{esc(s.why_useful)}}</div>
          </div>`;
      }}).join('');
      el('selectedBadge').textContent = `${{selectedIds.size}} selected`;
      document.querySelectorAll('.source-item').forEach((node) => {{
        node.onclick = () => {{
          const id = node.dataset.id;
          if (selectedIds.has(id)) selectedIds.delete(id);
          else selectedIds.add(id);
          if (selectedIds.size > 0) el('agentCountInput').value = Math.min(selectedIds.size, 10);
          renderSources();
        }};
      }});
    }}

    function statusPill(status) {{
      if (status === 'completed') return '<span class="pill ok">completed</span>';
      if (status === 'in_progress' || status === 'running' || status === 'queued') return '<span class="pill amber">' + esc(status) + '</span>';
      return '<span class="pill warn">' + esc(status || 'unknown') + '</span>';
    }}

    function renderBatch(batch) {{
      if (!batch) return;
      activeBatchId = batch.batch_id;
      const workers = batch.workers || [];
      const done = workers.filter((w) => w.status === 'completed').length;
      el('batchStatusBadge').textContent = `${{batch.batch_id}} · ${{batch.mode}} · ${{done}}/${{workers.length}} completed`;
      el('openTracesBtn').href = `/traces?batch=${{encodeURIComponent(batch.batch_id)}}`;
      el('openTracesBtn').style.display = 'inline-block';
      el('tracesNavLink').href = `/field-news?batch=${{encodeURIComponent(batch.batch_id)}}`;
      if (el('reportsNavLink')) el('reportsNavLink').href = `/reports?batch=${{encodeURIComponent(batch.batch_id)}}`;

      el('outputsContainer').innerHTML = workers.map((w) => {{
        const handoff = w.output_json;
        const leads = (handoff && Array.isArray(handoff.leads)) ? handoff.leads : [];
        const contractBadge = w.contract_valid === true
          ? '<span class="pill ok">Contract v1.0.0 VALID</span>'
          : (w.contract_valid === false
              ? '<span class="pill warn">Contract Errors</span>'
              : '<span class="pill">Awaiting Output…</span>');
        const sourcesHtml = (w.assigned_sources || []).map((s) => `<span class="pill blue">${{esc(s.name)}}</span>`).join(' ');
        const leadsHtml = leads.length ? leads.map((l) => `
          <div class="lead-box">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <strong>${{esc(l.stage_name)}}</strong>
              <span class="pill ${{l.attribution_status === 'verified' ? 'ok' : 'amber'}}">${{esc(l.attribution_status || 'uncertain')}}</span>
            </div>
            <div style="font-size:0.82rem; color:var(--muted); margin:4px 0 6px;">${{esc(l.context_snippet || 'No snippet')}}</div>
            <div style="display:flex; flex-direction:column; gap:4px;">
              ${{(l.seed_sources || []).map((ss) => `<a class="mono" href="${{esc(ss.url)}}" target="_blank" rel="noopener">↗ [${{esc(ss.source_channel)}}] ${{esc(ss.url)}}</a>`).join('')}}
            </div>
          </div>`).join('') : (w.error ? `<div class="pill warn">${{esc(w.error)}}</div>` : '<div class="mono">Agent working… open Traces to inspect live steps.</div>');

        return `
          <div class="worker-card">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <strong>${{esc(w.worker_id)}}</strong>
              <div style="display:flex; gap:6px;">${{statusPill(w.status)}} ${{contractBadge}}</div>
            </div>
            <div class="mono">interaction: ${{esc(w.interaction_id || 'pending')}} · ${{w.duration_ms || 0}}ms</div>
            <div style="display:flex; gap:5px; flex-wrap:wrap;">${{sourcesHtml}}</div>
            <div style="display:flex; flex-direction:column; gap:8px;">${{leadsHtml}}</div>
            <div style="margin-top:auto; padding-top:6px; display:flex; gap:12px; flex-wrap:wrap;">
              <a href="/field-news?batch=${{encodeURIComponent(batch.batch_id)}}">Follow Field News →</a>
              <a href="/reports?batch=${{encodeURIComponent(batch.batch_id)}}">View Scouting Report →</a>
            </div>
          </div>`;
      }}).join('');

      const anyRunning = workers.some((w) => !['completed', 'failed', 'error', 'cancelled', 'timeout'].includes(w.status));
      if (anyRunning && !pollTimer) {{
        pollTimer = true;
        (async () => {{
          let lastSteps = batch.total_steps || workers.reduce((acc, w) => acc + ((w.steps || []).length), 0);
          while (pollTimer && activeBatchId === batch.batch_id) {{
            try {{
              const res = await fetch(`/api/discovery/batches/${{encodeURIComponent(activeBatchId)}}?wait=1&since_steps=${{lastSteps}}&timeout=15`);
              if (!res.ok) break;
              const updated = await res.json();
              lastSteps = updated.total_steps || (updated.workers || []).reduce((acc, w) => acc + ((w.steps || []).length), 0);
              renderBatch(updated);
              const stillRunning = (updated.workers || []).some((w) => !['completed', 'failed', 'error', 'cancelled', 'timeout'].includes(w.status));
              if (!stillRunning) {{ pollTimer = null; break; }}
            }} catch (_e) {{
              await new Promise((r) => setTimeout(r, 2000));
            }}
          }}
        }})();
      }} else if (!anyRunning) {{
        pollTimer = null;
      }}
    }}

    async function init() {{
      const res = await fetch('/api/sources');
      const data = await res.json();
      allSources = data.sources || [];
      (data.channels || []).forEach((c) => el('channelFilter').add(new Option(c, c)));
      (data.cities || []).forEach((c) => el('cityFilter').add(new Option(c, c)));
      (data.tiers || []).forEach((t) => el('tierFilter').add(new Option(t, t)));
      // Default quick selection: 3 active diverse sources
      ['yt_sofar_sounds', 'nyc_babys_all_right', 'bc_brooklyn_soul_rnb'].forEach((id) => {{
        if (allSources.some((s) => s.source_id === id)) selectedIds.add(id);
      }});
      el('agentCountInput').value = Math.max(1, selectedIds.size);
      renderSources();

      // Load most recent batch if any
      const bRes = await fetch('/api/discovery/batches');
      if (bRes.ok) {{
        const bData = await bRes.json();
        if (bData.batches && bData.batches.length) {{
          const detail = await fetch(`/api/discovery/batches/${{encodeURIComponent(bData.batches[0].batch_id)}}`);
          if (detail.ok) renderBatch(await detail.json());
        }}
      }}
    }}

    ['channelFilter', 'cityFilter', 'tierFilter'].forEach((id) => el(id).onchange = renderSources);
    el('selectQuickBtn').onclick = () => {{
      selectedIds.clear();
      allSources.filter((s) => s.status === 'active' && (s.location && s.location.city === 'New York')).slice(0, 3)
        .forEach((s) => selectedIds.add(s.source_id));
      el('agentCountInput').value = Math.max(1, selectedIds.size);
      renderSources();
    }};
    el('clearSelBtn').onclick = () => {{ selectedIds.clear(); renderSources(); }};

    el('dispatchBtn').onclick = async () => {{
      if (selectedIds.size === 0) {{ showBanner('Select at least one source first.', 'err'); return; }}
      showBanner('Dispatching discovery agents…', 'info');
      el('dispatchBtn').disabled = true;
      try {{
        const res = await fetch('/api/discovery/dispatch', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            source_ids: Array.from(selectedIds),
            brief: el('briefInput').value,
            agent_count: Number(el('agentCountInput').value || 1),
            leads_per_agent: Number(el('leadsPerAgentInput').value || 2),
            live: el('liveToggle').checked,
          }}),
        }});
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Dispatch failed');
        showBanner(`Dispatched ${{payload.agent_count}} agent(s) in ${{payload.mode}} mode (${{payload.batch_id}}).`, 'info');
        renderBatch(payload);
      }} catch (err) {{
        showBanner(err.message, 'err');
      }} finally {{
        el('dispatchBtn').disabled = false;
      }}
    }};

    init();
  </script>
</body>
</html>
"""


FIELD_NEWS_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · 2. Field News (Agents in Motion)</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill ok">2. Field News</span></h1>
        <p>Agents in motion: live human-first updates on what each scout is looking at, what they are finding, and their analysis through the process.</p>
      </div>
      {render_top_nav("/field-news")}
    </header>

    <section class="card">
      <div class="section-head">
        <h2>Live Field Dispatches</h2>
        <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
          <select id="batchSelect" style="min-width:280px;"></select>
          <button id="refreshBtn" class="btn" type="button">Refresh Now</button>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.84rem; cursor:pointer;">
            <input type="checkbox" id="autoPollToggle" checked />
            <span>Live Auto-Update</span>
          </label>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.84rem; cursor:pointer;">
            <input type="checkbox" id="showArchivedToggle" />
            <span>Show archived</span>
          </label>
          <button id="clearFieldBtn" class="btn" type="button">Clear / Start Over</button>
          <span id="livePollBadge" class="pill blue">Idle</span>
        </div>
      </div>
      <div id="batchSummary" style="font-size:0.9rem; color:var(--muted);">Loading live field news…</div>
    </section>

    <div id="fieldCards" class="worker-grid"></div>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
    let currentBatchId = new URLSearchParams(window.location.search).get('batch') || '';
    let pollTimer = null;

    function statusPill(status) {{
      if (status === 'completed') return '<span class="pill ok">completed</span>';
      if (status === 'in_motion' || status === 'starting') return '<span class="pill amber">' + esc(status.replace('_', ' ')) + '</span>';
      return '<span class="pill warn">' + esc(status || 'unknown') + '</span>';
    }}

    function phaseBadge(phase) {{
      if (phase === 'looking_at') return '<span class="pill blue">Looking At</span>';
      if (phase === 'finding') return '<span class="pill amber">Finding</span>';
      if (phase === 'analysis') return '<span class="pill ok">Analysis</span>';
      return '<span class="pill">Saved</span>';
    }}

    function renderFieldNews(reports) {{
      if (!reports || !reports.length) {{
        el('batchSummary').textContent = 'No field dispatches yet. Launch scouts from the Discovery Dashboard.';
        el('fieldCards').innerHTML = '';
        return;
      }}
      const activeCount = reports.filter((r) => r.status === 'in_motion' || r.status === 'starting').length;
      const doneCount = reports.filter((r) => r.status === 'completed').length;
      const totalFindings = reports.reduce((acc, r) => acc + ((r.findings || []).length), 0);
      el('batchSummary').innerHTML = `Showing <strong>${{reports.length}}</strong> scout(s) · <strong>${{activeCount}}</strong> in motion · <strong>${{doneCount}}</strong> completed · <strong>${{totalFindings}}</strong> finding(s) logged · Brief: "${{esc(reports[0].brief || '')}}"`;

      el('fieldCards').innerHTML = reports.map((r) => {{
        const sourcesHtml = (r.assigned_sources || []).map((s) => `<span class="pill blue">${{esc(s.name)}}</span>`).join('');
        const steps = r.steps || [];
        const stepsHtml = steps.length ? steps.map((st) => `
          <div class="step-row">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:4px;">
              <strong>${{esc(st.step_number)}}. ${{esc(st.title)}}</strong>
              ${{phaseBadge(st.phase)}}
            </div>
            ${{st.looking_at ? `<div style="font-size:0.82rem;"><strong>Looking at:</strong> ${{esc(st.looking_at)}}</div>` : ''}}
            ${{st.finding ? `<div style="font-size:0.82rem; margin-top:2px;"><strong>Finding:</strong> ${{esc(st.finding)}}</div>` : ''}}
            ${{st.analysis ? `<div style="font-size:0.82rem; color:var(--muted); margin-top:2px;"><strong>Analysis:</strong> ${{esc(st.analysis)}}</div>` : ''}}
          </div>`).join('') : '<div style="color:var(--muted); font-size:0.84rem;">Scout is opening assigned sources…</div>';

        const findings = r.findings || [];
        const findingsPreview = findings.length ? `
          <div style="display:flex; flex-direction:column; gap:6px;">
            <div style="font-size:0.76rem; font-weight:700; text-transform:uppercase; color:var(--muted);">Live Findings (${{findings.length}})</div>
            ${{findings.map((f) => `
              <div class="lead-box">
                <div style="display:flex; justify-content:space-between; gap:8px; align-items:center;">
                  <strong>${{esc(f.title)}}</strong>
                  ${{f.source_name ? `<span class="pill">${{esc(f.source_name)}}</span>` : ''}}
                </div>
                <div style="font-size:0.82rem; color:var(--muted); margin-top:3px;">${{esc(f.summary)}}</div>
                ${{f.url ? `<div style="margin-top:4px; font-size:0.8rem;"><a href="${{esc(f.url)}}" target="_blank" rel="noopener">Open source link ↗</a></div>` : ''}}
              </div>`).join('')}}
          </div>` : '';

        return `
          <div class="worker-card" id="${{esc(r.report_id)}}">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <strong>${{esc(r.agent_name)}}</strong>
              ${{statusPill(r.status)}}
            </div>
            <div style="font-size:0.9rem; font-weight:600;">${{esc(r.headline || '')}}</div>
            ${{r.current_focus ? `<div style="font-size:0.82rem; color:var(--accent);">Current focus: ${{esc(r.current_focus)}}</div>` : ''}}
            <div style="display:flex; gap:6px; flex-wrap:wrap;">${{sourcesHtml}}</div>
            <div>
              <div style="font-size:0.76rem; font-weight:700; text-transform:uppercase; color:var(--muted); margin-bottom:6px;">Process &amp; Analysis (${{steps.length}})</div>
              ${{stepsHtml}}
            </div>
            ${{findingsPreview}}
            <div style="margin-top:auto; padding-top:8px; border-top:1px solid var(--border);">
              <a href="/reports?report=${{encodeURIComponent(r.report_id)}}">Open Full Scouting Report →</a>
            </div>
          </div>`;
      }}).join('');
    }}

    async function loadFieldNews() {{
      if (currentBatchId) {{
        // Trigger a gentle live refresh on the batch if it has active scouts
        await fetch(`/api/discovery/batches/${{encodeURIComponent(currentBatchId)}}`).catch(() => null);
      }}
      const qs = new URLSearchParams();
      if (currentBatchId) qs.set('batch_id', currentBatchId);
      if (el('showArchivedToggle') && el('showArchivedToggle').checked) qs.set('include_archived', '1');
      const queryStr = qs.toString() ? `?${{qs.toString()}}` : '';
      const res = await fetch(`/api/field-news${{queryStr}}`);
      if (!res.ok) return;
      const data = await res.json();
      const reports = data.reports || [];
      renderFieldNews(reports);
      const anyActive = reports.some((r) => r.status === 'in_motion' || r.status === 'starting');
      el('livePollBadge').textContent = anyActive ? 'Scouts in motion…' : 'Up to date';
      if (el('reportsNavLink') && currentBatchId) {{
        el('reportsNavLink').href = `/reports?batch=${{encodeURIComponent(currentBatchId)}}`;
      }}
    }}

    async function loadBatches() {{
      const res = await fetch('/api/discovery/batches');
      const data = await res.json();
      const batches = data.batches || [];
      const sel = el('batchSelect');
      sel.innerHTML = '';
      sel.add(new Option('All recent field dispatches', ''));
      batches.forEach((b) => {{
        const label = `${{b.search_brief ? b.search_brief.slice(0, 42) : b.batch_id}} (${{b.completed}}/${{b.agent_count}} done · ${{b.total_leads}} leads)`;
        sel.add(new Option(label, b.batch_id));
      }});
      if (currentBatchId && batches.some((b) => b.batch_id === currentBatchId)) {{
        sel.value = currentBatchId;
      }} else if (batches.length) {{
        currentBatchId = batches[0].batch_id;
        sel.value = currentBatchId;
      }}
      await loadFieldNews();
    }}

    function resetPolling() {{
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
      if (el('autoPollToggle').checked) {{
        pollTimer = setInterval(loadFieldNews, 4000);
      }} else {{
        el('livePollBadge').textContent = 'Paused';
      }}
    }}

    el('batchSelect').onchange = async () => {{ currentBatchId = el('batchSelect').value; await loadFieldNews(); }};
    el('refreshBtn').onclick = loadFieldNews;
    el('autoPollToggle').onchange = resetPolling;
    el('showArchivedToggle').onchange = loadFieldNews;
    el('clearFieldBtn').onclick = async () => {{
      const scopeLabel = currentBatchId ? 'this batch' : 'all active field dispatches';
      if (!confirm(`Archive ${{scopeLabel}} to start fresh? (You can restore them anytime via "Show archived".)`)) return;
      const payload = currentBatchId ? {{ batch_id: currentBatchId, archived: true }} : {{ archived: true }};
      await fetch('/api/reports/archive', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      await loadFieldNews();
    }};

    loadBatches().then(resetPolling);
  </script>
</body>
</html>
"""

TRACES_HTML = FIELD_NEWS_HTML


REPORTS_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · 3. Scouting Reports</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill blue">3. Scouting Reports</span></h1>
        <p>Human-first scouting reports with verified findings, process summaries, and stored agent outputs ready for review.</p>
      </div>
      {render_top_nav("/reports")}
    </header>

    <section class="card">
      <div class="section-head">
        <h2>Stored Scouting Reports</h2>
        <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
          <select id="statusFilter">
            <option value="">All statuses</option>
            <option value="completed">Completed</option>
            <option value="in_motion">In motion</option>
            <option value="blocked">Blocked</option>
          </select>
          <button id="refreshReportsBtn" class="btn" type="button">Refresh Reports</button>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.84rem; cursor:pointer;">
            <input type="checkbox" id="showArchivedReportsToggle" />
            <span>Show archived</span>
          </label>
          <button id="clearReportsBtn" class="btn" type="button">Clear / Start Over</button>
        </div>
      </div>
      <div id="reportsMeta" style="font-size:0.9rem; color:var(--muted);">Loading stored scouting reports…</div>
    </section>

    <div id="reportsList" style="display:flex; flex-direction:column; gap:18px;"></div>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
    const params = new URLSearchParams(window.location.search);
    const filterBatchId = params.get('batch') || '';
    const focusReportId = params.get('report') || '';

    function statusPill(status) {{
      if (status === 'completed') return '<span class="pill ok">completed</span>';
      if (status === 'in_motion' || status === 'starting') return '<span class="pill amber">' + esc(status.replace('_', ' ')) + '</span>';
      return '<span class="pill warn">' + esc(status || 'unknown') + '</span>';
    }}

    function renderReports(reports) {{
      if (!reports.length) {{
        el('reportsMeta').textContent = 'No scouting reports saved yet. Dispatch a discovery run from the Discovery Dashboard.';
        el('reportsList').innerHTML = '';
        return;
      }}
      const totalFindings = reports.reduce((acc, r) => acc + ((r.findings || []).length), 0);
      el('reportsMeta').innerHTML = `<strong>${{reports.length}}</strong> stored report(s) · <strong>${{totalFindings}}</strong> total finding(s)`;

      el('reportsList').innerHTML = reports.map((r) => {{
        const findings = r.findings || [];
        const steps = r.steps || [];
        const sourcesHtml = (r.assigned_sources || []).map((s) => `<span class="pill blue">${{esc(s.name)}}</span>`).join('');
        const findingsHtml = findings.length ? `
          <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:12px;">
            ${{findings.map((f) => `
              <div class="lead-box">
                <div style="display:flex; justify-content:space-between; gap:8px; align-items:center;">
                  <strong>${{esc(f.title)}}</strong>
                  ${{f.attribution_status ? `<span class="pill ok">${{esc(f.attribution_status)}}</span>` : ''}}
                </div>
                <div style="font-size:0.84rem; color:var(--muted); margin-top:4px;">${{esc(f.summary)}}</div>
                <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; align-items:center; justify-content:space-between;">
                  <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                    ${{f.source_name ? `<span class="pill">${{esc(f.source_name)}}</span>` : ''}}
                    ${{f.source_channel ? `<span class="pill">${{esc(f.source_channel)}}</span>` : ''}}
                    ${{f.url ? `<a href="${{esc(f.url)}}" target="_blank" rel="noopener" style="font-size:0.82rem;">Open source ↗</a>` : ''}}
                  </div>
                  <a class="btn" href="/investigate?subject=${{encodeURIComponent(f.title || '')}}${{f.lead_id ? '&lead=' + encodeURIComponent(f.lead_id) : ''}}" style="font-size:0.78rem; padding:5px 10px; color:var(--teal); border-color:rgba(45,212,191,0.4);">Investigate →</a>
                </div>
              </div>`).join('')}}
          </div>` : '<div style="color:var(--muted); font-size:0.86rem;">No verified findings recorded in this report yet.</div>';

        const processHtml = steps.map((st) => `
          <div class="step-row">
            <strong>${{esc(st.step_number)}}. ${{esc(st.title)}}</strong>
            ${{st.looking_at ? `<div style="font-size:0.82rem;"><strong>Looking at:</strong> ${{esc(st.looking_at)}}</div>` : ''}}
            ${{st.finding ? `<div style="font-size:0.82rem;"><strong>Finding:</strong> ${{esc(st.finding)}}</div>` : ''}}
            ${{st.analysis ? `<div style="font-size:0.82rem; color:var(--muted);"><strong>Analysis:</strong> ${{esc(st.analysis)}}</div>` : ''}}
          </div>`).join('');

        const outputHtml = r.output
          ? `<details style="margin-top:10px;">
               <summary style="cursor:pointer; font-size:0.85rem; color:var(--teal); font-weight:600;">View Stored Output Contract</summary>
               <pre class="json-view">${{esc(JSON.stringify(r.output, null, 2))}}</pre>
             </details>`
          : '<div style="font-size:0.82rem; color:var(--muted); margin-top:8px;">Final output pending completion…</div>';

        const highlightStyle = focusReportId && r.report_id === focusReportId ? 'border-color: var(--accent);' : '';
        return `
          <section class="card" id="${{esc(r.report_id)}}" style="${{highlightStyle}}">
            <div class="section-head">
              <div>
                <h2 style="margin:0;">${{esc(r.agent_name)}} <span class="pill">${{esc(r.stage)}}</span> ${{statusPill(r.status)}} ${{r.archived ? '<span class="pill warn">archived</span>' : ''}}</h2>
                <div style="font-size:0.95rem; font-weight:600; margin-top:6px;">${{esc(r.headline || '')}}</div>
                <div style="font-size:0.84rem; color:var(--muted); margin-top:2px;">Brief: ${{esc(r.brief || '')}}</div>
              </div>
              <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                ${{sourcesHtml}}
                ${{r.archived ? `<button class="btn" type="button" onclick="restoreReport('${{esc(r.report_id)}}')">Restore</button>` : ''}}
              </div>
            </div>
            <div style="margin-bottom:14px;">
              <div style="font-size:0.78rem; font-weight:700; text-transform:uppercase; color:var(--muted); margin-bottom:8px;">Findings (${{findings.length}})</div>
              ${{findingsHtml}}
            </div>
            <details>
              <summary style="cursor:pointer; font-size:0.85rem; color:var(--accent); font-weight:600;">Process &amp; Analysis Trail (${{steps.length}} steps)</summary>
              <div style="margin-top:10px;">${{processHtml}}</div>
            </details>
            ${{outputHtml}}
          </section>`;
      }}).join('');
    }}

    async function restoreReport(reportId) {{
      await fetch('/api/reports/archive', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ report_ids: [reportId], archived: false }}),
      }});
      await loadReports();
    }}

    async function loadReports() {{
      const qs = new URLSearchParams();
      if (filterBatchId) qs.set('batch_id', filterBatchId);
      const st = el('statusFilter').value;
      if (st) qs.set('status', st);
      if (el('showArchivedReportsToggle') && el('showArchivedReportsToggle').checked) qs.set('include_archived', '1');
      const url = '/api/reports' + (qs.toString() ? `?${{qs.toString()}}` : '');
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      renderReports(data.reports || []);
    }}

    el('statusFilter').onchange = loadReports;
    el('refreshReportsBtn').onclick = loadReports;
    el('showArchivedReportsToggle').onchange = loadReports;
    el('clearReportsBtn').onclick = async () => {{
      const scopeLabel = filterBatchId ? 'this batch' : 'all active scouting reports';
      if (!confirm(`Archive ${{scopeLabel}} to start fresh? (Historical runs remain recoverable via "Show archived".)`)) return;
      const payload = filterBatchId ? {{ batch_id: filterBatchId, archived: true }} : {{ archived: true }};
      await fetch('/api/reports/archive', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      await loadReports();
    }};
    loadReports();
  </script>
</body>
</html>
"""


INVESTIGATE_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · 4. Investigator Desk (Stage 2)</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill ok">4. Investigator Desk</span></h1>
        <p>Stage 2 Investigation: inspect verified leads from Discovery, follow live Investigator Field News, and review objective factual dossiers (zero ranking or scoring).</p>
      </div>
      {render_top_nav("/investigate")}
    </header>

    <div id="focusBanner" class="banner"></div>

    <section class="card">
      <div class="section-head">
        <h2>1. Verified Leads Ready for Stage 2 Investigation <span id="leadsCountBadge" class="pill blue">0 leads</span></h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <input id="leadSearchInput" type="text" placeholder="Filter by artist or lead ID…" style="min-width:220px;" />
          <button id="clearFocusBtn" class="btn" type="button" style="display:none;">Show All</button>
          <button id="refreshDeskBtn" class="btn" type="button">Refresh Desk</button>
        </div>
      </div>
      <div id="leadsGrid" class="worker-grid">
        <div class="mono">Loading verified leads from Discovery…</div>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>2. Stage 2 Investigator Field News <span id="invNewsCountBadge" class="pill amber">0 dispatches</span></h2>
        <span class="pill">stage=investigator</span>
      </div>
      <div id="invFieldNews" class="worker-grid">
        <div class="mono">Loading Stage 2 investigator field news…</div>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>3. Stored Investigator Dossiers <span id="dossiersCountBadge" class="pill ok">0 dossiers</span></h2>
        <span class="pill ok">Objective Facts Only · Unranked</span>
      </div>
      <div id="dossiersList" style="display:flex; flex-direction:column; gap:16px;">
        <div class="mono">Loading stored investigator dossiers…</div>
      </div>
    </section>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
    const params = new URLSearchParams(window.location.search);
    let focusLeadId = params.get('lead') || '';
    let focusSubject = params.get('subject') || '';
    let allLeads = [];
    let allDossiers = [];

    function statusPill(status) {{
      if (status === 'completed' || status === 'verified') return '<span class="pill ok">' + esc(status) + '</span>';
      if (status === 'in_motion' || status === 'starting' || status === 'uncertain') return '<span class="pill amber">' + esc(status.replace('_', ' ')) + '</span>';
      return '<span class="pill warn">' + esc(status || 'unknown') + '</span>';
    }}

    function phaseBadge(phase) {{
      if (phase === 'looking_at') return '<span class="pill blue">Looking At</span>';
      if (phase === 'finding') return '<span class="pill amber">Finding</span>';
      if (phase === 'analysis') return '<span class="pill ok">Analysis</span>';
      return '<span class="pill">Saved</span>';
    }}

    function matchesFocus(itemName, itemLeadId) {{
      const q = (el('leadSearchInput').value || '').trim().toLowerCase();
      if (q) {{
        const hay = `${{itemName || ''}} ${{itemLeadId || ''}}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }}
      if (focusLeadId && itemLeadId && itemLeadId !== focusLeadId) {{
        if (!focusSubject || (itemName || '').toLowerCase() !== focusSubject.toLowerCase()) return false;
      }} else if (focusSubject && !focusLeadId) {{
        if ((itemName || '').toLowerCase() !== focusSubject.toLowerCase()) return false;
      }}
      return true;
    }}

    function updateFocusBanner() {{
      const b = el('focusBanner');
      if (focusLeadId || focusSubject) {{
        const label = focusSubject || focusLeadId;
        b.textContent = `Focused on lead: ${{label}}${{focusLeadId ? ' (' + focusLeadId + ')' : ''}}`;
        b.className = 'banner info';
        b.style.display = 'block';
        el('clearFocusBtn').style.display = 'inline-flex';
      }} else {{
        b.style.display = 'none';
        el('clearFocusBtn').style.display = 'none';
      }}
    }}

    function renderLeads() {{
      const dossierLeadIds = new Set(allDossiers.map((d) => String(d.lead_id || '').toLowerCase()));
      const dossierNames = new Set(allDossiers.map((d) => String((d.identity_and_contact && d.identity_and_contact.stage_name) || d.stage_name || '').toLowerCase()));
      const visible = allLeads.filter((l) => matchesFocus(l.stage_name, l.lead_id));
      el('leadsCountBadge').textContent = `${{visible.length}} lead(s)`;
      if (!visible.length) {{
        el('leadsGrid').innerHTML = '<div class="mono">No matching leads found yet. Run Stage 1 Discovery or clear the filter.</div>';
        return;
      }}
      el('leadsGrid').innerHTML = visible.map((l) => {{
        const hasDossier = dossierLeadIds.has(String(l.lead_id || '').toLowerCase())
          || dossierNames.has(String(l.stage_name || '').toLowerCase());
        const seeds = l.seed_sources || [];
        return `
          <div class="worker-card">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <strong>${{esc(l.stage_name || l.lead_id)}}</strong>
              <div style="display:flex; gap:6px; flex-wrap:wrap;">
                ${{statusPill(l.attribution_status || 'uncertain')}}
                ${{hasDossier ? '<span class="pill ok">Dossier Stored</span>' : '<span class="pill blue">Ready for Stage 2</span>'}}
              </div>
            </div>
            <div class="mono">lead_id: ${{esc(l.lead_id || '—')}}</div>
            <div style="font-size:0.84rem; color:var(--muted);">${{esc(l.context_snippet || 'Discovered in Stage 1.')}}</div>
            <div style="display:flex; flex-direction:column; gap:4px;">
              ${{seeds.map((ss) => `<a class="mono" href="${{esc(ss.url)}}" target="_blank" rel="noopener">↗ [${{esc(ss.source_channel || 'source')}}] ${{esc(ss.url)}}</a>`).join('')}}
            </div>
            <div style="margin-top:auto; padding-top:6px; display:flex; justify-content:space-between; align-items:center;">
              <button class="btn" type="button" data-focus-lead="${{esc(l.lead_id || '')}}" data-focus-name="${{esc(l.stage_name || '')}}" style="font-size:0.78rem; padding:5px 10px;">Focus Lead &amp; Dossier</button>
              <a href="/reports" style="font-size:0.8rem;">View Discovery Report →</a>
            </div>
          </div>`;
      }}).join('');

      document.querySelectorAll('[data-focus-lead]').forEach((btn) => {{
        btn.onclick = () => {{
          focusLeadId = btn.dataset.focusLead || '';
          focusSubject = btn.dataset.focusName || '';
          updateFocusBanner();
          renderLeads();
          renderDossiers();
        }};
      }});
    }}

    function renderInvestigatorFieldNews(reports) {{
      el('invNewsCountBadge').textContent = `${{reports.length}} dispatch(es)`;
      if (!reports.length) {{
        el('invFieldNews').innerHTML = '<div class="mono">No Stage 2 investigator field dispatches yet. Dispatches posted with stage="investigator" appear here automatically.</div>';
        return;
      }}
      el('invFieldNews').innerHTML = reports.map((r) => {{
        const steps = r.steps || [];
        const stepsHtml = steps.length ? steps.map((st) => `
          <div class="step-row">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:4px;">
              <strong>${{esc(st.step_number)}}. ${{esc(st.title)}}</strong>
              ${{phaseBadge(st.phase)}}
            </div>
            ${{st.looking_at ? `<div style="font-size:0.82rem;"><strong>Looking at:</strong> ${{esc(st.looking_at)}}</div>` : ''}}
            ${{st.finding ? `<div style="font-size:0.82rem; margin-top:2px;"><strong>Finding:</strong> ${{esc(st.finding)}}</div>` : ''}}
            ${{st.analysis ? `<div style="font-size:0.82rem; color:var(--muted); margin-top:2px;"><strong>Analysis:</strong> ${{esc(st.analysis)}}</div>` : ''}}
          </div>`).join('') : '<div class="mono">Investigator starting…</div>';

        return `
          <div class="worker-card">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <strong>${{esc(r.agent_name)}}</strong>
              ${{statusPill(r.status)}}
            </div>
            <div style="font-size:0.9rem; font-weight:600;">${{esc(r.headline || '')}}</div>
            ${{r.current_focus ? `<div style="font-size:0.82rem; color:var(--teal);">Current focus: ${{esc(r.current_focus)}}</div>` : ''}}
            <div>${{stepsHtml}}</div>
          </div>`;
      }}).join('');
    }}

    function renderDossiers() {{
      const visible = allDossiers.filter((d) => {{
        const idObj = d.identity_and_contact || {{}};
        const name = idObj.stage_name || d.stage_name || d.lead_id || '';
        return matchesFocus(name, d.lead_id);
      }});
      el('dossiersCountBadge').textContent = `${{visible.length}} dossier(s)`;
      if (!visible.length) {{
        el('dossiersList').innerHTML = '<div class="mono">No stored investigator dossiers match this view yet.</div>';
        return;
      }}
      el('dossiersList').innerHTML = visible.map((d) => {{
        const idObj = d.identity_and_contact || {{}};
        const srcObj = d.source_and_media_queue || {{}};
        const fpObj = d.public_footprint || {{}};
        const reach = fpObj.public_reach || {{}};
        const cfObj = d.comment_forensics || {{}};
        const intents = cfObj.comment_intent_counts || {{}};
        const liveObj = d.live_history_and_credits || {{}};
        const team = liveObj.public_team_mentions || {{}};
        const stageName = idObj.stage_name || d.stage_name || d.lead_id || 'Unnamed Subject';
        const city = [idObj.home_neighborhood, idObj.home_city].filter(Boolean).join(', ') || d.home_city || '—';
        const projectType = idObj.project_type || d.project_type || 'unknown';
        const contactRoute = idObj.contact_route_type || (idObj.has_public_business_contact ? 'public_contact' : 'none');
        const regime = fpObj.footprint_regime || d.footprint_regime || 'unknown';
        const platformUrls = idObj.platform_urls || {{}};
        const platformLinks = Object.entries(platformUrls)
          .filter(([, url]) => Boolean(url))
          .map(([k, url]) => `<a class="pill blue" href="${{esc(url)}}" target="_blank" rel="noopener">${{esc(k)}} ↗</a>`)
          .join('');
        const mediaLinks = (srcObj.media_links || []).map((m) => `
          <div class="lead-box" style="padding:8px 10px;">
            <div style="display:flex; justify-content:space-between; gap:8px;">
              <strong>${{esc(m.title || m.url)}}</strong>
              <span class="pill ${{m.oembed_live_embeddable ? 'ok' : ''}}">${{m.oembed_live_embeddable ? 'embeddable' : 'link'}}</span>
            </div>
            <a class="mono" href="${{esc(m.url)}}" target="_blank" rel="noopener">${{esc(m.url)}}</a>
          </div>`).join('');
        const shows = (liveObj.show_history || []).concat(liveObj.upcoming_shows || []);
        const showsHtml = shows.length ? shows.slice(0, 6).map((sh) => `
          <span class="pill">${{esc(sh.venue || 'Venue')}} · ${{esc(sh.city || '')}} (${{esc(sh.date || '')}})</span>`).join(' ') : '<span class="mono">No public show dates logged.</span>';

        return `
          <div class="worker-card" style="background:var(--panel-2);">
            <div class="section-head" style="margin-bottom:4px;">
              <div>
                <strong style="font-size:1.08rem;">${{esc(stageName)}}</strong>
                <span class="pill ok" style="margin-left:8px;">${{esc(projectType)}}</span>
                <span class="pill blue">${{esc(regime)}}</span>
              </div>
              <span class="mono">lead_id: ${{esc(d.lead_id || '—')}}</span>
            </div>
            ${{srcObj.bio_text ? `<div style="font-size:0.86rem; color:var(--muted);">${{esc(srcObj.bio_text)}}</div>` : ''}}
            <div class="kv-grid">
              <div class="kv-cell"><div class="kv-label">Location</div><div class="kv-val">${{esc(city)}}</div></div>
              <div class="kv-cell"><div class="kv-label">Contact Route</div><div class="kv-val">${{esc(contactRoute)}}</div></div>
              <div class="kv-cell"><div class="kv-label">YouTube Subscribers</div><div class="kv-val">${{reach.youtube_subscribers != null ? esc(reach.youtube_subscribers) : '—'}}</div></div>
              <div class="kv-cell"><div class="kv-label">Top Video Views</div><div class="kv-val">${{reach.top_video_views != null ? esc(reach.top_video_views) : '—'}}</div></div>
              <div class="kv-cell"><div class="kv-label">Comment Forensics</div><div class="kv-val">${{intents.sample_size != null ? `${{intents.sample_size}} sampled · ${{intents.release_requests || 0}} release req · ${{intents.live_show_requests || 0}} show req` : '—'}}</div></div>
              <div class="kv-cell"><div class="kv-label">Public Team</div><div class="kv-val">${{esc(team.management || team.label || team.booking_agent || 'Independent / none observed')}}</div></div>
            </div>
            ${{platformLinks ? `<div style="display:flex; gap:6px; flex-wrap:wrap;">${{platformLinks}}</div>` : ''}}
            ${{mediaLinks ? `<div style="display:flex; flex-direction:column; gap:6px;">${{mediaLinks}}</div>` : ''}}
            <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">${{showsHtml}}</div>
            <details>
              <summary style="cursor:pointer; font-size:0.84rem; color:var(--teal); font-weight:600;">Inspect Full Factual Dossier JSON</summary>
              <pre class="json-view">${{esc(JSON.stringify(d, null, 2))}}</pre>
            </details>
          </div>`;
      }}).join('');
    }}

    async function loadDesk() {{
      const [leadsRes, newsRes, dossiersRes] = await Promise.all([
        fetch('/api/leads'),
        fetch('/api/field-news?stage=investigator'),
        fetch('/api/dossiers'),
      ]);
      if (leadsRes.ok) {{
        const data = await leadsRes.json();
        allLeads = data.leads || [];
      }}
      if (dossiersRes.ok) {{
        const data = await dossiersRes.json();
        allDossiers = data.dossiers || [];
      }}
      if (newsRes.ok) {{
        const data = await newsRes.json();
        renderInvestigatorFieldNews(data.reports || []);
      }}
      updateFocusBanner();
      renderLeads();
      renderDossiers();
    }}

    el('leadSearchInput').oninput = () => {{ renderLeads(); renderDossiers(); }};
    el('clearFocusBtn').onclick = () => {{
      focusLeadId = '';
      focusSubject = '';
      el('leadSearchInput').value = '';
      updateFocusBanner();
      renderLeads();
      renderDossiers();
    }};
    el('refreshDeskBtn').onclick = loadDesk;

    loadDesk();
  </script>
</body>
</html>
"""

