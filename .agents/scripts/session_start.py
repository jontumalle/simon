#!/usr/bin/env python3
"""Injects Simon's PROJECT.md pointer index and main-sync status at SessionStart."""

import json
from pathlib import Path
import subprocess
import sys


def resolve_repo_root(raw_stdin: str) -> Path:
    default_root = Path(__file__).resolve().parents[2]
    if not raw_stdin:
        return default_root
    try:
        payload = json.loads(raw_stdin)
        cwd_val = payload.get("cwd") if isinstance(payload, dict) else None
        if isinstance(cwd_val, str) and cwd_val.strip():
            cwd_path = Path(cwd_val).expanduser()
            if cwd_path.is_dir():
                proc = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=str(cwd_path),
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return Path(proc.stdout.strip()).resolve()
    except Exception:
        pass
    return default_root


def get_git_sync_summary(repo_root: Path) -> str:
    """Fast local check of branch ahead/behind status and uncommitted file count."""
    try:
        proc = subprocess.run(
            ["git", "status", "-sb"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return "Git status: unavailable"
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        branch_line = lines[0][3:].strip() if lines[0].startswith("## ") else lines[0].strip()
        if "..." in branch_line and "[" not in branch_line:
            branch_line = f"{branch_line} [in sync]"
        dirty_count = max(0, len(lines) - 1)
        dirty_label = (
            "clean working tree"
            if dirty_count == 0
            else f"{dirty_count} uncommitted path{'s' if dirty_count != 1 else ''}"
        )
        return f"Git status: {branch_line} · {dirty_label}"
    except Exception:
        return "Git status: unavailable"


def main() -> None:
    try:
        raw_stdin = sys.stdin.read().strip()
        repo_root = resolve_repo_root(raw_stdin)
        project_md = repo_root / "PROJECT.md"
        if not project_md.is_file():
            print("{}")
            return

        git_summary = get_git_sync_summary(repo_root)
        content = project_md.read_text(encoding="utf-8").strip()
        msg = (
            "Simon repository knowledge model active (Life OS pattern).\n"
            f"[{git_summary}]\n"
            "Trunk-Sync & Steward Rules (see .agents/skills/main-sync/SKILL.md & project-manager):\n"
            "- Pull (`git pull --rebase --autostash origin main`) and push `main` frequently so parallel chat windows and teammates stay aligned.\n"
            "- Zero-repercussion docs policy: ALL Markdown (`*.md`) and knowledge-model updates (`PROJECT.md`, `AGENTS.md`, `RESOURCES.md`, `pm/`, `notes/`, `ideas/`, `data/`, `agents/`, `.agents/`) commit and push directly to `main` via `python3 .agents/scripts/sync_main.py --docs-only -m \"...\"`.\n"
            "- Every chat window with substantive work, findings, or decisions should launch the background `project-manager` subagent to distill session docs into `pm/` + `PROJECT.md` and sync to `main`.\n"
            "Follow pointers from PROJECT.md below; check RESOURCES.md for shared partner tooling.\n\n"
            f"{content}"
        )
        print(
            json.dumps(
                {
                    "injectSteps": [
                        {
                            "systemMessage": {
                                "systemMessage": msg,
                            }
                        }
                    ]
                }
            )
        )
    except Exception:
        print("{}")


if __name__ == "__main__":
    main()
