#!/usr/bin/env python3
"""Stdlib validator for Stage 3 Talent Skeptic (`skeptic_case`) JSON output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    "cons",
    "missing_evidence_flags",
    "dealbreakers_checked",
)

REQUIRED_CON_KEYS = (
    "skill",
    "title",
    "evidence",
)


def _scan_forbidden(obj: Any, path: str = "$") -> List[str]:
    errors: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_str = str(k)
            if key_str.lower() in FORBIDDEN_KEYS:
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


def validate_skeptic_case(
    payload: Any,
    dossier: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """Validate a `skeptic_case` dictionary. Returns `(ok, errors)`."""
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

    for str_key in ("lead_id", "stage_name", "headline"):
        if str_key in payload and not _is_non_empty_str(payload[str_key]):
            errors.append(f"Field '{str_key}' must be a non-empty string.")

    if "cons" in payload:
        cons = payload["cons"]
        if not isinstance(cons, list):
            errors.append("Field 'cons' must be a list of con objects.")
        else:
            con_allowed = set(REQUIRED_CON_KEYS)
            for idx, item in enumerate(cons):
                if not isinstance(item, dict):
                    errors.append(f"cons[{idx}] must be an object.")
                    continue
                for ck in REQUIRED_CON_KEYS:
                    if ck not in item or not _is_non_empty_str(item[ck]):
                        errors.append(f"cons[{idx}].{ck} must be a non-empty string.")
                for uk in item:
                    if uk not in con_allowed and str(uk).lower() not in FORBIDDEN_KEYS:
                        errors.append(f"cons[{idx}] contains unexpected field '{uk}'.")

    if "missing_evidence_flags" in payload:
        flags = payload["missing_evidence_flags"]
        if not isinstance(flags, list):
            errors.append("Field 'missing_evidence_flags' must be a list of strings.")
        else:
            for idx, flag in enumerate(flags):
                if not _is_non_empty_str(flag):
                    errors.append(f"missing_evidence_flags[{idx}] must be a non-empty string.")
            if isinstance(dossier, dict):
                expected_missing = dossier.get("missing_fields") or []
                flag_set = set(flags)
                for mf in expected_missing:
                    if isinstance(mf, str) and mf.strip() and mf not in flag_set:
                        errors.append(
                            f"dossier.missing_fields item '{mf}' missing from missing_evidence_flags."
                        )

    if "dealbreakers_checked" in payload:
        checked = payload["dealbreakers_checked"]
        if not isinstance(checked, list) or len(checked) == 0:
            errors.append("Field 'dealbreakers_checked' must be a non-empty list of strings.")
        else:
            for idx, db_name in enumerate(checked):
                if not _is_non_empty_str(db_name):
                    errors.append(f"dealbreakers_checked[{idx}] must be a non-empty string.")

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
    parser = argparse.ArgumentParser(description="Validate Stage 3 skeptic_case JSON.")
    parser.add_argument("path", nargs="?", default=None, help="Path to JSON file (or '-' for stdin).")
    parser.add_argument("--input", "-i", dest="input_file", default=None, help="Path to JSON file.")
    parser.add_argument(
        "--dossier",
        dest="dossier_file",
        default=None,
        help="Optional Stage 2 dossier JSON path to verify missing_fields preservation.",
    )
    args = parser.parse_args(argv)

    target = args.input_file or args.path
    try:
        payload = _load_json_input(target)
        dossier_obj = (
            json.loads(Path(args.dossier_file).read_text(encoding="utf-8"))
            if args.dossier_file
            else None
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [f"Failed to parse JSON: {exc}"]}))
        return 1

    ok, errors = validate_skeptic_case(payload, dossier=dossier_obj)
    if not ok:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "lead_id": payload["lead_id"],
                "stage_name": payload["stage_name"],
                "cons_count": len(payload["cons"]),
                "missing_evidence_count": len(payload["missing_evidence_flags"]),
                "dealbreakers_checked_count": len(payload["dealbreakers_checked"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
