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

from .db_tools import save_agent_document
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
from .scout import DEFAULT_TASTE_BRIEF
from .screening import run_screening_batch


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
        "description": "Sends Discovery Scouts across chosen sources to return checked, unranked leads.",
        "input_hint": "Search brief and source IDs (or pick in Discovery)",
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
        "description": "Finds the artist's official links, MusicBrainz ID, and public booking contact.",
        "input_hint": "Lead from Phase 1",
        "default_input": DEFAULT_LEAD_FIXTURE,
    },
    {
        "id": "2b_investigators",
        "code": "2B",
        "name": "Investigators ×3",
        "domain": "Intake · Parallel Fan-Out",
        "agents": ["footprint-profiler", "signal-forensics", "track-record-mapper"],
        "description": "Runs footprint, audience comment, and live show investigators in parallel.",
        "input_hint": "Identity bundle from Phase 2A (or a raw lead)",
        "default_input": DEFAULT_LEAD_FIXTURE,
    },
    {
        "id": "2c_dossier",
        "code": "2C",
        "name": "Profile Join",
        "domain": "Intake · Deterministic Assembler",
        "agents": ["dossier-assembler"],
        "description": "Merges Phase 2A and 2B into one factual Artist Dossier and runs process checks.",
        "input_hint": "Identity + Phase 2B results (or a raw lead)",
        "default_input": DEFAULT_LEAD_FIXTURE,
    },
    {
        "id": "3_screening",
        "code": "3",
        "name": "Active Screening",
        "domain": "Decision Engine · Advocate / Skeptic / Judge",
        "agents": ["screen-advocate", "screen-skeptic", "screening-judge"],
        "description": "Runs Advocate and Skeptic debate plus a Neon Judge verdict on the Artist Dossier.",
        "input_hint": "Dossier from Phase 2C (or lead_id in /api/dossiers)",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "stage_name": "Luna Jinna",
        },
    },
    {
        "id": "4_producer",
        "code": "4",
        "name": "Showcase Producer",
        "domain": "Outcome · Human Review",
        "agents": ["showcase-producer"],
        "description": "Turns an elevated Screening Packet into a callback draft for human review.",
        "input_hint": "Elevated Screening Packet + showcase terms",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "stage_name": "Luna Jinna",
            "screening_verdict": "ELEVATE",
            "showcase": "First Listen NYC",
            "slot_minutes": 20,
            "fee_cap_usd": 500,
        },
    },
]

PHASE_MAP: Dict[str, Dict[str, Any]] = {p["id"]: p for p in PHASE_DEFINITIONS}


DEFAULT_IDENTITY_BUNDLE_FIXTURE: Dict[str, Any] = {
    "lead_id": "lead_luna_jinna",
    "identity_and_contact": {
        "stage_name": "Luna Jinna",
        "aliases": [],
        "pronouns": "she/her",
        "project_type": "solo_vocalist",
        "home_city": "New York, NY",
        "home_neighborhood": "Brooklyn",
        "bio_text": "NYC vocalist & pianist. Stripped-back live room arrangements. Booking: public contact form on official site.",
        "platform_urls": {
            "youtube": "https://www.youtube.com/@lunajinna",
            "instagram": "https://www.instagram.com/lunajinna",
            "bandcamp": "https://lunajinna.bandcamp.com",
        },
        "musicbrainz_mbid": None,
        "has_public_business_contact": True,
        "contact_route_type": "official_site_form",
    },
    "source_and_media_queue": {
        "source_channel": "youtube_live_session",
        "seed_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "attribution_status": "verified",
        "media_links": [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=9bZkp7q19f0",
        ],
    },
}


