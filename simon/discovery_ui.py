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
    genres = sorted(
        {
            str(g)
            for s in sources
            for g in (s.get("genre_tags") or [])
            if g and str(g) != "all"
        }
    )
    return {
        "count": len(sources),
        "channels": channels,
        "cities": cities,
        "tiers": tiers,
        "genres": genres,
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
                "title": f"Checked {src_names}",
                "looking_at": f"Checked {src_names} against your brief: {brief}",
                "finding": f"Scanned {len(assigned)} source(s) for active vocalists and public clips.",
                "analysis": "Kept only public bills with clear artist attribution.",
                "status": "done",
                "updated_at": now,
            },
            {
                "step_number": 2,
                "phase": "finding",
                "title": f"Found {len(findings)} artist(s)",
                "looking_at": f"Checked public links from {src_names}",
                "finding": f"Found {len(findings)} lead(s): {names_preview}.",
                "analysis": "Each artist has at least one public link and clear context.",
                "status": "done",
                "updated_at": now,
            },
            {
                "step_number": 3,
                "phase": "analysis",
                "title": "Checked & deduplicated leads",
                "looking_at": "Checked artist attribution, link hygiene, and unranked output.",
                "finding": (
                    "All leads passed lead handoff checks."
                    if worker.get("contract_valid")
                    else "Run finished with lead checklist notes to review."
                ),
                "analysis": (
                    "No scores or ranks added. Ready for Stage 2 investigation."
                    if worker.get("contract_valid")
                    else "; ".join(worker.get("contract_errors") or ["Review the saved lead handoff."])
                ),
                "status": "done" if worker.get("contract_valid") else "blocked",
                "updated_at": now,
            },
            {
                "step_number": 4,
                "phase": "saved",
                "title": "Scouting report & output stored",
                "looking_at": "Final lead handoff",
                "finding": f"Saved {len(findings)} lead(s) and full scouting details for review.",
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
                "title": "Collecting artists and public links",
                "looking_at": f"Checking public listings and channels across {src_names}",
                "finding": "Collecting artist names, live clip links, and venue/channel context.",
                "analysis": "Removing duplicates and checking public attribution before saving.",
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
        if not isinstance(doc, dict) or bool(doc.get("archived", False)):
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
        if not isinstance(raw, dict) or bool(raw.get("archived", False)):
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
        if isinstance(doc, dict) and not bool(doc.get("archived", False)):
            _add_lead(doc)

    for row in list_agent_documents(store, "discovery_handoffs", limit=50):
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict) or bool(doc.get("archived", False)):
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
        return {"valid": False, "errors": ["No lead handoff returned yet."], "lead_count": 0}
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
                "preview": f"Saved lead handoff with {len(leads)} unranked lead(s).",
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
    reset_previous: bool = False,
) -> Dict[str, Any]:
    """Dispatch N Stage 1 Discovery agents across selected sources and persist batch state."""
    registry = load_source_registry(store)
    by_id = {s["source_id"]: s for s in registry["sources"]}
    selected = [by_id[sid] for sid in source_ids if sid in by_id]
    if not selected:
        raise ValueError("Select at least one valid source from the Source Registry.")

    if reset_previous:
        from .demo_flow import archive_pipeline_workspace

        archive_pipeline_workspace(store)

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
    display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
    padding: 4px 7px; border-radius: 11px; border: 1px solid var(--border);
    background: var(--panel-2, var(--surface-2));
  }
  .nav-group-label {
    font-size: 0.68rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); padding: 0 7px 0 4px; border-right: 1px solid var(--border);
  }
  .nav-group.stage-discovery .nav-group-label { color: var(--accent); }
  .nav-group.stage-investigation .nav-group-label { color: var(--teal, var(--ok)); }
  .nav-group.stage-screening .nav-group-label { color: var(--purple, #7e22ce); }
  .nav-group a {
    padding: 5px 10px; border-radius: 8px; font-weight: 600; font-size: 0.8rem;
    border: 1px solid transparent; background: transparent; color: var(--muted);
    text-decoration: none; transition: all 0.14s ease;
  }
  .nav-group a:hover { color: var(--text); text-decoration: none; border-color: var(--border); background: var(--panel, var(--surface)); }
  .nav-group.stage-discovery a.active {
    background: var(--amber-bg, var(--accent-bg)); border-color: var(--accent); color: var(--accent);
  }
  .nav-group.stage-investigation a.active {
    background: var(--teal-bg, var(--ok-bg)); border-color: var(--teal, var(--ok)); color: var(--teal, var(--ok));
  }
  .nav-group.stage-screening a.active {
    background: var(--purple-bg, rgba(192, 132, 252, 0.15)); border-color: var(--purple, #7e22ce); color: var(--purple, #7e22ce);
  }
  .nav-theme-btn {
    padding: 5px 10px; border-radius: 8px; font-weight: 600; font-size: 12px;
    border: 1px solid var(--border); background: var(--panel-2, var(--surface-2));
    color: var(--text); cursor: pointer;
  }
  .nav-theme-btn:hover { border-color: var(--accent); }
  .simon-topbar {
    position: sticky; top: 0; z-index: 30;
    background: var(--panel, var(--surface));
    border-bottom: 1px solid var(--border);
    padding: 10px 20px; min-height: 56px;
  }
  .simon-topbar-inner {
    max-width: 1320px; margin: 0 auto;
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px;
  }
  .simon-brand-group { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
  .simon-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; color: inherit; }
  .simon-brand:hover { text-decoration: none; }
  .simon-brand-mark {
    width: 32px; height: 32px; border-radius: 9px;
    background: var(--accent); color: var(--accent-fg);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 15px; flex-shrink: 0;
  }
  .simon-brand-title { font-weight: 800; font-size: 15px; letter-spacing: -0.02em; line-height: 1.15; }
  .simon-brand-sub { font-size: 11px; color: var(--muted); line-height: 1.15; }
  .nav-primary-shell { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .nav-primary-tabs {
    display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap;
    background: var(--panel-2, var(--surface-2)); border: 1px solid var(--border);
    padding: 3px; border-radius: 11px;
  }
  .nav-primary-tab {
    display: inline-flex; align-items: center; justify-content: center;
    height: 32px; padding: 0 12px; border-radius: 8px;
    font-size: 12.5px; font-weight: 600; line-height: 1; white-space: nowrap;
    color: var(--muted); text-decoration: none; border: 1px solid transparent;
    transition: all 0.14s ease;
  }
  .nav-primary-tab:hover { color: var(--text); text-decoration: none; }
  .nav-primary-tab.active {
    background: var(--panel, var(--surface)); color: var(--text);
    border-color: var(--border); box-shadow: 0 1px 2px rgba(0,0,0,0.06);
  }
  .nav-tools-menu { position: relative; }
  .nav-tools-menu summary {
    list-style: none; display: inline-flex; align-items: center; height: 34px;
    padding: 0 12px; border-radius: 8px; font-size: 12.5px; font-weight: 600;
    border: 1px solid var(--border); background: var(--panel-2, var(--surface-2)); color: var(--text);
    cursor: pointer; user-select: none;
  }
  .nav-tools-menu summary::-webkit-details-marker { display: none; }
  .nav-tools-menu summary:hover { border-color: var(--accent); }
  .nav-tools-popover {
    position: absolute; right: 0; top: calc(100% + 8px); width: 320px; z-index: 60;
    background: var(--panel, var(--surface)); border: 1px solid var(--border);
    border-radius: 14px; padding: 12px; box-shadow: 0 18px 42px rgba(0,0,0,0.22);
    display: flex; flex-direction: column; gap: 8px;
  }
  .nav-tools-popover .nav-sections { flex-direction: column; align-items: stretch; gap: 8px; }
  .nav-tools-popover .nav-group { flex-direction: column; align-items: stretch; gap: 2px; padding: 8px; }
  .nav-tools-popover .nav-group-label { border-right: none; padding: 0 4px 4px; margin-bottom: 2px; border-bottom: 1px solid var(--border); }
  .nav-tools-popover .nav-group a { padding: 6px 8px; font-size: 0.8rem; }
  .nav-tools-footer {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    padding-top: 8px; border-top: 1px solid var(--border);
  }
  .page-hero {
    margin: 0 0 18px; padding-bottom: 14px; border-bottom: 1px solid var(--border);
  }
  .page-hero h1 {
    margin: 0; font-size: 1.45rem; font-weight: 800; letter-spacing: -0.02em;
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  }
  .page-hero p { margin: 5px 0 0; color: var(--muted); font-size: 0.88rem; }
  .subflow-nav {
    display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
    padding: 8px 12px; margin-bottom: 16px; border-radius: 12px;
    background: var(--panel, var(--surface)); border: 1px solid var(--border);
  }
  .subflow-label {
    font-size: 0.7rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); padding-right: 8px; border-right: 1px solid var(--border);
  }
  .subflow-steps { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; flex: 1; }
  .subflow-step {
    padding: 5px 11px; border-radius: 8px; font-size: 0.8rem; font-weight: 600;
    color: var(--muted); text-decoration: none; border: 1px solid transparent;
    transition: all 0.14s ease;
  }
  .subflow-step:hover { color: var(--text); border-color: var(--border); text-decoration: none; }
  .subflow-step.active {
    background: var(--accent-soft, rgba(217,119,6,0.12)); color: var(--accent);
    border-color: var(--accent);
  }
  .subflow-arrow { color: var(--muted); font-size: 0.8rem; user-select: none; }
  .subflow-next {
    padding: 5px 11px; border-radius: 8px; font-size: 0.8rem; font-weight: 700;
    color: var(--text); text-decoration: none; border: 1px solid var(--border);
    background: var(--panel-2, var(--surface-2));
  }
  .subflow-next:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; }
"""


def render_discovery_subnav(active_path: str) -> str:
    """Render the persistent Discovery sub-flow bar across Discovery, Field News, and Scouting Reports."""
    def _step(href: str, label: str, elem_id: str, is_active: bool) -> str:
        cls = " active" if is_active else ""
        return f'<a href="{href}" id="{elem_id}" class="subflow-step{cls}">{label}</a>'

    steps = (
        _step("/?tab=discovery", "1. Sources &amp; Dispatch", "subflowDiscoveryLink", active_path in ("/", "/discovery"))
        + '<span class="subflow-arrow" aria-hidden="true">→</span>'
        + _step("/field-news", "2. Field News", "subflowFieldNewsLink", active_path == "/field-news")
        + '<span class="subflow-arrow" aria-hidden="true">→</span>'
        + _step("/reports", "3. Scouting Reports", "subflowReportsLink", active_path == "/reports")
    )
    return (
        '<nav class="subflow-nav" aria-label="Discovery Sub-Flow">'
        '<span class="subflow-label">Discovery Flow</span>'
        f'<div class="subflow-steps">{steps}</div>'
        '<a href="/investigate" class="subflow-next">Next: Investigate →</a>'
        "</nav>"
    )


def render_top_nav(active_path: str) -> str:
    """Render the unified 4-stage Studio navigation + Tools directory across all pages."""
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
            _link("/evals", "6. Evals", "evalsNavLink"),
        ]
    )
    screening_links = "".join(
        [
            _link("/screen", "7. Screening Deck", "screenNavLink"),
            _link("/taste-profile", "8. Taste Profile", "tasteProfileNavLink"),
        ]
    )
    studio_tools_links = (
        ""
        if active_path == "/"
        else '<a href="/?tab=pipeline">Pipeline Stepper</a><a href="/?tab=lab">Agent Lab</a>'
    )
    directory_nav = (
        '<nav class="nav-sections" aria-label="Simon Pipeline Navigation">'
        '<div class="nav-group stage-discovery">'
        '<span class="nav-group-label">Discovery</span>'
        f"{discovery_links}"
        "</div>"
        '<div class="nav-group stage-investigation">'
        '<span class="nav-group-label">Investigation</span>'
        f"{investigation_links}"
        "</div>"
        '<div class="nav-group stage-screening">'
        '<span class="nav-group-label">Screening</span>'
        f"{screening_links}"
        f"{studio_tools_links}"
        "</div>"
        "</nav>"
    )

    if active_path == "/":
        return directory_nav

    def _stage(href: str, label: str, is_active: bool) -> str:
        cls = " active" if is_active else ""
        return f'<a href="{href}" class="nav-primary-tab{cls}">{label}</a>'

    primary_tabs = "".join(
        [
            _stage("/?tab=discovery", "1. Discovery", active_path in ("/discovery", "/field-news", "/reports")),
            _stage("/investigate", "2. Investigate", active_path == "/investigate"),
            _stage("/screen", "3. Screening", active_path in ("/screen", "/screening")),
            _stage("/taste-profile", "4. Taste Profile", active_path == "/taste-profile"),
            _stage("/?tab=review", "5. Talent Review", active_path == "/"),
        ]
    )
    theme_btn = (
        '<button type="button" id="simonNavThemeBtn" class="nav-theme-btn" '
        'title="Toggle Editorial Light / Studio Dark">☀ Light</button>'
        "<script>(function(){"
        "var k='simon_theme',b=document.getElementById('simonNavThemeBtn');"
        "function ap(t){document.documentElement.setAttribute('data-theme',t);"
        "try{localStorage.setItem(k,t);}catch(e){}"
        "if(b)b.textContent=t==='dark'?'☾ Studio Dark':'☀ Light';}"
        "var cur='light';try{cur=localStorage.getItem(k)||'light';}catch(e){}"
        "ap(cur);"
        "if(b)b.addEventListener('click',function(){ap((document.documentElement.getAttribute('data-theme')||'light')==='dark'?'light':'dark');});"
        "document.addEventListener('click',function(e){document.querySelectorAll('.nav-tools-menu[open]').forEach(function(m){if(!m.contains(e.target))m.removeAttribute('open');});});"
        "document.addEventListener('keydown',function(e){if(e.key==='Escape'){document.querySelectorAll('.nav-tools-menu[open]').forEach(function(m){m.removeAttribute('open');});}});"
        "})();</script>"
    )
    return (
        '<div class="nav-primary-shell">'
        f'<nav class="nav-primary-tabs" aria-label="Primary Pipeline Stages">{primary_tabs}</nav>'
        '<details class="nav-tools-menu">'
        '<summary>Tools ▾</summary>'
        f'<div class="nav-tools-popover">{directory_nav}<div class="nav-tools-footer"><span style="font-size:11px; color:var(--muted);">Theme</span>{theme_btn}</div></div>'
        "</details>"
        "</div>"
    )


def render_page_topbar(active_path: str, subtitle: str = "Studio") -> str:
    """Render the full-bleed sticky Simon topbar matching `/` across all standalone pages."""
    def _stage(href: str, label: str, is_active: bool) -> str:
        cls = " active" if is_active else ""
        return f'<a href="{href}" class="nav-primary-tab{cls}">{label}</a>'

    primary_tabs = "".join(
        [
            _stage("/?tab=discovery", "1. Discovery", active_path in ("/discovery", "/field-news", "/reports")),
            _stage("/investigate", "2. Investigate", active_path == "/investigate"),
            _stage("/screen", "3. Screening", active_path in ("/screen", "/screening")),
            _stage("/taste-profile", "4. Taste Profile", active_path == "/taste-profile"),
            _stage("/?tab=review", "5. Talent Review", active_path == "/"),
        ]
    )
    # Build Tools popover reusing render_top_nav's directory + theme toggle
    def _link(href: str, label: str, elem_id: str = "") -> str:
        cls = ' class="active"' if active_path == href else ""
        id_attr = f' id="{elem_id}"' if elem_id else ""
        return f'<a href="{href}"{id_attr}{cls}>{label}</a>'

    directory_nav = (
        '<nav class="nav-sections" aria-label="Simon Pipeline Navigation">'
        '<div class="nav-group stage-discovery">'
        '<span class="nav-group-label">Discovery</span>'
        f'{_link("/discovery", "1. Discovery Dashboard")}'
        f'{_link("/field-news", "2. Field News", "tracesNavLink")}'
        f'{_link("/reports", "3. Scouting Reports", "reportsNavLink")}'
        "</div>"
        '<div class="nav-group stage-investigation">'
        '<span class="nav-group-label">Investigation</span>'
        f'{_link("/investigate", "4. Investigator Desk")}'
        f'{_link("/", "5. Vocal Studio")}'
        f'{_link("/evals", "6. Evals", "evalsNavLink")}'
        "</div>"
        '<div class="nav-group stage-screening">'
        '<span class="nav-group-label">Screening</span>'
        f'{_link("/screen", "7. Screening Deck", "screenNavLink")}'
        f'{_link("/taste-profile", "8. Taste Profile", "tasteProfileNavLink")}'
        '<a href="/?tab=pipeline">Pipeline Stepper</a>'
        '<a href="/?tab=lab">Agent Lab</a>'
        "</div>"
        "</nav>"
    )
    theme_btn = (
        '<button type="button" id="simonNavThemeBtn" class="nav-theme-btn" '
        'title="Toggle Editorial Light / Studio Dark">☀ Light</button>'
        "<script>(function(){"
        "var k='simon_theme',b=document.getElementById('simonNavThemeBtn');"
        "function ap(t){document.documentElement.setAttribute('data-theme',t);"
        "try{localStorage.setItem(k,t);}catch(e){}"
        "if(b)b.textContent=t==='dark'?'☾ Studio Dark':'☀ Light';}"
        "var cur='light';try{cur=localStorage.getItem(k)||'light';}catch(e){}"
        "ap(cur);"
        "if(b)b.addEventListener('click',function(){ap((document.documentElement.getAttribute('data-theme')||'light')==='dark'?'light':'dark');});"
        "document.addEventListener('click',function(e){document.querySelectorAll('.nav-tools-menu[open]').forEach(function(m){if(!m.contains(e.target))m.removeAttribute('open');});});"
        "document.addEventListener('keydown',function(e){if(e.key==='Escape'){document.querySelectorAll('.nav-tools-menu[open]').forEach(function(m){m.removeAttribute('open');});}});"
        "})();</script>"
    )
    return (
        '<header class="simon-topbar">'
        '<div class="simon-topbar-inner">'
        '<div class="simon-brand-group">'
        '<a href="/" class="simon-brand">'
        '<div class="simon-brand-mark">S</div>'
        "<div>"
        '<div class="simon-brand-title">Simon</div>'
        f'<div class="simon-brand-sub">{subtitle}</div>'
        "</div>"
        "</a>"
        f'<nav class="nav-primary-tabs" aria-label="Primary Pipeline Stages">{primary_tabs}</nav>'
        "</div>"
        '<details class="nav-tools-menu">'
        '<summary>Tools ▾</summary>'
        f'<div class="nav-tools-popover">{directory_nav}<div class="nav-tools-footer"><span style="font-size:11px; color:var(--muted);">Theme</span>{theme_btn}</div></div>'
        "</details>"
        "</div>"
        "</header>"
    )


_render_top_nav = render_top_nav


_SHARED_CSS = (
    """
  :root {
    --bg: #f7f5f0; --panel: #ffffff; --panel-2: #f1eee7; --input-bg: #f7f5f0; --border: #e3ded3;
    --text: #181715; --muted: #666158; --accent: #b45309; --accent-hover: #92400e; --accent-fg: #ffffff;
    --teal: #0f766e; --warn: #be123c; --blue: #1d4ed8; --purple: #7e22ce;
    --amber-bg: #fef3c7; --teal-bg: #ccfbf1;
    --warn-bg: #ffe4e6; --blue-bg: #dbeafe; --purple-bg: #f3e8ff;
    --shadow: 0 2px 10px rgba(24, 23, 21, 0.05);
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
  }
  [data-theme="dark"] {
    --bg: #0c0e13; --panel: #141821; --panel-2: #1c2230; --input-bg: #0d1018; --border: #283044;
    --text: #f1f4fa; --muted: #98a3bc; --accent: #f59e0b; --accent-hover: #fbbf24; --accent-fg: #111318;
    --teal: #2dd4bf; --warn: #fb7185; --blue: #60a5fa; --purple: #c084fc;
    --amber-bg: rgba(245, 158, 11, 0.14); --teal-bg: rgba(45, 212, 191, 0.14);
    --warn-bg: rgba(251, 113, 133, 0.15); --blue-bg: rgba(96, 165, 250, 0.14); --purple-bg: rgba(192, 132, 252, 0.15);
    --shadow: 0 4px 14px rgba(0, 0, 0, 0.28);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; color: var(--text); font-family: var(--sans); font-size: 14px; line-height: 1.5;
    background: var(--bg); -webkit-font-smoothing: antialiased;
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .wrap { max-width: 1320px; margin: 0 auto; padding: 24px 20px 64px; }
  header {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
    gap: 16px; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 22px;
  }
  .brand h1 { margin: 0; font-size: 1.55rem; font-weight: 800; letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }
  .brand p { margin: 5px 0 0; color: var(--muted); font-size: 0.9rem; }
  .nav { display: flex; gap: 8px; flex-wrap: wrap; }
  .nav a {
    padding: 7px 12px; border-radius: 9px; font-weight: 600; font-size: 0.85rem;
    border: 1px solid var(--border); background: var(--panel-2); color: var(--muted);
  }
  .nav a.active { background: var(--amber-bg); border-color: var(--accent); color: var(--accent); }
  .nav a:hover { color: var(--text); text-decoration: none; border-color: var(--accent); }
  .pill {
    display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 999px;
    font-size: 0.74rem; font-weight: 600; border: 1px solid var(--border); background: var(--panel-2); color: var(--muted);
  }
  .pill.ok { color: var(--teal); border-color: transparent; background: var(--teal-bg); }
  .pill.warn { color: var(--warn); border-color: transparent; background: var(--warn-bg); }
  .pill.amber { color: var(--accent); border-color: transparent; background: var(--amber-bg); }
  .pill.blue { color: var(--blue); border-color: transparent; background: var(--blue-bg); }
  .pill.purple { color: var(--purple); border-color: transparent; background: var(--purple-bg); }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
    padding: 18px 20px; margin-bottom: 18px; box-shadow: var(--shadow);
  }
  .section-head {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
    margin: 0 0 14px;
  }
  .section-head h2 { margin: 0; font-size: 1.05rem; font-weight: 800; letter-spacing: -0.01em; }
  input, select, textarea {
    background: var(--input-bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 9px; padding: 8px 11px; font-family: inherit; font-size: 0.86rem;
  }
  textarea { width: 100%; min-height: 64px; resize: vertical; }
  input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent); }
  .btn {
    background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 7px 13px; font-size: 0.82rem; font-weight: 600; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px; transition: all 0.14s ease;
  }
  .btn:hover { border-color: var(--accent); text-decoration: none; }
  .btn.primary {
    background: var(--accent); color: var(--accent-fg); border-color: var(--accent); font-weight: 700; padding: 9px 16px;
  }
  .btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
  .btn:disabled { opacity: 0.55; cursor: wait; }
  .banner { padding: 10px 14px; border-radius: 10px; margin-bottom: 16px; font-size: 0.88rem; display: none; }
  .banner.info { display: block; background: var(--amber-bg); border: 1px solid var(--accent); color: var(--accent); }
  .banner.err { display: block; background: var(--warn-bg); border: 1px solid var(--warn); color: var(--warn); }
  .source-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(265px, 1fr)); gap: 10px;
    max-height: 360px; overflow-y: auto; padding-right: 4px;
  }
  .source-item {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 11px;
    padding: 11px 13px; cursor: pointer; transition: border-color 0.12s ease, background 0.12s ease;
  }
  .source-item:hover { border-color: var(--accent); }
  .source-item.selected { border-color: var(--accent); background: var(--amber-bg); }
  .source-title { font-weight: 700; font-size: 0.9rem; margin-bottom: 4px; display: flex; justify-content: space-between; gap: 6px; }
  .source-why { font-size: 0.8rem; color: var(--muted); margin-top: 6px; }
  .worker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
  .worker-card {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 12px; padding: 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .lead-box {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px;
  }
  .mono { font-family: var(--mono); font-size: 0.78rem; color: var(--muted); }
  pre.json-view {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 12px;
    overflow-x: auto; font-family: var(--mono); font-size: 0.76rem; color: var(--text); max-height: 280px;
  }
  .step-row {
    background: var(--panel-2); border-left: 3px solid var(--accent); border-radius: 8px;
    padding: 8px 11px; margin-bottom: 8px; font-size: 0.84rem;
  }
  .kv-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(175px, 1fr)); gap: 8px;
  }
  .kv-cell {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 9px; padding: 8px 10px;
  }
  .kv-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 700; }
  .kv-val { font-size: 0.86rem; font-weight: 600; margin-top: 2px; word-break: break-word; }
