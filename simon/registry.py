"""Source Registry seeding/querying and Agent Run trace tracking helpers.

Backed by any Simon store (`FirestoreStore` on Cloud Run or `SimonStore` locally)
via the native JSON document API (`save_document`, `get_document`, `list_documents`).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


DEFAULT_SOURCES_SEED = (
    Path(__file__).resolve().parents[1] / "data" / "reference" / "discovery_sources_seed.json"
)
SOURCE_COLLECTION = "source_registry"
AGENT_RUNS_COLLECTION = "agent_runs"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ----------------------------------------------------------------------
# Discovery Source Registry (data/reference/discovery_sources_seed.json)
# ----------------------------------------------------------------------
def load_source_seed(seed_path: Optional[Path | str] = None) -> Dict[str, Any]:
    path = Path(seed_path) if seed_path is not None else DEFAULT_SOURCES_SEED
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("sources"), list):
        raise ValueError(f"Invalid discovery sources seed file: {path}")
    return raw


def seed_discovery_sources(
    store: Any,
    seed_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Idempotently upsert all curated reference sources into `source_registry`."""
    seed = load_source_seed(seed_path)
    sources = seed["sources"]
    seeded_ids: List[str] = []
    for src in sources:
        source_id = str(src.get("source_id") or "").strip()
        if not source_id:
            continue
        doc = dict(src)
        doc.setdefault("domain", seed.get("domain", "music"))
        doc.setdefault("schema_version", seed.get("schema_version", "1.0.0"))
        store.save_document(SOURCE_COLLECTION, source_id, doc)
        seeded_ids.append(source_id)
    return {
        "collection": SOURCE_COLLECTION,
        "domain": seed.get("domain", "music"),
        "schema_version": seed.get("schema_version", "1.0.0"),
        "seeded_count": len(seeded_ids),
        "source_ids": seeded_ids,
    }


