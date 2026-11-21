#!/usr/bin/env python3
"""Stdlib validator for Stage 3 Screening Judge (`ScreeningPacket` v1.0.0) JSON output."""

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

RUBRIC_KEYS = (
    "identity_reachability",
    "live_vocal_proof",
    "early_window_depth",
    "listener_pull_cosigns",
    "stage_momentum_whitespace",
)

VALID_VERDICTS = ("elevate", "watch", "pass")

REQUIRED_CORE_KEYS = (
    "lead_id",
    "stage_name",
    "verdict",
    "confidence",
    "total_score",
    "rubric_scores",
    "rationale",
    "advocate_case",
    "skeptic_case",
)

OPTIONAL_TOP_KEYS = {
    "schema_version",
    "contract_version",
    "packet_version",
    "packet_id",
    "run_id",
    "screened_at",
    "generated_at",
    "domain",
    "dossier",
    "open_questions",
    "recommended_next_step",
}


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


def _is_strict_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _is_strict_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _validate_embedded_advocate(adv: Any, packet_lead_id: Optional[str]) -> List[str]:
    errors: List[str] = []
    if not isinstance(adv, dict):
        return ["Field 'advocate_case' must be an object."]
    for req in ("lead_id", "stage_name", "headline", "pros", "standout_hook"):
        if req not in adv:
            errors.append(f"advocate_case missing required field '{req}'.")
    for sk in ("lead_id", "stage_name", "headline", "standout_hook"):
        if sk in adv and not _is_non_empty_str(adv[sk]):
            errors.append(f"advocate_case.{sk} must be a non-empty string.")
    if packet_lead_id and _is_non_empty_str(adv.get("lead_id")) and adv["lead_id"] != packet_lead_id:
        errors.append(
            f"advocate_case.lead_id ('{adv['lead_id']}') does not match ScreeningPacket.lead_id ('{packet_lead_id}')."
        )
    if "pros" in adv:
        pros = adv["pros"]
        if not isinstance(pros, list) or len(pros) == 0:
            errors.append("advocate_case.pros must be a non-empty list.")
        else:
            for idx, item in enumerate(pros):
                if not isinstance(item, dict):
                    errors.append(f"advocate_case.pros[{idx}] must be an object.")
                    continue
                for pk in ("skill", "title", "evidence"):
                    if pk not in item or not _is_non_empty_str(item[pk]):
                        errors.append(f"advocate_case.pros[{idx}].{pk} must be a non-empty string.")
    return errors


def _validate_embedded_skeptic(skp: Any, packet_lead_id: Optional[str]) -> List[str]:
    errors: List[str] = []
    if not isinstance(skp, dict):
        return ["Field 'skeptic_case' must be an object."]
    for req in (
        "lead_id",
        "stage_name",
        "headline",
        "cons",
        "missing_evidence_flags",
        "dealbreakers_checked",
    ):
        if req not in skp:
            errors.append(f"skeptic_case missing required field '{req}'.")
    for sk in ("lead_id", "stage_name", "headline"):
        if sk in skp and not _is_non_empty_str(skp[sk]):
            errors.append(f"skeptic_case.{sk} must be a non-empty string.")
    if packet_lead_id and _is_non_empty_str(skp.get("lead_id")) and skp["lead_id"] != packet_lead_id:
        errors.append(
            f"skeptic_case.lead_id ('{skp['lead_id']}') does not match ScreeningPacket.lead_id ('{packet_lead_id}')."
        )
    if "cons" in skp:
        cons = skp["cons"]
        if not isinstance(cons, list):
            errors.append("skeptic_case.cons must be a list.")
        else:
            for idx, item in enumerate(cons):
                if not isinstance(item, dict):
                    errors.append(f"skeptic_case.cons[{idx}] must be an object.")
                    continue
                for ck in ("skill", "title", "evidence"):
                    if ck not in item or not _is_non_empty_str(item[ck]):
                        errors.append(f"skeptic_case.cons[{idx}].{ck} must be a non-empty string.")
    if "missing_evidence_flags" in skp:
        flags = skp["missing_evidence_flags"]
        if not isinstance(flags, list) or any(not _is_non_empty_str(x) for x in flags):
            errors.append("skeptic_case.missing_evidence_flags must be a list of non-empty strings.")
    if "dealbreakers_checked" in skp:
        checked = skp["dealbreakers_checked"]
        if (
            not isinstance(checked, list)
            or len(checked) == 0
            or any(not _is_non_empty_str(x) for x in checked)
        ):
            errors.append(
                "skeptic_case.dealbreakers_checked must be a non-empty list of non-empty strings."
            )
    return errors