"""
    + _NAV_CSS
)


_DISCOVERY_PAGE_CSS = """
  .wrap.wrap-wide { max-width: 1320px; }
  .selector-toolbar {
    display: grid;
    grid-template-columns: minmax(260px, 1.8fr) repeat(4, minmax(155px, 1fr));
    gap: 10px;
    margin-bottom: 12px;
  }
  @media (max-width: 980px) {
    .selector-toolbar { grid-template-columns: 1fr 1fr; }
  }
  @media (max-width: 600px) {
    .selector-toolbar { grid-template-columns: 1fr; }
  }
  .selector-toolbar input,
  .selector-toolbar select {
    width: 100%;
    min-height: 42px;
    padding: 10px 13px;
    font-size: 0.92rem;
  }
  .channel-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-bottom: 12px;
  }
  .chip-btn {
    padding: 5px 11px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    border: 1px solid var(--border);
    background: var(--panel-2);
    color: var(--muted);
    cursor: pointer;
    transition: border-color 0.12s ease, color 0.12s ease, background 0.12s ease;
  }
  .chip-btn:hover { border-color: var(--accent); color: var(--text); }
  .chip-btn.active {
    background: var(--amber-bg);
    border-color: var(--accent);
    color: var(--accent);
  }
  .selected-tray {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 7px;
    padding: 10px 12px;
    margin-bottom: 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--panel-2);
    font-size: 0.82rem;
  }
  .sel-chip {
    border: 1px solid var(--accent);
    background: var(--amber-bg);
    color: var(--accent);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
  }
  .source-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 14px;
    min-height: 520px;
    max-height: 76vh;
    overflow-y: auto;
    padding: 4px 6px 6px 2px;
  }
  .source-grid.expanded {
    max-height: none;
    overflow: visible;
  }
  .source-item {
    padding: 16px 18px;
    border-radius: 13px;
    display: flex;
    flex-direction: column;
    gap: 9px;
    min-height: 156px;
  }
  .source-check {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 6px;
    border: 1.5px solid var(--border);
    background: var(--panel);
    font-size: 0.78rem;
    font-weight: 800;
    flex-shrink: 0;
  }
  .source-item.selected .source-check {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-fg, #111318);
  }
  .source-title {
    font-weight: 700;
    font-size: 0.98rem;
    margin: 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
  }
  .source-why {
    font-size: 0.86rem;
    color: var(--text);
    opacity: 0.9;
    line-height: 1.45;
    margin: 0;
  }
  .source-genres {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: auto;
    padding-top: 2px;
  }
  .genre-tag {
    font-size: 0.71rem;
    padding: 2px 7px;
    border-radius: 6px;
    border: 1px solid var(--border);
    color: var(--muted);
  }
  .source-note {
    font-size: 0.77rem;
    color: var(--muted);
  }
  .source-ext {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--teal);
    white-space: nowrap;
  }
