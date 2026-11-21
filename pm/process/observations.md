# Session Process Observations Log

*Append-only, evidence-backed record of workflow signals across root chat windows and subagents. Generated & updated via `.agents/skills/process-observer/SKILL.md` (`inspect_sessions.py`).*

---

## 2026-11-21 · Baseline Multi-Window Telemetry Audit (9 Conversations: 3 Root Chats, 6 Subagents)

### `OBS-2026-11-21-01` · Cross-Window `Stop` Hook False-Positive & Double Re-Entry
- **Facets**: `hook-ergonomics`, `parallel-concurrency`
- **Evidence**: Root chat `69ddeaa4` (`steps ~200–208`) received `Stop hook blocked termination` **twice consecutively** on a pure read-only Q&A turn (`"okay so high level how does it work and what folders do we have"`) because root chat `2c4456c2` had uncommitted Dual-Track Sync edits in `.agents/` at that exact moment.
- **Operating Spectrum**:
  - *Where it helps*: In single-window documentation work, `stop_doc_sync.py` reliably prevents an agent from ending a turn while leaving newly drafted `.md` files unindexed and unsynced.
  - *Where it drags*: Because `stop_doc_sync.py` inspects global `git status --porcelain` without checking whether **the current turn/conversation** mutated any doc paths (and relied only on `continuationActive` rather than also checking `executionNum > 0` or recent file `mtime` from sibling windows), a read-only window gets nudged to commit another active window's mid-flight work — risking split atomic commits if the agent obeys blindly.

### `OBS-2026-11-21-02` · Concurrent `edit_file` Target Drift on Shared Head Files
- **Facets**: `parallel-concurrency`, `subagent-orchestration`, `skill-adoption`
- **Evidence**: `target content not found in the file` occurred across root chats `2c4456c2` (`step 53`), `e376eb31` (`step 76`), and Steward subagent `70b4937f` (`step 48`).
- **Operating Spectrum**:
  - *Where it helps*: Shared head files (`PROJECT.md`, `pm/current.md`, `RESOURCES.md`) keep all 3 parallel chat windows aligned on a single source of truth (`repo:project-manager` invoked **7×**, `repo:main-sync` **3×**).
  - *Where it drags*: When multiple Steward subagents and root windows edit `PROJECT.md` or `pm/current.md` within the same 2–3 minute window (or `git pull --rebase` updates lines mid-turn), cached `read_file` context becomes stale, causing avoidable `edit_file` retries.

### `OBS-2026-11-21-03` · `.venv` & SDK Package Surface Friction (`pytest` `sys.path`, `httpx` vs `httpx2`, Internal Imports)
- **Facets**: `toolchain-env`, `skill-adoption`
- **Evidence**:
  - `69ddeaa4`: Running `.venv/bin/pytest` directly failed collection with `ModuleNotFoundError: No module named 'simon'`, whereas `.venv/bin/python -m pytest` passed `6 passed, 52 subtests`.
  - `e376eb31` (`steps 119, 133, 137`): Scratch exploration hit `ModuleNotFoundError: No module named 'httpx'` (`google-genai 3.6.1` installs `httpx2`, not `httpx`) and two `ImportError` probes on private `google.genai` internals (`_gaos.models`, `_nextgen_client`).
- **Operating Spectrum**:
  - *Where it helps*: Shared `.venv` (`Python 3.12.16`) allowed instant sub-50ms test runs and live SDK experimentation across windows without global site-packages pollution.
  - *Where it drags*: Absence of a minimal `pyproject.toml` (`[tool.pytest.ini_options] pythonpath = ["."]`) makes bare `.venv/bin/pytest` behave differently from `python -m pytest`; and `httpx` isn't pre-installed alongside `httpx2` for REST scratch scripts.

