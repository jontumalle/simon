#!/usr/bin/env python3
"""Dual-track repository sync utility for Simon (Docs Sync vs. Code Sync).

Supports two distinct workflows managed by the `main-sync` skill:
1. Docs Sync (`--docs-only`, default — used by Project Manager Steward & doc updates):
   - Zero-ceremony, immediate sync straight to `origin/main`.
   - Stages ONLY Markdown and Life OS knowledge-model paths (`PROJECT.md`, `AGENTS.md`,
     `RESOURCES.md`, `README.md`, `pm/`, `notes/`, `ideas/`, `data/`, `agents/`, `.agents/`, `*.md`).
   - Leaves in-progress `simon/` or `tests/` edits untouched via `--rebase --autostash`.

2. Code Sync (`--code` — used when landing runtime `simon/`, `tests/`, or `examples/` changes):
   - Runs automated verification FIRST (`unittest` suite + `python -m simon` smoke check +
     optional `ruff check` on Python files) before committing. Aborts if checks fail.
   - Supports `--paths <file ...>` to stage ONLY an explicit code slice so parallel chat
     windows never sweep in unrelated work-in-progress.
   - Supports `--branch <feat/name>` for feature-branch/PR code pushes when changes shouldn't
     land directly on `main` yet, or pushes verified slices cleanly to `origin/main`.

Never stages `.env*`, `local/`, `.venv/`, or `__pycache__/`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


ROOT_DOC_FILES = frozenset({"PROJECT.md", "AGENTS.md", "RESOURCES.md", "README.md"})
KNOWLEDGE_DIRS = frozenset({"pm", "notes", "ideas", "data", "agents", ".agents"})
FORBIDDEN_TOP_DIRS = frozenset({"local", ".venv", ".git", ".pytest_cache", ".ruff_cache"})
FORBIDDEN_PART_NAMES = frozenset({".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store"})
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


def matches_explicit_paths(rel_path: str, explicit_prefixes: List[str]) -> bool:
    if is_forbidden_path(rel_path):
        return False
    norm = rel_path.strip("/")
    rel_p = Path(norm)
    for raw in explicit_prefixes:
        clean = raw.strip().strip("/")
        if not clean or clean == ".":
            continue
        target_p = Path(clean)
        if rel_p == target_p:
            return True
        try:
            rel_p.relative_to(target_p)
            return True
        except ValueError:
            continue
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


def get_head_branch_and_ahead(cwd: Path, env: Dict[str, str], remote_ref: str) -> Tuple[str, str, int]:
    head = ""
    branch = ""
    ahead = 0
    head_proc = run_git(["rev-parse", "--short", "HEAD"], cwd=cwd, env=env, timeout=5)
    if head_proc.returncode == 0:
        head = head_proc.stdout.strip()

    branch_proc = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, env=env, timeout=5)
    if branch_proc.returncode == 0:
        branch = branch_proc.stdout.strip()

    ahead_proc = run_git(
        ["rev-list", "--count", f"{remote_ref}..HEAD"], cwd=cwd, env=env, timeout=5
    )
    if ahead_proc.returncode == 0:
        try:
            ahead = int(ahead_proc.stdout.strip())
        except ValueError:
            ahead = 0
    return head, branch, ahead


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


def run_code_verification(repo_root: Path, staged_paths: List[str], env: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """Run unit tests, deterministic showcase smoke check, and optional ruff lint before code commit."""
    venv_py = repo_root / ".venv" / "bin" / "python"
    py_exe = str(venv_py) if venv_py.is_file() else sys.executable

    run_env = env.copy()
    existing_pp = run_env.get("PYTHONPATH", "")
    run_env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{existing_pp}" if existing_pp else str(repo_root)

    # 1. Unit test suite
    tests_dir = repo_root / "tests"
    if tests_dir.is_dir():
        test_proc = subprocess.run(
            [py_exe, "-m", "unittest", "discover", "-s", "tests"],
            cwd=str(repo_root),
            env=run_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if test_proc.returncode != 0:
            return False, compact_err("Unit tests failed", test_proc)

    # 2. Deterministic showcase smoke check (if simon package exists)
    if (repo_root / "simon" / "__main__.py").is_file():
        smoke_proc = subprocess.run(
            [py_exe, "-m", "simon"],
            cwd=str(repo_root),
            env=run_env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if smoke_proc.returncode != 0:
            return False, compact_err("`python -m simon` smoke check failed", smoke_proc)

    # 3. Optional ruff check (syntax & pyflakes bugs: E9,F) on staged Python files
    venv_ruff = repo_root / ".venv" / "bin" / "ruff"
    py_targets = [p for p in staged_paths if p.endswith(".py") and (repo_root / p).is_file()]
    if venv_ruff.is_file() and py_targets:
        ruff_proc = subprocess.run(
            [str(venv_ruff), "check", "--select", "E9,F", *py_targets],
            cwd=str(repo_root),
            env=run_env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if ruff_proc.returncode != 0:
            return False, compact_err("`ruff check` failed on staged Python files", ruff_proc)

    return True, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dual-track sync utility for Simon: Docs Sync (--docs-only) vs. Code Sync (--code)."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--docs-only",
        action="store_true",
        help="Docs Sync track (default): stage & push only Markdown/knowledge-model files directly to origin/main.",
    )
    mode_group.add_argument(
        "--code",
        action="store_true",
        help="Code Sync track: verify tests/smoke/lint first, stage code slice (use --paths), and sync to main or --branch.",
    )
    mode_group.add_argument(
        "--all",
        action="store_true",
        help="Legacy/full-tree sync: stage all non-forbidden changes (prefer --code --paths for code slices).",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=None,
        help="Explicit repo-relative file or directory paths to stage (recommended for --code).",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Target branch for --code when pushing a feature branch for PR instead of direct to main (e.g. feat/audio-scout).",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip pre-commit test/smoke verification during --code sync (not auto-approved).",
    )
    parser.add_argument(
        "-m",
        "--message",
        default=None,
        help="Commit message.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip pushing to origin after committing.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional path to repository root (defaults to Simon repo root).",
    )
    args = parser.parse_args()

    mode = "code" if args.code else ("all" if args.all else "docs")
    target_branch = args.branch.strip() if args.branch else "main"
    commit_msg = args.message or (
        "docs: sync knowledge model updates to main"
        if mode == "docs"
        else "feat(simon): sync verified code slice"
    )

    repo_root = (
        Path(args.repo).resolve()
        if args.repo
        else Path(__file__).resolve().parents[2]
    )
    env = build_git_env()

    committed = False
    verified: Optional[bool] = None
    pulled = False
    pushed = False
    errors: List[str] = []

    def emit(exit_code: int) -> int:
        remote_ref = f"origin/{target_branch}"
        head, current_branch, ahead = get_head_branch_and_ahead(repo_root, env, remote_ref)
        summary = {
            "mode": mode,
            "branch": current_branch or target_branch,
            "verified": verified,
            "committed": committed,
            "pulled": pulled,
            "pushed": pushed,
            "head": head,
            "ahead": ahead,
            "error": "; ".join(errors) if errors else None,
        }
        print(json.dumps(summary))
        return exit_code

    top_proc = run_git(["rev-parse", "--show-toplevel"], cwd=repo_root, env=env, timeout=5)
    if top_proc.returncode != 0:
        errors.append(compact_err("Not a valid git repository", top_proc))
        return emit(1)
    repo_root = Path(top_proc.stdout.strip()).resolve()

    if args.branch and mode == "docs":
        errors.append("--branch is only for --code sync; Docs Sync always targets main directly.")
        return emit(1)

    # Normalize explicit --paths relative to repo_root if provided.
    rel_prefixes: Optional[List[str]] = None
    if args.paths:
        rel_prefixes = []
        for p in args.paths:
            cand = Path(p)
            if cand.is_absolute():
                try:
                    rel_prefixes.append(str(cand.resolve().relative_to(repo_root)))
                except ValueError:
                    errors.append(f"Path outside repository: {p}")
                    return emit(1)
            else:
                rel_prefixes.append(str(cand))

    # Switch/create feature branch if --branch <name> was requested for --code.
    if args.branch:
        cur_branch_proc = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, env=env, timeout=5)
        cur_branch = cur_branch_proc.stdout.strip() if cur_branch_proc.returncode == 0 else ""
        if cur_branch != target_branch:
            exists_proc = run_git(
                ["show-ref", "--verify", "--quiet", f"refs/heads/{target_branch}"],
                cwd=repo_root,
                env=env,
                timeout=5,
            )
            switch_args = ["checkout", target_branch] if exists_proc.returncode == 0 else ["checkout", "-b", target_branch]
            sw_proc = run_git(switch_args, cwd=repo_root, env=env, timeout=10)
            if sw_proc.returncode != 0:
                errors.append(compact_err(f"Failed to switch to branch {target_branch}", sw_proc))
                return emit(1)

    if mode == "docs":
        if rel_prefixes:
            allowed_fn = lambda p: is_doc_or_knowledge_path(p) and matches_explicit_paths(p, rel_prefixes)
        else:
            allowed_fn = is_doc_or_knowledge_path
    else:
        if rel_prefixes:
            allowed_fn = lambda p: matches_explicit_paths(p, rel_prefixes)
        else:
            allowed_fn = lambda p: not is_forbidden_path(p)

    # 1. Unstage any pre-staged files outside the allowed scope.
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

    # 2. Discover candidate paths and stage allowed ones.
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

    # 3. For Code Sync (--code or --all), run verification gate BEFORE committing unless --skip-verify.
    diff_proc = run_git(["diff", "--cached", "--quiet"], cwd=repo_root, env=env, timeout=10)
    has_staged_changes = diff_proc.returncode == 1
    if diff_proc.returncode not in (0, 1):
        errors.append(compact_err("git diff --cached failed", diff_proc))
        return emit(1)

    if mode in ("code", "all") and not args.skip_verify:
        now_staged_proc = run_git(["diff", "--cached", "--name-only", "-z"], cwd=repo_root, env=env, timeout=10)
        now_staged = [p for p in now_staged_proc.stdout.split("\0") if p] if now_staged_proc.returncode == 0 else []
        ok, verify_err = run_code_verification(repo_root, now_staged, env)
        verified = ok
        if not ok:
            if now_staged:
                for batch in chunked(now_staged):
                    run_git(["reset", "-q", "HEAD", "--", *batch], cwd=repo_root, env=env, timeout=10)
            errors.append(verify_err or "Code verification gate failed")
            return emit(1)

    # 4. Commit if staged diff is non-empty.
    if has_staged_changes:
        commit_proc = run_git(["commit", "-m", commit_msg], cwd=repo_root, env=env, timeout=15)
        if commit_proc.returncode != 0:
            errors.append(compact_err("git commit failed", commit_proc))
            return emit(1)
        committed = True

    # 5. Rebase onto origin/main when syncing trunk (or pull --rebase when branch tracks remote).
    remote_proc = run_git(["remote", "get-url", "origin"], cwd=repo_root, env=env, timeout=5)
    has_origin = remote_proc.returncode == 0
    rebase_conflict = False
    pull_unreachable = False

    if has_origin and target_branch == "main":
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
    elif not has_origin:
        errors.append("Remote 'origin' is not configured")

    # 6. Push to origin/<target_branch> unless --no-push or blocked by conflict.
    if not args.no_push and has_origin and not rebase_conflict:
        if target_branch == "main" and pull_unreachable and not pulled:
            pass
        else:
            can_push = True
            if target_branch == "main" and mode == "docs":
                diff_main_proc = run_git(
                    ["diff", "--name-only", "-z", "origin/main..HEAD"],
                    cwd=repo_root,
                    env=env,
                    timeout=10,
                )
                if diff_main_proc.returncode == 0 and diff_main_proc.stdout:
                    ahead_paths = [p for p in diff_main_proc.stdout.split("\0") if p]
                    non_doc_ahead = [p for p in ahead_paths if not is_doc_or_knowledge_path(p)]
                    if non_doc_ahead:
                        can_push = False
                        errors.append(
                            "Skipped pushing HEAD:main in --docs-only mode because branch has "
                            f"unmerged non-doc commits ({', '.join(non_doc_ahead[:3])})"
                        )
            if can_push:
                push_args = (
                    ["push", "origin", "HEAD:main"]
                    if target_branch == "main"
                    else ["push", "-u", "origin", target_branch]
                )
                try:
                    push_proc = run_git(push_args, cwd=repo_root, env=env, timeout=20)
                    if push_proc.returncode == 0:
                        pushed = True
                    else:
                        errors.append(compact_err(f"git {' '.join(push_args)} failed", push_proc))
                except subprocess.TimeoutExpired:
                    errors.append(f"git {' '.join(push_args)} timed out after 20s")

    return emit(0)


if __name__ == "__main__":
    sys.exit(main())
