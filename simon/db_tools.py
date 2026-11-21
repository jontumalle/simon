"""Permissioned, contract-validated DB gateway for Managed Agents (Firestore + SQLite)."""

from __future__ import annotations

from datetime import datetime, timezone
import hmac
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import uuid

ALLOWED_AGENT_COLLECTIONS = frozenset(
    {
        "source_registry",
        "discovered_sources",
        "discovery_handoffs",
        "investigator_dossiers",
        "leads",
        "fleet_runs",
        "agent_runs",
        "agent_reports",
        "screening_packets",
        "screening_labels",
        "judging_models",
        "taste_scores",
        "eval_runs",
    }
)

VALID_SCREENING_VERDICTS = frozenset({"elevate", "watch", "pass"})

REPORT_FORBIDDEN_KEYS = frozenset(
    {
        "interaction_id",
        "environment_id",
        "metadata",
        "raw_trace",
        "trace_id",
    }
)

VALID_REPORT_STATUSES = frozenset({"starting", "in_motion", "completed", "blocked"})
VALID_REPORT_PHASES = frozenset({"looking_at", "finding", "analysis", "saved"})


def sanitize_agent_report(obj: Any) -> Any:
    """Recursively strip engineering telemetry keys from human-first agent reports."""
    if isinstance(obj, dict):
        return {
            k: sanitize_agent_report(v)
            for k, v in obj.items()
            if k not in REPORT_FORBIDDEN_KEYS
        }
    if isinstance(obj, list):
        return [sanitize_agent_report(item) for item in obj]
    return obj

