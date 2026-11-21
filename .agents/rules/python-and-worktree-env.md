# Python, Worktree & CLI Environment Rules (Simon)

Follow these environment rules in every shell command and subagent to avoid recurring path and version failures:

1. **Always use the repo's Python 3.12 `.venv`, never bare `/usr/bin/python3` (Python 3.9):**
   - In the main checkout: `.venv/bin/python` and `.venv/bin/ruff`.
   - Inside a `Workspace: "share"` git worktree (where gitignored `.venv/` does not exist), resolve `.venv` from the main repo root:
     ```bash
     MAIN_REPO="$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')"
     PY="${MAIN_REPO}/.venv/bin/python"
     RUFF="${MAIN_REPO}/.venv/bin/ruff"
     ```
   - Never run bare `pytest` or bare `ruff` (not on default `PATH`). Run `"$PY" -m unittest discover -s tests -p "test_*.py"` or `"$PY" -m pytest`.
   - For inline Python one-liners, prefer heredocs (`"$PY" - <<'PY' ... PY`) over escaped double quotes.

2. **Pre-fix lint before Track B (`sync_main.py --code`):**
   - Run `"$RUFF" check --fix <touched_files>` before calling `sync_main.py --code` so auto-fixable lint errors do not abort the commit gate.

3. **Known macOS CLI paths & absent binaries:**
   - `gcloud` is not on default `PATH` in non-interactive shells; use `~/google-cloud-sdk/bin/gcloud` (or prepend `export PATH="$HOME/google-cloud-sdk/bin:$PATH"`).
   - `rg` (ripgrep) and `node` are **not** installed in this environment. Use `grep -rn` / `git grep` instead of `rg`, and Python `unittest` instead of `node`.
   - In zsh, always quote URLs containing `?` (e.g., `gh api "repos/jontumalle/simon/commits?per_page=5"`) to avoid `no matches found` glob errors.

4. **Prevent `edit_file` target drift on shared files:**
   - Always `read_file` shared head files (`PROJECT.md`, `pm/current.md`, `RESOURCES.md`, `simon/web.py`, `simon/discovery_ui.py`) immediately before calling `edit_file`.
