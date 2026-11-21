"""Rate-limited fan-out dispatcher for scaling one Managed Agent across N targets."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from .gemini import _extract_interaction_text

INTERACTIONS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_API_REVISION = "2026-05-20"
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "incomplete", "budget_exceeded"})
RETRYABLE_HTTP_CODES = frozenset({429, 500, 502, 503, 504})


def _http_json(
    method: str,
    url: str,
    api_key: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> Tuple[int, Dict[str, Any]]:
    headers = {
        "Api-Revision": DEFAULT_API_REVISION,
        "x-goog-api-key": api_key,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8").strip()
            return resp.status, (json.loads(raw) if raw else {})
    except HTTPError as exc:
        with exc:
            raw = exc.read().decode("utf-8", errors="replace").strip()
            try:
                err_obj = json.loads(raw) if raw else {}
            except ValueError:
                err_obj = {"message": raw or str(exc.reason)}
        return exc.code, err_obj
    except (URLError, TimeoutError) as exc:
        return 599, {"message": str(exc)}


def _request_with_backoff(
    method: str,
    url: str,
    api_key: str,
    body: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    base_delay_s: float = 1.0,
    request_fn: Callable[..., Tuple[int, Dict[str, Any]]] = _http_json,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    last_code = 0
    last_body: Dict[str, Any] = {}
    for attempt in range(max_retries + 1):
        code, resp = request_fn(method, url, api_key, body=body)
        if 200 <= code < 300:
            return resp
        last_code, last_body = code, resp
        if code not in RETRYABLE_HTTP_CODES or attempt == max_retries:
            break
        sleep_fn(base_delay_s * (2 ** attempt))
    raise RuntimeError(f"Gemini API {method} {url} failed (HTTP {last_code}): {last_body}")


def _format_assignment(assignment: Any) -> Tuple[str, str]:
    """Return (serialized_text, short_label) for any string or JSON assignment."""
    if isinstance(assignment, str):
        cleaned = assignment.strip()
        return cleaned, cleaned[:120]
    serialized = json.dumps(assignment, ensure_ascii=False)
    if isinstance(assignment, dict):
        label = str(
            assignment.get("lead_id")
            or assignment.get("id")
            or assignment.get("stage_name")
            or assignment.get("name")
            or ""
        ).strip()
        if label:
            return serialized, label[:120]
    return serialized, serialized[:120]


def build_worker_request(
    agent_id: str,
    target: Any,
    prompt_template: Optional[str],
    batch_id: str,
    target_index: int,
    webhook_url: Optional[str] = None,
    environment: Any = None,
) -> Dict[str, Any]:
    """Build one isolated background interaction request for a fleet worker."""
    serialized, label = _format_assignment(target)
    if prompt_template:
        try:
            prompt = prompt_template.format(
                assignment=serialized,
                target=serialized,
                index=target_index,
                batch_id=batch_id,
            )
        except (KeyError, ValueError):
            prompt = f"{prompt_template}\n\n{serialized}"
    else:
        prompt = serialized

    body: Dict[str, Any] = {
        "agent": agent_id,
        "environment": environment if environment is not None else {"type": "remote"},
        "store": True,
        "background": True,
        "input": [{"type": "text", "text": prompt}],
    }
    if webhook_url:
        body["webhook_config"] = {
            "uris": [webhook_url],
            "user_metadata": {
                "batch_id": batch_id,
                "target_index": str(target_index),
                "target": label,
                "agent_id": agent_id,
            },
        }
    return body


def dispatch_fleet(
    agent_id: str,
    targets: Optional[List[Any]] = None,
    assignments: Optional[List[Any]] = None,
    prompt_template: Optional[str] = None,
    max_concurrency: int = 5,
    webhook_url: Optional[str] = None,
    wait: bool = False,
    poll_interval_s: float = 2.0,
    poll_timeout_s: float = 180.0,
    dry_run: bool = False,
    api_key: Optional[str] = None,
    request_fn: Callable[..., Tuple[int, Dict[str, Any]]] = _http_json,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Fan out one deployed Managed Agent across N opaque assignments with rate-limited concurrency."""
    raw_items = assignments if assignments is not None else (targets or [])
    cleaned_items: List[Any] = []
    for item in raw_items:
        if isinstance(item, str):
            s = item.strip()
            if s:
                cleaned_items.append(s)
        elif item is not None:
            cleaned_items.append(item)

    if not cleaned_items:
        raise ValueError("Provide at least one assignment (or target) to scale across the fleet.")
    if not agent_id or not agent_id.strip():
        raise ValueError("Provide a non-empty agent ID.")

    workers_cap = max(1, min(int(max_concurrency), len(cleaned_items), 20))
    batch_id = f"batch_{uuid.uuid4().hex[:10]}"

    if dry_run:
        planned = []
        for idx, item in enumerate(cleaned_items):
            req_body = build_worker_request(
                agent_id=agent_id.strip(),
                target=item,
                prompt_template=prompt_template,
                batch_id=batch_id,
                target_index=idx,
                webhook_url=webhook_url,
            )
            planned.append(
                {
                    "index": idx,
                    "assignment": item,
                    "target": item,
                    "status": "dry_run",
                    "interaction_id": None,
                    "request": req_body,
                }
            )
        return {
            "batch_id": batch_id,
            "agent_id": agent_id.strip(),
            "mode": "dry_run",
            "max_concurrency": workers_cap,
            "total": len(planned),
            "dispatched": len(planned),
            "failed": 0,
            "workers": planned,
        }

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_key:
        raise ValueError("Set GEMINI_API_KEY (or pass dry_run=True) before running a live fleet.")

    def _run_one(idx: int, item: Any) -> Dict[str, Any]:
        req_body = build_worker_request(
            agent_id=agent_id.strip(),
            target=item,
            prompt_template=prompt_template,
            batch_id=batch_id,
            target_index=idx,
            webhook_url=webhook_url,
        )
        try:
            created = _request_with_backoff(
                "POST",
                INTERACTIONS_ENDPOINT,
                resolved_key,
                body=req_body,
                request_fn=request_fn,
                sleep_fn=sleep_fn,
            )
            raw_name = str(created.get("name") or "")
            interaction_id = str(created.get("id") or (raw_name.split("/")[-1] if raw_name else ""))
            status = str(created.get("status") or "in_progress")
            result_obj = created

            if wait and interaction_id:
                started = time.monotonic()
                while status not in TERMINAL_STATUSES:
                    if time.monotonic() - started > poll_timeout_s:
                        status = "timeout"
                        break
                    sleep_fn(poll_interval_s)
                    result_obj = _request_with_backoff(
                        "GET",
                        f"{INTERACTIONS_ENDPOINT}/{interaction_id}",
                        resolved_key,
                        request_fn=request_fn,
                        sleep_fn=sleep_fn,
                    )
                    status = str(result_obj.get("status") or status)

            worker_out: Dict[str, Any] = {
                "index": idx,
                "assignment": item,
                "target": item,
                "interaction_id": interaction_id,
                "environment_id": result_obj.get("environment_id"),
                "status": status,
                "error": None,
            }
            if status == "completed":
                worker_out["output_text"] = _extract_interaction_text(result_obj)
            elif status in ("failed", "timeout"):
                worker_out["error"] = str(result_obj.get("error") or status)
            return worker_out
        except Exception as exc:  # noqa: BLE001 - isolate per-worker failures
            return {
                "index": idx,
                "assignment": item,
                "target": item,
                "interaction_id": None,
                "environment_id": None,
                "status": "error",
                "error": str(exc),
            }

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers_cap) as pool:
        futures = [pool.submit(_run_one, idx, item) for idx, item in enumerate(cleaned_items)]
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda item: item["index"])
    failed = sum(1 for r in results if r["status"] in ("error", "failed", "timeout"))
    return {
        "batch_id": batch_id,
        "agent_id": agent_id.strip(),
        "mode": "wait" if wait else "async_background",
        "max_concurrency": workers_cap,
        "webhook_url": webhook_url,
        "total": len(results),
        "dispatched": len(results) - failed,
        "failed": failed,
        "workers": results,
    }
