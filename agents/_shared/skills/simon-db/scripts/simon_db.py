#!/usr/bin/env python3
"""Zero-dependency shared DB client library & CLI for Simon Managed Agents."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DEFAULT_DB_URL = "https://simon-staging-139550420825.us-east1.run.app"


class SimonDB:
    """Thin HTTP client for Simon's permissioned, schema-validated Firestore API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (base_url or os.environ.get("SIMON_DB_URL") or DEFAULT_DB_URL).rstrip("/")
        # In Managed Agent sandboxes, Google's egress proxy injects Authorization automatically;
        # token is optional for local/dev testing.
        self.token = token if token is not None else os.environ.get("SIMON_AGENT_DB_TOKEN", "").strip()
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        data = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")

        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8").strip()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            with exc:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"SimonDB HTTP {exc.code} on {method} {path}: {detail}") from None
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"SimonDB network error on {method} {path}: {exc}") from None

    def list_docs(self, collection: str, limit: int = 25) -> List[Dict[str, Any]]:
        qs = urlencode({"limit": int(limit)})
        res = self._request("GET", f"/api/db/{quote(collection, safe='')}?{qs}")
        return list(res.get("documents") or [])

    def get_doc(self, collection: str, doc_id: str) -> Dict[str, Any]:
        res = self._request(
            "GET",
            f"/api/db/{quote(collection, safe='')}/{quote(doc_id, safe='')}",
        )
        return dict(res.get("document") or res)

    def save_doc(
        self,
        collection: str,
        payload: Dict[str, Any],
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        path = f"/api/db/{quote(collection, safe='')}"
        if doc_id:
            path = f"{path}?{urlencode({'doc_id': doc_id})}"
        return self._request("POST", path, body=payload)

    def log_discovered_source(
        self,
        url: str,
        source_channel: str,
        why_useful: str,
        discovered_by: str = "stage_1_discovery",
        title_or_node: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.save_doc(
            "discovered_sources",
            {
                "url": url,
                "source_channel": source_channel,
                "why_useful": why_useful,
                "discovered_by": discovered_by,
                "title_or_node": title_or_node,
            },
        )


def _load_json_arg(raw: str) -> Dict[str, Any]:
    if raw.startswith("@"):
        text = Path(raw[1:]).read_text(encoding="utf-8")
    elif raw == "-":
        text = sys.stdin.read()
    else:
        text = raw
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("JSON payload must be an object.")
    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Simon shared agent DB CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List documents in a collection.")
    p_list.add_argument("collection")
    p_list.add_argument("--limit", type=int, default=25)

    p_get = sub.add_parser("get", help="Get one document by ID.")
    p_get.add_argument("collection")
    p_get.add_argument("doc_id")

    p_save = sub.add_parser("save", help="Validate and save a JSON document.")
    p_save.add_argument("collection")
    p_save.add_argument("payload", help="Inline JSON, @path/to/file.json, or - for stdin.")
    p_save.add_argument("--doc-id", default=None)

    args = parser.parse_args(argv)
    db = SimonDB()

    if args.cmd == "list":
        out = db.list_docs(args.collection, limit=args.limit)
    elif args.cmd == "get":
        out = db.get_doc(args.collection, args.doc_id)
    else:
        out = db.save_doc(args.collection, _load_json_arg(args.payload), doc_id=args.doc_id)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
