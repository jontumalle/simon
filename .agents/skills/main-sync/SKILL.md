---
name: main-sync
description: >-
  Dual-track repository synchronization skill for Simon separating zero-ceremony Documentation Sync
  (--docs-only, direct to origin/main, auto-approved for Project Manager Steward) from gated Code
  Sync (--code, requiring unit/smoke/lint verification, explicit --paths slice staging, and main or
  feature-branch PR options). Activate whenever syncing documentation, running Project Manager
  Steward distillation, or landing runtime code and test changes.
---

# `main-sync` Skill — Dual-Track Synchronization (Docs Sync vs. Code Sync)

As Simon scales across parallel chat windows and teammates, **documentation** and **executable code** synchronize differently. Always choose the matching track below via `.agents/scripts/sync_main.py`.

| Dimension | Track A · Docs & Knowledge Sync (`--docs-only`) | Track B · Code Sync (`--code`) |
| :--- | :--- | :--- |
| **Who uses it** | `Project Manager (Steward)` subagent & any doc/note update | Primary coding agents landing `simon/`, `tests/`, `examples/` |
| **Paths allowed** | `PROJECT.md`, `AGENTS.md`, `RESOURCES.md`, `README.md`, `pm/**`, `notes/**`, `ideas/**`, `data/**`, `agents/**`, `.agents/**`, `*.md` | Explicit code/test slice via `--paths <files...>` |
| **Permission (`PreToolUse`)** | **Auto-approved** (both doc file writes & `--docs-only` sync) | **Auto-approved ONLY when verified** (`--skip-verify` & raw `--all` fall back to manual prompt) |
| **Pre-commit gate** | None — zero ceremony, zero repercussions | Mandatory `unittest` + `python -m simon` smoke check + `ruff check` (if installed) |
| **Branch strategy** | Always rebases & pushes **straight to `origin/main`** (`--autostash` preserves dirty code) | Small verified slices → `origin/main`; breaking/multi-part changes → `--branch feat/<slug>` + PR |

---

## Track A · Documentation & Knowledge Sync (`--docs-only`)

All Markdown and Life OS knowledge-model files push **straight to `origin/main` immediately** without touching in-progress runtime code:

```bash
python3 .agents/scripts/sync_main.py --docs-only -m "docs(pm): <concise summary>"
```

### Guarantees for the Steward & Parallel Windows
1. **Never Sweeps Dirty Code**: Any accidentally staged `simon/` or `tests/` edits are automatically unstaged before committing, so half-written code stays safely in your working tree.
2. **Auto-Approved End-to-End**: `.agents/scripts/auto_approve_toolchain.py` (`PreToolUse`) auto-approves creating/editing files in documentation buckets and running `sync_main.py --docs-only`.
3. **Conflict-Free Rebase**: Runs `git pull --rebase --autostash origin main` and prepends `~/.local/bin` to `PATH` so `gh` credentials work out of the box.

---

## Track B · Code Sync (`--code`)

Runtime code (`simon/`), tests (`tests/`), and fixtures (`examples/`) **never** piggyback on background Steward doc syncs. Choose **Verified Trunk Slice** or **Feature Branch / PR** depending on risk:

### Option B1 · Verified Trunk Slice (Small, Non-Breaking, Tested Slice → `origin/main`)
Always pass `--paths` naming the exact files in your slice so you never sweep in another chat window's unfinished edits:

```bash
python3 .agents/scripts/sync_main.py --code \
  --paths simon/orchestrator.py tests/test_orchestrator.py \
  -m "feat(simon): wire parallel performance and booking critics"
```

What `--code` enforces automatically **before** creating a commit:
1. Unstages anything outside `--paths` (and blocks `.env*`, `local/`, `.venv/`).
2. Runs `python -m unittest discover -s tests`.
3. Runs deterministic smoke check `python -m simon`.
4. Runs `.venv/bin/ruff check` on staged `.py` files (when `.venv/bin/ruff` is present).
5. If any check fails, unstages and exits non-zero (`"verified": false, "committed": false`) so broken code never lands on `main`.

### Option B2 · Feature Branch + PR (Breaking, Experimental, or Teammate-Reviewed Code)
When refactoring core interfaces in `simon/`, touching shared schemas in breaking ways, or wanting teammate review before merging to `main`:

```bash
python3 .agents/scripts/sync_main.py --code \
  --branch feat/managed-agent-runner \
  --paths simon/ tests/ \
  -m "feat(simon): add Managed Agents v1beta runner"

gh pr create --fill --base main --head feat/managed-agent-runner
```

---

## Diagnostics & Error Recovery

`sync_main.py` prints a single JSON status line:
```json
{"mode": "code", "branch": "main", "verified": true, "committed": true, "pulled": true, "pushed": true, "head": "a1b2c3d", "ahead": 0, "error": null}
```

- **`verified: false`**: Fix the failing unit test, smoke check, or `ruff` lint error reported in `"error"` and re-run `--code`.
- **`committed: true, pushed: false`**: Changes are safely committed locally (`ahead > 0`). Check `"error"` (e.g., offline Wi-Fi, `gh auth status`, or rebase conflict automatically aborted cleanly).
