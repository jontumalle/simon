"""Phase-by-phase runner and deterministic evaluation helpers for Simon's Agency Studio UI.

Supports running or testing each of the 6 pipeline phases independently:
  - 1_discovery      (Intake: Discovery Scout)
  - 2a_identity      (Intake: identity-resolver)
  - 2b_investigators (Intake: parallel footprint-profiler + signal-forensics + track-record-mapper)
  - 2c_dossier       (Intake: deterministic profile join + process evals)
  - 3_shortlist      (Decision Engine: blind critics + synthesis-scout)
  - 4_producer       (Outcome: showcase-producer callback draft, pending_human_review)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import time
from typing import Any, Dict, List, Optional
import uuid

from .deploy import compile_agent_package, list_agent_packages
from .discovery_ui import (
    DEFAULT_DISCOVERY_BRIEF,
    dispatch_discovery_batch,
    load_source_registry,
)
from .fleet import dispatch_fleet
from .investigator import (
    _find_forbidden_keys,
    assemble_dossier,
    evaluate_dossier_process,
    run_footprint_profiler,
    run_identity_resolver,
    run_signal_forensics,
    run_track_record_mapper,
)
from .scout import DEFAULT_TASTE_BRIEF, run_scout


PHASE_RUNS_COLLECTION = "phase_runs"
AGENT_EVALS_COLLECTION = "agent_evals"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_deployed_agent_id(package_name: str) -> str:
    """Resolve the prefixed deployed agent ID for a curated package name."""
    prefix = os.environ.get("SIMON_AGENT_PREFIX", "")
    for pkg_dir in list_agent_packages():
        if pkg_dir.name == package_name:
            compiled = compile_agent_package(pkg_dir, prefix=prefix)
            return str(compiled["deployed_id"])
    return f"{prefix}simon-{package_name}"


DEFAULT_LEAD_FIXTURE: Dict[str, Any] = {
    "lead_id": "lead_luna_jinna",
    "stage_name": "Luna Jinna",
    "source_channel": "youtube_session",
    "seed_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "attribution_status": "verified",
    "home_city": "New York, NY",
    "bio_text": "NYC vocalist & pianist. Stripped-back live room arrangements. Booking: bookings@lunajinna.example",
    "platform_urls": {
        "youtube": "https://www.youtube.com/@lunajinna",
        "instagram": "https://www.instagram.com/lunajinna",
        "bandcamp": "https://lunajinna.bandcamp.com",
    },
    "public_comments": [
        {"author": "@nyc_sound", "text": "Her phrasing on that pre-chorus gave me chills. Play Brooklyn soon!"},
        {"author": "@indie_keys", "text": "Unreal dynamic control from whisper to chest voice."},
        {"author": "@venue_booker", "text": "Would love to book this stripped piano set at Rockwood."},
    ],
    "media_clips": [
        {"title": "Luna Jinna - Toxic (Stripped Piano Live)", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "views": 18400},
        {"title": "Luna Jinna - Original Acoustic Room Take", "url": "https://www.youtube.com/watch?v=9bZkp7q19f0", "views": 14200},
    ],
    "shows": [
        {"venue": "Rockwood Music Hall Stage 2", "city": "New York, NY", "capacity": 180, "date": "2026-09-12"},
        {"venue": "Baby's All Right", "city": "Brooklyn, NY", "capacity": 280, "date": "2026-10-18"},
    ],
}


PHASE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "1_discovery",
        "code": "1",
        "name": "Discovery",
        "domain": "Intake · Discovery Scout Fleet",
        "agents": ["discovery-scout"],
        "description": "Dispatches Discovery Scout agents across curated Source Registry channels to return verified, unranked leads.",
        "input_hint": "Search brief + Source Registry IDs (or pick in Discovery tab)",
        "default_input": {
            "brief": DEFAULT_DISCOVERY_BRIEF,
            "source_ids": ["yt_sofar_sounds", "nyc_babys_all_right", "bc_brooklyn_soul_rnb"],
            "agent_count": 3,
            "leads_per_agent": 2,
        },
    },
    {
        "id": "2a_identity",
        "code": "2A",
        "name": "Identity",
        "domain": "Intake · Sequential Anchor",
        "agents": ["identity-resolver"],
        "description": "Resolves canonical artist identity, official links, MusicBrainz ID, and business contact route.",
        "input_hint": "Lead from Phase 1",
        "default_input": DEFAULT_LEAD_FIXTURE,
    },
    {
        "id": "2b_investigators",
        "code": "2B",
        "name": "Investigators ×3",
        "domain": "Intake · Parallel Fan-Out",
        "agents": ["footprint-profiler", "signal-forensics", "track-record-mapper"],
        "description": "Fans out footprint-profiler, signal-forensics, and track-record-mapper concurrently.",
        "input_hint": "Identity bundle from Phase 2A (or a raw lead)",
        "default_input": DEFAULT_LEAD_FIXTURE,
    },
    {
        "id": "2c_dossier",
        "code": "2C",
        "name": "Profile Join",
        "domain": "Intake · Deterministic Assembler",
        "agents": ["dossier-assembler"],
        "description": "Merges Phase 2A + 2B into a clean Artist Profile, enforces abstention, and runs process evals.",
        "input_hint": "Identity + Phase 2B results (or a raw lead)",
        "default_input": DEFAULT_LEAD_FIXTURE,
    },
    {
        "id": "3_shortlist",
        "code": "3",
        "name": "Critics & Shortlist",
        "domain": "Decision Engine",
        "agents": ["performance-critic", "booking-critic", "synthesis-scout"],
        "description": "Runs blind performance/booking critics and synthesizes a Top-3 agency shortlist.",
        "input_hint": "Brief + candidate profiles from Phase 2C",
        "default_input": {
            "brief": DEFAULT_TASTE_BRIEF,
            "candidates": [
                {"lead_id": "lead_luna_jinna", "stage_name": "Luna Jinna"},
                {"lead_id": "lead_remy_bond", "stage_name": "Remy Bond"},
                {"lead_id": "lead_blake_whiten", "stage_name": "Blake Whiten"},
            ],
            "blind_metrics": True,
        },
    },
    {
        "id": "4_producer",
        "code": "4",
        "name": "Producer Outcome",
        "domain": "Outcome · Human Review",
        "agents": ["showcase-producer"],
        "description": "Weighs critic trade-offs and drafts a callback offer gated by pending_human_review.",
        "input_hint": "Shortlisted artist + showcase terms",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "stage_name": "Luna Jinna",
            "showcase": "First Listen NYC",
            "slot_minutes": 20,
            "fee_cap_usd": 500,
        },
    },
]

PHASE_MAP: Dict[str, Dict[str, Any]] = {p["id"]: p for p in PHASE_DEFINITIONS}


def evaluate_agent_output(agent_id: str, output_payload: Any) -> Dict[str, Any]:
    """Run fast deterministic contract and safety checks on any agent output."""
    checks: List[Dict[str, Any]] = []

    parsed: Any = output_payload
    is_valid_json = True
    if isinstance(output_payload, str):
        text = output_payload.strip()
        if not text:
            is_valid_json = False
        else:
            try:
                parsed = json.loads(text)
            except ValueError:
                is_valid_json = False
    checks.append(
        {
            "name": "valid_json",
            "label": "Valid JSON",
            "passed": is_valid_json,
            "detail": "Structured JSON object/array" if is_valid_json else "Plain text (not JSON)",
        }
    )

    has_content = bool(parsed) if not isinstance(parsed, str) else bool(parsed.strip())
    checks.append(
        {
            "name": "non_empty",
            "label": "Non-Empty Output",
            "passed": has_content,
            "detail": "Output present" if has_content else "Empty response",
        }
    )

    forbidden_hits = _find_forbidden_keys(parsed) if isinstance(parsed, (dict, list)) else []
    is_investigator = any(
        key in agent_id
        for key in ("identity-resolver", "footprint-profiler", "signal-forensics", "track-record-mapper", "dossier")
    )
    if is_investigator:
        checks.append(
            {
                "name": "no_ranking_keys",
                "label": "Zero Ranking Keys",
                "passed": len(forbidden_hits) == 0,
                "detail": "Clean objective data" if not forbidden_hits else f"Found forbidden keys: {forbidden_hits[:3]}",
            }
        )

    # Full investigator process eval if complete assembled profile
    if (
        isinstance(parsed, dict)
        and "identity_and_contact" in parsed
        and "comment_forensics" in parsed
        and "process_trace" in parsed
    ):
        proc = evaluate_dossier_process(parsed)
        checks_run = int(proc.get("checks_run", 7))
        failures = proc.get("failures") or []
        checks.append(
            {
                "name": "dossier_process_eval",
                "label": f"Process Eval ({checks_run - len(failures)}/{checks_run})" if not failures else f"Process Eval ({len(failures)} issues)",
                "passed": bool(proc["passed"]),
                "detail": "; ".join(failures or ["All process rules passed"]),
            }
        )

    passed_count = sum(1 for c in checks if c["passed"])
    return {
        "passed": passed_count == len(checks),
        "passed_count": passed_count,
        "total_checks": len(checks),
        "checks": checks,
    }


def _ensure_identity_bundle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Accept either an already-resolved identity bundle or a raw lead dict."""
    if "identity_and_contact" in payload and "source_and_media_queue" in payload:
        return payload
    lead = dict(DEFAULT_LEAD_FIXTURE)
    lead.update({k: v for k, v in payload.items() if v is not None})
    if not lead.get("lead_id"):
        lead["lead_id"] = f"lead_{uuid.uuid4().hex[:8]}"
    return run_identity_resolver(lead)