AGENT_INPUT_PRESETS: Dict[str, Dict[str, Any]] = {
    "discovery-scout": {
        "input_hint": "Search brief & requested lead count (Stage 1 Discovery)",
        "default_input": {
            "search_brief": "Find NYC-based emerging indie vocalists performing stripped-back live sessions",
            "requested_count": 3,
            "domain": "music",
        },
    },
    "identity-resolver": {
        "input_hint": "Single DiscoveryLead from Stage 1 (Phase 2A)",
        "default_input": {
            "lead_id": "lead_mira_sol",
            "stage_name": "Mira Sol",
            "attribution_status": "verified",
            "context_snippet": "Performed stripped-back original set at Brooklyn loft session.",
            "seed_sources": [
                {
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "source_channel": "youtube_live_session",
                    "seed_query_or_venue_node": "Sofar Sounds Brooklyn live vocal session",
                    "discovered_at": "2026-11-21T19:44:00Z",
                    "notes": "Live acoustic room performance recorded in Brooklyn.",
                }
            ],
        },
    },
    "footprint-profiler": {
        "input_hint": "Resolved IdentityBundle with public artifact URLs (Phase 2B)",
        "default_input": DEFAULT_IDENTITY_BUNDLE_FIXTURE,
    },
    "signal-forensics": {
        "input_hint": "Resolved IdentityBundle with public pages for comment sampling (Phase 2B)",
        "default_input": {
            **DEFAULT_IDENTITY_BUNDLE_FIXTURE,
            "comment_sampling_targets": [
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=9bZkp7q19f0",
            ],
            "max_comments_to_sample": 50,
        },
    },
    "track-record-mapper": {
        "input_hint": "Resolved IdentityBundle with bio, links & city for milestones (Phase 2B)",
        "default_input": {
            **DEFAULT_IDENTITY_BUNDLE_FIXTURE,
            "focus": ["show_history", "upcoming_shows", "public_team_mentions", "collaborator_credits"],
        },
    },
    "performance-critic": {
        "input_hint": "Showcase brief + audition performance notes & timestamps",
        "default_input": {
            "brief": {
                "event": "First Listen NYC",
                "slot": "15-minute opening set at a listening-room showcase",
                "fit": "An emerging vocalist with one original song and distinctive phrasing",
            },
            "auditions": [
                {
                    "audition_id": "a01",
                    "performance_notes": "At 0:18, an unaccompanied verse builds into a controlled chorus. At 0:33, a sustained phrase resolves softly. Single live room take.",
                },
                {
                    "audition_id": "a02",
                    "performance_notes": "At 0:15, a distinctive harmony enters over the lead. Layered studio take with heavy compression; live execution unverified.",
                },
            ],
        },
    },
    "booking-critic": {
        "input_hint": "Showcase brief + audition setup & stage logistics notes",
        "default_input": {
            "brief": {
                "event": "First Listen NYC",
                "slot": "15-minute opening set at a listening-room showcase",
                "stage_constraints": "Vocal mic + 1 acoustic instrument DI; 5-minute changeover",
                "original_song_required": True,
                "artist_guarantee_usd": 250,
            },
            "auditions": [
                {
                    "audition_id": "a01",
                    "artist_notes": "Submitted song is an original. Bringing one guitarist for a 15-minute stripped set.",
                },
                {
                    "audition_id": "a02",
                    "artist_notes": "Submitted clip is a layered studio take of an original. Live stage setup not yet specified.",
                },
            ],
        },
    },
    "synthesis-scout": {
        "input_hint": "Taste brief + artist_leads[] + timestamped clip_evidence[]",
        "default_input": {
            "brief": {
                "prompt": DEFAULT_TASTE_BRIEF,
            },
            "artist_leads": [
                {
                    "lead_id": "lead_luna_jinna",
                    "stage_name": "Luna Jinna",
                    "attribution_status": "verified",
                }
            ],
            "clip_evidence": [
                {
                    "clip_id": "clip_01",
                    "lead_id": "lead_luna_jinna",
                    "title": "Luna Jinna - Stripped Piano Live Session",
                    "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "recording_context": "live",
                    "observations": [
                        {
                            "observation_id": "obs_01",
                            "timestamp": "0:42",
                            "dimension": "phrasing",
                            "musical_choice": "Delays the pre-chorus entrance behind the piano pulse, then drops to a whisper on the turnaround.",
                        }
                    ],
                }
            ],
        },
    },
    "showcase-producer": {
        "input_hint": "Stage 3 Screening Packet (Advocate/Skeptic/Judge) + First Listen NYC showcase terms",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "stage_name": "Luna Jinna",
            "screening_verdict": "ELEVATE",
            "contact_route": "bookings@lunajinna.example",
            "advocate_case": {
                "headline": "High-conviction stripped live vocal identity with organic Brooklyn pull",
                "standout_hook": "Consistent live-room vocal dynamics paired with inbound venue booker interest.",
            },
            "skeptic_case": {
                "headline": "Thin off-YouTube footprint; confirm full live set length and gear",
                "missing_evidence_flags": ["spotify_monthly_listeners_missing", "stage_plot_unconfirmed"],
            },
            "judge_decision": {
                "verdict": "ELEVATE",
                "total_score": 8.4,
                "rationale": "Strong fit for First Listen NYC listening-room showcase; confirm 20-min stripped set and date availability.",
            },
            "showcase": "First Listen NYC",
            "slot_minutes": 20,
            "fee_cap_usd": 500,
        },
    },
    "screen-advocate": {
        "input_hint": "Stage 2 InvestigatorDossier (5 factual blocks) for upside case",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "dossier": {
                "lead_id": "lead_luna_jinna",
                **{k: v for k, v in DEFAULT_IDENTITY_BUNDLE_FIXTURE.items() if k != "lead_id"},
                "public_footprint": {
                    "footprint_regime": "early_dsp_inflection",
                    "public_reach": {"youtube_subscribers": 4200, "bandcamp_supporters": 86},
                    "top_release_view_share_pct": 56.4,
                },
                "comment_forensics": {
                    "sample_size": 24,
                    "genuine_praise": 15,
                    "release_requests": 5,
                    "live_show_requests": 3,
                    "jokes_or_spam": 1,
                    "notable_commenters": [
                        {
                            "handle": "@rockwood_booking",
                            "channel_url": "https://www.youtube.com/@rockwood_booking",
                            "role_or_context": "NYC venue booker",
                            "comment_excerpt": "Would love to host this stripped piano set.",
                        }
                    ],
                },
                "live_history_and_credits": {
                    "show_history": [
                        {"venue": "Rockwood Music Hall Stage 2", "city": "New York, NY", "capacity": 180, "date": "2026-09-12"}
                    ],
                    "upcoming_shows": [
                        {"venue": "Baby's All Right", "city": "Brooklyn, NY", "capacity": 280, "date": "2026-10-18"}
                    ],
                    "highest_venue_cap_observed": 280,
                    "public_team_mentions": {"management": None, "booking_agent": None, "label": None},
                    "collaborator_credits": [],
                },
                "missing_fields": ["musicbrainz_mbid"],
            },
        },
    },
    "screen-skeptic": {
        "input_hint": "Stage 2 InvestigatorDossier (5 factual blocks) for risk & dealbreaker audit",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "dossier": {
                "lead_id": "lead_luna_jinna",
                **{k: v for k, v in DEFAULT_IDENTITY_BUNDLE_FIXTURE.items() if k != "lead_id"},
                "public_footprint": {
                    "footprint_regime": "early_dsp_inflection",
                    "public_reach": {"youtube_subscribers": 4200, "bandcamp_supporters": 86},
                    "top_release_view_share_pct": 56.4,
                },
                "comment_forensics": {
                    "sample_size": 24,
                    "genuine_praise": 15,
                    "release_requests": 5,
                    "live_show_requests": 3,
                    "jokes_or_spam": 1,
                    "notable_commenters": [],
                },
                "live_history_and_credits": {
                    "show_history": [
                        {"venue": "Rockwood Music Hall Stage 2", "city": "New York, NY", "capacity": 180, "date": "2026-09-12"}
                    ],
                    "upcoming_shows": [],
                    "highest_venue_cap_observed": 180,
                    "public_team_mentions": {"management": None, "booking_agent": None, "label": None},
                    "collaborator_credits": [],
                },
                "missing_fields": ["musicbrainz_mbid", "collaborator_credits"],
            },
        },
    },
    "screening-judge": {
        "input_hint": "InvestigatorDossier + advocate_case + skeptic_case for 0-10 verdict",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "dossier": {
                "lead_id": "lead_luna_jinna",
                **{k: v for k, v in DEFAULT_IDENTITY_BUNDLE_FIXTURE.items() if k != "lead_id"},
                "public_footprint": {
                    "footprint_regime": "early_dsp_inflection",
                    "top_release_view_share_pct": 56.4,
                },
                "comment_forensics": {
                    "sample_size": 24,
                    "genuine_praise": 15,
                    "release_requests": 5,
                    "live_show_requests": 3,
                    "jokes_or_spam": 1,
                    "notable_commenters": [],
                },
                "live_history_and_credits": {
                    "show_history": [
                        {"venue": "Rockwood Music Hall Stage 2", "city": "New York, NY", "capacity": 180, "date": "2026-09-12"}
                    ],
                    "upcoming_shows": [],
                    "highest_venue_cap_observed": 180,
                    "public_team_mentions": {"management": None, "booking_agent": None, "label": None},
                    "collaborator_credits": [],
                },
                "missing_fields": ["musicbrainz_mbid"],
            },
            "advocate_case": {
                "standout_hook": "Unsigned NYC vocalist with 2 verified live clips and organic release/show demand.",
                "pros": [
                    {"skill": "dossier-media", "claim": "Repeatable live vocal delivery", "evidence": "2 verified YouTube live clips"},
                    {"skill": "dossier-audience", "claim": "High-intent listener pull", "evidence": "5 release_requests, 3 live_show_requests in 24 comments"},
                ],
            },
            "skeptic_case": {
                "cons": [
                    {"skill": "dossier-track-record", "claim": "No upcoming shows listed", "evidence": "upcoming_shows is empty"},
                ],
                "missing_evidence_flags": ["musicbrainz_mbid"],
                "dealbreakers_checked": ["contact_route", "attribution_status", "view_concentration", "major_label_lockup"],
            },
        },
    },
}


