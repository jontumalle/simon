#!/usr/bin/env python3
"""Read-only telemetry extractor for the `process-observer` skill.

Scans Antigravity session transcripts (`<brain-dir>/<conv-id>/.system_generated/logs/transcript.jsonl`)
for conversations operating in the Simon repository and extracts structured, non-binary signals:
- Root chat sessions vs. spawned subagents
- Skill invocations (`SKILL.md` reads) vs. available repo skills
- Lifecycle hook events (`SessionStart` injections, `Stop` blocks, `PreToolUse` blocks)
- Tool validation errors, non-zero command exits, sandbox/permission errors, canceled tasks
- Concise user prompt timeline for qualitative context

Outputs JSON (`--format json`) or a readable Markdown digest (`--format markdown`, default).
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any


USER_REQ_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
EXIT_CODE_RE = re.compile(r"Command exited with code (\d+)\.")
SKILL_PATH_RE = re.compile(r"([^/\"\\]+)/SKILL\.md")
STOP_BLOCK_RE = re.compile(r"Stop hook blocked termination:\s*(.+)")
CANCELED_TASK_RE = re.compile(r'Task id "([^"]+)" was canceled')


def clean_arg_str(val: Any) -> str:
    if not isinstance(val, str):
        return ""
    s = val.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return json.loads(s)
        except Exception:
            return s.strip('"')
    return s


def default_brain_dir() -> Path:
    return Path.home() / ".gemini" / "antigravity" / "brain"


def default_repo_root() -> Path:
    # .agents/skills/process-observer/scripts/inspect_sessions.py -> parents[4] is repo root
    return Path(__file__).resolve().parents[4]


def discover_repo_skills(repo_root: Path) -> list[str]:
    skills_dir = repo_root / ".agents" / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(
        p.parent.name
        for p in skills_dir.glob("*/SKILL.md")
        if p.is_file()
    )


def analyze_transcript(
    jsonl_path: Path,
    workspace_marker: str,
    max_events_per_session: int = 25,
) -> dict[str, Any] | None:
    conv_id = jsonl_path.parents[2].name
    matched_workspace = False
    is_root_chat = False
    started_at = None
    ended_at = None
    step_count = 0

    skills_read: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    hook_events: list[dict[str, Any]] = []
    frictions: list[dict[str, Any]] = []
    user_prompts: list[dict[str, Any]] = []
    subagents_spawned = 0

    try:
        raw_lines = jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    for raw in raw_lines:
        if not raw.strip():
            continue
        if workspace_marker in raw:
            matched_workspace = True
        try:
            step = json.loads(raw)
        except json.JSONDecodeError:
            continue

        step_count += 1
        ts = step.get("created_at")
        if ts:
            if started_at is None:
                started_at = ts
            ended_at = ts

        step_idx = step.get("step_index")
        source = step.get("source", "")
        stype = step.get("type", "")
        status = step.get("status", "")
        content = step.get("content", "") or ""

        if stype == "USER_INPUT" or source == "USER_EXPLICIT":
            is_root_chat = True
            m = USER_REQ_RE.search(content)
            text = (m.group(1) if m else content).strip()
            if text:
                snippet = " ".join(text.split())[:220]
                user_prompts.append({"step": step_idx, "at": ts, "prompt": snippet})

        # Hook detections in SYSTEM_MESSAGE / content
        if "injected by a SessionStart hook" in content:
            hook_events.append({
                "step": step_idx,
                "hook": "SessionStart",
                "kind": "context_injected",
            })
        for stop_m in STOP_BLOCK_RE.finditer(content):
            reason = " ".join(stop_m.group(1).split())[:240]
            hook_events.append({
                "step": step_idx,
                "hook": "Stop",
                "kind": "blocked_termination",
                "detail": reason,
            })
            frictions.append({
                "step": step_idx,
                "signal": "hook_block",
                "summary": f"Stop hook blocked termination: {reason}",
            })

        # Tool calls
        for tc in step.get("tool_calls") or []:
            tname = tc.get("name", "unknown")
            tool_counts[tname] += 1
            args = tc.get("args") or {}
            if tname == "invoke_subagent":
                subagents_spawned += 1
            if tname == "read_file":
                p_val = clean_arg_str(args.get("Path", ""))
                sm = SKILL_PATH_RE.search(p_val)
                if sm:
                    skill_name = sm.group(1)
                    scope = "repo" if "/.agents/skills/" in p_val else (
                        "plugin" if "/plugins/" in p_val else "builtin"
                    )
                    skills_read[f"{scope}:{skill_name}"] += 1

        # Friction signals in tool outputs / errors
        if status == "ERROR" or "Encountered error in tool validation" in content:
            snippet = " ".join(content.split())[:220]
            frictions.append({
                "step": step_idx,
                "signal": "tool_validation_or_step_error",
                "summary": snippet,
            })

        exit_m = EXIT_CODE_RE.search(content)
        if exit_m and exit_m.group(1) != "0":
            code = int(exit_m.group(1))
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            tail = " | ".join(lines[-3:])[:240]
            signal_type = "command_nonzero_exit"
            if "Operation not permitted" in content:
                signal_type = "sandbox_or_fs_permission"
            elif "403" in content or "Permission to " in content:
                signal_type = "auth_or_rate_limit_403"
            elif "ModuleNotFoundError" in content or "ImportError" in content:
                signal_type = "python_import_or_env"
            frictions.append({
                "step": step_idx,
                "signal": signal_type,
                "exit_code": code,
                "summary": tail,
            })

        cancel_m = CANCELED_TASK_RE.search(content)
        if cancel_m:
            frictions.append({
                "step": step_idx,
                "signal": "canceled_background_task",
                "summary": f"Background task canceled ({cancel_m.group(1)})",
            })

    if not matched_workspace:
        return None

    return {
        "conversation_id": conv_id,
        "kind": "root_chat" if is_root_chat else "subagent",
        "started_at": started_at,
        "ended_at": ended_at,
        "steps": step_count,
        "subagents_spawned": subagents_spawned,
        "skills_invoked": dict(skills_read),
        "top_tools": dict(tool_counts.most_common(8)),
        "hook_events": hook_events[:max_events_per_session],
        "friction_signals": frictions[:max_events_per_session],
        "user_prompts": user_prompts[:12],
    }


def collect_telemetry(brain_dir: Path, repo_root: Path, limit: int) -> dict[str, Any]:
    workspace_marker = str(repo_root)
    repo_skills = discover_repo_skills(repo_root)

    sessions: list[dict[str, Any]] = []
    if brain_dir.is_dir():
        candidates = sorted(
            brain_dir.glob("*/.system_generated/logs/transcript.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for jsonl in candidates:
            info = analyze_transcript(jsonl, workspace_marker)
            if info is not None:
                sessions.append(info)
                if len(sessions) >= limit:
                    break

    skill_totals: Counter[str] = Counter()
    friction_totals: Counter[str] = Counter()
    hook_totals: Counter[str] = Counter()

    for s in sessions:
        for k, v in s["skills_invoked"].items():
            skill_totals[k] += v
        for f in s["friction_signals"]:
            friction_totals[f["signal"]] += 1
        for h in s["hook_events"]:
            hook_totals[f"{h['hook']}:{h['kind']}"] += 1

    invoked_repo_skill_names = {
        k.split(":", 1)[1]
        for k in skill_totals
        if k.startswith("repo:")
    }
    uninvoked_repo_skills = [sk for sk in repo_skills if sk not in invoked_repo_skill_names]

    return {
        "workspace": workspace_marker,
        "sessions_scanned": len(sessions),
        "root_chats": sum(1 for s in sessions if s["kind"] == "root_chat"),
        "subagents": sum(1 for s in sessions if s["kind"] == "subagent"),
        "repo_skills_defined": repo_skills,
        "repo_skills_not_yet_invoked": uninvoked_repo_skills,
        "skill_invocation_counts": dict(skill_totals.most_common()),
        "hook_event_counts": dict(hook_totals.most_common()),
        "friction_signal_counts": dict(friction_totals.most_common()),
        "sessions": sessions,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Session Process Telemetry Digest",
        "",
        f"- **Workspace**: `{report['workspace']}`",
        f"- **Conversations matched**: `{report['sessions_scanned']}` "
        f"(`{report['root_chats']}` root chat windows, `{report['subagents']}` subagents)",
        f"- **Repo skills defined**: `{', '.join(report['repo_skills_defined']) or 'none'}`",
        f"- **Repo skills not yet invoked via `read_file`**: "
        f"`{', '.join(report['repo_skills_not_yet_invoked']) or 'none'}`",
        "",
        "## Aggregate Signal Counts",
        "- **Skills read**: "
        + (
            ", ".join(f"`{k}` ({v})" for k, v in report["skill_invocation_counts"].items())
            or "none"
        ),
        "- **Hook events**: "
        + (
            ", ".join(f"`{k}` ({v})" for k, v in report["hook_event_counts"].items())
            or "none"
        ),
        "- **Friction signals**: "
        + (
            ", ".join(f"`{k}` ({v})" for k, v in report["friction_signal_counts"].items())
            or "none"
        ),
        "",
        "## Per-Session Highlights",
    ]
    for s in report["sessions"]:
        cid = s["conversation_id"]
        lines.append(
            f"### `{cid[:8]}` ({s['kind']}) · steps={s['steps']} · "
            f"subagents={s['subagents_spawned']} · last={s['ended_at']}"
        )
        if s["skills_invoked"]:
            sk = ", ".join(f"`{k}`×{v}" for k, v in s["skills_invoked"].items())
            lines.append(f"- **Skills**: {sk}")
        if s["user_prompts"]:
            lines.append(f"- **Recent user intent**: {s['user_prompts'][-1]['prompt']}")
        if s["friction_signals"]:
            lines.append("- **Observed frictions**:")
            for f in s["friction_signals"][:5]:
                lines.append(f"  - `[step {f['step']}]` `{f['signal']}`: {f['summary']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Antigravity transcripts for process telemetry.")
    parser.add_argument("--brain-dir", type=Path, default=default_brain_dir())
    parser.add_argument("--workspace", type=Path, default=default_repo_root())
    parser.add_argument("--limit", type=int, default=20, help="Max matching conversations to scan.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    report = collect_telemetry(args.brain_dir.expanduser(), args.workspace.resolve(), args.limit)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
