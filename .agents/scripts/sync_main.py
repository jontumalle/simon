#!/usr/bin/env python3
"""Safe trunk-sync utility for the Simon repository (origin/main).

Stages documentation/knowledge-model changes by default (--docs-only) or all safe
repository files (--all), commits if staged changes exist, pulls with rebase +
autostash from origin/main, and pushes to origin/main unless --no-push is set.
Never stages .env*, local/, or .venv/.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


ROOT_DOC_FILES = frozenset({"PROJECT.md", "AGENTS.md", "RESOURCES.md", "README.md"})
KNOWLEDGE_DIRS = frozenset({"pm", "notes", "ideas", "data", "agents", ".agents"})
FORBIDDEN_TOP_DIRS = frozenset({"local", ".venv", ".git"})
FORBIDDEN_PART_NAMES = frozenset({".git", ".venv", "__pycache__", ".DS_Store"})
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pyd")


def build_git_env() -> Dict[str, str]:
    """Ensure ~/.local/bin is prepended to PATH so gh git-credential helper works."""
    env = os.environ.copy()
    local_bin = str(Path.home() / ".local" / "bin")
    current_path = env.get("PATH", "")
    parts = current_path.split(os.pathsep) if current_path else []
    if local_bin not in parts:
        env["PATH"] = f"{local_bin}{os.pathsep}{current_path}" if current_path else local_bin
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return env


def run_git(
    args: List[str],
    cwd: Path,
    env: Dict[str, str],
    timeout: Optional[int] = 15,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def is_forbidden_path(rel_path: str) -> bool:
    norm = rel_path.strip("/")
    if not norm:
        return True
    parts = Path(norm).parts
    if not parts:
        return True
    if parts[0] in FORBIDDEN_TOP_DIRS:
        return True
    for part in parts:
        if part in FORBIDDEN_PART_NAMES or part.startswith(".env"):
            return True
    if norm.endswith(FORBIDDEN_SUFFIXES):
        return True
    return False


def is_doc_or_knowledge_path(rel_path: str) -> bool:
    if is_forbidden_path(rel_path):
        return False
    norm = rel_path.strip("/")
    parts = Path(norm).parts
    if norm in ROOT_DOC_FILES:
        return True
    if parts and parts[0] in KNOWLEDGE_DIRS:
        return True
    if norm.endswith(".md"):
        return True
    return False


def parse_porcelain_z(output: str) -> List[str]:
    """Parse `git status --porcelain=v1 -z -uall` output into repo-relative paths."""
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


def get_head_and_ahead(cwd: Path, env: Dict[str, str]) -> Tuple[str, int]:
    head = ""
    ahead = 0
    head_proc = run_git(["rev-parse", "--short", "HEAD"], cwd=cwd, env=env, timeout=5)
    if head_proc.returncode == 0:
        head = head_proc.stdout.strip()

    ahead_proc = run_git(
        ["rev-list", "--count", "origin/main..HEAD"], cwd=cwd, env=env, timeout=5
    )
    if ahead_proc.returncode == 0:
        try:
            ahead = int(ahead_proc.stdout.strip())
        except ValueError:
            ahead = 0
    return head, ahead


def is_rebase_in_progress(cwd: Path, env: Dict[str, str]) -> bool:
    for marker in ("rebase-merge", "rebase-apply"):
        proc = run_git(["rev-parse", "--git-path", marker], cwd=cwd, env=env, timeout=5)
        if proc.returncode == 0:
            p = Path(proc.stdout.strip())
            full = p if p.is_absolute() else (cwd / p)
            if full.exists():
                return True
    return False


def compact_err(prefix: str, proc_or_msg: object) -> str:
    if isinstance(proc_or_msg, subprocess.CompletedProcess):
        detail = (proc_or_msg.stderr or proc_or_msg.stdout or "").strip()
    else:
        detail = str(proc_or_msg).strip()
    detail_single = " | ".join(line.strip() for line in detail.splitlines() if line.strip())
    return f"{prefix}: {detail_single}" if detail_single else prefix


def chunked(items: List[str], size: int = 200) -> List[List[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage, commit, pull-rebase, and push Simon updates safely to origin/main."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--docs-only",
        action="store_true",
        help="Stage only Markdown and knowledge-model paths (default when --all is omitted).",
    )
    mode_group.add_argument(
        "--all",
        action="store_true",
        help="Stage all repository changes except .env*, local/, and .venv/.",
    )
    parser.add_argument(
        "-m",
        "--message",
        default="docs: sync knowledge model updates to main",
        help='Commit message (default: "docs: sync knowledge model updates to main").',
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip pushing to origin/main after committing and rebasing.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional path to repository root (defaults to Simon repo root).",
    )
    args = parser.parse_args()

    docs_only = not args.all
    repo_root = (
        Path(args.repo).resolve()
        if args.repo
        else Path(__file__).resolve().parents[2]
    )
    env = build_git_env()

    committed = False
    pulled = False
    pushed = False
    errors: List[str] = []

    def emit(exit_code: int) -> int:
        head, ahead = get_head_and_ahead(repo_root, env)
        summary = {
            "committed": committed,
            "pulled": pulled,
            "pushed": pushed,
            "head": head,
            "ahead": ahead,
            "error": "; ".join(errors) if errors else None,
        }
        print(json.dumps(summary))
        return exit_code

    # Verify repository root is a valid git working tree.
    top_proc = run_git(["rev-parse", "--show-toplevel"], cwd=repo_root, env=env, timeout=5)
    if top_proc.returncode != 0:
        errors.append(compact_err("Not a valid git repository", top_proc))
        return emit(1)
    repo_root = Path(top_proc.stdout.strip()).resolve()

    allowed_fn = is_doc_or_knowledge_path if docs_only else (lambda p: not is_forbidden_path(p))

    # 1. Ensure pre-staged files outside the allowed scope (or forbidden paths) are unstaged.
    staged_proc = run_git(["diff", "--cached", "--name-only", "-z"], cwd=repo_root, env=env, timeout=10)
    if staged_proc.returncode == 0 and staged_proc.stdout:
        staged_paths = [p for p in staged_proc.stdout.split("\0") if p]
        unstage_targets = [p for p in staged_paths if not allowed_fn(p)]
        if unstage_targets:
            has_head = run_git(["rev-parse", "--verify", "HEAD"], cwd=repo_root, env=env, timeout=5).returncode == 0
            for batch in chunked(unstage_targets):
                if has_head:
                    run_git(["reset", "-q", "HEAD", "--", *batch], cwd=repo_root, env=env, timeout=10)
                else:
                    run_git(["rm", "--cached", "-q", "--", *batch], cwd=repo_root, env=env, timeout=10)

    # 2. Discover candidate modified/deleted/untracked paths and stage allowed ones.
    status_proc = run_git(
        ["status", "--porcelain=v1", "-z", "-uall"], cwd=repo_root, env=env, timeout=10
    )
    if status_proc.returncode != 0:
        errors.append(compact_err("git status failed", status_proc))
        return emit(1)

    candidate_paths = parse_porcelain_z(status_proc.stdout)
    paths_to_stage = [p for p in candidate_paths if allowed_fn(p)]
    for batch in chunked(paths_to_stage):
        add_proc = run_git(["add", "-A", "--", *batch], cwd=repo_root, env=env, timeout=15)
        if add_proc.returncode != 0:
            errors.append(compact_err("git add failed", add_proc))
            return emit(1)

    # 3. Commit if staged diff is non-empty.
    diff_proc = run_git(["diff", "--cached", "--quiet"], cwd=repo_root, env=env, timeout=10)
    if diff_proc.returncode == 1:
        commit_proc = run_git(["commit", "-m", args.message], cwd=repo_root, env=env, timeout=15)
        if commit_proc.returncode != 0:
            errors.append(compact_err("git commit failed", commit_proc))
            return emit(1)
        committed = True
    elif diff_proc.returncode != 0:
        errors.append(compact_err("git diff --cached failed", diff_proc))
        return emit(1)

    # 4. Pull --rebase --autostash origin main (handle missing/unreachable remote gracefully).
    remote_proc = run_git(["remote", "get-url", "origin"], cwd=repo_root, env=env, timeout=5)
    has_origin = remote_proc.returncode == 0
    rebase_conflict = False
    pull_unreachable = False

    if has_origin:
        try:
            pull_proc = run_git(
                ["pull", "--rebase", "--autostash", "origin", "main"],
                cwd=repo_root,
                env=env,
                timeout=15,
            )
            if pull_proc.returncode == 0:
                pulled = True
            else:
                if is_rebase_in_progress(repo_root, env):
                    rebase_conflict = True
                    run_git(["rebase", "--abort"], cwd=repo_root, env=env, timeout=10)
                    errors.append(
                        compact_err(
                            "Rebase conflict during pull from origin/main (rebase aborted cleanly)",
                            pull_proc,
                        )
                    )
                else:
                    stderr_lower = (pull_proc.stderr or "").lower()
                    if any(
                        token in stderr_lower
                        for token in (
                            "could not resolve host",
                            "failed to connect",
                            "connection refused",
                            "network is unreachable",
                            "unable to access",
                            "repository not found",
                            "authentication failed",
                            "permission to",
                            "403",
                        )
                    ):
                        pull_unreachable = True
                    errors.append(compact_err("git pull --rebase origin main failed", pull_proc))
        except subprocess.TimeoutExpired:
            pull_unreachable = True
            if is_rebase_in_progress(repo_root, env):
                rebase_conflict = True
                run_git(["rebase", "--abort"], cwd=repo_root, env=env, timeout=10)
            errors.append("git pull --rebase origin main timed out after 15s")
    else:
        errors.append("Remote 'origin' is not configured")

    # 5. Push to origin/main unless --no-push or blocked by rebase conflict / unreachable origin.
    if not args.no_push and has_origin and not rebase_conflict:
        if pull_unreachable and not pulled:
            #Still attempt push only if pull didn't already fail with hard network timeout;
            # skip redundant timeout wait while preserving the pull error diagnostics.
            pass
        else:
            try:
                push_proc = run_git(
                    ["push", "origin", "main"],
                    cwd=repo_root,
                    env=env,
                    timeout=20,
                )
                if push_proc.returncode == 0:
                    pushed = True
                else:
                    errors.append(compact_err("git push origin main failed", push_proc))
            except subprocess.TimeoutExpired:
                errors.append("git push origin main timed out after 20s")

    return emit(0)


if __name__ == "__main__":
    sys.exit(main())