def validate_screening_packet(payload: Any) -> Tuple[bool, List[str]]:
    """Validate a `ScreeningPacket` v1.0.0 dictionary. Returns `(ok, errors)`."""
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["Root payload must be a JSON object."]

    errors.extend(_scan_forbidden(payload))

    version_keys = [k for k in ("schema_version", "contract_version", "packet_version") if k in payload]
    if not version_keys:
        errors.append("Missing required version field ('schema_version': '1.0.0').")
    else:
        for vk in version_keys:
            if payload[vk] != "1.0.0":
                errors.append(f"Field '{vk}' must equal '1.0.0' (got {payload[vk]!r}).")

    for req in REQUIRED_CORE_KEYS:
        if req not in payload:
            errors.append(f"Missing required field '{req}'.")

    allowed_top = set(REQUIRED_CORE_KEYS) | OPTIONAL_TOP_KEYS
    for k in payload:
        if k not in allowed_top and str(k).lower() not in FORBIDDEN_KEYS:
            errors.append(f"Unexpected top-level field '{k}'.")

    for sk in ("lead_id", "stage_name", "rationale"):
        if sk in payload and not _is_non_empty_str(payload[sk]):
            errors.append(f"Field '{sk}' must be a non-empty string.")

    for opt_sk in ("packet_id", "run_id", "screened_at", "generated_at", "domain", "recommended_next_step"):
        if opt_sk in payload and payload[opt_sk] is not None and not _is_non_empty_str(payload[opt_sk]):
            errors.append(f"Optional field '{opt_sk}' must be a non-empty string when provided.")

    if "verdict" in payload and payload["verdict"] not in VALID_VERDICTS:
        errors.append(
            f"Field 'verdict' must be one of {list(VALID_VERDICTS)} (got {payload['verdict']!r})."
        )

    if "confidence" in payload:
        conf = payload["confidence"]
        if not _is_strict_number(conf) or conf < 0.0 or conf > 1.0:
            errors.append("Field 'confidence' must be a number between 0.0 and 1.0.")

    computed_sum: Optional[int] = None
    if "rubric_scores" in payload:
        scores = payload["rubric_scores"]
        if not isinstance(scores, dict):
            errors.append("Field 'rubric_scores' must be an object mapping all 5 rubrics to 0..2.")
        else:
            valid_all_scores = True
            running_total = 0
            for rk in RUBRIC_KEYS:
                if rk not in scores:
                    errors.append(f"rubric_scores missing required rubric '{rk}'.")
                    valid_all_scores = False
                else:
                    val = scores[rk]
                    if not _is_strict_int(val) or val < 0 or val > 2:
                        errors.append(f"rubric_scores.{rk} must be an integer in 0..2 (got {val!r}).")
                        valid_all_scores = False
                    else:
                        running_total += val
            for uk in scores:
                if uk not in RUBRIC_KEYS and str(uk).lower() not in FORBIDDEN_KEYS:
                    errors.append(f"rubric_scores contains unexpected key '{uk}'.")
            if valid_all_scores:
                computed_sum = running_total

    if "total_score" in payload:
        ts = payload["total_score"]
        if not _is_strict_int(ts) or ts < 0 or ts > 10:
            errors.append(f"Field 'total_score' must be an integer in 0..10 (got {ts!r}).")
        elif computed_sum is not None and ts != computed_sum:
            errors.append(
                f"Field 'total_score' ({ts}) does not equal sum of rubric_scores ({computed_sum})."
            )

    packet_lead_id = payload.get("lead_id") if _is_non_empty_str(payload.get("lead_id")) else None
    if "advocate_case" in payload:
        errors.extend(_validate_embedded_advocate(payload["advocate_case"], packet_lead_id))
    if "skeptic_case" in payload:
        errors.extend(_validate_embedded_skeptic(payload["skeptic_case"], packet_lead_id))

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
    parser = argparse.ArgumentParser(description="Validate Stage 3 ScreeningPacket v1.0.0 JSON.")
    parser.add_argument("path", nargs="?", default=None, help="Path to JSON file (or '-' for stdin).")
    parser.add_argument("--input", "-i", dest="input_file", default=None, help="Path to JSON file.")
    args = parser.parse_args(argv)

    target = args.input_file or args.path
    try:
        payload = _load_json_input(target)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [f"Failed to parse JSON: {exc}"]}))
        return 1

    ok, errors = validate_screening_packet(payload)
    if not ok:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "lead_id": payload["lead_id"],
                "stage_name": payload["stage_name"],
                "verdict": payload["verdict"],
                "total_score": payload["total_score"],
                "confidence": payload["confidence"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