### `OBS-2026-11-21-04` · Sandbox Boundary Friction Before `PreToolUse` Auto-Approve Hook
- **Facets**: `permission-surface`, `subagent-orchestration`, `velocity-tailwind`
- **Evidence**: Early steps (`69ddeaa4` steps 2 & 124, `5cd83453` steps 29 & 50, `e376eb31` step 81) hit `Operation not permitted` on `.git/index.lock`, `/tmp/`, and `~/google-cloud-sdk`, plus interactive git credential prompt (`task-130` canceled before `gh auth setup-git`) and GitHub unauthenticated `403` in `gemini-api` `install.sh`.
- **Operating Spectrum**:
  - *Where it helps*: Introducing `auto_approve_toolchain.py` (`PreToolUse`), `gh auth setup-git`, `GIT_TERMINAL_PROMPT=0` in `sync_main.py`, and `GEMINI_VERSION="$(gh api ...)"` in `RESOURCES.md` eliminated nearly all repetitive command stalls in subsequent turns.
  - *Where it drags*: `.agents/skills/*/scripts/*.py` (nested skill helper scripts, as opposed to top-level `.agents/scripts/*.py`) are worth checking in `auto_approve_toolchain.py` so new skill scripts enjoy the same zero-friction read-only execution.

### `OBS-2026-11-21-05` · Strong Natural Adoption of Repo & Plugin Skills
- **Facets**: `skill-adoption`, `velocity-tailwind`
- **Evidence**: Across 9 conversations, agents organically read `repo:project-manager` (`7×`), `builtin:agy-customizations` (`4×`), `builtin:antigravity_guide` (`4×`), `repo:main-sync` (`3×`), `plugin:gemini-api-cli` (`2×`), `plugin:gemini-api-dev` (`2×`), `repo:knowledge-governance` (`1×`), and `repo:managed-agents-curator` (`1×`), paired with `6×` `SessionStart` context injections.
- **Operating Spectrum**:
  - *Where it helps*: Progressive disclosure via `SessionStart` (`PROJECT.md`) + crisp `SKILL.md` frontmatter descriptions is working as intended — every root window and Steward subagent discovered and followed the governance loop without context bloat.

### `OBS-2026-11-21-06` · Worktree Branch Push Refspec in `sync_main.py --docs-only`
- **Facets**: `parallel-concurrency`, `subagent-orchestration`, `hook-ergonomics`
- **Evidence**: Inside git worktree branch `content_alignment_skill_rule` (`b2a966c3` / Steward `5673c610`), `sync_main.py --docs-only` pulls and rebases `HEAD` onto `origin/main` cleanly, so pushing `HEAD:main` (`git push origin HEAD:main`) is required when the local worktree branch is not named `main`.
- **Operating Spectrum**:
  - *Where it helps*: Isolated git worktrees eliminate concurrent `edit_file` target drift and shared working-tree collisions across parallel windows.
  - *Where it drags*: If `sync_main.py --docs-only` pushes `origin main` rather than `origin HEAD:main` when running on a non-`main` worktree branch, `origin/main` does not advance until `git push origin HEAD:main` runs explicitly.

---

## 2026-11-21 · Full-Workspace 53-Session Telemetry Audit (21 Root Chats, 32 Subagents, 168 Friction Signals)

### `OBS-2026-11-21-07` · Ad-Hoc `self` Subagent Repetition Across 4 Core Flows
- **Facets**: `subagent-orchestration`, `velocity-tailwind`
- **Evidence**: Across 21 root chats, `invoke_subagent(TypeName="self", ...)` was invoked **32+ times** with repeated hand-written prompt boilerplate:
  - **Project Manager Steward**: `16×` (`10×` `"Project Manager Steward"`, `6×` `"Project Manager (Steward)"`).
  - **Isolated Feature / UI / Demo Engineer** (`Workspace: "share"`): `10×` across `e376eb31` and `bf1eed02`.
  - **Parallel Eval / Rubric Author**: `4×` in `b2669acb`.
  - **Managed Agent Model/Config Deployer & CI Fixer**: repeated across `c565b9ea`, `b6b3bee4`, `b734fdf9`, `e376eb31`.
- **Operating Spectrum**:
  - *Where it helps*: Delegating to `self` with `Workspace: "share"` unlocked high-throughput parallel builds (Stage 3 Screening Fleet, 9-agent rubrics, Two-Stage UI) without blocking root chats.
  - *Where it drags*: Every parent chat re-explains repo conventions, verification commands, worktree `.venv` paths, and sync rules from scratch — leading to drift and avoidable retry turns.