"""


_FORMAT_LABEL_JS = """
    function formatLabel(val) {
      if (val == null || val === '') return '';
      const special = {
        nyc: 'NYC', diy: 'DIY', rnb: 'R&B', ep: 'EP', dsp: 'DSP', dm: 'DM',
        youtube: 'YouTube', soundcloud: 'SoundCloud', bandcamp: 'Bandcamp',
        tiktok: 'TikTok', instagram: 'Instagram', spotify: 'Spotify',
        musicbrainz: 'MusicBrainz', ai: 'AI', url: 'URL', gcp: 'GCP', cli: 'CLI', ui: 'UI',
      };
      return String(val)
        .replace(/^staging-/, '')
        .replace(/^simon-/, '')
        .replace(/[_-]+/g, ' ')
        .trim()
        .split(/\\s+/)
        .map((w) => {
          const low = w.toLowerCase();
          if (special[low]) return special[low];
          return low.charAt(0).toUpperCase() + low.slice(1);
        })
        .join(' ');
    }
"""


DISCOVERY_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · Stage 1 Discovery &amp; Source Orchestrator</title>
  <style>{_SHARED_CSS}{_DISCOVERY_PAGE_CSS}</style>
</head>
<body>
  {render_page_topbar("/discovery", "Discovery")}
  <div class="wrap wrap-wide">
    <div class="page-hero">
      <h1>1. Discovery Dashboard <span class="pill amber">Stage 1</span></h1>
      <p>Pick your sources, write a brief, and send scouts. Track live progress in <strong>Field News</strong>.</p>
    </div>
    {render_discovery_subnav("/discovery")}

    <div id="banner" class="banner"></div>

    <section class="card">
      <div class="section-head">
        <h2>1. Select Discovery Sources <span id="selectedBadge" class="pill amber">0 selected</span> <span id="showingBadge" class="pill">0 / 0 shown</span></h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <button class="btn" type="button" id="selectQuickBtn">Quick Pick: 3 NYC Active</button>
          <button class="btn" type="button" id="selectFilteredBtn">Select All Shown</button>
          <button class="btn" type="button" id="clearSelBtn">Clear</button>
          <button class="btn" type="button" id="toggleExpandBtn">Expand Full List</button>
        </div>
      </div>

      <div class="selector-toolbar">
        <input type="search" id="sourceSearchInput" placeholder="Search sources by name, neighborhood, genre, or scouting note…" aria-label="Search discovery sources" />
        <select id="channelFilter"><option value="">All channels</option></select>
        <select id="cityFilter"><option value="">All locations</option></select>
        <select id="tierFilter"><option value="">All career tiers</option></select>
        <select id="genreFilter"><option value="">All genres</option></select>
      </div>

      <div id="channelChips" class="channel-chips"></div>
      <div id="selectedTray" class="selected-tray" style="display:none;"></div>
      <div id="sourceGrid" class="source-grid"></div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>2. Orchestrate Discovery Fleet</h2>
        <span id="agentIdBadge" class="pill blue">Discovery Scout</span>
      </div>
      <label for="briefInput" style="display:block; font-weight:600; font-size:0.86rem; margin-bottom:6px;">Search Brief</label>
      <textarea id="briefInput">{DEFAULT_DISCOVERY_BRIEF}</textarea>
      <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; margin-top:14px;">
        <div style="display:flex; flex-wrap:wrap; gap:14px; align-items:center;">
          <label style="font-size:0.86rem;">
            Discovery Scouts:
            <input type="number" id="agentCountInput" min="1" max="10" value="3" style="width:68px; margin-left:6px;" />
          </label>
          <label style="font-size:0.86rem;">
            Leads / Scout:
            <input type="number" id="leadsPerAgentInput" min="1" max="10" value="2" style="width:68px; margin-left:6px;" />
          </label>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.86rem; cursor:pointer;">
            <input type="checkbox" id="liveToggle" />
            <span>Run Live Scouts</span>
          </label>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.86rem; cursor:pointer;">
            <input type="checkbox" id="resetPrevToggle" checked />
            <span>Start fresh (archive old runs)</span>
          </label>
        </div>
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
          <div id="postDispatchLinks" style="display:none; gap:8px; flex-wrap:wrap; align-items:center;">
            <a id="nextInvestigateBtn" class="btn primary" href="/investigate?autorun=1">Next: Investigate Discovered Leads →</a>
            <a id="followFieldNewsBtn" class="btn" href="/field-news">Follow in Field News →</a>
            <a id="openReportsBtn" class="btn" href="/reports">Open Scouting Reports →</a>
          </div>
          <button id="clearOldRunsBtn" class="btn" type="button">↺ Clear Old Runs</button>
          <a class="btn" href="/?tab=discovery">Open in Agency Studio →</a>
          <button id="dispatchBtn" class="btn primary" type="button">Send Discovery Scouts</button>
        </div>
      </div>
    </section>
  </div>

  <script>
    let allSources = [];
    let currentFiltered = [];
    const selectedIds = new Set();
    let isExpanded = false;

    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
    function showBanner(msg, kind) {{
      const b = el('banner');
      if (!msg) {{ b.style.display = 'none'; return; }}
      b.textContent = msg; b.className = 'banner ' + (kind || 'info'); b.style.display = 'block';
    }}
{_FORMAT_LABEL_JS}

    function syncBatchLinks(batchId) {{
      if (!batchId) return;
      const q = `?batch=${{encodeURIComponent(batchId)}}`;
      if (el('tracesNavLink')) el('tracesNavLink').href = `/field-news${{q}}`;
      if (el('reportsNavLink')) el('reportsNavLink').href = `/reports${{q}}`;
      if (el('subflowFieldNewsLink')) el('subflowFieldNewsLink').href = `/field-news${{q}}`;
      if (el('subflowReportsLink')) el('subflowReportsLink').href = `/reports${{q}}`;
      if (el('followFieldNewsBtn')) el('followFieldNewsBtn').href = `/field-news${{q}}`;
      if (el('openReportsBtn')) el('openReportsBtn').href = `/reports${{q}}`;
      if (el('postDispatchLinks')) el('postDispatchLinks').style.display = 'inline-flex';
    }}

    function renderChannelChips() {{
      const activeChannel = el('channelFilter').value;
      const counts = new Map();
      allSources.forEach((s) => {{
        const ch = s.source_channel || 'other';
        counts.set(ch, (counts.get(ch) || 0) + 1);
      }});
      const chips = [
        `<button type="button" class="chip-btn ${{activeChannel === '' ? 'active' : ''}}" data-channel="">All (${{allSources.length}})</button>`,
      ];
      Array.from(counts.keys()).sort().forEach((ch) => {{
        chips.push(
          `<button type="button" class="chip-btn ${{activeChannel === ch ? 'active' : ''}}" data-channel="${{esc(ch)}}">${{esc(formatLabel(ch))}} (${{counts.get(ch)}})</button>`
        );
      }});
      el('channelChips').innerHTML = chips.join('');
      el('channelChips').querySelectorAll('.chip-btn').forEach((btn) => {{
        btn.onclick = () => {{
          el('channelFilter').value = btn.dataset.channel || '';
          renderSources();
        }};
      }});
    }}

    function renderSelectedTray() {{
      const tray = el('selectedTray');
      if (!selectedIds.size) {{
        tray.style.display = 'none';
        tray.innerHTML = '';
        return;
      }}
      const byId = new Map(allSources.map((s) => [s.source_id, s]));
      const items = Array.from(selectedIds).map((id) => {{
        const src = byId.get(id);
        const name = src ? src.name : id;
        return `<button type="button" class="sel-chip" data-remove-id="${{esc(id)}}" title="Remove source">${{esc(name)}} ×</button>`;
      }});
      tray.innerHTML = `<span style="font-weight:700; color:var(--muted);">Selected:</span>` + items.join('');
      tray.style.display = 'flex';
      tray.querySelectorAll('.sel-chip').forEach((btn) => {{
        btn.onclick = () => {{
          selectedIds.delete(btn.dataset.removeId);
          renderSources();
        }};
      }});
    }}

    function resetFilters() {{
      el('sourceSearchInput').value = '';
      el('channelFilter').value = '';
      el('cityFilter').value = '';
      el('tierFilter').value = '';
      el('genreFilter').value = '';
      renderSources();
    }}

    function renderSources() {{
      const q = (el('sourceSearchInput').value || '').trim().toLowerCase();
      const ch = el('channelFilter').value;
      const city = el('cityFilter').value;
      const tier = el('tierFilter').value;
      const genre = el('genreFilter').value;

      currentFiltered = allSources.filter((s) => {{
        const loc = s.location || {{}};
        const sCity = loc.city || 'Global';
        const tags = Array.isArray(s.genre_tags) ? s.genre_tags : [];
        if (ch && s.source_channel !== ch) return false;
        if (city && sCity !== city) return false;
        if (tier && s.career_tier !== tier) return false;
        if (genre && !tags.includes(genre)) return false;
        if (q) {{
          const hay = [
            s.name,
            s.why_useful,
            s.notes,
            s.source_channel,
            sCity,
            loc.area,
            tags.join(' '),
          ].filter(Boolean).join(' ').toLowerCase();
          if (!hay.includes(q)) return false;
        }}
        return true;
      }});

      renderChannelChips();
      renderSelectedTray();

      el('selectedBadge').textContent = `${{selectedIds.size}} selected`;
      el('showingBadge').textContent = `${{currentFiltered.length}} / ${{allSources.length}} shown`;

      if (!currentFiltered.length) {{
        el('sourceGrid').innerHTML = `
          <div style="grid-column: 1 / -1; padding: 36px 20px; text-align: center; color: var(--muted);">
            <div style="font-weight:700; margin-bottom:8px;">No sources match the active filters.</div>
            <button type="button" class="btn" id="resetFiltersBtn">Reset Filters</button>
          </div>`;
        if (el('resetFiltersBtn')) el('resetFiltersBtn').onclick = resetFilters;
        return;
      }}

      el('sourceGrid').innerHTML = currentFiltered.map((s) => {{
        const isSel = selectedIds.has(s.source_id);
        const loc = s.location || {{}};
        const sCity = loc.city || 'Global';
        const locLabel = loc.area ? `${{loc.area}} · ${{sCity}}` : sCity;
        const statusCls = s.status === 'active' ? 'ok' : 'warn';
        const tags = (Array.isArray(s.genre_tags) ? s.genre_tags : []).filter((g) => g && g !== 'all').slice(0, 5);
        const tagsHtml = tags.length
          ? `<div class="source-genres">${{tags.map((g) => `<span class="genre-tag">${{esc(formatLabel(g))}}</span>`).join('')}}</div>`
          : '';
        const noteHtml = s.notes ? `<div class="source-note">Note: ${{esc(s.notes)}}</div>` : '';
        const extHtml = s.url
          ? `<a class="source-ext" href="${{esc(s.url)}}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Open ↗</a>`
          : '';

        return `
          <div class="source-item ${{isSel ? 'selected' : ''}}" data-id="${{esc(s.source_id)}}">
            <div class="source-title">
              <span style="display:flex; align-items:flex-start; gap:9px;">
                <span class="source-check">${{isSel ? '✓' : ''}}</span>
                <span>${{esc(s.name)}}</span>
              </span>
              <span style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
                ${{extHtml}}
                <span class="pill ${{statusCls}}">${{esc(formatLabel(s.status))}}</span>
              </span>
            </div>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              <span class="pill blue">${{esc(formatLabel(s.source_channel))}}</span>
              <span class="pill">${{esc(locLabel)}}</span>
              <span class="pill">${{esc(formatLabel(s.career_tier))}}</span>
            </div>
            <div class="source-why">${{esc(s.why_useful)}}</div>
            ${{noteHtml}}
            ${{tagsHtml}}
          </div>`;
      }}).join('');

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

    async function init() {{
      const res = await fetch('/api/sources');
      const data = await res.json();
      allSources = data.sources || [];
      (data.channels || []).forEach((c) => el('channelFilter').add(new Option(formatLabel(c), c)));
      (data.cities || []).forEach((c) => el('cityFilter').add(new Option(c, c)));
      (data.tiers || []).forEach((t) => el('tierFilter').add(new Option(formatLabel(t), t)));
      const genres = (data.genres && data.genres.length)
        ? data.genres
        : Array.from(new Set(allSources.flatMap((s) => Array.isArray(s.genre_tags) ? s.genre_tags : []).filter((g) => g && g !== 'all'))).sort();
      genres.forEach((g) => el('genreFilter').add(new Option(formatLabel(g), g)));
      // Default quick selection: 3 active diverse sources
      ['yt_sofar_sounds', 'nyc_babys_all_right', 'bc_brooklyn_soul_rnb'].forEach((id) => {{
        if (allSources.some((s) => s.source_id === id)) selectedIds.add(id);
      }});
      el('agentCountInput').value = Math.max(1, selectedIds.size);
      renderSources();

      const bRes = await fetch('/api/discovery/batches');
      if (bRes.ok) {{
        const bData = await bRes.json();
        if (bData.batches && bData.batches.length) {{
          syncBatchLinks(bData.batches[0].batch_id);
        }}
      }}
    }}

    el('sourceSearchInput').oninput = renderSources;
    ['channelFilter', 'cityFilter', 'tierFilter', 'genreFilter'].forEach((id) => el(id).onchange = renderSources);
    el('selectQuickBtn').onclick = () => {{
      selectedIds.clear();
      allSources.filter((s) => s.status === 'active' && (s.location && s.location.city === 'New York')).slice(0, 3)
        .forEach((s) => selectedIds.add(s.source_id));
      el('agentCountInput').value = Math.max(1, selectedIds.size);
      renderSources();
    }};
    el('selectFilteredBtn').onclick = () => {{
      currentFiltered.forEach((s) => selectedIds.add(s.source_id));
      if (selectedIds.size > 0) el('agentCountInput').value = Math.min(selectedIds.size, 10);
      renderSources();
    }};
    el('clearSelBtn').onclick = () => {{ selectedIds.clear(); renderSources(); }};
    el('toggleExpandBtn').onclick = () => {{
      isExpanded = !isExpanded;
      el('sourceGrid').classList.toggle('expanded', isExpanded);
      el('toggleExpandBtn').textContent = isExpanded ? 'Collapse List' : 'Expand Full List';
    }};

    el('clearOldRunsBtn').onclick = async () => {{
      el('clearOldRunsBtn').disabled = true;
      showBanner('Archiving previous pipeline runs…', 'info');
      try {{
        const res = await fetch('/api/demo/reset', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{}}),
        }});
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Reset failed');
        if (el('postDispatchLinks')) el('postDispatchLinks').style.display = 'none';
        showBanner(`Workspace cleared (${{payload.total_archived || 0}} old run(s) archived). Ready for a new Discovery run.`, 'info');
      }} catch (err) {{
        showBanner(err.message, 'err');
      }} finally {{
        el('clearOldRunsBtn').disabled = false;
      }}
    }};

    el('dispatchBtn').onclick = async () => {{
      if (selectedIds.size === 0) {{ showBanner('Select at least one source first.', 'err'); return; }}
      showBanner('Sending discovery scouts…', 'info');
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
            reset_previous: el('resetPrevToggle') ? el('resetPrevToggle').checked : false,
          }}),
        }});
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Dispatch failed');
        const modeLabel = payload.mode === 'live' ? 'live' : 'preview';
        showBanner(`Sent ${{payload.agent_count}} scout(s) in ${{modeLabel}} mode. Click "Next: Investigate Discovered Leads →" to continue.`, 'info');
        syncBatchLinks(payload.batch_id);
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
  <title>Simon · 2. Field News (Live Scouts)</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {render_page_topbar("/field-news", "Field News")}
  <div class="wrap">
    <div class="page-hero">
      <h1>2. Field News <span class="pill ok">Stage 1</span></h1>
      <p>Live updates from active scouts: what each scout checks, finds, and notes in real time.</p>
    </div>
    {render_discovery_subnav("/field-news")}

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
{_FORMAT_LABEL_JS}
    let currentBatchId = new URLSearchParams(window.location.search).get('batch') || '';
    let pollTimer = null;

    function statusPill(status) {{
      if (status === 'completed') return '<span class="pill ok">Completed</span>';
      if (status === 'in_motion' || status === 'starting') return '<span class="pill amber">' + esc(formatLabel(status)) + '</span>';
      return '<span class="pill warn">' + esc(formatLabel(status || 'unknown')) + '</span>';
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
      if (el('subflowReportsLink') && currentBatchId) {{
        el('subflowReportsLink').href = `/reports?batch=${{encodeURIComponent(currentBatchId)}}`;
      }}
      try {{
        const u = new URL(window.location.href);
        if (currentBatchId) u.searchParams.set('batch', currentBatchId);
        else u.searchParams.delete('batch');
        window.history.replaceState({{}}, '', u.toString());
      }} catch (e) {{}}
    }}

    async function loadBatches() {{
      const res = await fetch('/api/discovery/batches');
      const data = await res.json();
      const batches = data.batches || [];
      const sel = el('batchSelect');
      sel.innerHTML = '';
      sel.add(new Option('All recent field dispatches', ''));
      batches.forEach((b) => {{
        const label = `${{b.search_brief ? b.search_brief.slice(0, 42) : 'Recent Scout Batch'}} (${{b.completed}}/${{b.agent_count}} done · ${{b.total_leads}} leads)`;
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
  {render_page_topbar("/reports", "Scouting Reports")}
  <div class="wrap">
    <div class="page-hero">
      <h1>3. Scouting Reports <span class="pill blue">Stage 1</span></h1>
      <p>Saved scouting reports with checked leads, step-by-step notes, and full lead details.</p>
    </div>
    {render_discovery_subnav("/reports")}

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
{_FORMAT_LABEL_JS}
    const params = new URLSearchParams(window.location.search);
    const filterBatchId = params.get('batch') || '';
    const focusReportId = params.get('report') || '';
    if (filterBatchId && el('subflowFieldNewsLink')) {{
      el('subflowFieldNewsLink').href = `/field-news?batch=${{encodeURIComponent(filterBatchId)}}`;
    }}

    function statusPill(status) {{
      if (status === 'completed') return '<span class="pill ok">Completed</span>';
      if (status === 'in_motion' || status === 'starting') return '<span class="pill amber">' + esc(formatLabel(status)) + '</span>';
      return '<span class="pill warn">' + esc(formatLabel(status || 'unknown')) + '</span>';
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
                  ${{f.attribution_status ? `<span class="pill ok">${{esc(formatLabel(f.attribution_status))}}</span>` : ''}}
                </div>
                <div style="font-size:0.84rem; color:var(--muted); margin-top:4px;">${{esc(f.summary)}}</div>
                <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; align-items:center; justify-content:space-between;">
                  <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                    ${{f.source_name ? `<span class="pill">${{esc(f.source_name)}}</span>` : ''}}
                    ${{f.source_channel ? `<span class="pill">${{esc(formatLabel(f.source_channel))}}</span>` : ''}}
                    ${{f.url ? `<a href="${{esc(f.url)}}" target="_blank" rel="noopener" style="font-size:0.82rem;">Open source ↗</a>` : ''}}
                  </div>
                  <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                    <a class="btn" href="/?tab=pipeline&amp;phase=2a_identity&amp;subject=${{encodeURIComponent(f.title || '')}}${{f.lead_id ? '&amp;lead=' + encodeURIComponent(f.lead_id) : ''}}" style="font-size:0.78rem; padding:5px 10px;">Send to Studio Pipeline →</a>
                    <a class="btn" href="/investigate?subject=${{encodeURIComponent(f.title || '')}}${{f.lead_id ? '&lead=' + encodeURIComponent(f.lead_id) : ''}}" style="font-size:0.78rem; padding:5px 10px; color:var(--teal); border-color:rgba(45,212,191,0.4);">Investigate →</a>
                  </div>
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
               <summary style="cursor:pointer; font-size:0.85rem; color:var(--teal); font-weight:600;">View Full Lead Handoff</summary>
               <pre class="json-view">${{esc(JSON.stringify(r.output, null, 2))}}</pre>
             </details>`
          : '<div style="font-size:0.82rem; color:var(--muted); margin-top:8px;">Final handoff pending completion…</div>';

        const highlightStyle = focusReportId && r.report_id === focusReportId ? 'border-color: var(--accent);' : '';
        return `
          <section class="card" id="${{esc(r.report_id)}}" style="${{highlightStyle}}">
            <div class="section-head">
              <div>
                <h2 style="margin:0;">${{esc(r.agent_name)}} <span class="pill">${{esc(formatLabel(r.stage))}}</span> ${{statusPill(r.status)}} ${{r.archived ? '<span class="pill warn">Archived</span>' : ''}}</h2>
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
  {render_page_topbar("/investigate", "Investigate")}
  <div class="wrap">
    <div class="page-hero">
      <h1>4. Investigator Desk <span class="pill ok">Stage 2</span></h1>
      <p>Check Stage 1 leads, run Stage 2 investigators, and read factual artist dossiers. No scores or ranks.</p>
    </div>

    <div id="focusBanner" class="banner"></div>

    <section class="card">
      <div class="section-head">
        <h2>1. Verified Leads Ready for Stage 2 Investigation <span id="leadsCountBadge" class="pill blue">0 leads</span></h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <input id="leadSearchInput" type="text" placeholder="Filter by artist name…" style="min-width:220px;" />
          <button id="clearFocusBtn" class="btn" type="button" style="display:none;">Show All</button>
          <button id="refreshDeskBtn" class="btn" type="button">Refresh Desk</button>
          <button id="runInvestigateBtn" class="btn primary" type="button">▶ Run Stage 2 Investigation on Active Leads</button>
        </div>
      </div>
      <div id="leadsGrid" class="worker-grid">
        <div class="mono">Loading verified leads from Discovery…</div>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>2. Stage 2 Investigator Field News <span id="invNewsCountBadge" class="pill amber">0 dispatches</span></h2>
        <span class="pill">Stage 2 · Live Updates</span>
      </div>
      <div id="invFieldNews" class="worker-grid">
        <div class="mono">Loading Stage 2 investigator field news…</div>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>3. Stored Investigator Dossiers <span id="dossiersCountBadge" class="pill ok">0 dossiers</span></h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <span class="pill ok">Verified Facts Only · Unranked</span>
          <button id="sendToScreenBtn" class="btn primary" type="button">Next: Screen These Dossiers →</button>
          <a class="btn" href="/screen" style="border-color:rgba(192,132,252,0.45); color:var(--purple);">Open Screening Deck →</a>
        </div>
      </div>
      <div id="dossiersList" style="display:flex; flex-direction:column; gap:16px;">
        <div class="mono">Loading stored investigator dossiers…</div>
      </div>
    </section>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
{_FORMAT_LABEL_JS}
    const params = new URLSearchParams(window.location.search);
    let focusLeadId = params.get('lead') || '';
    let focusSubject = params.get('subject') || '';
    let allLeads = [];
    let allDossiers = [];

    function statusPill(status) {{
      if (status === 'completed' || status === 'verified') return '<span class="pill ok">' + esc(formatLabel(status)) + '</span>';
      if (status === 'in_motion' || status === 'starting' || status === 'uncertain') return '<span class="pill amber">' + esc(formatLabel(status)) + '</span>';
      return '<span class="pill warn">' + esc(formatLabel(status || 'unknown')) + '</span>';
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
        const label = focusSubject || 'Selected Artist';
        b.textContent = `Focused on artist: ${{label}}`;
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
        const firstSeed = seeds[0] || {{}};
        const leadMeta = [
          firstSeed.seed_query_or_venue_node,
          firstSeed.source_channel ? formatLabel(firstSeed.source_channel) : '',
        ].filter(Boolean).join(' · ');
        return `
          <div class="worker-card">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <strong>${{esc(l.stage_name || 'Unnamed Artist')}}</strong>
              <div style="display:flex; gap:6px; flex-wrap:wrap;">
                ${{statusPill(l.attribution_status || 'uncertain')}}
                ${{hasDossier ? '<span class="pill ok">Dossier Stored</span>' : '<span class="pill blue">Ready for Stage 2</span>'}}
              </div>
            </div>
            ${{leadMeta ? `<div style="font-size:0.8rem; color:var(--muted);">${{esc(leadMeta)}}</div>` : ''}}
            <div style="font-size:0.84rem; color:var(--muted);">${{esc(l.context_snippet || 'Discovered in Stage 1.')}}</div>
            <div style="display:flex; flex-direction:column; gap:4px;">
              ${{seeds.map((ss) => `<a class="mono" href="${{esc(ss.url)}}" target="_blank" rel="noopener">↗ ${{esc(formatLabel(ss.source_channel || 'Source'))}} · ${{esc(ss.seed_query_or_venue_node || ss.url)}}</a>`).join('')}}
            </div>
            <div style="margin-top:auto; padding-top:6px; display:flex; justify-content:space-between; align-items:center; gap:6px; flex-wrap:wrap;">
              <button class="btn" type="button" data-focus-lead="${{esc(l.lead_id || '')}}" data-focus-name="${{esc(l.stage_name || '')}}" style="font-size:0.78rem; padding:5px 10px;">Focus Lead &amp; Dossier</button>
              <a class="btn" href="/?tab=pipeline&amp;phase=2a_identity&amp;subject=${{encodeURIComponent(l.stage_name || '')}}${{l.lead_id ? '&amp;lead=' + encodeURIComponent(l.lead_id) : ''}}" style="font-size:0.78rem; padding:5px 10px;">Send to Studio Pipeline →</a>
              ${{hasDossier ? `<a class="btn" href="/screen?lead=${{encodeURIComponent(l.lead_id || '')}}" style="font-size:0.78rem; padding:5px 10px; border-color:rgba(192,132,252,0.45); color:var(--purple);">Open Screening Deck →</a>` : ''}}
              <a href="/reports${{l.batch_id ? '?batch=' + encodeURIComponent(l.batch_id) : ''}}" style="font-size:0.8rem;">View Discovery Report →</a>
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
        el('invFieldNews').innerHTML = '<div class="mono">No Stage 2 investigator updates yet. Live notes appear here once an investigation starts.</div>';
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
        const stageName = idObj.stage_name || d.stage_name || 'Unnamed Artist';
        const city = [idObj.home_neighborhood, idObj.home_city].filter(Boolean).join(', ') || d.home_city || '—';
        const projectType = formatLabel(idObj.project_type || d.project_type || 'unknown');
        const contactRoute = idObj.contact_route_type
          ? formatLabel(idObj.contact_route_type)
          : (idObj.has_public_business_contact ? 'Public Contact' : 'None Listed');
        const regime = (fpObj.footprint_regime || d.footprint_regime)
          ? formatLabel(fpObj.footprint_regime || d.footprint_regime)
          : 'Not Classified';
        const platformUrls = idObj.platform_urls || {{}};
        const platformLinks = Object.entries(platformUrls)
          .filter(([, url]) => Boolean(url))
          .map(([k, url]) => `<a class="pill blue" href="${{esc(url)}}" target="_blank" rel="noopener">${{esc(formatLabel(k))}} ↗</a>`)
          .join('');
        const mediaLinks = (srcObj.media_links || []).map((m) => `
          <div class="lead-box" style="padding:8px 10px;">
            <div style="display:flex; justify-content:space-between; gap:8px;">
              <strong>${{esc(m.title || m.url)}}</strong>
              <span class="pill ${{m.oembed_live_embeddable ? 'ok' : ''}}">${{m.oembed_live_embeddable ? 'Playable' : 'Link'}}</span>
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
              <span class="pill">${{esc(city !== '—' ? city : 'Factual Dossier')}}</span>
            </div>
            ${{srcObj.bio_text ? `<div style="font-size:0.86rem; color:var(--muted);">${{esc(srcObj.bio_text)}}</div>` : ''}}
            <div class="kv-grid">
              <div class="kv-cell"><div class="kv-label">Location</div><div class="kv-val">${{esc(city)}}</div></div>
              <div class="kv-cell"><div class="kv-label">Contact Route</div><div class="kv-val">${{esc(contactRoute)}}</div></div>
              <div class="kv-cell"><div class="kv-label">YouTube Subscribers</div><div class="kv-val">${{reach.youtube_subscribers != null ? esc(reach.youtube_subscribers) : '—'}}</div></div>
              <div class="kv-cell"><div class="kv-label">Top Video Views</div><div class="kv-val">${{reach.top_video_views != null ? esc(reach.top_video_views) : '—'}}</div></div>
              <div class="kv-cell"><div class="kv-label">Comment Signals</div><div class="kv-val">${{intents.sample_size != null ? `${{intents.sample_size}} sampled · ${{intents.release_requests || 0}} release requests · ${{intents.live_show_requests || 0}} show requests` : '—'}}</div></div>
              <div class="kv-cell"><div class="kv-label">Public Team</div><div class="kv-val">${{esc(team.management || team.label || team.booking_agent || 'Independent / none observed')}}</div></div>
            </div>
            ${{platformLinks ? `<div style="display:flex; gap:6px; flex-wrap:wrap;">${{platformLinks}}</div>` : ''}}
            ${{mediaLinks ? `<div style="display:flex; flex-direction:column; gap:6px;">${{mediaLinks}}</div>` : ''}}
            <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">${{showsHtml}}</div>
            <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center; justify-content:space-between; padding-top:4px; border-top:1px solid var(--border);">
              <details style="flex:1;">
                <summary style="cursor:pointer; font-size:0.84rem; color:var(--teal); font-weight:600;">Inspect Full Artist Dossier</summary>
                <pre class="json-view">${{esc(JSON.stringify(d, null, 2))}}</pre>
              </details>
              <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                <button type="button" class="btn primary run-screen-btn" data-screen-lead="${{esc(d.lead_id || '')}}" style="font-size:0.78rem; padding:5px 10px;">Run Screening →</button>
                <a class="btn" href="/screen?lead=${{encodeURIComponent(d.lead_id || '')}}" style="font-size:0.78rem; padding:5px 10px;">Open Screening Deck →</a>
              </div>
            </div>
          </div>`;
      }}).join('');

      document.querySelectorAll('.run-screen-btn').forEach((btn) => {{
        btn.onclick = async () => {{
          const lid = btn.dataset.screenLead;
          const dossier = visible.find((x) => (x.lead_id || '') === lid) || null;
          btn.disabled = true;
          btn.textContent = 'Running Screening…';
          try {{
            const res = await fetch('/api/screening/run', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ lead_id: lid || undefined, dossier, live: false }}),
            }});
            if (res.ok) {{
              window.location.href = `/screen?lead=${{encodeURIComponent(lid || '')}}`;
              return;
            }}
            btn.textContent = 'Screening failed — Open Deck';
          }} catch (e) {{
            btn.textContent = 'Network error';
          }} finally {{
            btn.disabled = false;
          }}
        }};
      }});
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

    async function runInvestigationNow() {{
      const btn = el('runInvestigateBtn');
      const b = el('focusBanner');
      if (btn) btn.disabled = true;
      b.textContent = 'Running Stage 2 Scout Investigator across active Discovery leads…';
      b.className = 'banner info';
      b.style.display = 'block';
      try {{
        const payload = focusLeadId ? {{ lead_id: focusLeadId }} : {{}};
        const res = await fetch('/api/investigate/run', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Stage 2 investigation failed');
        await loadDesk();
        b.textContent = `Built ${{data.count || 0}} factual artist dossier(s). Click "Next: Screen These Dossiers →" to review in Screening Deck.`;
        b.className = 'banner info';
        b.style.display = 'block';
      }} catch (err) {{
        b.textContent = err.message;
        b.className = 'banner err';
        b.style.display = 'block';
      }} finally {{
        if (btn) btn.disabled = false;
      }}
    }}

    el('runInvestigateBtn').onclick = runInvestigationNow;

    el('sendToScreenBtn').onclick = async () => {{
      const btn = el('sendToScreenBtn');
      const b = el('focusBanner');
      btn.disabled = true;
      b.textContent = 'Preparing Stage 3 screening briefs…';
      b.className = 'banner info';
      b.style.display = 'block';
      try {{
        const res = await fetch('/api/screening/run', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ live: false }}),
        }});
        if (!res.ok) {{
          const data = await res.json().catch(() => ({{}}));
          throw new Error(data.error || 'Screening batch failed');
        }}
        window.location.href = '/screen';
      }} catch (err) {{
        b.textContent = err.message;
        b.className = 'banner err';
        b.style.display = 'block';
        btn.disabled = false;
      }}
    }};

    loadDesk().then(() => {{
      if (params.get('autorun') === '1' && allLeads.length > 0) {{
        const cleanUrl = window.location.pathname;
        window.history.replaceState({{}}, '', cleanUrl);
        runInvestigationNow();
      }}
    }});
  </script>
</body>
</html>
"""