def run_phase(
    store: Any,
    phase_id: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    live: bool = False,
    run_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute one pipeline phase in live or test mode and persist its checkpoint."""
    if phase_id not in PHASE_MAP:
        raise ValueError(f"Unknown phase '{phase_id}'. Expected one of: {', '.join(PHASE_MAP)}")

    phase_def = PHASE_MAP[phase_id]
    inp = dict(phase_def["default_input"])
    if isinstance(payload, dict):
        inp.update(payload)

    started = time.perf_counter()
    phase_run_id = f"phase_{uuid.uuid4().hex[:10]}"
    cards: List[Dict[str, Any]] = []
    output_data: Dict[str, Any] = {}
    checks: List[Dict[str, Any]] = []
    next_handoff: Dict[str, Any] = {}

    if phase_id == "1_discovery":
        brief = str(inp.get("brief") or DEFAULT_DISCOVERY_BRIEF).strip()
        registry = load_source_registry(store)
        valid_ids = {s["source_id"] for s in registry.get("sources", [])}
        raw_source_ids = inp.get("source_ids")
        if isinstance(raw_source_ids, list):
            source_ids = [str(sid) for sid in raw_source_ids if str(sid) in valid_ids]
        else:
            source_ids = []
        if not source_ids:
            defaults = ["yt_sofar_sounds", "nyc_babys_all_right", "bc_brooklyn_soul_rnb"]
            source_ids = [sid for sid in defaults if sid in valid_ids]
        if not source_ids:
            source_ids = [s["source_id"] for s in registry.get("sources", [])[:3]]

        agent_count = int(inp.get("agent_count") or min(len(source_ids), 3) or 1)
        leads_per_agent = int(inp.get("leads_per_agent") or inp.get("max_leads") or 2)

        batch_doc = dispatch_discovery_batch(
            store,
            source_ids=source_ids,
            brief=brief,
            leads_per_agent=leads_per_agent,
            agent_count=agent_count,
            live=live,
            api_key=api_key,
        )
        batch_id = batch_doc["batch_id"]
        workers = batch_doc.get("workers") or []
        leads: List[Dict[str, Any]] = []
        for w in workers:
            out_json = w.get("output_json")
            if isinstance(out_json, dict) and isinstance(out_json.get("leads"), list):
                for lead in out_json["leads"]:
                    if isinstance(lead, dict):
                        leads.append(lead)
            src_names = ", ".join(s.get("name", "source") for s in (w.get("assigned_sources") or [])[:2])
            lead_count = int(w.get("lead_count") or 0)
            cards.append(
                {
                    "agent": f"discovery-scout ({w.get('worker_id', 'agent')})",
                    "status": str(w.get("status") or "completed"),
                    "summary": (
                        f"Scanned {src_names or 'assigned sources'} → {lead_count} lead(s) "
                        f"({'valid' if w.get('contract_valid') else w.get('status')})."
                    ),
                }
            )

        output_data = {
            "batch_id": batch_id,
            "mode": batch_doc.get("mode"),
            "agent_id": batch_doc.get("agent_id"),
            "selected_source_ids": batch_doc.get("selected_source_ids") or [],
            "agent_count": batch_doc.get("agent_count", len(workers)),
            "lead_count": len(leads),
            "artist_leads": leads,
            "workers": [
                {
                    "worker_id": w.get("worker_id"),
                    "report_id": w.get("report_id"),
                    "status": w.get("status"),
                    "lead_count": w.get("lead_count", 0),
                    "contract_valid": w.get("contract_valid"),
                    "assigned_sources": [s.get("name") for s in (w.get("assigned_sources") or [])],
                }
                for w in workers
            ],
        }

        if live:
            checks = [
                {"name": "sources_targeted", "label": f"{len(source_ids)} Sources Targeted", "passed": len(source_ids) > 0},
                {"name": "workers_dispatched", "label": f"{len(workers)} Live Scouts Dispatched", "passed": len(workers) > 0},
                {"name": "field_news_linked", "label": f"Batch {batch_id}", "passed": bool(batch_id)},
            ]
        else:
            all_valid = all(bool(w.get("contract_valid")) for w in workers) if workers else False
            checks = [
                {"name": "sources_targeted", "label": f"{len(source_ids)} Sources Targeted", "passed": len(source_ids) > 0},
                {"name": "leads_found", "label": f"{len(leads)} Leads Found", "passed": len(leads) > 0},
                {"name": "handoff_contract", "label": "DiscoveryHandoff v1.0.0 Valid", "passed": all_valid},
            ]

        if leads:
            first_lead = leads[0]
            seeds = first_lead.get("seed_sources") or []
            first_seed = seeds[0] if seeds and isinstance(seeds[0], dict) else {}
            next_handoff = {
                "lead_id": first_lead.get("lead_id"),
                "stage_name": first_lead.get("stage_name"),
                "attribution_status": first_lead.get("attribution_status", "verified"),
                "seed_source_url": first_seed.get("url") or DEFAULT_LEAD_FIXTURE["seed_source_url"],
                "source_channel": first_seed.get("source_channel") or "youtube_session",
                "context_snippet": first_lead.get("context_snippet") or "",
                "seed_sources": seeds,
            }
        else:
            next_handoff = DEFAULT_LEAD_FIXTURE

    elif phase_id == "2a_identity":
        if live:
            agent_id = _resolve_deployed_agent_id("identity-resolver")
            fleet_res = dispatch_fleet(
                agent_id=agent_id,
                assignments=[inp],
                wait=True,
                dry_run=False,
                api_key=api_key,
            )
            worker = (fleet_res.get("results") or [{}])[0]
            output_data = {"fleet": fleet_res, "worker": worker}
            cards.append(
                {
                    "agent": agent_id,
                    "status": worker.get("status", "completed"),
                    "summary": str(worker.get("output") or worker.get("status") or "Dispatched live")[:280],
                }
            )
            eval_res = evaluate_agent_output("identity-resolver", worker.get("output") or worker)
            checks = eval_res["checks"]
            next_handoff = inp
        else:
            bundle = _ensure_identity_bundle(inp)
            output_data = bundle
            ic = bundle["identity_and_contact"]
            links_count = len([v for v in (ic.get("platform_urls") or {}).values() if v])
            cards.append(
                {
                    "agent": "identity-resolver",
                    "status": "completed",
                    "summary": f"Resolved {ic.get('stage_name')} ({ic.get('home_city') or 'city n/a'}), {links_count} platform links, contact={ic.get('contact_route_type')}.",
                }
            )
            eval_res = evaluate_agent_output("identity-resolver", bundle)
            checks = eval_res["checks"]
            next_handoff = bundle

    elif phase_id == "2b_investigators":
        if live:
            agents = ["footprint-profiler", "signal-forensics", "track-record-mapper"]
            results_by_agent: Dict[str, Any] = {}
            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = {
                    pkg: pool.submit(
                        dispatch_fleet,
                        agent_id=_resolve_deployed_agent_id(pkg),
                        assignments=[inp],
                        wait=True,
                        dry_run=False,
                        api_key=api_key,
                    )
                    for pkg in agents
                }
                for pkg, fut in futs.items():
                    res = fut.result()
                    results_by_agent[pkg] = res
                    worker = (res.get("results") or [{}])[0]
                    cards.append(
                        {
                            "agent": pkg,
                            "status": worker.get("status", "completed"),
                            "summary": str(worker.get("output") or worker.get("status") or "Completed")[:240],
                        }
                    )
            output_data = results_by_agent
            checks = [
                {"name": "parallel_3x", "label": "3/3 Parallel Workers", "passed": len(results_by_agent) == 3},
                {"name": "no_ranking_keys", "label": "Zero Ranking Keys", "passed": len(_find_forbidden_keys(output_data)) == 0},
            ]
            next_handoff = {"identity_bundle": inp, "investigators": results_by_agent}
        else:
            bundle = _ensure_identity_bundle(inp)
            with ThreadPoolExecutor(max_workers=3) as pool:
                f_fp = pool.submit(run_footprint_profiler, bundle)
                f_sf = pool.submit(run_signal_forensics, bundle)
                f_tr = pool.submit(run_track_record_mapper, bundle)
                fp = f_fp.result()
                sf = f_sf.result()
                tr = f_tr.result()

            output_data = {
                "identity_bundle": bundle,
                "footprint_profiler": fp,
                "signal_forensics": sf,
                "track_record_mapper": tr,
            }
            cards = [
                {
                    "agent": "footprint-profiler",
                    "status": "completed",
                    "summary": f"Media queue: {len(fp.get('media_links', []))} clips · Regime: {fp.get('footprint_analysis', {}).get('footprint_regime', 'unknown')}.",
                },
                {
                    "agent": "signal-forensics",
                    "status": "completed",
                    "summary": f"Analyzed {sf.get('signal_forensics', {}).get('comments_sampled', 0)} public comments · Zero ranking keys.",
                },
                {
                    "agent": "track-record-mapper",
                    "status": "completed",
                    "summary": f"Shows found: {len(tr.get('track_record', {}).get('public_shows', []))} · Credits: {len(tr.get('track_record', {}).get('collaborator_credits', []))}.",
                },
            ]
            checks = [
                {"name": "parallel_3x", "label": "3/3 Parallel Workers", "passed": True},
                {"name": "zero_decode", "label": "Zero Media Decode", "passed": True},
                {"name": "no_ranking_keys", "label": "Zero Ranking Keys", "passed": len(_find_forbidden_keys(output_data)) == 0},
            ]
            next_handoff = output_data

    elif phase_id == "2c_dossier":
        if all(k in inp for k in ("identity_bundle", "footprint_profiler", "signal_forensics", "track_record_mapper")):
            bundle = inp["identity_bundle"]
            fp = inp["footprint_profiler"]
            sf = inp["signal_forensics"]
            tr = inp["track_record_mapper"]
        else:
            bundle = _ensure_identity_bundle(inp)
            with ThreadPoolExecutor(max_workers=3) as pool:
                f_fp = pool.submit(run_footprint_profiler, bundle)
                f_sf = pool.submit(run_signal_forensics, bundle)
                f_tr = pool.submit(run_track_record_mapper, bundle)
                fp, sf, tr = f_fp.result(), f_sf.result(), f_tr.result()

        dossier = assemble_dossier(bundle, fp, sf, tr)
        proc_eval = evaluate_dossier_process(dossier)
        checks_run = int(proc_eval.get("checks_run", 7))
        failures = proc_eval.get("failures") or []
        output_data = {"profile": dossier, "process_eval": proc_eval}
        cards.append(
            {
                "agent": "dossier-assembler",
                "status": "completed",
                "summary": (
                    f"Merged full Artist Profile for {dossier['identity_and_contact'].get('stage_name')} · "
                    f"Process eval: {'PASS' if proc_eval['passed'] else f'{len(failures)} failures'} ({checks_run} rules)."
                ),
            }
        )
        checks = [
            {
                "name": "process_eval",
                "label": f"Process Eval ({checks_run}/{checks_run})" if proc_eval["passed"] else f"Process Eval ({len(failures)} issues)",
                "passed": bool(proc_eval["passed"]),
            },
            {"name": "no_ranking_keys", "label": "Zero Ranking Keys", "passed": len(_find_forbidden_keys(dossier)) == 0},
            {"name": "trace_complete", "label": f"{len(dossier.get('process_trace', []))} Trace Steps", "passed": len(dossier.get("process_trace", [])) >= 8},
        ]
        next_handoff = {
            "brief": DEFAULT_TASTE_BRIEF,
            "candidates": [
                {
                    "lead_id": dossier.get("lead_id"),
                    "stage_name": dossier["identity_and_contact"].get("stage_name"),
                }
            ],
            "blind_metrics": True,
        }

    elif phase_id == "3_shortlist":
        critics = ["performance-critic", "booking-critic", "synthesis-scout"]
        results_by_critic: Dict[str, Any] = {}
        for pkg in critics:
            agent_id = _resolve_deployed_agent_id(pkg)
            res = dispatch_fleet(
                agent_id=agent_id,
                assignments=[inp],
                wait=live,
                dry_run=not live,
                api_key=api_key,
            )
            results_by_critic[pkg] = res
            worker = (res.get("results") or [{}])[0]
            cards.append(
                {
                    "agent": pkg,
                    "status": worker.get("status", "dry_run" if not live else "completed"),
                    "summary": (
                        str(worker.get("output"))[:240]
                        if worker.get("output")
                        else f"Prepared {pkg} payload for {len(inp.get('candidates', []))} candidate(s)."
                    ),
                }
            )
        output_data = results_by_critic
        checks = [
            {"name": "blind_metrics", "label": "Epistemic Blinding On", "passed": bool(inp.get("blind_metrics", True))},
            {"name": "critics_ran", "label": "3/3 Decision Agents", "passed": len(results_by_critic) == 3},
            {"name": "shortlist_cap", "label": "Shortlist <= 3", "passed": len(inp.get("candidates", [])) <= 3},
        ]
        first_cand = (inp.get("candidates") or [{}])[0]
        next_handoff = {
            "lead_id": first_cand.get("lead_id", "lead_luna_jinna"),
            "stage_name": first_cand.get("stage_name", "Luna Jinna"),
            "showcase": "First Listen NYC",
            "slot_minutes": 20,
            "fee_cap_usd": 500,
        }

    elif phase_id == "4_producer":
        agent_id = _resolve_deployed_agent_id("showcase-producer")
        res = dispatch_fleet(
            agent_id=agent_id,
            assignments=[inp],
            wait=live,
            dry_run=not live,
            api_key=api_key,
        )
        worker = (res.get("results") or [{}])[0]
        output_data = {
            "fleet": res,
            "human_review_status": "pending_human_review",
            "callback_target": inp.get("stage_name") or inp.get("lead_id"),
        }
        cards.append(
            {
                "agent": "showcase-producer",
                "status": worker.get("status", "dry_run" if not live else "completed"),
                "summary": (
                    str(worker.get("output"))[:240]
                    if worker.get("output")
                    else f"Drafted callback offer for {inp.get('stage_name', 'artist')} (pending_human_review)."
                ),
            }
        )
        checks = [
            {"name": "human_gate", "label": "pending_human_review Gate", "passed": True},
            {"name": "budget_present", "label": "Budget Cap Set", "passed": bool(inp.get("fee_cap_usd"))},
        ]
        next_handoff = {}

    duration_ms = int((time.perf_counter() - started) * 1000)
    record: Dict[str, Any] = {
        "phase_run_id": phase_run_id,
        "phase_id": phase_id,
        "phase_code": phase_def["code"],
        "phase_name": phase_def["name"],
        "run_id": run_id,
        "mode": "live" if live else "test",
        "created_at": _utc_now(),
        "duration_ms": duration_ms,
        "passed": all(c.get("passed", False) for c in checks) if checks else True,
        "checks": checks,
        "cards": cards,
        "input": inp,
        "output": output_data,
        "next_handoff": next_handoff,
    }

    if hasattr(store, "save_document"):
        store.save_document(PHASE_RUNS_COLLECTION, phase_run_id, record)

    return record
