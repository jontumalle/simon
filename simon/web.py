"""Zero-dependency HTTP server and interactive Scouting Studio UI for Simon's MVP demo.

Launch with:
    python3 -m simon serve --port 8765
"""

from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse
import uuid

from .db_tools import (
    ALLOWED_AGENT_COLLECTIONS,
    get_agent_document,
    list_agent_documents,
    save_agent_document,
    verify_agent_db_auth,
)
from .deploy import compile_agent_package, list_agent_packages
from .discovery_ui import (
    DISCOVERY_HTML,
    EVALS_HTML,
    FIELD_NEWS_HTML,
    INVESTIGATE_HTML,
    REPORTS_HTML,
    _NAV_CSS,
    archive_agent_reports,
    dispatch_discovery_batch,
    get_agent_report,
    list_agent_reports,
    list_discovery_batches,
    list_discovery_leads,
    list_eval_runs,
    list_investigator_dossiers,
    load_source_registry,
    refresh_discovery_batch,
    render_top_nav,
)
from .vertex_eval import list_available_eval_agents, load_agent_rubrics, run_agent_eval
from .fleet import dispatch_fleet
from .phases import (
    AGENT_EVALS_COLLECTION,
    PHASE_DEFINITIONS,
    PHASE_RUNS_COLLECTION,
    evaluate_agent_output,
    run_phase,
)
from .registry import (
    AGENT_RUNS_COLLECTION,
    append_agent_trace,
    list_agent_runs,
    new_run_id,
    record_agent_run,
    record_fleet_agent_runs,
    seed_discovery_sources,
    upsert_discovery_source,
)
from .scout import DEFAULT_TASTE_BRIEF, load_dotenv_if_present, run_scout
from .screening import (
    compile_judging_model,
    evaluate_with_taste_engine,
    list_judging_models,
    list_screening_deck,
    list_screening_evals,
    list_screening_labels,
    list_taste_scores,
    render_fallback_screening_html,
    run_screening_batch,
    run_screening_evals,
    save_screening_label,
)
from .store import SimonStore, create_store


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _load_index_html() -> str:
    return (
        (STATIC_DIR / "index.html")
        .read_text(encoding="utf-8")
        .replace("/*__NAV_CSS__*/", _NAV_CSS)
        .replace("<!--__TOP_NAV__-->", render_top_nav("/"))
    )


INDEX_HTML = _load_index_html()


def _serve_static(rel_path: str) -> Optional[tuple[int, str, bytes]]:
    """Safely serve a static asset from simon/static/ without directory traversal."""
    cleaned = rel_path.lstrip("/")
    if not cleaned or ".." in Path(cleaned).parts:
        return None
    target = (STATIC_DIR / cleaned).resolve()
    try:
        target.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None
    if not target.is_file():
        return None
    ctype = STATIC_CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return (HTTPStatus.OK, ctype, target.read_bytes())



