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
