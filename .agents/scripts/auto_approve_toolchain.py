#!/usr/bin/env python3
"""PreToolUse hook for Simon: auto-approves safe, repo-relevant toolchain commands.

Inspects `run_command` tool calls against the shared toolchain in RESOURCES.md
(git, gh, uv, python3, pytest, ruff, gemini-api, gcloud, ffmpeg/ffprobe, yt-dlp, jq).
- Returns {"decision": "auto_approve"} when EVERY command segment in the shell line
  is a verified, non-destructive Simon workflow command.
- Returns {"decision": "allow"} otherwise, delegating to Antigravity's normal
  permission policy (so destructive, unknown, or complex shell commands still prompt
  or respect user settings).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

# Raw shell substrings that can hide subcommands or redirections; always defer to normal policy.
UNSAFE_RAW_PATTERNS = (
    "`",
    "$(",
    "<(",
    ">(",
    "$((",
)

# Allow only harmless $HOME / $PATH variable references; reject other $ expansions.
DOLLAR_TOKEN_RE = re.compile(r"\$(?!HOME\b|PATH\b|\{HOME\}|\{PATH\})")
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

SAFE_ENV_VARS = {
    "PATH",
    "PYTHONPATH",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
    "CLOUDSDK_PYTHON",
    "SIMON_AGENT_PREFIX",
    "GEMINI_AGENT",
    "GEMINI_AUDIO_MODEL",
    "GEMINI_PRODUCER_MODEL",
    "GOOGLE_CLOUD_PROJECT",
    "AGY_ACCOUNT",
    "NO_COLOR",
    "TERM",
    "LANG",
    "LC_ALL",
}

SAFE_REDIRECT_PATTERNS = re.compile(
    r"(?:^|\s)(?:2>&1|1>&2|&>/dev/null|1>/dev/null|2>/dev/null|>/dev/null)(?=\s|$|;|&|\|)"
)

CHAIN_OPERATORS = {";", "&&", "||", "|"}

GIT_READONLY_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "rev-parse",
    "ls-files",
    "check-ignore",
    "describe",
    "shortlog",
}

DESTRUCTIVE_KEYWORDS = {
    "delete",
    "destroy",
    "remove",
    "rm",
    "revoke",
    "purge",
    "reset",
    "drop",
    "clear",
}


def _trusted_bin_dirs(workspace_roots: list[Path]) -> set[Path]:
    home = Path.home()
    dirs = {
        Path("/usr/bin"),
        Path("/bin"),
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
        Path("/Library/Developer/CommandLineTools/usr/bin"),
        home / ".local" / "bin",
        home / "google-cloud-sdk" / "bin",
    }
    for root in workspace_roots:
        dirs.add(root / ".venv" / "bin")
    res = set()
    for d in dirs:
        res.add(d)
        try:
            res.add(d.resolve())
        except OSError:
            pass
    return res


def _is_within(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _resolve_executable(exe: str, cwd: Path, workspace_roots: list[Path], trusted_dirs: set[Path]) -> str | None:
    """Returns canonical executable basename if from a trusted location, else None."""
    if "/" not in exe:
        return exe

    expanded = Path(os.path.expanduser(exe))
    if not expanded.is_absolute():
        # Only allow workspace .venv relative executables (e.g. .venv/bin/python)
        candidate = (cwd / expanded)
        if candidate.parent in trusted_dirs or candidate.resolve().parent in trusted_dirs:
            return expanded.name
        return None

    if expanded.parent in trusted_dirs:
        return expanded.name
    try:
        if expanded.resolve().parent in trusted_dirs:
            return expanded.name
    except OSError:
        pass
    return None


def _split_shell_segments(command_line: str) -> list[list[str]] | None:
    """Splits a shell command into argv segments across ;, &&, ||, |, newline.

    Returns None if any unsafe construct, subshell, background `&`, or file redirect is present.
    """
    if not command_line or not command_line.strip():
        return None

    for pat in UNSAFE_RAW_PATTERNS:
        if pat in command_line:
            return None

    if DOLLAR_TOKEN_RE.search(command_line):
        return None

    # Strip known-safe /dev/null and fd redirections before lexing so `>` checks stay strict.
    cleaned = SAFE_REDIRECT_PATTERNS.sub(" ", command_line)
    cleaned = cleaned.replace("\r\n", "\n").replace("\n", " ; ")

    try:
        lexer = shlex.shlex(cleaned, posix=True, punctuation_chars=True)
        lexer.wordchars += ":@+%,"
        tokens = list(lexer)
    except ValueError:
        return None

    if not tokens:
        return None

    punct_set = set("();<>|&")
    segments: list[list[str]] = []
    current: list[str] = []

    for tok in tokens:
        if tok in CHAIN_OPERATORS:
            if not current:
                return None
            segments.append(current)
            current = []
        elif tok and set(tok) <= punct_set:
            # Rejects unquoted background `&`, subshells `(...)`, and non-/dev/null redirections.
            return None
        elif "{" in tok and "," in tok and "}" in tok:
            # Reject brace expansion tricks.
            return None
        else:
            current.append(tok)

    if current:
        segments.append(current)

    return segments if segments else None


def _strip_env_and_wrappers(argv: list[str]) -> list[str] | None:
    """Strips safe leading KEY=VALUE env assignments and `env` wrapper."""
    idx = 0
    while idx < len(argv) and ENV_ASSIGN_RE.match(argv[idx]):
        key = argv[idx].split("=", 1)[0]
        if key not in SAFE_ENV_VARS:
            return None
        idx += 1

    rest = argv[idx:]
    if not rest:
        # Pure safe env assignment (e.g. `VAR=1` before `;`)
        return []

    if rest[0] == "env":
        idx = 1
        while idx < len(rest) and ENV_ASSIGN_RE.match(rest[idx]):
            key = rest[idx].split("=", 1)[0]
            if key not in SAFE_ENV_VARS:
                return None
            idx += 1
        rest = rest[idx:]

    return rest


def _check_git(args: list[str], cwd: Path, workspace_roots: list[Path]) -> bool:
    idx = 0
    while idx < len(args) and args[idx].startswith("-"):
        flag = args[idx]
        if flag == "--no-pager":
            idx += 1
        elif flag == "-C":
            if idx + 1 >= len(args):
                return False
            target = Path(os.path.expanduser(args[idx + 1]))
            if not target.is_absolute():
                target = cwd / target
            if not _is_within(target, workspace_roots):
                return False
            idx += 2
        else:
            # Disallow -c, --git-dir, --work-tree, --exec-path, etc.
            return False

    if idx >= len(args):
        return False

    sub = args[idx]
    rest = args[idx + 1 :]

    if any(a in {"--upload-pack", "--receive-pack", "--exec"} or a.startswith("--upload-pack=") or a.startswith("--exec=") for a in rest):
        return False

    if sub in GIT_READONLY_SUBCOMMANDS:
        return True

    if sub == "branch":
        return all(a in {"-a", "-r", "-v", "-vv", "--list", "--show-current", "--merged", "--no-merged"} for a in rest)

    if sub == "switch":
        if not rest:
            return False
        if any(
            a in {"-f", "--force", "--discard-changes", "--detach", "-d", "--"}
            or a.startswith("--conflict")
            for a in rest
        ):
            return False
        return True

    if sub == "checkout":
        # Allow only safe new-branch creation (`git checkout -b <branch>`); keep file checkout gated.
        return len(rest) == 2 and rest[0] == "-b" and not rest[1].startswith("-")

    if sub == "remote":
        return not rest or rest[0] in {"-v", "show", "get-url"}

    if sub == "config":
        return bool(rest) and all(
            a in {"--get", "--get-all", "--list", "-l", "--local", "--global"} or not a.startswith("-")
            for a in rest
        ) and any(a in {"--get", "--get-all", "--list", "-l"} for a in rest)

    if sub in {"fetch", "add", "commit"}:
        if any(a in {"-f", "--force"} for a in rest):
            return False
        return True

    if sub == "pull":
        if any(a in {"-f", "--force"} for a in rest):
            return False
        return True

    if sub == "push":
        for a in rest:
            if a in {"-f", "--force", "--delete", "-d", "--mirror"} or a.startswith("--force"):
                return False
            if a.startswith(":") and len(a) > 1:
                # Refspec deletion (`git push origin :branch`)
                return False
        return True

    if sub == "stash":
        if not rest:
            return True
        return rest[0] in {"push", "pop", "apply", "list", "show"}

    return False


def _check_gh(args: list[str]) -> bool:
    if not args:
        return False
    if args[0] in {"--version", "version", "--help", "help"}:
        return True
    if args[0] == "auth":
        # Explicitly allow `gh auth setup-git` and `gh auth status`; never `gh auth token`.
        return len(args) >= 2 and args[1] in {"status", "setup-git"}
    if args[0] == "repo":
        return len(args) >= 2 and args[1] in {"view", "list"}
    if args[0] == "pr":
        return len(args) >= 2 and args[1] in {"list", "view", "status", "checks", "diff", "create"}
    if args[0] == "issue":
        return len(args) >= 2 and args[1] in {"list", "view", "status"}
    if args[0] == "run":
        return len(args) >= 2 and args[1] in {"list", "view"}
    return False


def _check_python(args: list[str], cwd: Path, workspace_roots: list[Path]) -> bool:
    if not args:
        return False
    if args[0] in {"--version", "-V", "--help", "-h"}:
        return len(args) == 1

    if args[0] == "-m" and len(args) >= 2:
        mod = args[1]
        if mod in {"unittest", "pytest", "ruff", "simon", "py_compile", "json.tool"}:
            return True
        return False

    # Allow checked-in repo helper scripts under .agents/scripts/ or scripts/
    script_arg = args[0]
    script_rest = args[1:]
    if not script_arg.startswith("-") and script_arg.endswith(".py"):
        script_path = Path(os.path.expanduser(script_arg))
        if not script_path.is_absolute():
            script_path = cwd / script_path
        try:
            resolved = script_path.resolve()
        except OSError:
            return False
        for root in workspace_roots:
            for allowed_sub in (root / ".agents" / "scripts", root / "scripts"):
                try:
                    resolved.relative_to(allowed_sub.resolve())
                    if resolved.name == "sync_main.py":
                        # Docs Sync (`--docs-only` / default) and verified Code Sync (`--code`) are
                        # auto-approved; `--skip-verify` or unscoped `--all` fall back to normal review.
                        if any(a in {"--skip-verify", "--all"} for a in script_rest):
                            return False
                    return True
                except ValueError:
                    continue
    return False


def _check_uv(args: list[str], cwd: Path, workspace_roots: list[Path], trusted_dirs: set[Path]) -> bool:
    if not args:
        return False
    sub = args[0]
    rest = args[1:]

    if sub in {"--version", "version", "--help", "help", "lock", "sync"}:
        return True

    if sub == "venv":
        # Allow `uv venv` inside workspace (e.g. `uv venv --python 3.12 .venv`)
        positional: list[str] = []
        i = 0
        while i < len(rest):
            arg = rest[i]
            if arg in {"--python", "-p", "--prompt", "--directory"}:
                i += 2
                continue
            if arg.startswith("-"):
                i += 1
                continue
            positional.append(arg)
            i += 1
        if not positional:
            return True
        if len(positional) == 1:
            target = Path(os.path.expanduser(positional[0]))
            if not target.is_absolute():
                target = cwd / target
            return _is_within(target.parent, workspace_roots)
        return False

    if sub == "python":
        return bool(rest) and rest[0] in {"list", "find", "install"}

    if sub == "tool":
        if not rest:
            return False
        if rest[0] == "list":
            return True
        if rest[0] == "install":
            pkgs = [a for a in rest[1:] if not a.startswith("-")]
            return pkgs in (["yt-dlp"], ["ruff"], ["pytest"])
        return False

    if sub == "pip":
        if not rest:
            return False
        pip_sub = rest[0]
        pip_args = rest[1:]
        if pip_sub in {"list", "show", "check", "freeze", "tree"}:
            return True
        if pip_sub == "install":
            # Disallow custom index URLs, git+/http URLs, or editable paths outside workspace
            disallowed_flags = {"-i", "--index-url", "--extra-index-url", "-f", "--find-links"}
            for a in pip_args:
                if a in disallowed_flags or any(a.startswith(f + "=") for f in disallowed_flags):
                    return False
                if "://" in a or a.startswith("git+"):
                    return False
            return True
        return False

    if sub == "run":
        # Strip uv run flags like --python / -p / --no-sync and validate inner command
        idx = 0
        while idx < len(rest) and rest[idx].startswith("-"):
            if rest[idx] in {"--python", "-p", "--directory"}:
                idx += 2
            else:
                idx += 1
        inner = rest[idx:]
        return bool(inner) and _is_segment_approved(inner, cwd, workspace_roots, trusted_dirs)

    return False


def _check_gemini_api(args: list[str]) -> bool:
    if not args:
        return True
    lowered = {a.lower() for a in args}
    if lowered & DESTRUCTIVE_KEYWORDS:
        return False
    return True


def _check_gcloud(args: list[str]) -> bool:
    if not args:
        return False
    # Never auto-approve token printing or destructive mutations
    joined = " ".join(args).lower()
    if "token" in joined or "key" in joined:
        return False
    if any(a.lower() in DESTRUCTIVE_KEYWORDS for a in args):
        return False

    if args[0] in {"--version", "version", "info", "--help"}:
        return True
    if args[:2] == ["auth", "list"]:
        return True
    if args[0] == "config" and len(args) >= 2 and args[1] in {"list", "get", "get-value"}:
        return True
    if args[0] == "projects" and len(args) >= 2 and args[1] in {"list", "describe"}:
        return True
    if args[:2] == ["storage", "ls"]:
        return True
    return False


def _check_media_and_json(exe: str, args: list[str], cwd: Path, workspace_roots: list[Path]) -> bool:
    if exe == "ffprobe":
        return True
    if exe == "ffmpeg":
        # Reject network protocols; ensure output file (last non-flag arg) is inside workspace
        if any("://" in a for a in args):
            return False
        if not args:
            return False
        if args[0] in {"-version", "-h", "-help", "-formats", "-codecs"}:
            return True
        out_arg = args[-1]
        if out_arg == "-" or out_arg.startswith("-"):
            return False
        out_path = Path(os.path.expanduser(out_arg))
        if not out_path.is_absolute():
            out_path = cwd / out_path
        return _is_within(out_path.parent, workspace_roots)
    if exe == "yt-dlp":
        # Reject --exec / --plugin-dirs which can execute arbitrary commands
        for a in args:
            if a in {"--exec", "--plugin-dirs"} or a.startswith("--exec=") or a.startswith("--plugin-dirs="):
                return False
        return True
    if exe == "jq":
        for a in args:
            if a in {"-f", "--from-file"}:
                return False
        return True
    return False


def _check_readonly_shell_util(exe: str, args: list[str]) -> bool:
    if exe in {"true", "pwd", "uname", "whoami"}:
        return all(a.startswith("-") for a in args) if exe != "true" else True
    if exe in {"which", "ls", "head", "tail", "wc", "stat", "echo", "printf"}:
        return True
    if exe == "command":
        return bool(args) and args[0] in {"-v", "-V"}
    return False


def _is_segment_approved(
    raw_argv: list[str],
    cwd: Path,
    workspace_roots: list[Path],
    trusted_dirs: set[Path],
) -> bool:
    argv = _strip_env_and_wrappers(raw_argv)
    if argv is None:
        return False
    if not argv:
        return True

    exe = _resolve_executable(argv[0], cwd, workspace_roots, trusted_dirs)
    if exe is None:
        return False
    args = argv[1:]

    if exe == "git":
        return _check_git(args, cwd, workspace_roots)
    if exe == "gh":
        return _check_gh(args)
    if exe in {"python", "python3"}:
        return _check_python(args, cwd, workspace_roots)
    if exe == "uv":
        return _check_uv(args, cwd, workspace_roots, trusted_dirs)
    if exe == "pytest":
        return True
    if exe == "ruff":
        return not args or args[0] in {"check", "format", "version", "--version", "--help", "rule", "config"}
    if exe == "gemini-api":
        return _check_gemini_api(args)
    if exe == "gcloud":
        return _check_gcloud(args)
    if exe in {"ffmpeg", "ffprobe", "yt-dlp", "jq"}:
        return _check_media_and_json(exe, args, cwd, workspace_roots)
    if _check_readonly_shell_util(exe, args):
        return True

    return False


DOC_WRITE_TOOLS = {
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
    "write_file",
    "edit_file",
}

ROOT_DOC_FILES = {"PROJECT.md", "AGENTS.md", "RESOURCES.md", "README.md"}
KNOWLEDGE_BUCKETS = {"governance", "pm", "notes", "ideas", "data", "agents", ".agents"}
FORBIDDEN_DOC_DIRS = {"local", ".venv", ".git", "__pycache__"}


def _is_approved_doc_write(args: dict, cwd: Path, workspace_roots: list[Path]) -> bool:
    """Returns True when creating/editing a safe documentation or Knowledge Model file."""
    raw_target = (
        args.get("Path")
        or args.get("TargetFile")
        or args.get("path")
        or args.get("targetFile")
        or ""
    )
    if not isinstance(raw_target, str) or not raw_target.strip():
        return False

    target = Path(os.path.expanduser(raw_target.strip()))
    if not target.is_absolute():
        target = cwd / target

    try:
        resolved = target.resolve()
    except OSError:
        return False

    for root in workspace_roots:
        try:
            rel = resolved.relative_to(root.resolve())
        except ValueError:
            continue

        parts = rel.parts
        if not parts:
            continue
        if parts[0] in FORBIDDEN_DOC_DIRS:
            return False
        if any(part in FORBIDDEN_DOC_DIRS or part.startswith(".env") for part in parts):
            return False

        rel_str = rel.as_posix()
        if rel_str in ROOT_DOC_FILES:
            return True
        if parts[0] in KNOWLEDGE_BUCKETS:
            return True
        if resolved.suffix.lower() == ".md":
            return True

    return False


def evaluate_tool_call(payload: dict) -> dict:
    tool_call = payload.get("toolCall") or {}
    tool_name = tool_call.get("name") or ""
    args = tool_call.get("args") or {}

    ws_paths = payload.get("workspacePaths") or []
    workspace_roots = [REPO_ROOT]
    for p in ws_paths:
        if isinstance(p, str) and p:
            workspace_roots.append(Path(p))

    raw_cwd = args.get("Cwd") or payload.get("cwd") or str(REPO_ROOT)
    cwd = Path(os.path.expanduser(raw_cwd))

    if tool_name in DOC_WRITE_TOOLS:
        if _is_approved_doc_write(args, cwd, workspace_roots):
            return {
                "decision": "auto_approve",
                "reason": "Auto-approved Simon Knowledge Model / Steward documentation write.",
            }
        return {"decision": "allow"}

    if tool_name != "run_command":
        return {"decision": "allow"}

    command_line = args.get("CommandLine") or args.get("commandLine") or ""

    trusted_dirs = _trusted_bin_dirs(workspace_roots)
    segments = _split_shell_segments(command_line)
    if not segments:
        return {"decision": "allow"}

    if all(_is_segment_approved(seg, cwd, workspace_roots, trusted_dirs) for seg in segments):
        return {
            "decision": "auto_approve",
            "reason": "Auto-approved Simon toolchain command (RESOURCES.md).",
        }

    return {"decision": "allow"}


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        result = evaluate_tool_call(payload)
        print(json.dumps(result))
    except Exception:
        # Fail safe: delegate to Antigravity's default permission policy.
        print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
