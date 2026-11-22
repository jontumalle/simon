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

---

## 2026-11-21 · 60-Session Product/UI Convergence & Steward Lifecycle Audit (22 Root Chats, 38 Subagents, PRs #1–#35)

### `OBS-2026-11-21-12` · Split-Brain SPA vs. SSR UI Drift & 5-PR Convergence Loop
- **Facets**: `parallel-concurrency`, `skill-adoption`, `subagent-orchestration`
- **Observed Signal & Evidence**: Across PRs `#10–#35`, JT built `/` as a vanilla-JS SPA (`simon/static/{index.html,app.js,app.css}` in PRs `#16, #19, #25, #33`) while Kevin built 7 Python SSR pages (`simon/{discovery_ui,screening_ui,taste_profile_ui}.py` in PRs `#10, #13–#15, #18, #20–#24, #28, #35`). In [d82cb8b4](conversation://d82cb8b4-4fee-4513-ae62-4555bf78bc11) (`steps 0, 134, 287`) and [07ae3887](conversation://07ae3887-55a1-4a51-b26d-6fedd56987c5) (`steps 0, 132, 207, 257`), the user flagged unlinked Discovery screens, unequal headers (`1440px` vs `1320px`), hidden sub-flows, and raw internal keys — requiring a **5-PR stabilization loop** (`#27, #30, #31, #32, #34`). Minutes after PR `#34` unified the `56px` topbar, subagent [0a227a03](conversation://0a227a03-c05c-42fe-8185-e538378def33) merged PR `#35` (`Source Hunter`, 42 sources across 8 regions, `American Idol` preset, `Run Full Pipeline Cascade`) onto SSR `/discovery` while topbar tab `1. Discovery` still routed to stale SPA `/?tab=discovery`, prompting [c6683ac6](conversation://c6683ac6-75a0-4c58-8c8e-fd0d192e135d) (`step 0`).
- **Operating Spectrum**:
  - *Where it helps*: Letting teammates ship zero-build Python SSR templates alongside a zero-dependency `/` SPA enabled 35 PRs and 8 working screens in one hackathon day without Node/bundler setup drag.
  - *Where it drags*: Without a shared route-ownership table or wireframe spec, parallel builders attach new controls to whichever shell they open first — creating duplicate Stage 1 implementations (`/?tab=discovery` vs `/discovery`), duplicated CSS/JS helpers, and multi-PR visual alignment loops.
- **Graduated Adaptation Space**:
  - *Light calibration*: Lock canonical route ownership and STE-100 terminology in `pm/product/ui-strategy.md` and `pm/product/README.md`, requiring engineers to check which shell owns a stage before editing UI files.
  - *Medium calibration*: Enforce a single-owner rule per stage (e.g., `FEAT-20` routing `1. Discovery` directly to `/discovery` and retiring `/?tab=discovery` in the same PR) while keeping `/`, `/screen`, and `/taste-profile` on their proven shells so 117 existing tests stay intact.
  - *Deeper calibration*: Extract shared Python/HTML shell chrome (`topbar`, theme tokens, `formatLabel`, status banners) or unify onto one frontend shell post-hackathon once live demo velocity is no longer the primary constraint.

### `OBS-2026-11-21-13` · Retrospective-Changelog Steward Gap vs. Living Versioned Product Specs
- **Facets**: `skill-adoption`, `subagent-orchestration`
- **Observed Signal & Evidence**: `repo:project-manager` ran `21×` across 60 sessions (including dedicated `simon-steward` runs [82db7ab9](conversation://82db7ab9-3000-4326-b58d-09f6d3fb82b2) and [e54ea46d](conversation://e54ea46d-7ed6-4600-bbbf-df6b1b968659)), reliably recording every PR in `pm/log/` and `PROJECT.md`. However, `ui-flow-audit` was invoked only `1×` ([921c1b75](conversation://921c1b75-517e-434b-9d7e-f3b15c282211) at `23:51Z`, `0×` during PR `#35` in [0a227a03](conversation://0a227a03-c05c-42fe-8185-e538378def33)), and zero files in `pm/` tracked current wireframes, user stories, or feature versions (`v1.0` -> `v2.0` -> `Retired`).
- **Operating Spectrum**:
  - *Where it helps*: Append-only session logs (`pm/log/`) and `decisions.md` preserve complete historical provenance with zero risk of overwriting teammate history during fast parallel sprints.
  - *Where it drags*: When Steward acts purely as a post-hoc changelog writer, no document answers *"what does each screen show right now, and which user stories are live vs. proposed?"* — forcing teammates and coding agents to reverse-engineer product truth from raw `app.js` and `*_ui.py` code.
- **Graduated Adaptation Space**:
  - *Light calibration*: Add `pm/product/` (`README.md`, `ui-strategy.md`, `features.md`, `user-stories.md`, `wireframes.md`) to `PROJECT.md` so every `SessionStart` surfaces the product blueprint.
  - *Medium calibration*: Upgrade the existing `Project Manager (Steward)` (`project-manager/SKILL.md` + `simon-steward.md`) with an **in-place Versioned Product Maintenance Protocol** (`v1.0`, `v1.x`, `v2.0`, `Proposed`, `Split-UI`, `Retired`) fed by one-line `FEAT-XX` deltas from `simon-feature-engineer` — explicitly avoiding a separate technical-writer subagent that would double token spend and re-create concurrent `edit_file` collisions on `pm/`.
  - *Deeper calibration*: Pair Steward updates with lightweight contract assertions in `tests/` that verify every topbar link and active `FEAT-XX` route resolves to its canonical owner.

### `OBS-2026-11-21-14` · Stale `Next Up` & Retired-Feature Residue After Fast Refactors
- **Facets**: `parallel-concurrency`, `skill-adoption`, `toolchain-env`
- **Observed Signal & Evidence**: After PR `#29` (`f75d51f`, retiring Phase 3B `performance-critic`/`booking-critic` from `phases.py` in [d82cb8b4](conversation://d82cb8b4-4fee-4513-ae62-4555bf78bc11) `steps 236–244`) and PR `#33` (`f80a6f5`, deleting legacy MVP shortlist UI and `agents/synthesis-scout/`), `pm/current.md` remained 85 lines / 26 KB long — still instructing agents in `Next Up` (`lines 79–83`) to wire deleted `SIMON_SYNTHESIS_AGENT` and `run_881b5370` into `data/mvp_contracts.json`, while mixing obsolete `3-tab Studio`, `5. Vocal Studio`, and `6. Evals / 7. Screening Deck / 8. Taste Profile` labels (`lines 14–37`). Simultaneously, `simon/static/app.js` retained dead DOM hooks (`#reviewTopbarControls`, `#promoteBar`, `#profileDrawer`, empty `#traceDrawer`), `simon/gemini.py:417` kept `synthesize_shortlist()`, `phases.py` kept legacy critic Lab presets, and retiring `performance-critic` dropped `@ MM:SS` vocal moment chips.
- **Operating Spectrum**:
  - *Where it helps*: Scoped feature-branch refactors (PRs `#29` and `#33`) shipped user-visible decluttering fast without blocking on repo-wide dead-code sweeps across `simon/scout.py` and `tests/test_mvp_scout.py`.
  - *Where it drags*: Without an explicit `Retired` lifecycle step in Steward and a conciseness cap on `pm/current.md`, historical paragraphs accumulate indefinitely and stale `Next Up` items mislead new chat windows into building against deleted agents or schemas.
- **Graduated Adaptation Space**:
  - *Light calibration*: Enforce a strict `<120-line` live-snapshot cap on `pm/current.md` and require Steward to prune shipped or `Retired` items from `Live Now` and `Next Up` on every run.
  - *Medium calibration*: Track retired capabilities explicitly under `Retired` (`FEAT-18`, `FEAT-19`) in `pm/product/features.md` — recording both what was removed and any quarantined code (`simon/scout.py`, orphan DOM IDs, dropped `@ MM:SS` chips tracked as `FEAT-22`) so staged cleanup never loses context.
  - *Deeper calibration*: Add DOM-ID and route-label smoke checks to `tests/test_agency_studio_ui.py` and `tests/test_discovery_ui.py` so orphaned selectors or stale `5. Vocal Studio` menu labels fail unit tests immediately on refactor PRs.

### `OBS-2026-11-21-15` · Multi-Agent Swarm Velocity Tailwinds on Cross-Screen UI Overhauls & Full-Repo Audits
- **Facets**: `subagent-orchestration`, `velocity-tailwind`
- **Observed Signal & Evidence**: In [07ae3887](conversation://07ae3887-55a1-4a51-b26d-6fedd56987c5) (`step 207` -> PR `#32` `76cf37f`), a 6-agent swarm partitioned `/taste-profile`, `/screen`, `/discovery`–`/evals`, and `/` SPA by file ownership, stripping raw internal jargon across all 8 screens in one cohesive pass (`113/113` tests passing). Similarly, [c6683ac6](conversation://c6683ac6-75a0-4c58-8c8e-fd0d192e135d) orchestrated 4 read-only mappers (`git-historian`, `ui-mapper`, `chat-auditor`, `backend-mapper` -> board `#10–#13`) feeding a single `triage-lead` (`#14`) before waking non-overlapping authors (`spec-author` vs. `process-author`) and a dedicated `verifier`.
- **Operating Spectrum**:
  - *Where it helps*: Two-phase swarm topology (**read-only fan-out -> single taxonomy/ID lock -> disjoint-file authors -> independent verifier**) eliminates concurrent `edit_file` collisions completely while synthesizing 60 sessions and 35 PRs in minutes.
  - *Where it drags*: Multi-agent swarms carry fixed coordination and board-reading token overhead; spawning a 6–8 agent swarm for a single-file bug fix or routine 1-route copy edit is slower and costlier than one `simon-feature-engineer` worktree run.
- **Graduated Adaptation Space**:
  - *Light calibration*: Reserve multi-agent swarms for cross-cutting audits, multi-surface refactors (`>= 4` disjoint files), or parallel eval authoring; route single-slice code changes to a single `simon-feature-engineer` subagent.
  - *Medium calibration*: When parallel writers share cross-file IDs or locked terms, insert a canonical ID/terminology lock post (`triage-lead`) between read-only discovery workers and parallel writers so cross-references (`FEAT-01`–`FEAT-22`, route tables) align on the first pass; skip the extra stage when writers own fully independent domains.
  - *Deeper calibration*: Gate final `sync_main.py` execution behind a read-only `verifier` pass (`[author-done]` -> `[verified-sync]`) whenever multiple authors update coupled governance and product specs simultaneously.
