#!/usr/bin/env python3
"""Stdlib validator for Stage 3 Talent Advocate (`advocate_case`) JSON output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

FORBIDDEN_KEYS = {
    "interaction_id",
    "environment_id",
    "sandbox_id",
    "session_id",
    "agent_session_id",
    "raw_trace",
    "api_key",
    "simon_agent_db_token",
}

FORBIDDEN_SUBSTRINGS = (
    "interaction_id",
    "environment_id",
)

REQUIRED_TOP_KEYS = (
    "lead_id",
    "stage_name",
    "headline",
    "pros",
    "standout_hook",
)

REQUIRED_PRO_KEYS = (
    "skill",
    "title",
    "evidence",
)


def _scan_forbidden(obj: Any, path: str = "$") -> List[str]:
    errors: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_str = str(k)
            key_low = key_str.lower()
            if key_low in FORBIDDEN_KEYS:
                errors.append(f"{path}.{key_str}: forbidden internal key '{key_str}' is not allowed.")
            errors.extend(_scan_forbidden(v, f"{path}.{key_str}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            errors.extend(_scan_forbidden(item, f"{path}[{idx}]"))
    elif isinstance(obj, str):
        low = obj.lower()
        for sub in FORBIDDEN_SUBSTRINGS:
            if sub in low:
                errors.append(f"{path}: string value leaks forbidden token '{sub}'.")
    return errors


def _is_non_empty_str(val: Any) -> bool:
    return isinstance(val, str) and bool(val.strip())


def validate_advocate_case(payload: Any) -> Tuple[bool, List[str]]:
    """Validate an `advocate_case` dictionary. Returns `(ok, errors)`."""
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["Root payload must be a JSON object."]

    errors.extend(_scan_forbidden(payload))

    for req in REQUIRED_TOP_KEYS:
        if req not in payload:
            errors.append(f"Missing required field '{req}'.")

    allowed = set(REQUIRED_TOP_KEYS)
    for k in payload:
        if k not in allowed and str(k).lower() not in FORBIDDEN_KEYS:
            errors.append(f"Unexpected top-level field '{k}'.")

    for str_key in ("lead_id", "stage_name", "headline", "standout_hook"):
        if str_key in payload and not _is_non_empty_str(payload[str_key]):
            errors.append(f"Field '{str_key}' must be a non-empty string.")

    if "pros" in payload:
        pros = payload["pros"]
        if not isinstance(pros, list) or len(pros) == 0:
            errors.append("Field 'pros' must be a non-empty list of pro objects.")
        else:
            pro_allowed = set(REQUIRED_PRO_KEYS)
            for idx, item in enumerate(pros):
                if not isinstance(item, dict):
                    errors.append(f"pros[{idx}] must be an object.")
                    continue
                for pk in REQUIRED_PRO_KEYS:
                    if pk not in item or not _is_non_empty_str(item[pk]):
                        errors.append(f"pros[{idx}].{pk} must be a non-empty string.")
                for uk in item:
                    if uk not in pro_allowed and str(uk).lower() not in FORBIDDEN_KEYS:
                        errors.append(f"pros[{idx}] contains unexpected field '{uk}'.")

    return len(errors) == 0, errors


def _load_json_input(file_arg: Optional[str]) -> Any:
    if file_arg and file_arg != "-":
        raw = Path(file_arg).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Stage 3 advocate_case JSON.")
    parser.add_argument("path", nargs="?", default=None, help="Path to JSON file (or '-' for stdin).")
    parser.add_argument("--input", "-i", dest="input_file", default=None, help="Path to JSON file.")
    args = parser.parse_args(argv)

    target = args.input_file or args.path
    try:
        payload = _load_json_input(target)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [f"Failed to parse JSON: {exc}"]}))
        return 1

    ok, errors = validate_advocate_case(payload)
    if not ok:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "lead_id": payload["lead_id"],
                "stage_name": payload["stage_name"],
                "pros_count": len(payload["pros"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
