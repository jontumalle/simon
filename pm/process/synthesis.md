# Process Synthesis & Continuous Evolution Guide

*Living analytical model for Simon's dedicated **System Improver** agent. Synthesizes empirical telemetry from [observations.md](./observations.md) without collapsing nuanced tradeoffs into binary choices.*

*Last synthesized: 2026-11-21 (53-session full audit: 21 root chats, 32 subagents, 168 friction signals)*

---

## 1. What Is Working Well (Preserve & Compound)

1. **`SessionStart` Progressive Disclosure (`session_start.py` → `PROJECT.md`)**:
   - Fired cleanly across **51** sessions/subagents with zero latency spikes, orienting every chat window on `Focus`, bucket locations, and `Recent sessions` immediately.
2. **Dual-Track Sync Separation (`--docs-only` vs. `--code` in `sync_main.py`)**:
   - Separating Steward documentation commits (`--docs-only`, `--autostash`) from verified code slices (`--code --paths ...`) kept `origin/main` continuously live across 21 parallel chats while catching `11×` lint issues before push.
3. **Organic Skill Discovery (`project-manager`, `main-sync`, `plain-english`, `agent-evals`, `gemini-api-*`)**:
   - Agents consistently activated repo and plugin runbooks (`21×` Steward, `18×` `main-sync`, `8×` `plain-english`, `5×` `agent-evals`, `8×` `gemini-api-*`) because frontmatter descriptions name concrete workflow triggers.
4. **Non-Interactive Git & Toolchain Hardening**:
   - `gh auth setup-git`, `GIT_TERMINAL_PROMPT=0`, and `auto_approve_toolchain.py` eliminated early terminal hangs and repetitive approval prompts.
5. **Parallel Isolated Subagent Execution (`Workspace: "share"`)**:
   - Running feature/UI/eval subagents in parallel worktrees shipped Stage 3 Screening, 9-agent rubrics, and Two-Stage UI in hours.

---

## 2. Active Friction Dynamics & Nuanced Root Causes

### Theme A · Shared Working-Tree Contention Across Parallel Chat Windows
- **Root Cause**: Multiple Antigravity chat windows (`69ddeaa4`, `2c4456c2`, `e376eb31`) and background Steward subagents operate against the **same physical working tree** (`/Users/kevinquizhpi/Life/projects/hackathon/simon`).
- **Observed Symptoms**:
  1. **Cross-window `Stop` hook bleed (`OBS-2026-11-21-01`)**: `stop_doc_sync.py` queries repo-wide `git status --porcelain`, which cannot distinguish *files modified by this conversation's turn* from *files actively being edited 10 seconds ago in a sibling chat window*. Additionally, `stop_doc_sync.py` checks `continuationActive` alone without checking `executionNum > 0` or `transcriptPath` turn mutations.
  2. **Stale-context `edit_file` collisions (`OBS-2026-11-21-02`)**: High-traffic files (`PROJECT.md`, `pm/current.md`, `RESOURCES.md`) get rebased or edited by sibling Steward runs between an agent's `read_file` and `edit_file`.

### Theme B · Python Workspace Ergonomics, Worktree `.venv` Drift & Missing CLI Paths
- **Root Cause**: `/usr/bin/python3` is Python 3.9 while `.venv/bin/python` is Python 3.12; gitignored `.venv/` does not exist inside `Workspace: "share"` worktrees; `gcloud` is outside default `PATH`; and `rg`/`node` are not installed.
- **Observed Symptoms (`OBS-2026-11-21-03`, `OBS-2026-11-21-08`, `OBS-2026-11-21-09`)**:
  - `10×` Python 3.9 f-string backslash `SyntaxError` when running `python3 -c` instead of `.venv/bin/python`.
  - `5×` `no such file or directory: .venv/bin/python` inside `Workspace: "share"` subagent worktrees.
  - `11×` auto-fixable `ruff` lint errors caught late at `sync_main.py --code` instead of pre-fixed.
  - `4×` bare `pytest`/`ruff` not found, `2×` `gcloud` not found, `4×` `rg`/`node` not found.

### Theme C · High-Frequency Flows Still Running as Ad-Hoc `self` Subagents & Uncodified Prompts
- **Root Cause**: The team has converged on 5 repeatable engineering/ops flows, yet every chat still invokes generic `self` subagents with hand-written prompts (`32` subagents across `21` root chats) and re-discovers Cloud Run deploy / UI audit steps.
- **Observed Symptoms (`OBS-2026-11-21-07`, `OBS-2026-11-21-11`)**:
  - `16×` ad-hoc Project Manager Steward subagents, `10×` isolated feature/UI builders, `4×` parallel rubric authors, plus repeated Managed Agent deploy/model-swap and Cloud Run/CI debugging sessions.

---

