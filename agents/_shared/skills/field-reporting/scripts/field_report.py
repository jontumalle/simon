#!/usr/bin/env python3
"""Human-first Field News & Scouting Report helper for Simon Managed Agents."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Allow importing SimonDB from sibling shared skill inside sandbox or repo
_HERE = Path(__file__).resolve()
for _candidate in (
    _HERE.parents[2] / "simon-db" / "scripts",
    Path(".agents/skills/simon-db/scripts"),
):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from simon_db import SimonDB  # type: ignore[import-not-found]

FORBIDDEN_KEYS = frozenset({"interaction_id", "environment_id", "metadata", "raw_trace", "trace_id"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_forbidden(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_forbidden(v) for k, v in obj.items() if k not in FORBIDDEN_KEYS}
    if isinstance(obj, list):
        return [_strip_forbidden(item) for item in obj]
    return obj


def _load_or_init_report(
    db: SimonDB,
    report_id: str,
    batch_id: Optional[str] = None,
    agent_name: str = "Simon Agent",
    stage: str = "discovery",
    brief: str = "",
) -> Dict[str, Any]:
    try:
        existing = db.get_doc("agent_reports", report_id)
        if isinstance(existing, dict) and existing.get("report_id"):
            return _strip_forbidden(existing)
    except RuntimeError:
        pass
    now = _utc_now()
    return {
        "contract_version": "1.0.0",
        "report_id": report_id,
        "batch_id": batch_id,
        "agent_name": agent_name,
        "stage": stage,
        "brief": brief,
        "assigned_sources": [],
        "status": "starting",
        "headline": f"{agent_name} started scouting.",
        "current_focus": brief or "Starting assignment",
        "steps": [],
        "findings": [],
        "output": None,
        "created_at": now,
        "updated_at": now,
    }


def _load_json_arg(raw: str) -> Any:
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    return json.loads(raw)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Publish human-first Field News and Scouting Reports.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_step = sub.add_parser("step", help="Append a human-readable Field News step.")
    p_step.add_argument("--report-id", required=True)
    p_step.add_argument("--batch-id", default=None)
    p_step.add_argument("--agent-name", default="Simon Agent")
    p_step.add_argument("--stage", default="discovery")
    p_step.add_argument("--brief", default="")
    p_step.add_argument("--phase", choices=["looking_at", "finding", "analysis", "saved"], default="looking_at")
    p_step.add_argument("--title", required=True)
    p_step.add_argument("--looking-at", default="")
    p_step.add_argument("--finding", default="")
    p_step.add_argument("--analysis", default="")
    p_step.add_argument("--status", choices=["active", "done", "blocked"], default="done")
    p_step.add_argument("--headline", default=None)

    p_find = sub.add_parser("finding", help="Add a concrete human-readable finding item.")
    p_find.add_argument("--report-id", required=True)
    p_find.add_argument("--title", required=True)
    p_find.add_argument("--summary", required=True)
    p_find.add_argument("--source-name", default="")
    p_find.add_argument("--source-channel", default="")
    p_find.add_argument("--url", default="")
    p_find.add_argument("--attribution-status", default="")

    p_fin = sub.add_parser("finish", help="Mark report completed and store final agent output.")
    p_fin.add_argument("--report-id", required=True)
    p_fin.add_argument("--headline", required=True)
    p_fin.add_argument("--output", required=True, help="JSON string or @path/to/output.json")
    p_fin.add_argument("--status", choices=["completed", "blocked"], default="completed")

    args = parser.parse_args(argv)
    db = SimonDB()

    if args.cmd == "step":
        report = _load_or_init_report(
            db,
            report_id=args.report_id,
            batch_id=args.batch_id,
            agent_name=args.agent_name,
            stage=args.stage,
            brief=args.brief,
        )
        steps: List[Dict[str, Any]] = list(report.get("steps") or [])
        step_obj = {
            "step_number": len(steps) + 1,
            "phase": args.phase,
            "title": args.title,
            "looking_at": args.looking_at,
            "finding": args.finding,
            "analysis": args.analysis,
            "status": args.status,
            "updated_at": _utc_now(),
        }
        steps.append(step_obj)
        report["steps"] = steps
        report["status"] = "blocked" if args.status == "blocked" else "in_motion"
        report["current_focus"] = args.looking_at or args.title
        if args.headline:
            report["headline"] = args.headline
        elif args.finding:
            report["headline"] = args.finding
        report["updated_at"] = _utc_now()
        saved = db.save_doc("agent_reports", _strip_forbidden(report), doc_id=args.report_id)
        print(json.dumps(saved, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "finding":
        report = _load_or_init_report(db, report_id=args.report_id)
        findings: List[Dict[str, Any]] = list(report.get("findings") or [])
        item = {
            "title": args.title,
            "summary": args.summary,
            "source_name": args.source_name,
            "source_channel": args.source_channel,
            "url": args.url,
            "attribution_status": args.attribution_status,
        }
        findings.append({k: v for k, v in item.items() if v})
        report["findings"] = findings
        report["status"] = "in_motion"
        report["updated_at"] = _utc_now()
        saved = db.save_doc("agent_reports", _strip_forbidden(report), doc_id=args.report_id)
        print(json.dumps(saved, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "finish":
        report = _load_or_init_report(db, report_id=args.report_id)
        output_payload = _load_json_arg(args.output)
        steps = list(report.get("steps") or [])
        steps.append(
            {
                "step_number": len(steps) + 1,
                "phase": "saved",
                "title": "Scouting report & output saved",
                "looking_at": "Final verified output contract",
                "finding": args.headline,
                "analysis": "Stored structured output in agent_reports for human review.",
                "status": "done" if args.status == "completed" else "blocked",
                "updated_at": _utc_now(),
            }
        )
        report["steps"] = steps
        report["status"] = args.status
        report["headline"] = args.headline
        report["current_focus"] = "Report completed"
        report["output"] = output_payload
        report["updated_at"] = _utc_now()
        saved = db.save_doc("agent_reports", _strip_forbidden(report), doc_id=args.report_id)
        print(json.dumps(saved, indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
