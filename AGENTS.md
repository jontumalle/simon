# Simon Repository Governance

This repository uses a **Life OS-inspired knowledge model** to keep governance, project management, Managed Agent playbooks, curated agent definitions, product code, data, ideas, and tests cleanly separated — and continuously synchronized across every chat window and teammate via `origin/main`.

## 1. Progressive Disclosure & Navigation
- Start at [PROJECT.md](./PROJECT.md) to orient on current **Focus**, the **Knowledge & Code Map**, and **Recent sessions**.
- Before acting on scope or architecture, check [pm/scope.md](./pm/scope.md), [pm/current.md](./pm/current.md), and [pm/decisions.md](./pm/decisions.md).
- Do not load every file in the repository at once; follow pointers into the relevant bucket.

## 2. Knowledge Buckets & Setup-Stage Filing Rule
- **Established Buckets**:
  - `PROJECT.md` — Root index, Focus, and LRU `Recent sessions` pointer cache (max 12).
  - `RESOURCES.md` — Running manifest of required CLIs, SDKs, plugins, env vars, and install commands for teammates' agents.
  - `pm/` — Governance & Steward tracking (`current.md`, `scope.md`, `decisions.md`, `log/`, `inbox/`).
  - `notes/managed-agents/` — How-to engineering playbooks and research on building/deploying Managed Agents ("agent as a repo").
  - `agents/` — Curated, deployable task-specific Managed Agents maintained in this repository.
  - `simon/` — Product runtime code and CLI (`python3 -m simon`).
  - `data/` · `examples/` · `local/` — Schemas/benchmarks (`data/`), public demo fixtures (`examples/`), and gitignored private/live inputs & raw transcripts (`local/`).
  - `ideas/` — Product explorations, discovery sources, pitch concepts, and future verticals.
  - `tests/` — Automated tests and agent evaluations.
  - `.agents/` — Repository skills, hooks, and sync utilities (`sync_main.py`).
- **Ask When Unmapped (Setup-Stage Guardrail)**: Do **not** invent new top-level directories. Ask the user **only** when new work does not fit an established bucket above (or could reasonably live in two places) or would invent a new top-level folder. Files belonging to established documentation/knowledge buckets go straight into the model and push directly to `main`!

## 3. Dual-Track Synchronization (`main-sync` Skill: Docs Sync vs. Code Sync)
Always follow [`.agents/skills/main-sync/SKILL.md`](./.agents/skills/main-sync/SKILL.md) — documentation and runtime code synchronize differently:
- **Track A · Docs & Knowledge Sync (`--docs-only`, Auto-Approved → Direct to `origin/main`)**:
  - Any documentation or knowledge-model file (`*.md`, `PROJECT.md`, `RESOURCES.md`, `pm/**`, `notes/**`, `ideas/**`, `data/**`, `agents/**`, `.agents/**`) is **auto-approved** on creation/edit (`PreToolUse`) and commits/pushes **straight to `origin/main` immediately** with zero ceremony via `python3 .agents/scripts/sync_main.py --docs-only -m "docs: ..."`.
  - `--docs-only` automatically leaves in-progress `simon/` or `tests/` edits untouched in your working tree (`--rebase --autostash`).
- **Track B · Code Sync (`--code`, Gated by Tests & Scoped by `--paths` / `--branch`)**:
  - Runtime code and tests (`simon/**`, `tests/**`, `examples/**`) **never** ride along in background Steward doc syncs.
  - Sync code using `python3 .agents/scripts/sync_main.py --code --paths <files...> -m "feat(simon): ..."`, which enforces `unittest` + `python -m simon` smoke + `ruff` verification *before* committing (and supports `--branch feat/<slug>` + `gh pr create` when a change is breaking or needs teammate review before hitting `main`).

## 4. Background Project Manager (Steward) — Every Chat Window
- In **every chat window**, whenever documents, research, artifacts, plans, architectural findings, decisions, or code milestones are produced, launch a **background `Project Manager (Steward)` subagent** (`invoke_subagent` following `.agents/skills/project-manager/SKILL.md` + `.agents/skills/main-sync/SKILL.md`) to:
  1. **Harvest session documents & artifacts**: Grab any newly created standalone docs, research notes, plans, or reusable Antigravity brain/scratch artifacts (`<appDataDir>/brain/<conversation-id>/*.md`) so nothing stays trapped inside an ephemeral chat window or scratch artifact folder.
  2. **Organize & distill into the Knowledge Model**: File reusable knowledge and session updates into the appropriate established buckets (`notes/`, `pm/log/YYYY-MM-DD-<topic>.md`, `pm/decisions.md`, `pm/current.md`, `ideas/`, `agents/`, `data/`, `RESOURCES.md`, and the `Recent sessions` LRU cache in `PROJECT.md`) — auto-approved by `.agents/hooks.json`.
  3. **Sync docs via `main-sync` (`--docs-only`)**: Commit and push **only** documentation/knowledge updates straight to `origin/main` via `python3 .agents/scripts/sync_main.py --docs-only` while leaving code changes to Track B (`--code`).
- Respect modality boundaries: never fabricate commitments or overwrite authored product code (`simon/`) during PM distillation, and ask the user only when an item is genuinely unmapped per the Setup-Stage Guardrail.

## 5. Partner Resource Sync (`RESOURCES.md`)
- Whenever a new CLI tool, Python dependency, MCP server, Antigravity plugin, or environment variable is introduced, update [RESOURCES.md](./RESOURCES.md) with reproducible macOS/Linux install instructions (never commit secret values) so a teammate's agent can self-install after `git pull`.