## 3. Calibrated Evolution Spectrums (For Dedicated System Improver Agent)

*Each opportunity below lays out a **spectrum of nuanced refinements** rather than a binary toggle, ordered from lightest-touch calibration to deeper structural evolution:*

### Opportunity 1 · Calibrating `stop_doc_sync.py` (`Stop` Hook) for Multi-Window Harmony
- **Light calibration ( Re-entry & Recency Guard)**:
  - Check `int(payload.get("executionNum", 0) or 0) > 0` alongside `continuationActive` so the hook can **never** fire more than once per user turn, and skip files whose `mtime` is within the last ~20s if the current session made zero file-write/command calls in the turn.
- **Medium calibration (Transcript-Scoped Attribution)**:
  - Read `payload["transcriptPath"]` (passed natively to `Stop` hooks!) for the current turn's `write_file` / `edit_file` / `run_command` calls, and only nudge when **at least one dirty doc path was touched by this conversation** (or when `pm/inbox/` has unfiled items created in this session).
  - *Tradeoff*: Preserves 100% of single-window safety while completely eliminating cross-window false positives on read-only Q&A turns.
- **Deeper calibration (Advisory vs. Blocking Gradient)**:
  - Distinguish pure `.md` notes from `.agents/scripts/*.py` mixed edits: if dirty `.agents/` files coexist with dirty `tests/` files (indicating an atomic code+hook slice in progress), defer to Track B `--code` rather than nudging `--docs-only`.

### Opportunity 2 · Reducing Concurrent Edit Collisions on Shared Governance Files
- **Skill-level guidance (`project-manager/SKILL.md`)**:
  - Instruct Steward subagents to `read_file` `PROJECT.md` and `pm/current.md` **immediately before** `edit_file` (after completing `git pull --rebase --autostash` or right before editing) rather than reading them 10 steps earlier at session start.
- **Granular file layout (`pm/log/` & `pm/process/`)**:
  - Keep high-volume append-only detail in per-workstream files (`pm/log/YYYY-MM-DD-<topic>.md`, `pm/process/observations.md`) and keep `PROJECT.md` strictly to 1-line LRU pointers so merge surfaces stay tiny.
- **Workspace isolation when coding in parallel**:
  - Encourage `Workspace: "share"` (git-worktree-like isolation) on heavy coding subagents (`invoke_subagent` / `swarm`) while keeping `Workspace: "inherit"` for lightweight readers.

### Opportunity 3 · Smoothing `.venv`, Test Runner & Skill Script Execution
- **Minimal `pyproject.toml` config**:
  - Add `[tool.pytest.ini_options] pythonpath = ["."]` (and calibrated `[tool.ruff]` rules matching Python 3.9+ compatibility in `.agents/scripts/` vs. Python 3.12 in `simon/`) so bare `pytest` and `ruff` behave identically regardless of how an agent invokes them.
- **Auto-Approve Nested Skill Scripts (`auto_approve_toolchain.py`)**:
  - Check whether `.agents/skills/*/scripts/*.py` (such as `inspect_sessions.py`) is covered alongside `.agents/scripts/*.py` for read-only inspection runs.
- **SDK Exploration Habit**:
  - Reinforce checking `gemini-api-dev` skill / `gemini_search_docs` MCP before guessing private `google.genai._*` imports in scratch scripts, and note `httpx` in `RESOURCES.md` if REST scratch scripts need it alongside `httpx2`.

### Opportunity 4 · Codifying Dedicated Subagents, Env Rule & Missing Workflow Skills
- **Dedicated Workspace Plugin Subagents (`.agents/plugins/simon-ops/agents/*.md`)**:
  - Package the 5 empirically proven roles as native Antigravity subagents so any chat window can invoke them directly by `TypeName` without boilerplate prompts: `simon-steward` (`16×`), `simon-feature-engineer` (`10×`), `simon-eval-author` (`4×`), `simon-agent-deployer`, and `simon-system-improver`.
  - *Tradeoff*: Centralizes guardrails (worktree `.venv` fallback, `ruff check --fix`, re-read before `edit_file`) in one versioned place; keep agent prompts lean and pointer-driven to existing `SKILL.md` files so instructions never duplicate or drift.
- **Always-On Environment Rule (`.agents/rules/python-and-worktree-env.md`)**:
  - Eliminate ~36 recurring friction hits (`python3` 3.9 vs `.venv` 3.12, worktree `.venv` fallback, `gcloud` path, no `node`/`rg`, pre-sync `ruff check --fix`).
- **Two High-Leverage Missing Skills**:
  - `cloudrun-deploy-and-verify` (Cloud Run staging build/deploy, GitHub Actions CI triage, live endpoint & Firestore checks).
  - `ui-flow-audit` (management-facing Plain-English copy pass, explicit state-machine check, Python `unittest` UI regression run).
