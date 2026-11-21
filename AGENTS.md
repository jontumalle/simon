# Simon Repository Governance

This repository uses a **Life OS-inspired knowledge model** to keep governance, project management, Managed Agent playbooks, curated agent definitions, product code, data, ideas, and tests cleanly separated.

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
- **Ask When Unmapped (Setup-Stage Guardrail)**: Do **not** invent new top-level directories. Whenever new work does not clearly fit an established bucket above (or could reasonably live in two places), **ask the user where to place it** before saving.

## 3. Background Project Manager (Steward)
- After substantive work, architectural findings, or decisions in a chat session, launch a **background Project Manager subagent** (`invoke_subagent` using `.agents/skills/project-manager/SKILL.md`) to distill and file updates into:
  - `pm/log/YYYY-MM-DD-<topic>.md` (what happened — factual, dated)
  - `pm/decisions.md` (decisions made — dated, append-only)
  - `pm/current.md` (live state & blockers)
  - `PROJECT.md` (`Recent sessions` LRU line)
- Respect modality boundaries: never fabricate commitments or overwrite authored product code during PM distillation.

## 4. Partner Resource Sync (`RESOURCES.md`)
- Whenever a new CLI tool, Python dependency, MCP server, Antigravity plugin, or environment variable is introduced, update [RESOURCES.md](./RESOURCES.md) with reproducible macOS/Linux install instructions (never commit secret values) so a teammate's agent can self-install after `git pull`.