def dispatch_http_request(
    store: SimonStore,
    method: str,
    path: str,
    raw_body: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
) -> tuple[int, str, bytes]:
    """Pure HTTP routing dispatcher returning (status_code, content_type, response_bytes)."""
    parsed = urlparse(path)

    # Permissioned, schema-validated agent DB gateway: /api/db/<collection>[/<doc_id>]
    if parsed.path.startswith("/api/db/"):
        authed, auth_err = verify_agent_db_auth(headers)
        if not authed:
            return (
                HTTPStatus.UNAUTHORIZED,
                "application/json; charset=utf-8",
                json.dumps({"error": auth_err}).encode("utf-8"),
            )
        parts = [p for p in parsed.path[len("/api/db/"):].split("/") if p]
        if not parts:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Collection name required."}).encode("utf-8"),
            )
        collection = parts[0]
        if collection not in ALLOWED_AGENT_COLLECTIONS:
            return (
                HTTPStatus.FORBIDDEN,
                "application/json; charset=utf-8",
                json.dumps(
                    {
                        "error": f"Collection '{collection}' is not permitted for agent access.",
                        "allowed_collections": sorted(ALLOWED_AGENT_COLLECTIONS),
                    }
                ).encode("utf-8"),
            )

        if method == "GET":
            if len(parts) == 2:
                doc = get_agent_document(store, collection, parts[1])
                if doc is None:
                    return (
                        HTTPStatus.NOT_FOUND,
                        "application/json; charset=utf-8",
                        json.dumps({"error": "Document not found."}).encode("utf-8"),
                    )
                return (
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps({"collection": collection, "doc_id": parts[1], "document": doc}, ensure_ascii=False).encode("utf-8"),
                )
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["25"])[0])
            docs = list_agent_documents(store, collection, limit=limit)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"collection": collection, "count": len(docs), "documents": docs}, ensure_ascii=False).encode("utf-8"),
            )

        if method == "POST" and len(parts) == 1:
            try:
                payload = json.loads((raw_body or b"{}").decode("utf-8"))
            except ValueError:
                return (
                    HTTPStatus.BAD_REQUEST,
                    "application/json; charset=utf-8",
                    json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
                )
            qs = parse_qs(parsed.query)
            doc_id = (qs.get("doc_id") or [None])[0]
            try:
                saved = save_agent_document(store, collection, payload, doc_id=doc_id)
            except ValueError as exc:
                return (
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "application/json; charset=utf-8",
                    json.dumps({"error": str(exc)}).encode("utf-8"),
                )
            return (
                HTTPStatus.CREATED,
                "application/json; charset=utf-8",
                json.dumps(saved, ensure_ascii=False).encode("utf-8"),
            )

        return (
            HTTPStatus.METHOD_NOT_ALLOWED,
            "application/json; charset=utf-8",
            json.dumps({"error": "Method not allowed on /api/db endpoint."}).encode("utf-8"),
        )

    if method == "GET":
        if parsed.path == "/":
            return (HTTPStatus.OK, "text/html; charset=utf-8", _load_index_html().encode("utf-8"))

        if parsed.path.startswith("/static/"):
            served = _serve_static(parsed.path[len("/static/"):])
            if served is not None:
                return served
            return (
                HTTPStatus.NOT_FOUND,
                "application/json; charset=utf-8",
                json.dumps({"error": "Static asset not found."}).encode("utf-8"),
            )

        if parsed.path == "/api/phases":
            runs = store.list_documents(PHASE_RUNS_COLLECTION, limit=30) if hasattr(store, "list_documents") else []
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(
                    {"phases": PHASE_DEFINITIONS, "phase_runs": runs},
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        if parsed.path == "/api/evals":
            qs = parse_qs(parsed.query)
            agent_filter = (qs.get("agent_id") or [None])[0]
            evals = store.list_documents(AGENT_EVALS_COLLECTION, limit=50) if hasattr(store, "list_documents") else []
            if agent_filter:
                evals = [e for e in evals if e.get("agent_id") == agent_filter]
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"evals": evals}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path in ("/discovery", "/scouting"):
            return (HTTPStatus.OK, "text/html; charset=utf-8", DISCOVERY_HTML.encode("utf-8"))

        if parsed.path in ("/field-news", "/traces"):
            return (HTTPStatus.OK, "text/html; charset=utf-8", FIELD_NEWS_HTML.encode("utf-8"))

        if parsed.path == "/reports":
            return (HTTPStatus.OK, "text/html; charset=utf-8", REPORTS_HTML.encode("utf-8"))

        if parsed.path == "/investigate":
            return (HTTPStatus.OK, "text/html; charset=utf-8", INVESTIGATE_HTML.encode("utf-8"))

        if parsed.path in ("/screen", "/screening"):
            try:
                from .screening_ui import render_screening_page  # type: ignore[import-not-found]

                sig = inspect.signature(render_screening_page)
                params = list(sig.parameters.values())
                accepts_varargs = any(
                    p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                    for p in params
                )
                if "store" in sig.parameters:
                    rendered = render_screening_page(store=store)
                elif len(params) >= 1 or accepts_varargs:
                    rendered = render_screening_page(store)
                else:
                    rendered = render_screening_page()
                html_bytes = rendered if isinstance(rendered, bytes) else str(rendered).encode("utf-8")
            except ImportError:
                html_bytes = render_fallback_screening_html().encode("utf-8")
            return (HTTPStatus.OK, "text/html; charset=utf-8", html_bytes)

        if parsed.path == "/api/screening/packets":
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["100"])[0])
            verdict_filter = (qs.get("verdict") or [None])[0]
            deck = list_screening_deck(store, limit=limit, verdict_filter=verdict_filter)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(deck, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/screening/labels":
            qs = parse_qs(parsed.query)
            lead_id = (qs.get("lead_id") or [None])[0]
            limit = int((qs.get("limit") or ["100"])[0])
            labels = list_screening_labels(store, lead_id=lead_id, limit=limit)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(labels), "labels": labels}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/screening/models":
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["25"])[0])
            models = list_judging_models(store, limit=limit)
            active = next((m for m in models if m.get("is_active")), models[0] if models else None)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(
                    {"count": len(models), "active_model": active, "models": models},
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        if parsed.path in ("/api/screening/taste-scores", "/api/screening/taste-score"):
            qs = parse_qs(parsed.query)
            lead_id = (qs.get("lead_id") or [None])[0]
            limit = int((qs.get("limit") or ["100"])[0])
            scores = list_taste_scores(store, lead_id=lead_id, limit=limit)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(scores), "taste_scores": scores}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/screening/evals":
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["25"])[0])
            evals_payload = list_screening_evals(store, limit=limit)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(evals_payload, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/evals":
            return (HTTPStatus.OK, "text/html; charset=utf-8", EVALS_HTML.encode("utf-8"))

        if parsed.path == "/api/evals/agents":
            agents = list_available_eval_agents()
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(agents), "agents": agents}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/evals/rubrics":
            qs = parse_qs(parsed.query)
            agent = (qs.get("agent") or ["discovery-scout"])[0]
            try:
                spec = load_agent_rubrics(agent)
            except FileNotFoundError as exc:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": str(exc)}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(spec, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/eval-runs":
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["50"])[0])
            agent_id = (qs.get("agent_id") or [None])[0]
            runs = list_eval_runs(store, agent_id=agent_id, limit=limit)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(runs), "eval_runs": runs}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/dossiers":
            qs = parse_qs(parsed.query)
            dossiers = list_investigator_dossiers(
                store,
                lead_id=(qs.get("lead_id") or [None])[0],
                limit=int((qs.get("limit") or ["50"])[0]),
            )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(dossiers), "dossiers": dossiers}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/leads":
            qs = parse_qs(parsed.query)
            leads = list_discovery_leads(
                store,
                limit=int((qs.get("limit") or ["100"])[0]),
            )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(leads), "leads": leads}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path in ("/api/field-news", "/api/reports"):
            qs = parse_qs(parsed.query)
            include_archived = (qs.get("include_archived") or ["0"])[0].lower() in ("1", "true", "yes")
            reports = list_agent_reports(
                store,
                batch_id=(qs.get("batch_id") or [None])[0],
                status=(qs.get("status") or [None])[0],
                stage=(qs.get("stage") or [None])[0],
                include_archived=include_archived,
                limit=int((qs.get("limit") or ["50"])[0]),
            )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(reports), "reports": reports}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path.startswith("/api/reports/"):
            report_id = parsed.path[len("/api/reports/"):].strip("/")
            report = get_agent_report(store, report_id)
            if report is None:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": f"Report '{report_id}' not found."}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(report, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path in ("/healthz", "/api/health"):
            payload = {
                "ok": True,
                "store_backend": getattr(store, "backend", "sqlite"),
            }
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/discovery/batches":
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["20"])[0])
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"batches": list_discovery_batches(store, limit=limit)}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path.startswith("/api/discovery/batches/"):
            batch_id = parsed.path[len("/api/discovery/batches/"):].strip("/")
            qs = parse_qs(parsed.query)
            wait_flag = (qs.get("wait") or ["0"])[0].lower() in ("1", "true", "yes")
            since_steps = int((qs.get("since_steps") or ["-1"])[0])
            timeout_s = min(25.0, max(1.0, float((qs.get("timeout") or ["15"])[0])))
            load_dotenv_if_present()
            batch = refresh_discovery_batch(
                store,
                batch_id,
                wait=wait_flag,
                since_steps=since_steps,
                timeout_s=timeout_s,
            )
            if batch is None:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": "Discovery batch not found."}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            )
        if parsed.path == "/api/status":
            load_dotenv_if_present()
            payload = {
                "ok": True,
                "has_api_key": bool(os.environ.get("GEMINI_API_KEY")),
                "default_brief": DEFAULT_TASTE_BRIEF,
                "store_backend": getattr(store, "backend", "sqlite"),
            }
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/fleet/runs":
            runs = store.list_documents("fleet_runs", limit=20) if hasattr(store, "list_documents") else []
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"fleet_runs": runs}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/sources":
            qs = parse_qs(parsed.query)
            ch = (qs.get("channel") or [None])[0]
            city = (qs.get("city") or [None])[0]
            tier = (qs.get("tier") or [None])[0]
            status_f = (qs.get("status") or [None])[0]
            limit = int((qs.get("limit") or ["100"])[0])
            registry = load_source_registry(store)
            sources = registry["sources"]
            if ch:
                sources = [s for s in sources if s.get("source_channel") == ch]
            if city:
                sources = [s for s in sources if ((s.get("location") or {}).get("city") or "Global").lower() == city.lower()]
            if tier:
                sources = [s for s in sources if s.get("career_tier") == tier]
            if status_f:
                sources = [s for s in sources if s.get("status") == status_f]
            sources = sources[:limit]
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(
                    {
                        "count": len(sources),
                        "channels": registry["channels"],
                        "cities": registry["cities"],
                        "tiers": registry["tiers"],
                        "sources": sources,
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        if parsed.path == "/api/agent-runs":
            qs = parse_qs(parsed.query)
            runs = list_agent_runs(
                store,
                run_id=(qs.get("run_id") or [None])[0],
                agent_id=(qs.get("agent_id") or [None])[0],
                status=(qs.get("status") or [None])[0],
                limit=int((qs.get("limit") or ["50"])[0]),
            )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(runs), "agent_runs": runs}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path.startswith("/api/agent-runs/"):
            arun_id = parsed.path[len("/api/agent-runs/"):].strip("/")
            doc = store.get_document(AGENT_RUNS_COLLECTION, arun_id) if hasattr(store, "get_document") else None
            if not doc:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": f"Agent run '{arun_id}' not found."}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(doc, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/agents":
            prefix = os.environ.get("SIMON_AGENT_PREFIX", "")
            items = []
            for pkg_dir in list_agent_packages():
                compiled = compile_agent_package(pkg_dir, prefix=prefix)
                items.append(
                    {
                        "package": compiled["package"],
                        "deployed_id": compiled["deployed_id"],
                        "sha256": compiled["sha256"],
                        "base_agent": compiled["payload"]["base_agent"],
                        "model": compiled["payload"].get("agent_config", {}).get("model"),
                    }
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"prefix": prefix, "agents": items}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/runs":
            qs = parse_qs(parsed.query)
            run_id = (qs.get("id") or [None])[0]
            if run_id:
                found = store.get_run(run_id)
                if not found:
                    return (
                        HTTPStatus.NOT_FOUND,
                        "application/json; charset=utf-8",
                        json.dumps({"error": "Run not found."}).encode("utf-8"),
                    )
                return (
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps(found, ensure_ascii=False).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"runs": store.list_runs(limit=20)}, ensure_ascii=False).encode("utf-8"),
            )

        return (
            HTTPStatus.NOT_FOUND,
            "application/json; charset=utf-8",
            json.dumps({"error": "Not found."}).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/screening/run":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        lead_id = str(req.get("lead_id") or "").strip() or None
        dossier_obj = req.get("dossier") if isinstance(req.get("dossier"), dict) else None
        live = bool(req.get("live", False))
        api_key = str(req.get("api_key") or "").strip() or None
        prefix = str(req.get("prefix") or "").strip() or None
        load_dotenv_if_present()
        try:
            packets = run_screening_batch(
                store=store,
                lead_id=lead_id,
                dossier=dossier_obj,
                live=live,
                api_key=api_key,
                prefix=prefix,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        deck = list_screening_deck(store)
        response_payload = {
            "ok": True,
            "mode": packets[0].get("mode", "deterministic_baseline") if packets else "deterministic_baseline",
            "count": len(packets),
            "packet": packets[0] if len(packets) == 1 else None,
            "packets": packets,
            "deck": deck,
        }
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(response_payload, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/screening/labels":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        try:
            saved_label = save_screening_label(store, req)
        except ValueError as exc:
            return (
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        out = dict(saved_label)
        out["ok"] = True
        out["label"] = saved_label
        return (
            HTTPStatus.CREATED,
            "application/json; charset=utf-8",
            json.dumps(out, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/screening/train":
        try:
            _ = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        try:
            policy = compile_judging_model(store)
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        out = dict(policy)
        out["ok"] = True
        out["policy"] = policy
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(out, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/screening/taste-score":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        load_dotenv_if_present()
        live = bool(req.get("live", True))
        api_key = str(req.get("api_key") or "").strip() or None
        dossier_obj = req.get("dossier") if isinstance(req.get("dossier"), dict) else None
        target_id = str(req.get("lead_id") or req.get("packet_id") or "").strip() or None
        try:
            if dossier_obj is not None:
                score_doc = evaluate_with_taste_engine(store, dossier_obj, live=live, api_key=api_key)
                out = dict(score_doc)
                out["ok"] = True
                out["taste_score"] = score_doc
                return (
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps(out, ensure_ascii=False).encode("utf-8"),
                )
            if target_id:
                score_doc = evaluate_with_taste_engine(store, target_id, live=live, api_key=api_key)
                out = dict(score_doc)
                out["ok"] = True
                out["taste_score"] = score_doc
                return (
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps(out, ensure_ascii=False).encode("utf-8"),
                )
            deck = list_screening_deck(store, limit=50)
            results = [
                evaluate_with_taste_engine(store, pkt["lead_id"], live=live, api_key=api_key)
                for pkt in (deck.get("packets") or [])
            ]
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(
                    {
                        "ok": True,
                        "count": len(results),
                        "taste_scores": results,
                        "taste_score": results[0] if results else None,
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )

    if method == "POST" and parsed.path == "/api/screening/evals/run":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        trigger = str(req.get("trigger") or "platform_ui").strip() or "platform_ui"
        try:
            eval_report = run_screening_evals(store, trigger=trigger)
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        out = dict(eval_report)
        out["ok"] = True
        out["eval_run"] = eval_report
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(out, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/reports/archive":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        report_ids = req.get("report_ids")
        if report_ids is not None and not isinstance(report_ids, list):
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Field 'report_ids' must be a list of report IDs."}).encode("utf-8"),
            )
        batch_id = req.get("batch_id")
        archived_flag = True if "archived" not in req else bool(req.get("archived"))
        result = archive_agent_reports(
            store,
            report_ids=report_ids,
            batch_id=str(batch_id).strip() if batch_id else None,
            archived=archived_flag,
        )
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(result, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/phases/run":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        phase_id = str(req.get("phase_id") or "").strip()
        payload = req.get("payload") if isinstance(req.get("payload"), dict) else {}
        live = bool(req.get("live", False))
        run_id = str(req.get("run_id") or "").strip() or None
        api_key = str(req.get("api_key") or "").strip() or None
        load_dotenv_if_present()
        try:
            result = run_phase(
                store=store,
                phase_id=phase_id,
                payload=payload,
                live=live,
                run_id=run_id,
                api_key=api_key,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(result, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/evals":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        agent_id = str(req.get("agent_id") or "").strip()
        if not agent_id:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "`agent_id` is required."}).encode("utf-8"),
            )
        output_payload = req.get("output")
        auto = evaluate_agent_output(agent_id, output_payload)
        save_flag = bool(req.get("save", True))
        record = {
            "eval_id": f"eval_{uuid.uuid4().hex[:10]}",
            "agent_id": agent_id,
            "verdict": str(req.get("verdict") or ("pass" if auto["passed"] else "fail")).lower(),
            "note": str(req.get("note") or "").strip(),
            "auto_passed": auto["passed"],
            "checks": auto["checks"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if save_flag and hasattr(store, "save_document"):
            store.save_document(AGENT_EVALS_COLLECTION, record["eval_id"], record)
        return (
            HTTPStatus.CREATED if save_flag else HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(record, ensure_ascii=False).encode("utf-8"),
        )
    if method == "POST" and parsed.path == "/api/eval-runs":
        ok_auth, auth_err = verify_agent_db_auth(headers)
        if not ok_auth:
            return (
                HTTPStatus.UNAUTHORIZED,
                "application/json; charset=utf-8",
                json.dumps({"error": auth_err}).encode("utf-8"),
            )
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        try:
            saved = save_agent_document(store, "eval_runs", req)
        except ValueError as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        return (
            HTTPStatus.CREATED,
            "application/json; charset=utf-8",
            json.dumps(saved, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/eval-runs/run":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        mode = str(req.get("mode") or "offline").strip()
        if mode not in ("offline", "vertex"):
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "`mode` must be 'offline' or 'vertex'."}).encode("utf-8"),
            )
        sample_source = str(req.get("sample_source") or "mixed").strip()
        all_agents = bool(req.get("all_agents", False))
        agent = str(req.get("agent") or "discovery-scout").strip()
        try:
            if all_agents:
                results = []
                for ag in list_available_eval_agents():
                    ev = run_agent_eval(
                        agent=ag["slug"],
                        mode=mode,
                        sample_source=sample_source,
                        store=store,
                        trigger="platform_ui",
                    )
                    save_agent_document(store, "eval_runs", ev)
                    results.append(ev)
                return (
                    HTTPStatus.CREATED,
                    "application/json; charset=utf-8",
                    json.dumps({"count": len(results), "eval_runs": results}, ensure_ascii=False).encode("utf-8"),
                )
            eval_run = run_agent_eval(
                agent=agent,
                mode=mode,
                sample_source=sample_source,
                store=store,
                trigger="platform_ui",
            )
            save_agent_document(store, "eval_runs", eval_run)
        except Exception as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        return (
            HTTPStatus.CREATED,
            "application/json; charset=utf-8",
            json.dumps(eval_run, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/discovery/dispatch":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        source_ids = req.get("source_ids") or []
        if not isinstance(source_ids, list) or not source_ids:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "`source_ids` must be a non-empty list."}).encode("utf-8"),
            )
        brief = str(req.get("brief") or "").strip()
        leads_per_agent = int(req.get("leads_per_agent") or 2)
        agent_count = int(req.get("agent_count") or len(source_ids))
        live = bool(req.get("live", False))
        api_key = str(req.get("api_key") or "").strip() or None
        load_dotenv_if_present()
        try:
            batch = dispatch_discovery_batch(
                store=store,
                source_ids=[str(s) for s in source_ids],
                brief=brief,
                leads_per_agent=leads_per_agent,
                agent_count=agent_count,
                live=live,
                api_key=api_key,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        http_status = HTTPStatus.ACCEPTED if live else HTTPStatus.OK
        return (
            http_status,
            "application/json; charset=utf-8",
            json.dumps(batch, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/fleet/run":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )

        agent_id = str(req.get("agent") or "").strip()
        raw_assignments = req.get("assignments") if "assignments" in req else req.get("targets")
        if not isinstance(raw_assignments, list) or not raw_assignments:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps(
                    {"error": "`assignments` (or `targets`) must be a non-empty list."}
                ).encode("utf-8"),
            )
        prompt_template = req.get("prompt_template")
        prompt_template_str = str(prompt_template) if prompt_template is not None else None
        max_concurrency = int(req.get("max_concurrency") or 5)
        webhook_url = str(req.get("webhook_url") or "").strip() or None
        wait = bool(req.get("wait", False))
        dry_run = bool(req.get("dry_run", False))
        api_key = str(req.get("api_key") or "").strip() or None
        try:
            summary = dispatch_fleet(
                agent_id=agent_id,
                assignments=raw_assignments,
                prompt_template=prompt_template_str,
                max_concurrency=max_concurrency,
                webhook_url=webhook_url,
                wait=wait,
                dry_run=dry_run,
                api_key=api_key,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        fleet_run_id = f"fleet_{uuid.uuid4().hex[:10]}"
        parent_run_id = str(req.get("run_id") or "").strip() or new_run_id("run")
        stage = str(req.get("stage") or "fleet").strip() or "fleet"
        summary["fleet_run_id"] = fleet_run_id
        summary["run_id"] = parent_run_id
        if hasattr(store, "save_document"):
            created_runs = record_fleet_agent_runs(store, summary, run_id=parent_run_id, stage=stage)
            summary["agent_run_ids"] = [r["agent_run_id"] for r in created_runs]
            store.save_document("fleet_runs", fleet_run_id, summary)
        http_status = HTTPStatus.OK if (wait or dry_run) else HTTPStatus.ACCEPTED
        return (
            http_status,
            "application/json; charset=utf-8",
            json.dumps(summary, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/sources/seed":
        try:
            summary = seed_discovery_sources(store)
        except (OSError, ValueError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        summary["store_backend"] = getattr(store, "backend", "sqlite")
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(summary, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/sources":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
            saved = upsert_discovery_source(store, req)
        except ValueError as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        return (
            HTTPStatus.CREATED,
            "application/json; charset=utf-8",
            json.dumps(saved, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/agent-runs":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        if req.get("agent_run_id") and isinstance(req.get("trace"), dict):
            trace = req["trace"]
            updated = append_agent_trace(
                store,
                str(req["agent_run_id"]),
                kind=str(trace.get("kind") or "tool_call"),
                summary=str(trace.get("summary") or ""),
                metadata=trace.get("metadata") if isinstance(trace.get("metadata"), dict) else None,
                status=req.get("status"),
                output_payload=req.get("output"),
                error=req.get("error"),
            )
            if not updated:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": "Agent run not found."}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(updated, ensure_ascii=False).encode("utf-8"),
            )
        agent_id = str(req.get("agent_id") or "").strip()
        if not agent_id:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "`agent_id` is required."}).encode("utf-8"),
            )
        saved = record_agent_run(
            store,
            run_id=str(req.get("run_id") or "").strip() or new_run_id("run"),
            agent_id=agent_id,
            stage=str(req.get("stage") or "custom"),
            status=str(req.get("status") or "running"),
            agent_run_id=req.get("agent_run_id"),
            parent_agent_run_id=req.get("parent_agent_run_id"),
            interaction_id=req.get("interaction_id"),
            target=req.get("target"),
            input_payload=req.get("input"),
            output_payload=req.get("output"),
            error=req.get("error"),
            traces=req.get("traces") if isinstance(req.get("traces"), list) else None,
        )
        return (
            HTTPStatus.CREATED,
            "application/json; charset=utf-8",
            json.dumps(saved, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/scout":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )

        brief_text = str(req.get("brief") or DEFAULT_TASTE_BRIEF).strip()
        live = bool(req.get("live", False))
        api_key = str(req.get("api_key") or "").strip() or None
        try:
            run = run_scout(brief_prompt=brief_text, live=live, store=store, api_key=api_key)
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(run.to_dict(), ensure_ascii=False).encode("utf-8"),
        )

    return (
        HTTPStatus.NOT_FOUND,
        "application/json; charset=utf-8",
        json.dumps({"error": "Not found."}).encode("utf-8"),
    )


def create_handler(store: SimonStore):
    class SimonHTTPHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _write(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            status, content_type, body = dispatch_http_request(
                store, "GET", self.path, headers=dict(self.headers.items())
            )
            self._write(status, content_type, body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            status, content_type, body = dispatch_http_request(
                store, "POST", self.path, raw_body, headers=dict(self.headers.items())
            )
            self._write(status, content_type, body)

    return SimonHTTPHandler


def serve_web(host: str = "127.0.0.1", port: int = 8765, store: Optional[Any] = None) -> None:
    load_dotenv_if_present()
    active_store = store or create_store()
    server = ThreadingHTTPServer((host, port), create_handler(active_store))
    print(f"Simon platform running at http://{host}:{port} (store={getattr(active_store, 'backend', 'sqlite')})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
