---
name: main-sync
description: >-
  Runbook for continuous trunk-based synchronization on origin/main in the Simon repository.
  Explains the zero-repercussion policy for committing and pushing Markdown/knowledge-model
  docs directly to main, how parallel chat windows and teammates stay conflict-free using
  .agents/scripts/sync_main.py (pull --rebase --autostash), and how to push incremental code
  slices cleanly. Use whenever syncing docs, wrapping up a session, resolving ahead/behind main
  state, or landing tested code slices.
---

# Main-Sync Skill (`origin/main` Trunk Workflow)

Simon runs on **continuous trunk-based sync** directly on `main` so human teammates and multiple parallel Antigravity chat windows always share fresh context, Managed Agent specs, and toolchain manifests without branch drift.

---

## 1. Zero-Repercussion Documentation & Knowledge Sync Policy

All Markdown and Life OS knowledge-model artifacts can be **committed and pushed directly to `main` at any time with zero repercussions**:

- Root indices & manifests: `PROJECT.md`, `AGENTS.md`, `RESOURCES.md`, `README.md`
- Governance & Steward memory: `pm/` (`current.md`, `scope.md`, `decisions.md`, `log/`, `inbox/`)
- Engineering playbooks & ideas: `notes/`, `ideas/`
- Curated agent configs, schemas & repo ops: `agents/`, `data/`, `.agents/`
- Any nested `*.md` documentation (excluding gitignored `local/` and `.venv/`)

### One-Command Safe Doc Sync
```bash
python3 .agents/scripts/sync_main.py --docs-only -m "docs(pm): distill session findings and update status"
```

What `sync_main.py --docs-only` guarantees:
1. **Strict Scope Guard**: Stages *only* safe doc/knowledge paths (unstaging any accidentally pre-staged runtime code so unfinished `simon/` or `tests/` edits stay untouched in your working tree). Never stages `.env*`, `local/`, or `.venv/`.
2. **Credential Helper Ready**: Automatically prepends `~/.local/bin` to `PATH` so `gh auth git-credential` authenticates HTTPS pushes seamlessly.
3. **Conflict-Free Parallelism**: Runs `git pull --rebase --autostash origin main` before pushing, stashing any in-progress code edits, rebasing your doc commit cleanly atop teammates' or sibling chat windows' commits, and restoring your working tree.
4. **Structured Diagnostics**: Prints a JSON summary (`committed`, `pulled`, `pushed`, `head`, `ahead`, `error`) and exits `0` whenever local commit succeeds — even if remote push hits a temporary 403/network issue (if `pushed: false`, report `error` clearly to the user).

---

## 2. How Parallel Chat Windows & Teammates Stay Conflict-Free

1. **Pull Early & Often**:
   - At the start of work or before editing shared head files (`PROJECT.md`, `pm/current.md`, `RESOURCES.md`), pull latest `main`:
     ```bash
     git pull --rebase --autostash origin main
     ```
2. **Append-Oriented Knowledge Files**:
   - Write new session logs as distinct dated files (`pm/log/YYYY-MM-DD-<topic>.md`) and append dated entries to `pm/decisions.md` to minimize overlapping line edits across parallel windows.
3. **Automatic Lifecycle Guardrails**:
   - **`SessionStart` (`.agents/scripts/session_start.py`)**: Injects `PROJECT.md` plus live `git status -sb` ahead/behind & dirty counts.
   - **`Stop` (`.agents/scripts/stop_doc_sync.py`)**: Detects uncommitted doc/knowledge files at turn completion (`NO_TOOL_CALL`) and prompts one clean filing + `sync_main.py --docs-only` pass (guarded by `continuationActive` so it never loops).
   - **Steward Subagent (`project-manager`)**: Launch the background `project-manager` subagent in every substantive chat window so discoveries and decisions are distilled and pushed to `main` automatically.

---

## 3. Pushing Incremental Code Slices to `main`

Code and tests (`simon/`, `tests/`, `examples/`) should also land on `main` in **small, verified slices** rather than sitting unpushed across long sessions:

1. Run verification first:
   ```bash
   python3 -m unittest discover -s tests
   ```
2. Sync everything (code + tests + updated docs/manifests) to `main`:
   ```bash
   python3 .agents/scripts/sync_main.py --all -m "feat(simon): <concise slice summary>"
   ```
   *(Even with `--all`, `sync_main.py` blocks `.env*`, `local/`, and `.venv/` from ever being staged.)*
3. For offline verification without pushing to GitHub yet, pass `--no-push`:
   ```bash
   python3 .agents/scripts/sync_main.py --docs-only --no-push -m "docs: local checkpoint"
   ```

---

## 4. Handling Remote Push Errors (`pushed: false`)

If `sync_main.py` returns `"committed": true, "pushed": false`:
- Your changes are **safely committed locally** on `main` (`ahead > 0`).
- Inspect the `"error"` field:
  - **HTTP 403 / Collaborator Permission**: Tell the user their local commit succeeded (`head` SHA) and ask the repo owner to grant write access (or switch `gh auth switch` to the authorized GitHub account), after which `python3 .agents/scripts/sync_main.py --docs-only` will push all queued commits.
  - **Rebase Conflict**: `sync_main.py` automatically aborts a conflicted rebase to keep the working tree clean; inspect the conflicting file manually, resolve, and re-run.