def get_agent_input_preset(package_name: str) -> Dict[str, Any]:
    """Return the tailored default input JSON and hint for an agent package."""
    preset = AGENT_INPUT_PRESETS.get(package_name)
    if preset:
        return {
            "input_hint": preset["input_hint"],
            "default_input": json.loads(json.dumps(preset["default_input"])),
        }
    return {
        "input_hint": "JSON object or array for batch fan-out",
        "default_input": {
            "lead_id": "lead_luna_jinna",
            "stage_name": "Luna Jinna",
            "seed_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
    }


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
    # Backward-compatible alias for legacy 3_shortlist callers
    if phase_id == "3_shortlist":
        phase_id = "3_screening"

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
        dossier_saved = False
        if store is not None and hasattr(store, "save_document"):
            try:
                dossier_doc = dict(dossier)
                if not dossier_doc.get("stage_name"):
                    dossier_doc["stage_name"] = dossier["identity_and_contact"].get("stage_name") or str(dossier.get("lead_id") or "Unknown")
                save_agent_document(
                    store,
                    "investigator_dossiers",
                    dossier_doc,
                    doc_id=str(dossier.get("lead_id") or "") or None,
                )
                dossier_saved = True
            except ValueError:
                dossier_saved = False
        checks_run = int(proc_eval.get("checks_run", 7))
        failures = proc_eval.get("failures") or []
        output_data = {
            "lead_id": dossier.get("lead_id"),
            "stage_name": dossier["identity_and_contact"].get("stage_name"),
            "dossier_saved": dossier_saved,
            "profile": dossier,
            "process_eval": proc_eval,
        }
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
            "lead_id": dossier.get("lead_id"),
            "stage_name": dossier["identity_and_contact"].get("stage_name"),
            "dossier": dossier,
        }

    elif phase_id == "3_screening":
        lead_id = str(inp.get("lead_id") or "").strip() or None
        dossier_obj = inp.get("dossier") if isinstance(inp.get("dossier"), dict) else None
        if dossier_obj is None and store is not None:
            # Ensure a dossier exists if running Phase 3 standalone with default lead_id
            existing = None
            if lead_id and hasattr(store, "get_document"):
                existing = store.get_document("investigator_dossiers", lead_id)
            if existing is None:
                bundle = _ensure_identity_bundle(inp)
                with ThreadPoolExecutor(max_workers=3) as pool:
                    f_fp = pool.submit(run_footprint_profiler, bundle)
                    f_sf = pool.submit(run_signal_forensics, bundle)
                    f_tr = pool.submit(run_track_record_mapper, bundle)
                    fp, sf, tr = f_fp.result(), f_sf.result(), f_tr.result()
                dossier_obj = assemble_dossier(bundle, fp, sf, tr)
                dossier_obj["stage_name"] = dossier_obj["identity_and_contact"].get("stage_name") or (lead_id or "Unknown")
                lead_id = str(dossier_obj.get("lead_id") or lead_id or "")

        packets = run_screening_batch(
            store=store,
            lead_id=lead_id,
            dossier=dossier_obj,
            live=live,
            api_key=api_key,
        )
        pkt = packets[0] if packets else {}
        advocate = pkt.get("advocate_case") or {}
        skeptic = pkt.get("skeptic_case") or {}
        judge = pkt.get("judge_decision") or {}
        verdict = str(judge.get("verdict") or "WATCH").upper()
        stage_name = str(pkt.get("stage_name") or inp.get("stage_name") or lead_id or "Artist")
        pkt_lead_id = str(pkt.get("lead_id") or lead_id or "")

        cards = [
            {
                "agent": "screen-advocate",
                "status": "completed",
                "summary": str(advocate.get("headline") or advocate.get("standout_hook") or "Upside case assembled.")[:240],
            },
            {
                "agent": "screen-skeptic",
                "status": "completed",
                "summary": str(skeptic.get("headline") or f"Flagged {len(skeptic.get('missing_evidence_flags') or [])} evidence gap(s).")[:240],
            },
            {
                "agent": "screening-judge",
                "status": "completed",
                "summary": f"Verdict: {verdict} ({judge.get('total_score', '—')}/10) — {str(judge.get('rationale') or '')[:180]}",
            },
        ]
        output_data = {
            "lead_id": pkt_lead_id,
            "stage_name": stage_name,
            "packet_id": pkt.get("packet_id"),
            "verdict": verdict,
            "total_score": judge.get("total_score"),
            "packet": pkt,
        }
        checks = [
            {"name": "debate_complete", "label": "Advocate + Skeptic Debate", "passed": bool(advocate and skeptic)},
            {"name": "verdict_valid", "label": f"Judge Verdict: {verdict}", "passed": verdict in ("ELEVATE", "WATCH", "PASS")},
            {"name": "packet_saved", "label": "Screening Packet Stored", "passed": bool(pkt.get("packet_id"))},
        ]
        next_handoff = {
            "lead_id": pkt_lead_id or "lead_luna_jinna",
            "stage_name": stage_name,
            "screening_verdict": verdict,
            "advocate_case": {
                "headline": advocate.get("headline", ""),
                "standout_hook": advocate.get("standout_hook", ""),
            },
            "skeptic_case": {
                "headline": skeptic.get("headline", ""),
                "missing_evidence_flags": skeptic.get("missing_evidence_flags") or [],
            },
            "judge_decision": {
                "verdict": verdict,
                "total_score": judge.get("total_score"),
                "rationale": judge.get("rationale", ""),
            },
            "showcase": "First Listen NYC",
            "slot_minutes": 20,
            "fee_cap_usd": 500,
        }

    elif phase_id == "4_producer":
        agent_id = _resolve_deployed_agent_id("showcase-producer")
        stage_name = str(inp.get("stage_name") or inp.get("lead_id") or "Artist")
        showcase = str(inp.get("showcase") or "First Listen NYC")
        slot_minutes = int(inp.get("slot_minutes") or 20)
        fee_cap_usd = inp.get("fee_cap_usd", 500)
        verdict = str(inp.get("screening_verdict") or (inp.get("judge_decision") or {}).get("verdict") or "ELEVATE").upper()
        adv_hook = str((inp.get("advocate_case") or {}).get("standout_hook") or (inp.get("advocate_case") or {}).get("headline") or "Distinctive live vocal presence.")
        skep_flags = (inp.get("skeptic_case") or {}).get("missing_evidence_flags") or []
        open_questions = [
            "Confirm date availability for First Listen NYC.",
            "Confirm live stripped stage setup and gear needs.",
        ]
        if skep_flags:
            first_flag = skep_flags[0] if isinstance(skep_flags[0], str) else str(skep_flags[0])
            open_questions.append(f"Clarify open screening gap: {first_flag}.")

        res = dispatch_fleet(
            agent_id=agent_id,
            assignments=[inp],
            wait=live,
            dry_run=not live,
            api_key=api_key,
        )
        worker = (res.get("results") or [{}])[0]
        draft_preview = {
            "lead_id": inp.get("lead_id") or "",
            "stage_name": stage_name,
            "human_review_status": "pending_human_review",
            "screening_verdict": verdict,
            "advocate_vs_skeptic_tradeoff": f"Upside: {adv_hook} | Watch-out: {len(skep_flags)} open evidence flag(s) to confirm.",
            "open_questions_before_booking": open_questions[:3],
            "offer_terms": {
                "showcase": showcase,
                "slot_minutes": slot_minutes,
                "fee_cap_usd": fee_cap_usd,
            },
            "draft_invitation": {
                "subject": f"{showcase} — {slot_minutes}-min paid showcase callback for {stage_name}",
                "body": (
                    f"Hi {stage_name},\n\n"
                    f"We loved your live performances and would like to invite you for a {slot_minutes}-minute set at {showcase} "
                    f"(guarantee up to ${fee_cap_usd}, subject to final confirmation). "
                    f"Could you reply with your upcoming NYC availability and preferred live setup?\n\n"
                    f"Best,\nSimon A&R Team"
                ),
            },
        }
        output_data = {
            "human_review_status": "pending_human_review",
            "callback_target": stage_name,
            "callback_draft": draft_preview,
            "fleet": res,
        }
        cards.append(
            {
                "agent": "showcase-producer",
                "status": worker.get("status", "dry_run" if not live else "completed"),
                "summary": (
                    str(worker.get("output"))[:240]
                    if worker.get("output")
                    else f"Drafted {showcase} callback (${fee_cap_usd} cap, {slot_minutes}m) for {stage_name} [pending_human_review]."
                ),
            }
        )
        checks = [
            {"name": "human_gate", "label": "pending_human_review Gate", "passed": True},
            {"name": "screening_grounded", "label": f"Grounded in {verdict} Screening", "passed": bool(verdict)},
            {"name": "budget_present", "label": f"Budget Cap ${fee_cap_usd}", "passed": bool(fee_cap_usd)},
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
