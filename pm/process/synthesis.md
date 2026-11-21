# Process Synthesis & Continuous Evolution Guide

*Living analytical model for Simon's dedicated **System Improver** agent. Synthesizes empirical telemetry from [observations.md](./observations.md) without collapsing nuanced tradeoffs into binary choices.*

*Last synthesized: 2026-11-21*

---

## 1. What Is Working Well (Preserve & Compound)

1. **`SessionStart` Progressive Disclosure (`session_start.py` → `PROJECT.md`)**:
   - Fired cleanly across 6 new sessions/subagents with zero latency spikes, orienting every chat window on `Focus`, bucket locations, and `Recent sessions` immediately.
2. **Dual-Track Sync Separation (`--docs-only` vs. `--code` in `sync_main.py`)**:
   - Separating Steward documentation commits (`--docs-only`, `--autostash`) from verified code slices (`--code --paths ...`) prevented parallel windows from sweeping half-written code into doc syncs while keeping `origin/main` live.
3. **Organic Skill Discovery (`project-manager`, `main-sync`, `gemini-api-*`)**:
   - Agents consistently activate repo and plugin `SKILL.md` runbooks (`7×` Steward, `3×` `main-sync`, `4×` `gemini-api-*`) because frontmatter descriptions name concrete workflow triggers.
4. **Non-Interactive Git & Toolchain Hardening**:
   - `gh auth setup-git`, `GIT_TERMINAL_PROMPT=0`, and `auto_approve_toolchain.py` eliminated early terminal hangs and repetitive approval prompts.

---

## 2. Active Friction Dynamics & Nuanced Root Causes

### Theme A · Shared Working-Tree Contention Across Parallel Chat Windows
- **Root Cause**: Multiple Antigravity chat windows (`69ddeaa4`, `2c4456c2`, `e376eb31`) and background Steward subagents operate against the **same physical working tree** (`/Users/kevinquizhpi/Life/projects/hackathon/simon`).
- **Observed Symptoms**:
  1. **Cross-window `Stop` hook bleed (`OBS-2026-11-21-01`)**: `stop_doc_sync.py` queries repo-wide `git status --porcelain`, which cannot distinguish *files modified by this conversation's turn* from *files actively being edited 10 seconds ago in a sibling chat window*. Additionally, `stop_doc_sync.py` checks `continuationActive` alone without checking `executionNum > 0` or `transcriptPath` turn mutations.
  2. **Stale-context `edit_file` collisions (`OBS-2026-11-21-02`)**: High-traffic files (`PROJECT.md`, `pm/current.md`, `RESOURCES.md`) get rebased or edited by sibling Steward runs between an agent's `read_file` and `edit_file`.

### Theme B · Python Workspace Ergonomics & Scratch Dependency Drift
- **Root Cause**: The repo intentionally started zero-dependency (`urllib.request` in `simon/gemini.py`) without a `pyproject.toml`, while `.venv` grew organically across parallel windows (`google-genai`, `dspy`, `pytest`, `ruff`).
- **Observed Symptoms (`OBS-2026-11-21-03`)**:
  - `.venv/bin/pytest` fails module resolution without `PYTHONPATH=.` (unlike `.venv/bin/python -m pytest`).
  - Scratch scripts assume `httpx` is present (`google-genai 3.6.1` ships `httpx2`) or guess internal SDK module paths before querying `mcp_gemini-api_gemini-api-docs_gemini_search_docs` / `gemini-api-dev` skill.

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