### `OBS-2026-11-21-08` · Python 3.9 System Binary vs. `.venv` 3.12 & Worktree `.venv` Absence
- **Facets**: `toolchain-env`, `parallel-concurrency`
- **Evidence**:
  - **`10×` `SyntaxError: f-string expression part cannot include a backslash`** (`e376eb31`, `b6b3bee4`, `b2669acb`, `08b9a835`, `b734fdf9`) because `/usr/bin/python3` is Python 3.9 while `.venv/bin/python` is Python 3.12.
  - **`5×` `no such file or directory: .venv/bin/python`** (`0a227a03`, `59f63cd3`, `d1f89a55`, `1208d6c7`) inside `Workspace: "share"` git worktrees where gitignored `.venv/` is not copied.
  - **`4×` bare `pytest` / `ruff` not found**, **`2×` `gcloud` not on `PATH`**, and **`4×` missing `node` / `rg`** (`07ae3887`, `d82cb8b4`, `b6b3bee4`, `bfd77457`, `3fe73228`).
- **Operating Spectrum**:
  - *Where it helps*: `.venv` keeps Python 3.12 dependencies clean and fast when invoked directly from the main checkout.
  - *Where it drags*: Agents default to `python3`, bare `pytest`/`ruff`, or relative `.venv/bin/python` inside worktrees, burning ~25 wasted tool turns on predictable environment errors.

### `OBS-2026-11-21-09` · `ruff` Lint Failures Caught Only at `sync_main.py --code` Gate
- **Facets**: `toolchain-env`, `velocity-tailwind`
- **Evidence**: `11×` lint failures (`07ae3887`, `fbeaa94a`, `b2669acb`, `9640c972`, `1208d6c7`, `231add58`) where `sync_main.py --code` rejected commits for auto-fixable ruff issues (`[*] N fixable with --fix`).
- **Operating Spectrum**:
  - *Where it helps*: `sync_main.py --code` reliably protects `main` and CI from lint regressions.
  - *Where it drags*: Agents rarely run `.venv/bin/ruff check --fix` before calling `sync_main.py --code`, causing a full failed sync + re-run cycle.

### `OBS-2026-11-21-10` · Persistent `edit_file` Target Drift & Unstaged Rebase Blocks
- **Facets**: `parallel-concurrency`, `subagent-orchestration`
- **Evidence**: `17×` `target content not found in the file` (`07ae3887` steps 60–97, `e376eb31`, `59f63cd3`, `4965b4db`) plus `git pull --rebase` unstaged-changes errors and `2×` merge conflicts (`simon/discovery_ui.py`, `simon/web.py` in `59f63cd3`).
- **Operating Spectrum**:
  - *Where it helps*: Parallel UI/backend edits let multiple streams ship in a single afternoon.
  - *Where it drags*: Editing large shared UI files (`simon/discovery_ui.py`, `simon/web.py`) across concurrent windows or after stale reads triggers repeated `edit_file` retries and merge conflicts.

### `OBS-2026-11-21-11` · High Skill Adoption + Clear Skill Gaps in Deploy & UI Audit Flows
- **Facets**: `skill-adoption`, `velocity-tailwind`
- **Evidence**: Across 53 sessions, `repo:project-manager` (`21×`), `repo:main-sync` (`18×`), `repo:plain-english` (`8×`), `repo:agent-evals` (`5×`), and `plugin:gemini-api-*` (`8×`) saw strong organic adoption. Only `gcp-shared-agent-tool` has `0` reads so far. Conversely, **Cloud Run deploy / GitHub Actions debugging** (`edc88c8c`, `bfd77457`, `98dc3a65`, `b734fdf9`) and **UI flow / copy / state-machine audits** (`07ae3887`, `d82cb8b4`, `bfd77457`) ran repeatedly with zero dedicated skill runbook.
- **Operating Spectrum**:
  - *Where it helps*: Existing repo skills drove consistent governance, evals, and doc syncing.
  - *Where it drags*: Uncodified Cloud Run / CI and UI-audit flows forced agents to re-discover CLI paths (`gcloud`), staging service names, and test suites on every session.