def list_eval_runs(store: SimonStore, agent_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List recent agent evaluation runs stored in Firestore/SQLite."""
    rows = list_agent_documents(store, "eval_runs", limit=limit)
    runs: List[Dict[str, Any]] = []
    for row in rows:
        doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
        if not isinstance(doc, dict):
            continue
        if agent_id and doc.get("agent_id") != agent_id and not str(doc.get("agent_id", "")).endswith(agent_id):
            continue
        runs.append(doc)
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return runs


EVALS_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · 6. Agent Evals &amp; Rubrics (Vertex AI)</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {render_page_topbar("/evals", "Quality Evals")}
  <div class="wrap">
    <div class="page-hero">
      <h1>6. Evals (Vertex AI) <span class="pill blue">Quality Tools</span></h1>
      <p>Check each agent against quality rubrics, review Vertex AI scorecards, and catch regressions.</p>
    </div>

    <div id="evalBanner" class="banner"></div>

    <section class="card">
      <div class="section-head">
        <h2>Run Quality Check</h2>
        <span class="pill amber">Quality Rubrics</span>
      </div>
      <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;">
        <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center;">
          <label style="font-size:0.86rem;">
            Agent:
            <select id="evalAgentSelect" style="margin-left:6px;">
              <option value="discovery-scout">Discovery Scout</option>
            </select>
          </label>
          <label style="font-size:0.86rem;">
            Runner:
            <select id="evalModeSelect" style="margin-left:6px;">
              <option value="offline">Instant Quality Checks (Offline)</option>
              <option value="vertex">Full Vertex AI Review (Cloud)</option>
            </select>
          </label>
          <label style="font-size:0.86rem;">
            Sample Run:
            <select id="evalTraceSelect" style="margin-left:6px; max-width:340px;">
              <option value="">All Samples (Batch)</option>
            </select>
          </label>
          <label style="font-size:0.86rem;">
            Samples:
            <select id="evalSampleSelect" style="margin-left:6px;">
              <option value="live_reports">Live Scouting Reports Only</option>
              <option value="mixed">Live Reports + Benchmark Set</option>
              <option value="golden_dataset">Benchmark Set Only</option>
            </select>
          </label>
        </div>
        <div style="display:flex; gap:8px;">
          <button id="refreshEvalsBtn" class="btn" type="button">Refresh</button>
          <button id="runAllEvalsBtn" class="btn" type="button">Run All Agents</button>
          <button id="runEvalBtn" class="btn primary" type="button">Run Check Now</button>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>Eval Runs &amp; Vertex AI Scorecards <span id="evalCountBadge" class="pill">0 runs</span></h2>
        <span style="font-size:0.8rem; color:var(--muted);">Synced from automated checks and manual runs</span>
      </div>
      <div id="evalRunsContainer">
        <div class="mono">Loading evaluation runs...</div>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <h2>Active Quality Rubrics <span id="rubricVersionBadge" class="pill blue">v1.0.0</span></h2>
        <span id="rubricAgentLabel" class="pill">Discovery Scout</span>
      </div>
      <div id="rubricCatalogContainer">
        <div class="mono">Loading rubrics...</div>
      </div>
    </section>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
{_FORMAT_LABEL_JS}

    function showBanner(msg, isError) {{
      const b = el('evalBanner');
      b.style.display = 'block';
      b.style.borderColor = isError ? 'var(--bad)' : 'var(--ok)';
      b.style.color = isError ? '#ff8e99' : '#7ef0ba';
      b.textContent = msg;
    }}

    function statusPill(status) {{
      if (status === 'passed') return '<span class="pill ok">Passed</span>';
      if (status === 'failed' || status === 'error') return '<span class="pill bad">' + esc(formatLabel(status)) + '</span>';
      return '<span class="pill amber">' + esc(formatLabel(status || 'warning')) + '</span>';
    }}

    function renderRubrics(spec) {{
      el('rubricVersionBadge').textContent = 'v' + (spec.version || '1.0.0');
      el('rubricAgentLabel').textContent = formatLabel(spec.agent_id || 'agent');
      const layers = spec.layers || [];
      el('rubricCatalogContainer').innerHTML = layers.map((layer) => {{
        const rows = (layer.rubrics || []).map((r) => `
          <div class="step-row">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <strong>${{esc(r.name)}}</strong>
              <div style="display:flex; gap:6px;">
                <span class="pill blue">${{esc(r.skill ? formatLabel(r.skill) : 'Core Guidelines')}}</span>
                <span class="pill">${{esc(formatLabel(r.scale || 'pass_fail'))}}</span>
              </div>
            </div>
            <div style="color:var(--muted); margin-top:4px;">${{esc(r.criteria || '')}}</div>
          </div>`).join('');
        return `
          <div style="margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <strong style="font-size:0.95rem;">${{esc(layer.name)}}</strong>
              <span class="pill ${{layer.blocking ? 'bad' : 'amber'}}">${{layer.blocking ? 'Required Gate (100%)' : 'Target >= ' + Math.round((layer.pass_threshold || 0.75) * 100) + '%'}}</span>
            </div>
            ${{rows}}
          </div>`;
      }}).join('');
    }}

    function renderEvalRuns(runs) {{
      el('evalCountBadge').textContent = `${{runs.length}} run${{runs.length === 1 ? '' : 's'}}`;
      if (!runs.length) {{
        el('evalRunsContainer').innerHTML = '<div class="mono">No quality checks recorded yet. Click <strong>Run Check Now</strong> or <strong>Run All Agents</strong> above.</div>';
        return;
      }}
      el('evalRunsContainer').innerHTML = runs.map((run, idx) => {{
        const pct = Math.round((run.overall_score || 0) * 100);
        const agentLabel = formatLabel(run.agent_id || 'agent');
        const prev = runs.slice(idx + 1).find((r) => r.agent_id === run.agent_id);
        let deltaHtml = '';
        if (prev) {{
          const delta = Math.round(((run.overall_score || 0) - (prev.overall_score || 0)) * 100);
          if (delta < 0) deltaHtml = `<span class="pill bad">Regression ${{delta}}%</span>`;
          else if (delta > 0) deltaHtml = `<span class="pill ok">+${{delta}}% vs prev</span>`;
          else deltaHtml = `<span class="pill">0% vs prev</span>`;
        }}
        const dims = run.dimensions || [];
        const dimsHtml = dims.map((d) => `
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--border); font-size:0.84rem;">
            <div>
              <strong>${{esc(d.name)}}</strong>
              ${{d.skill ? `<span class="pill" style="margin-left:6px;">${{esc(formatLabel(d.skill))}}</span>` : ''}}
              <div style="color:var(--muted); font-size:0.78rem;">${{esc(d.detail || '')}}</div>
            </div>
            <div style="white-space:nowrap;">
              <span class="pill ${{d.passed ? 'ok' : 'bad'}}">${{Math.round((d.score || 0) * 100)}}%</span>
            </div>
          </div>`).join('');
        const cases = run.case_results || [];
        const casesHtml = cases.length ? `
          <details style="margin-top:10px;">
            <summary style="cursor:pointer; font-size:0.84rem; color:var(--accent); font-weight:600;">Per-Case Review Notes (${{cases.length}})</summary>
            <div style="margin-top:8px;">
              ${{cases.map((c) => `
                <div class="step-row">
                  <div><strong>${{esc(formatLabel(c.case_id))}}</strong> <span class="pill ${{c.passed ? 'ok' : 'bad'}}">${{c.passed ? 'Pass' : 'Fail'}}</span></div>
                  <div style="color:var(--muted); margin-top:3px;">${{esc(c.rationale || '')}}</div>
                </div>`).join('')}}
            </div>
          </details>` : '';
        const vertexBtn = run.vertex_console_url
          ? `<a class="btn" href="${{esc(run.vertex_console_url)}}" target="_blank" rel="noopener">Open in Vertex AI Console →</a>`
          : '';
        return `
          <div class="worker-card" style="margin-bottom:14px;">
            <div class="section-head" style="margin-bottom:8px;">
              <div>
                <h3 style="margin:0; font-size:1rem;">${{esc(agentLabel)}} ${{statusPill(run.status)}} <span class="pill blue">${{pct}}% overall</span> ${{deltaHtml}}</h3>
                <div style="margin-top:4px; font-size:0.78rem; color:var(--muted);">
                  Runner: ${{esc(formatLabel(run.runner || ''))}} · Source: ${{esc(formatLabel(run.trigger || 'manual'))}} · Samples: ${{esc(run.sample_count)}} (${{esc(formatLabel(run.sample_source || 'mixed'))}}) · ${{esc(run.created_at || '')}}
                </div>
              </div>
              <div style="display:flex; gap:8px; align-items:center;">
                <span class="pill ${{run.passed_gates ? 'ok' : 'bad'}}">Gates: ${{run.passed_gates ? 'Pass' : 'Fail'}}</span>
                ${{vertexBtn}}
              </div>
            </div>
            ${{dimsHtml}}
            ${{casesHtml}}
          </div>`;
      }}).join('');
    }}

    async function loadAgentsList() {{
      const res = await fetch('/api/evals/agents');
      if (!res.ok) return;
      const data = await res.json();
      const agents = data.agents || [];
      if (!agents.length) return;
      const sel = el('evalAgentSelect');
      const current = sel.value || 'discovery-scout';
      sel.innerHTML = agents.map((a) => `<option value="${{esc(a.slug)}}">${{esc(formatLabel(a.slug))}} (${{a.rubric_count}} checks)</option>`).join('');
      if (agents.some((a) => a.slug === current)) sel.value = current;
    }}

    async function loadRubricAndRuns() {{
      const agent = el('evalAgentSelect').value || 'discovery-scout';
      const [rubRes, runsRes, tracesRes] = await Promise.all([
        fetch('/api/evals/rubrics?agent=' + encodeURIComponent(agent)),
        fetch('/api/eval-runs'),
        fetch('/api/evals/traces?agent=' + encodeURIComponent(agent)),
      ]);
      if (rubRes.ok) renderRubrics(await rubRes.json());
      if (runsRes.ok) {{
        const data = await runsRes.json();
        renderEvalRuns(data.eval_runs || []);
      }}
      if (tracesRes.ok) {{
        const tdata = await tracesRes.json();
        const traces = tdata.traces || [];
        const sel = el('evalTraceSelect');
        const prev = sel.value;
        sel.innerHTML = '<option value="">All Samples (Batch)</option>' + traces.map((t) =>
          `<option value="${{esc(t.collection + '::' + t.trace_id)}}">${{esc(t.label)}}</option>`
        ).join('');
        if (prev && Array.from(sel.options).some((o) => o.value === prev)) sel.value = prev;
      }}
    }}

    async function triggerEval(allAgents) {{
      const btn = allAgents ? el('runAllEvalsBtn') : el('runEvalBtn');
      const orig = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Running...';
      try {{
        const traceVal = allAgents ? '' : (el('evalTraceSelect').value || '');
        const [traceCollection, traceId] = traceVal.includes('::') ? traceVal.split('::', 2) : ['', ''];
        const res = await fetch('/api/eval-runs/run', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            agent: el('evalAgentSelect').value,
            all_agents: !!allAgents,
            mode: el('evalModeSelect').value,
            sample_source: el('evalSampleSelect').value,
            trace_id: traceId || null,
            trace_collection: traceCollection || null,
          }}),
        }});
        const data = await res.json();
        if (!res.ok) {{
          showBanner(data.error || 'Eval run failed.', true);
        }} else if (allAgents) {{
          showBanner(`Completed quality checks across ${{(data.eval_runs || []).length}} agents.`, false);
          await loadRubricAndRuns();
        }} else {{
          showBanner(`Completed ${{formatLabel(data.agent_id || 'agent')}} (${{Math.round((data.overall_score || 0) * 100)}}% overall).`, false);
          await loadRubricAndRuns();
        }}
      }} catch (err) {{
        showBanner('Network error running eval: ' + err, true);
      }} finally {{
        btn.disabled = false;
        btn.textContent = orig;
      }}
    }}

    el('evalAgentSelect').onchange = loadRubricAndRuns;
    el('runEvalBtn').onclick = () => triggerEval(false);
    el('runAllEvalsBtn').onclick = () => triggerEval(true);
    el('refreshEvalsBtn').onclick = loadRubricAndRuns;
    loadAgentsList().then(loadRubricAndRuns);
  </script>
</body>
</html>
"""