def query_discovery_sources(
    store: Any,
    channel: Optional[str] = None,
    city: Optional[str] = None,
    tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Query `source_registry` documents with optional metadata filters."""
    docs = store.list_documents(SOURCE_COLLECTION, limit=max(limit, 200))
    results: List[Dict[str, Any]] = []
    city_lc = (city or "").strip().lower()
    for doc in docs:
        if channel and doc.get("source_channel") != channel:
            continue
        if tier and doc.get("career_tier") != tier:
            continue
        if status and doc.get("status") != status:
            continue
        if city_lc:
            loc = doc.get("location") or {}
            loc_city = str(loc.get("city") or "").lower()
            loc_area = str(loc.get("area") or "").lower()
            loc_scope = str(loc.get("scope") or "").lower()
            if city_lc not in loc_city and city_lc not in loc_area and loc_scope not in ("global", "national"):
                continue
        results.append(doc)
    results.sort(key=lambda item: (str(item.get("source_channel") or ""), str(item.get("name") or "")))
    return results[:limit]


def upsert_discovery_source(store: Any, source: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        raise ValueError("`source_id` is required.")
    if not str(source.get("name") or "").strip() or not str(source.get("url") or "").strip():
        raise ValueError("`name` and `url` are required.")
    doc = dict(source)
    doc.setdefault("status", "active")
    return store.save_document(SOURCE_COLLECTION, source_id, doc)


# ----------------------------------------------------------------------
# Agent Runs & Trace Tracking (`agent_runs` collection)
# ----------------------------------------------------------------------
def record_agent_run(
    store: Any,
    *,
    run_id: str,
    agent_id: str,
    stage: str = "fleet",
    status: str = "queued",
    agent_run_id: Optional[str] = None,
    parent_agent_run_id: Optional[str] = None,
    interaction_id: Optional[str] = None,
    target: Optional[str] = None,
    input_payload: Any = None,
    output_payload: Any = None,
    error: Optional[str] = None,
    traces: Optional[List[Dict[str, Any]]] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Create or update an `agent_runs` record with trace spans."""
    arun_id = agent_run_id or new_run_id("arun")
    now = utc_now_iso()
    record: Dict[str, Any] = {
        "agent_run_id": arun_id,
        "run_id": run_id,
        "parent_agent_run_id": parent_agent_run_id,
        "agent_id": agent_id,
        "interaction_id": interaction_id,
        "stage": stage,
        "target": target,
        "status": status,
        "started_at": started_at or now,
        "completed_at": completed_at or (now if status in ("completed", "failed", "dry_run") else None),
        "duration_ms": duration_ms,
        "input": input_payload,
        "output": output_payload,
        "error": error,
        "traces": list(traces or []),
    }
    return store.save_document(AGENT_RUNS_COLLECTION, arun_id, record)


def append_agent_trace(
    store: Any,
    agent_run_id: str,
    *,
    kind: str,
    summary: str,
    metadata: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
    output_payload: Any = None,
    error: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Append a trace span to an existing agent run document."""
    doc = store.get_document(AGENT_RUNS_COLLECTION, agent_run_id)
    if not doc:
        return None
    traces = list(doc.get("traces") or [])
    traces.append(
        {
            "step_id": f"step_{len(traces) + 1:02d}",
            "timestamp": utc_now_iso(),
            "kind": kind,
            "summary": summary,
            "metadata": dict(metadata or {}),
        }
    )
    doc["traces"] = traces
    if status:
        doc["status"] = status
        if status in ("completed", "failed", "dry_run") and not doc.get("completed_at"):
            doc["completed_at"] = utc_now_iso()
    if output_payload is not None:
        doc["output"] = output_payload
    if error is not None:
        doc["error"] = error
    return store.save_document(AGENT_RUNS_COLLECTION, agent_run_id, doc)


def list_agent_runs(
    store: Any,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    docs = store.list_documents(AGENT_RUNS_COLLECTION, limit=max(limit, 100))
    results: List[Dict[str, Any]] = []
    for doc in docs:
        if run_id and doc.get("run_id") != run_id:
            continue
        if agent_id and doc.get("agent_id") != agent_id:
            continue
        if status and doc.get("status") != status:
            continue
        results.append(doc)
    results.sort(key=lambda item: str(item.get("started_at") or item.get("updated_at") or ""), reverse=True)
    return results[:limit]


def record_fleet_agent_runs(
    store: Any,
    summary: Dict[str, Any],
    *,
    run_id: Optional[str] = None,
    stage: str = "fleet",
) -> List[Dict[str, Any]]:
    """Expand a `dispatch_fleet` summary into individual traceable `agent_runs` docs."""
    parent_run_id = run_id or summary.get("run_id") or new_run_id("run")
    summary["run_id"] = parent_run_id
    agent_id = str(summary.get("agent_id") or "")
    now = utc_now_iso()
    created: List[Dict[str, Any]] = []
    for worker in summary.get("workers") or []:
        w_status = str(worker.get("status") or "queued")
        if w_status == "dispatched":
            norm_status = "running"
        elif w_status in ("completed", "failed", "dry_run", "queued", "running"):
            norm_status = w_status
        else:
            norm_status = "running"
        traces: List[Dict[str, Any]] = [
            {
                "step_id": "step_01",
                "timestamp": now,
                "kind": "dispatch",
                "summary": f"Dispatched {agent_id} ({summary.get('mode', 'live')})",
                "metadata": {
                    "batch_id": summary.get("batch_id"),
                    "worker_index": worker.get("index"),
                    "interaction_id": worker.get("interaction_id"),
                },
            }
        ]
        if worker.get("output") is not None:
            traces.append(
                {
                    "step_id": "step_02",
                    "timestamp": now,
                    "kind": "output",
                    "summary": "Received agent output",
                    "metadata": {},
                }
            )
        if worker.get("error"):
            traces.append(
                {
                    "step_id": f"step_{len(traces) + 1:02d}",
                    "timestamp": now,
                    "kind": "error",
                    "summary": str(worker.get("error")),
                    "metadata": {},
                }
            )
        rec = record_agent_run(
            store,
            run_id=parent_run_id,
            agent_id=agent_id,
            stage=stage,
            status=norm_status,
            interaction_id=worker.get("interaction_id"),
            target=str(worker.get("target") or worker.get("assignment") or ""),
            input_payload=worker.get("assignment"),
            output_payload=worker.get("output"),
            error=worker.get("error"),
            traces=traces,
        )
        worker["agent_run_id"] = rec["agent_run_id"]
        created.append(rec)
    return created
