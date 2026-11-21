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
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from .db_tools import get_agent_document, list_agent_documents, save_agent_document
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
            workers.append(worker)
            if worker["contract_valid"] and isinstance(worker.get("output_json"), dict):
                try:
                    save_agent_document(store, "discovery_handoffs", worker["output_json"])
                except ValueError:
                    pass
        mode = "simulated"
    else:
        assignments = [
            {
                "run_id": f"{batch_id}_w{idx + 1}",
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
            "Follow your Layer 1 SYSTEM.md and Layer 2 music SKILL.md steps, run verify_handoff.py, "
            "save to simon-db, and return ONLY the verified DiscoveryHandoff v1.0.0 JSON object."
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
            workers.append(
                {
                    "index": idx,
                    "worker_id": f"agent_{idx + 1:02d}",
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
            )
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


def refresh_discovery_batch(
    store: SimonStore,
    batch_id: str,
    api_key: Optional[str] = None,
    request_fn: Callable[..., Tuple[int, Dict[str, Any]]] = _http_json,
) -> Optional[Dict[str, Any]]:
    """Fetch a batch from fleet_runs and poll Gemini for any in-progress live workers."""
    found = get_agent_document(store, "fleet_runs", batch_id)
    if not isinstance(found, dict):
        return None
    batch = found.get("data") if isinstance(found.get("data"), dict) else found
    if batch.get("mode") != "live":
        return batch

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

        worker["status"] = polled["status"]
        if polled.get("environment_id"):
            worker["environment_id"] = polled["environment_id"]
        if polled.get("steps"):
            worker["steps"] = polled["steps"]
        if polled.get("error"):
            worker["error"] = polled["error"]

        if polled["status"] == "completed":
            worker["output_text"] = polled.get("output_text")
            validation = _validate_handoff_payload(polled.get("output_json"))
            worker["output_json"] = validation.get("cleaned", polled.get("output_json"))
            worker["contract_valid"] = validation["valid"]
            worker["contract_errors"] = validation["errors"]
            worker["lead_count"] = validation["lead_count"]
            if validation["valid"] and isinstance(worker["output_json"], dict):
                try:
                    save_agent_document(store, "discovery_handoffs", worker["output_json"])
                except ValueError:
                    pass
        changed = True

    if changed:
        batch["updated_at"] = _utc_now_iso()
        save_agent_document(store, "fleet_runs", batch, doc_id=batch_id)
    return batch


_SHARED_CSS = """
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
  }
  .btn:hover { border-color: var(--accent); }
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
"""


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
        <h1>Simon <span class="pill amber">Stage 1 Discovery</span></h1>
        <p>Select sources from the registry, choose how many Discovery agents to fan out, and inspect each agent's <code>DiscoveryHandoff v1.0.0</code> output.</p>
      </div>
      <nav class="nav">
        <a href="/discovery" class="active">1. Discovery &amp; Sources</a>
        <a href="/traces" id="tracesNavLink">2. Agent Traces</a>
        <a href="/">3. Vocal Studio</a>
      </nav>
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
      el('tracesNavLink').href = `/traces?batch=${{encodeURIComponent(batch.batch_id)}}`;

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
            <div style="margin-top:auto; padding-top:6px;">
              <a class="mono" href="/traces?batch=${{encodeURIComponent(batch.batch_id)}}#${{esc(w.worker_id)}}">Inspect Steps &amp; Raw JSON →</a>
            </div>
          </div>`;
      }}).join('');

      const anyRunning = workers.some((w) => !['completed', 'failed', 'error', 'cancelled', 'timeout'].includes(w.status));
      if (anyRunning && !pollTimer) {{
        pollTimer = setInterval(async () => {{
          const res = await fetch(`/api/discovery/batches/${{encodeURIComponent(activeBatchId)}}`);
          if (res.ok) {{
            const updated = await res.json();
            renderBatch(updated);
          }}
        }}, 3500);
      }} else if (!anyRunning && pollTimer) {{
        clearInterval(pollTimer);
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


TRACES_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · Live Agent Traces &amp; Contract Inspector</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill ok">Live Agent Traces</span></h1>
        <p>Track dispatched Discovery agents as they run, inspect tool calls (<code>simon-db</code>, <code>google_search</code>, <code>code_execution</code>), and verify contract outputs.</p>
      </div>
      <nav class="nav">
        <a href="/discovery">1. Discovery &amp; Sources</a>
        <a href="/traces" class="active">2. Agent Traces</a>
        <a href="/">3. Vocal Studio</a>
      </nav>
    </header>

    <section class="card">
      <div class="section-head">
        <h2>Batch Trace Selector</h2>
        <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
          <select id="batchSelect" style="min-width:300px;"></select>
          <button id="refreshBtn" class="btn" type="button">Refresh Now</button>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.84rem; cursor:pointer;">
            <input type="checkbox" id="autoPollToggle" checked />
            <span>Auto-poll (3s)</span>
          </label>
        </div>
      </div>
      <div id="batchMeta" class="mono">Loading batches…</div>
    </section>

    <div id="traceWorkers" class="worker-grid"></div>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }}
    let currentBatchId = new URLSearchParams(window.location.search).get('batch') || '';
    let pollHandle = null;

    function statusPill(status) {{
      if (status === 'completed') return '<span class="pill ok">completed</span>';
      if (status === 'in_progress' || status === 'running' || status === 'queued') return '<span class="pill amber">' + esc(status) + '</span>';
      return '<span class="pill warn">' + esc(status || 'unknown') + '</span>';
    }}

    function renderTraceBatch(batch) {{
      if (!batch) {{
        el('batchMeta').textContent = 'No discovery batches found yet. Dispatch agents from /discovery.';
        el('traceWorkers').innerHTML = '';
        return;
      }}
      el('batchMeta').innerHTML = `Batch <strong>${{esc(batch.batch_id)}}</strong> · mode: <strong>${{esc(batch.mode)}}</strong> · agent: <strong>${{esc(batch.agent_id)}}</strong> · brief: "${{esc(batch.search_brief)}}" · updated: ${{esc(batch.updated_at)}}`;
      const workers = batch.workers || [];
      el('traceWorkers').innerHTML = workers.map((w) => {{
        const steps = w.steps || [];
        const stepsHtml = steps.length ? steps.map((st) => `
          <div class="step-row">
            <div style="display:flex; justify-content:space-between; gap:8px;">
              <strong>Step ${{esc(st.index)}} · ${{esc(st.type)}}</strong>
              <span class="mono">${{esc((st.tools || []).join(', '))}}</span>
            </div>
            <div style="color:var(--muted); margin-top:4px;">${{esc(st.preview || '')}}</div>
          </div>`).join('') : '<div class="mono">No steps captured yet (waiting on remote sandbox)…</div>';

        const errHtml = (w.contract_errors || []).length
          ? `<div class="pill warn">Contract errors: ${{esc(w.contract_errors.join(' | '))}}</div>`
          : (w.contract_valid === true ? '<div class="pill ok">DiscoveryHandoff v1.0.0 VALID</div>' : '');

        const jsonText = w.output_json ? JSON.stringify(w.output_json, null, 2) : (w.output_text || 'Pending output…');
        return `
          <div class="worker-card" id="${{esc(w.worker_id)}}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong>${{esc(w.worker_id)}}</strong>
              ${{statusPill(w.status)}}
            </div>
            <div class="mono">interaction_id: ${{esc(w.interaction_id || '—')}} · duration: ${{w.duration_ms || 0}}ms · leads: ${{w.lead_count || 0}}</div>
            <div style="display:flex; gap:5px; flex-wrap:wrap;">
              ${{(w.assigned_sources || []).map((s) => `<span class="pill blue">${{esc(s.name)}}</span>`).join('')}}
            </div>
            ${{errHtml}}
            <div>
              <div style="font-size:0.78rem; font-weight:700; text-transform:uppercase; color:var(--muted); margin-bottom:6px;">Execution Trace</div>
              ${{stepsHtml}}
            </div>
            <details>
              <summary style="cursor:pointer; font-size:0.84rem; color:var(--teal); font-weight:600;">Inspect Raw Contract Output JSON</summary>
              <pre class="json-view">${{esc(jsonText)}}</pre>
            </details>
          </div>`;
      }}).join('');
    }}

    async function loadBatch(batchId) {{
      if (!batchId) return;
      currentBatchId = batchId;
      const res = await fetch(`/api/discovery/batches/${{encodeURIComponent(batchId)}}`);
      if (res.ok) renderTraceBatch(await res.json());
    }}

    async function loadBatches() {{
      const res = await fetch('/api/discovery/batches');
      const data = await res.json();
      const batches = data.batches || [];
      const sel = el('batchSelect');
      sel.innerHTML = '';
      batches.forEach((b) => {{
        const label = `${{b.batch_id}} (${{b.mode}} · ${{b.completed}}/${{b.agent_count}} done · ${{b.total_leads}} leads)`;
        sel.add(new Option(label, b.batch_id));
      }});
      if (!batches.length) {{ renderTraceBatch(null); return; }}
      const chosen = batches.some((b) => b.batch_id === currentBatchId) ? currentBatchId : batches[0].batch_id;
      sel.value = chosen;
      await loadBatch(chosen);
    }}

    el('batchSelect').onchange = () => loadBatch(el('batchSelect').value);
    el('refreshBtn').onclick = () => loadBatch(currentBatchId);

    function resetPolling() {{
      if (pollHandle) clearInterval(pollHandle);
      if (el('autoPollToggle').checked) {{
        pollHandle = setInterval(() => {{ if (currentBatchId) loadBatch(currentBatchId); }}, 3000);
      }}
    }}
    el('autoPollToggle').onchange = resetPolling;

    loadBatches().then(resetPolling);
  </script>
</body>
</html>
"""
