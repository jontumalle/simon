#!/usr/bin/env python3
"""Antigravity Stop hook enforcing Simon's zero-repercussion doc/knowledge sync policy.

When a turn ends normally (`terminationReason == "NO_TOOL_CALL"` and
`not continuationActive`), checks `git status --porcelain` for uncommitted
Markdown or knowledge-model files (`*.md`, `pm/`, `notes/`, `ideas/`, `data/`,
`agents/`, `.agents/`, excluding `local/` and `.venv/`). If found, nudges the
agent once to file and sync them to `main` via `sync_main.py --docs-only`.
"""

import json
from pathlib import Path
import subprocess
import sys
from typing import List


KNOWLEDGE_DIRS = frozenset({"governance", "pm", "notes", "ideas", "data", "agents", ".agents"})
FORBIDDEN_TOP_DIRS = frozenset({"local", ".venv", ".git"})
FORBIDDEN_PART_NAMES = frozenset({".git", ".venv", "__pycache__", ".DS_Store"})
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pyd")


def is_doc_or_knowledge_path(rel_path: str) -> bool:
    norm = rel_path.strip("/")
    if not norm:
        return False
    parts = Path(norm).parts
    if not parts or parts[0] in FORBIDDEN_TOP_DIRS:
        return False
    for part in parts:
        if part in FORBIDDEN_PART_NAMES or part.startswith(".env"):
            return False
    if norm.endswith(FORBIDDEN_SUFFIXES):
        return False
    if norm.endswith(".md"):
        return True
    if parts[0] in KNOWLEDGE_DIRS:
        return True
    return False


def parse_porcelain_z(output: str) -> List[str]:
    tokens = output.split("\0")
    idx = 0
    seen = set()
    paths: List[str] = []
    while idx < len(tokens):
        entry = tokens[idx]
        idx += 1
        if len(entry) < 4:
            continue
        xy = entry[:2]
        path = entry[3:]
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
        if xy[0] in ("R", "C") and idx < len(tokens):
            orig = tokens[idx]
            idx += 1
            if orig and orig not in seen:
                seen.add(orig)
                paths.append(orig)
    return paths


def resolve_repo_root(cwd_value: object) -> Path:
    default_root = Path(__file__).resolve().parents[2]
    candidate = default_root
    if isinstance(cwd_value, str) and cwd_value.strip():
        cwd_path = Path(cwd_value).expanduser()
        if cwd_path.is_dir():
            candidate = cwd_path

    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(candidate),
        capture_output=True,
        text=True,
        timeout=3,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return default_root


def main() -> None:
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            print("{}")
            return

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            print("{}")
            return

        termination_reason = payload.get("terminationReason")
        continuation_active = bool(payload.get("continuationActive", False))
        fully_idle = bool(payload.get("fullyIdle", True))
        if termination_reason != "NO_TOOL_CALL" or continuation_active or not fully_idle:
            print("{}")
            return

        repo_root = resolve_repo_root(payload.get("cwd"))
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "-uall"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=4,
        )
        if proc.returncode != 0:
            print("{}")
            return

        all_dirty = parse_porcelain_z(proc.stdout)
        dirty_docs = [p for p in all_dirty if is_doc_or_knowledge_path(p)]
        if not dirty_docs:
            print("{}")
            return

        shown = ", ".join(dirty_docs[:5])
        if len(dirty_docs) > 5:
            shown = f"{shown} (+{len(dirty_docs) - 5} more)"

        reason = (
            f"Uncommitted documentation/knowledge-model files detected ({shown}). "
            "Per repo governance, Markdown and knowledge-model docs can be committed and "
            "pushed directly to main with zero repercussions. Organize them into the "
            "knowledge model (via the project-manager / main-sync skill) and run "
            'python3 .agents/scripts/sync_main.py --docs-only -m "..." before finishing.'
        )
        print(json.dumps({"decision": "continue", "reason": reason}))
    except Exception:
        print("{}")


if __name__ == "__main__":
    main()
