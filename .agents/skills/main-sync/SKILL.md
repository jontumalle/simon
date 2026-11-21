---
name: main-sync
description: >-
  Dual-track repository synchronization skill for Simon separating zero-ceremony Documentation Sync
  (--docs-only, direct to origin/main, auto-approved for Project Manager Steward) from Feature-Branch
  Code Sync (--code --branch <domain>/<slug> --paths <files...>, requiring unit/smoke/lint
  verification and merging via PR into main). Activate whenever syncing documentation, running
  Project Manager Steward distillation, or landing runtime code and test changes.
---

# `main-sync` Skill — Dual-Track Synchronization (Docs on `main` vs. Code on Feature Branches)

Documentation and executable code follow two distinct git tracks via `.agents/scripts/sync_main.py` (governed by [governance/git-flow.md](../../../governance/git-flow.md)).

| Dimension | Track A · Docs & Knowledge Sync (`--docs-only`) | Track B · Code Sync (`--code --branch ...`) |
| :--- | :--- | :--- |
| **Who uses it** | `Project Manager (Steward)` subagent & any doc/note update | Coding agents landing `simon/`, `tests/`, `examples/`, or script changes |
| **Paths allowed** | `PROJECT.md`, `AGENTS.md`, `RESOURCES.md`, `README.md`, `governance/**`, `pm/**`, `notes/**`, `ideas/**`, `data/**`, `agents/**`, `.agents/**`, `*.md` | Explicit code/test slice via `--paths <files...>` |
| **Permission (`PreToolUse`)** | **Auto-approved** (doc writes & `--docs-only` sync) | **Auto-approved ONLY when verified** (`--skip-verify` & raw `--all` stay gated) |
| **Pre-commit gate** | None — zero ceremony, zero repercussions | Mandatory `unittest` + `python -m simon` smoke check + `ruff check --select E9,F` |
| **Branch strategy** | Always rebases & pushes **straight to `origin/main`** (`--autostash` preserves dirty code) | **Always on a feature branch** (`intake/*`, `decision/*`, `outcome/*`, `feat/*`, `fix/*`) → PR into `main` |

---

## Track A · Documentation & Knowledge Sync (`--docs-only` → `origin/main`)

All Markdown and Life OS knowledge-model files push **straight to `origin/main` immediately**:

```bash
python3 .agents/scripts/sync_main.py --docs-only -m "docs(pm): <concise summary>"
```

- Unstages any non-doc files first so work-in-progress code stays untouched in your working tree.
- Runs `git pull --rebase --autostash origin main` and pushes straight to `origin/main` (or to `origin/<feature-branch>` if your current branch already carries unmerged code commits).

---

## Track B · Feature-Branch Code Sync (`--code` → Feature Branch + PR)

Runtime code (`simon/`), tests (`tests/`), fixtures (`examples/`), and executable hook changes **always use a feature branch** — never commit code directly to `main`:

```bash
python3 .agents/scripts/sync_main.py --code \
  --branch intake/flyer-ocr \
  --paths simon/youtube.py tests/test_mvp_scout.py \
  -m "feat(intake): add flyer venue parser"

gh pr create --fill --base main --head intake/flyer-ocr
```

### What `--code` Enforces Automatically
1. **Blocks direct `main` code commits**: Requires `--branch <domain>/<slug>` (or an already checked-out feature branch).
2. **Stages only `--paths`**: Never sweeps in another chat window's unfinished files (and blocks `.env*`, `local/`, `.venv/`).
3. **Runs verification before committing**: `unittest` suite + `python -m simon` smoke check + `ruff check --select E9,F`. If any check fails, unstages and exits non-zero.
4. **Shared workspace etiquette**: When sharing one local working tree across chat windows, run `git switch main` after pushing your feature branch and opening the PR unless you are immediately adding another commit on that branch.