VALID_SOURCE_CHANNELS = frozenset(
    {
        "youtube_live_session",
        "diy_venue_calendar",
        "diy_venue_flyer_ocr",
        "bandcamp_local_arrival",
        "open_mic_lineup",
        "bgv_or_session_credit_graph",
        "musicbrainz",
        "event_listing",
        "other",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def verify_agent_db_auth(
    headers: Optional[Dict[str, str]],
    expected_token: Optional[str] = None,
) -> Tuple[bool, str]:
    """Verify Bearer or X-Simon-Agent-Token auth when SIMON_AGENT_DB_TOKEN is configured."""
    secret = (
        expected_token
        if expected_token is not None
        else os.environ.get("SIMON_AGENT_DB_TOKEN", "").strip()
    )
    if not secret:
        return True, ""

    norm = {k.lower(): v.strip() for k, v in (headers or {}).items()}
    token = ""
    auth_header = norm.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    elif norm.get("x-simon-agent-token"):
        token = norm["x-simon-agent-token"]

    if not token or not hmac.compare_digest(token, secret):
        return False, "Unauthorized: valid Bearer token required for /api/db access."
    return True, ""


def validate_collection_payload(collection: str, payload: Any) -> Tuple[List[str], Optional[str]]:
    """Validate payload against Simon's Stage 1/2 contracts. Returns (errors, suggested_doc_id)."""
    if collection not in ALLOWED_AGENT_COLLECTIONS:
        return [f"Collection '{collection}' is not allowed for agent access."], None
    if not isinstance(payload, dict):
        return ["Payload must be a JSON object."], None

    errors: List[str] = []
    doc_id: Optional[str] = None

    if collection == "discovered_sources":
        for field in ("url", "source_channel", "why_useful"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        channel = str(payload.get("source_channel") or "").strip()
        if channel and channel not in VALID_SOURCE_CHANNELS:
            errors.append(
                f"Invalid source_channel '{channel}'. Must be one of: {sorted(VALID_SOURCE_CHANNELS)}."
            )
        doc_id = str(payload.get("doc_id") or payload.get("id") or "").strip() or None

    elif collection == "leads":
        for field in ("lead_id", "stage_name"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        seeds = payload.get("seed_sources")
        if not isinstance(seeds, list) or not seeds:
            errors.append("Field 'seed_sources' must be a non-empty list of {url, source_channel}.")
        else:
            for idx, seed in enumerate(seeds):
                if not isinstance(seed, dict) or not seed.get("url") or not seed.get("source_channel"):
                    errors.append(f"seed_sources[{idx}] requires 'url' and 'source_channel'.")
        doc_id = str(payload.get("lead_id") or "").strip() or None

    elif collection == "discovery_handoffs":
        for field in ("contract_version", "run_id", "search_brief"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        if not isinstance(payload.get("requested_count"), int) or payload["requested_count"] < 1:
            errors.append("Field 'requested_count' must be an integer >= 1.")
        leads = payload.get("leads")
        if not isinstance(leads, list):
            errors.append("Field 'leads' must be a list of DiscoveryLead objects.")
        else:
            for idx, lead in enumerate(leads):
                lead_errs, _ = validate_collection_payload("leads", lead)
                for err in lead_errs:
                    errors.append(f"leads[{idx}]: {err}")
        doc_id = str(payload.get("run_id") or "").strip() or None

    elif collection == "investigator_dossiers":
        for field in ("lead_id", "stage_name"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        doc_id = str(payload.get("dossier_id") or payload.get("lead_id") or "").strip() or None

    elif collection == "fleet_runs":
        doc_id = str(payload.get("batch_id") or payload.get("id") or "").strip() or None

    elif collection == "source_registry":
        for field in ("source_id", "name", "url", "source_channel"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        channel = str(payload.get("source_channel") or "").strip()
        if channel and channel not in VALID_SOURCE_CHANNELS:
            errors.append(f"Invalid source_channel '{channel}'.")
        doc_id = str(payload.get("source_id") or "").strip() or None

    elif collection == "agent_runs":
        for field in ("run_id", "agent_id", "status"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        doc_id = str(payload.get("agent_run_id") or payload.get("doc_id") or "").strip() or None

    elif collection == "agent_reports":
        for field in ("report_id", "agent_name", "stage", "status"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        status = str(payload.get("status") or "").strip()
        if status and status not in VALID_REPORT_STATUSES:
            errors.append(f"Invalid status '{status}'. Must be one of: {sorted(VALID_REPORT_STATUSES)}.")
        for forbidden in sorted(REPORT_FORBIDDEN_KEYS):
            if forbidden in payload:
                errors.append(f"Field '{forbidden}' is forbidden in human-first agent_reports.")
        steps = payload.get("steps")
        if steps is not None and not isinstance(steps, list):
            errors.append("Field 'steps' must be a list of human-readable Field News steps.")
        elif isinstance(steps, list):
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"steps[{idx}] must be an object.")
                    continue
                for forbidden in sorted(REPORT_FORBIDDEN_KEYS):
                    if forbidden in step:
                        errors.append(f"steps[{idx}].{forbidden} is forbidden in agent_reports.")
                phase = str(step.get("phase") or "").strip()
                if phase and phase not in VALID_REPORT_PHASES:
                    errors.append(f"steps[{idx}].phase '{phase}' must be one of: {sorted(VALID_REPORT_PHASES)}.")
        findings = payload.get("findings")
        if findings is not None and not isinstance(findings, list):
            errors.append("Field 'findings' must be a list of human-readable findings.")
        doc_id = str(payload.get("report_id") or payload.get("doc_id") or "").strip() or None

    elif collection == "screening_packets":
        for field in ("lead_id", "stage_name"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        judge_decision = payload.get("judge_decision")
        if not isinstance(judge_decision, dict):
            errors.append("Field 'judge_decision' must be an object containing 'verdict'.")
        else:
            verdict = str(judge_decision.get("verdict") or "").strip().lower()
            if verdict not in VALID_SCREENING_VERDICTS:
                errors.append(
                    f"Invalid judge_decision.verdict '{verdict}'. Must be one of: {sorted(VALID_SCREENING_VERDICTS)}."
                )
        lead_id_clean = str(payload.get("lead_id") or "").strip()
        doc_id = (
            str(payload.get("packet_id") or "").strip()
            or (f"scr_{lead_id_clean}" if lead_id_clean else None)
        )

    elif collection == "screening_labels":
        if not str(payload.get("lead_id") or "").strip():
            errors.append("Missing required field 'lead_id'.")
        verdict = str(payload.get("human_verdict") or "").strip().lower()
        if not verdict:
            errors.append("Missing required field 'human_verdict'.")
        elif verdict not in VALID_SCREENING_VERDICTS:
            errors.append(
                f"Invalid human_verdict '{verdict}'. Must be one of: {sorted(VALID_SCREENING_VERDICTS)}."
            )
        doc_id = str(payload.get("label_id") or "").strip() or f"lbl_{uuid.uuid4().hex[:8]}"

    elif collection == "judging_models":
        policy_id = str(payload.get("policy_id") or "").strip()
        if not policy_id:
            errors.append("Missing required field 'policy_id'.")
        raw_version = payload.get("version")
        if raw_version is None or isinstance(raw_version, bool) or not str(raw_version).strip():
            errors.append("Missing required field 'version'.")
        doc_id = policy_id or None

    elif collection == "taste_scores":
        lead_id = str(payload.get("lead_id") or "").strip()
        if not lead_id:
            errors.append("Missing required field 'lead_id'.")
        verdict = str(payload.get("taste_verdict") or "").strip().lower()
        if verdict not in VALID_SCREENING_VERDICTS:
            errors.append(
                f"Invalid taste_verdict '{verdict}'. Must be one of: {sorted(VALID_SCREENING_VERDICTS)}."
            )
        doc_id = str(payload.get("taste_score_id") or "").strip() or (f"taste_{lead_id}" if lead_id else None)

    elif collection == "eval_runs":
        for field in ("eval_run_id", "status"):
            if not str(payload.get(field) or "").strip():
                errors.append(f"Missing required field '{field}'.")
        doc_id = str(payload.get("eval_run_id") or payload.get("doc_id") or "").strip() or None

    return errors, doc_id


def _ensure_fallback_table(db_path: Any) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_documents (
            collection TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (collection, doc_id)
        )
        """
    )
    conn.commit()
    return conn


def save_agent_document(
    store: Any,
    collection: str,
    payload: Dict[str, Any],
    doc_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate and save a document to FirestoreStore or SQLite SimonStore."""
    cleaned_payload = (
        sanitize_agent_report(payload)
        if collection == "screening_packets" and isinstance(payload, dict)
        else payload
    )
    errors, inferred_id = validate_collection_payload(collection, cleaned_payload)
    if errors:
        raise ValueError("; ".join(errors))

    resolved_id = (doc_id or inferred_id or f"{collection[:6]}_{uuid.uuid4().hex[:10]}").strip()
    record = dict(cleaned_payload)
    record.setdefault("_saved_at", _utc_now())
    record["_doc_id"] = resolved_id

    if hasattr(store, "save_document"):
        store.save_document(collection, resolved_id, record)
    else:
        conn = _ensure_fallback_table(store.db_path)
        try:
            conn.execute(
                """
                INSERT INTO agent_documents (collection, doc_id, updated_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(collection, doc_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (collection, resolved_id, _utc_now(), json.dumps(record, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    return {"ok": True, "collection": collection, "doc_id": resolved_id, "document": record}


def get_agent_document(store: Any, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
    if collection not in ALLOWED_AGENT_COLLECTIONS:
        raise PermissionError(f"Collection '{collection}' is not allowed for agent access.")
    if hasattr(store, "get_document"):
        doc = store.get_document(collection, doc_id)
    else:
        conn = _ensure_fallback_table(store.db_path)
        try:
            row = conn.execute(
                "SELECT payload_json FROM agent_documents WHERE collection = ? AND doc_id = ?",
                (collection, doc_id),
            ).fetchone()
            doc = json.loads(row["payload_json"]) if row else None
        finally:
            conn.close()
    if doc is not None and collection == "screening_packets":
        return sanitize_agent_report(doc)
    return doc


def list_agent_documents(store: Any, collection: str, limit: int = 25) -> List[Dict[str, Any]]:
    if collection not in ALLOWED_AGENT_COLLECTIONS:
        raise PermissionError(f"Collection '{collection}' is not allowed for agent access.")
    capped = max(1, min(int(limit), 100))
    if hasattr(store, "list_documents"):
        docs = store.list_documents(collection, limit=capped)
    else:
        conn = _ensure_fallback_table(store.db_path)
        try:
            rows = conn.execute(
                """
                SELECT payload_json FROM agent_documents
                WHERE collection = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (collection, capped),
            ).fetchall()
            docs = [json.loads(r["payload_json"]) for r in rows]
        finally:
            conn.close()
    if collection == "screening_packets":
        return [sanitize_agent_report(d) for d in docs]
    return docs
