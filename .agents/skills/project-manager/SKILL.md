---
name: project-manager
description: >-
  Harvests session documents and brain artifacts across chat windows, maintains versioned product
  and UI truth in pm/product/, distills decisions, concise live status (<120 lines), session logs,
  and partner resources into the Simon knowledge model, updates the Recent sessions LRU cache in
  PROJECT.md, and syncs documentation directly to origin/main. Activate in every chat window
  whenever features, UI routes, documents, research, plans, or code milestones are produced.
---

# Simon Project Manager (Steward) Skill — Product Truth, Harvesting & `main` Sync

This skill defines Simon's single **Project Manager (Steward)** role. We intentionally maintain product and UI specs inside this Steward rather than adding a separate technical-writer subagent: one Steward keeps `pm/product/`, `pm/current.md`, `pm/decisions.md`, `pm/log/`, and `PROJECT.md` atomic in a single `--docs-only` commit and avoids concurrent `edit_file` collisions across parallel chats.

## 1. Launching in the Background (For Primary Agent — Every Chat Window)

Whenever a chat window ships or modifies features/UI, produces research or brain artifacts, confirms decisions, or lands code PRs, launch the dedicated Steward subagent via `invoke_subagent` (prefer `simon-ops:simon-steward`, or `TypeName: "self"` with `Role: "Project Manager (Steward)"`). Pass:
1. Instruction to read `.agents/skills/project-manager/SKILL.md`, `.agents/skills/main-sync/SKILL.md`, `pm/product/README.md`, `PROJECT.md`, `pm/scope.md`, and `pm/current.md`.
2. The session's artifact directory (`<appDataDir>/brain/<conversation-id>`) and paths to any standalone markdown docs, notes, or `pm/inbox/` items so nothing stays trapped in chat.
3. Concise summary of changed files/PRs, confirmed owner decisions, new CLIs/SDKs/plugins/env vars, and **one Feature-Version Delta line per touched feature**:
   `FEAT-XX: v1.1 -> v1.2 | PR #NN | Summary of user-visible change or retirement`
4. Instruction to sync exclusively via **`main-sync` Track A (`--docs-only`)** — Steward never commits or pushes runtime code (`--code` belongs to coding agents).

---

## 2. Steward Runbook: Harvest, Maintain Product Versions & Sync `main`

Before editing, run `git pull --rebase --autostash origin main`. Always call `read_file` on shared head files (`PROJECT.md`, `pm/current.md`, `pm/decisions.md`, `RESOURCES.md`, and any target `pm/product/*.md` file) **immediately before** calling `edit_file` on them.

### Step 1 · Harvest Session Documents & Brain Artifacts
Check whether the session produced standalone markdown docs, research notes, plans, or brain artifacts (`<appDataDir>/brain/<conversation-id>/*.md`) that belong in the repository:
- Distill reusable artifacts into established buckets (`pm/product/`, `notes/managed-agents/`, `ideas/`, `agents/`, `pm/`, `data/`).
- Skip transient scratch checklists once distilled into `pm/log/` and `pm/product/`.
- **Setup-Stage Guardrail**: Never invent new top-level directories or touch runtime code (`simon/`, `tests/`, `examples/`). Ask the caller/user only when an item is genuinely unmapped.

### Step 2 · Versioned Product & UI Maintenance Protocol (`pm/product/`)
On **every** Steward run, check whether any feature, route, wireframe, or user story was added, changed, proposed, split across UI shells, or retired. Update `pm/product/` **in place** using the locked terms in [pm/product/README.md](../../../pm/product/README.md) so product docs always show current truth plus version provenance:

| Lifecycle Tag | Trigger | Required In-Place Steward Update |
| :--- | :--- | :--- |
| **`v1.0` (Added)** | New feature, agent stage, or UI route merged | Assign next `FEAT-XX` in `pm/product/features.md`, map persona acceptance criteria in `pm/product/user-stories.md`, and add layout/handoff zones in `pm/product/wireframes.md` (and `ui-strategy.md` if routes changed). |
| **`v1.x` (Modified)** | Filter, copy pass, model swap, state fix, or API tweak | Update current behavior **in place** in `features.md` (plus `wireframes.md` / `user-stories.md` if UI/criteria changed) and append one dated PR line to `Version History`. |
| **`v2.0` (Remodeled)** | Major layout, contract, or primary user-flow overhaul | Replace current-state spec in place across `features.md`, `wireframes.md`, and `ui-strategy.md`, recording prior behavior in `Version History`. |
| **`Proposed` (Backlog)** | User requested a feature/fix in chat or triage, not yet merged | Add or update under `Proposed / Backlog` in `features.md` and `user-stories.md` with source chat/PR and target wave. |
| **`Split-UI`** | SPA (`simon/static/`) and SSR (`simon/*_ui.py`) diverge | Mark `Split-UI` in `features.md` and `ui-strategy.md`, naming exact missing controls on each surface until consolidated. |
| **`Retired`** | Feature, route, or agent removed (e.g., PR `#33` MVP shortlist) | Move entry to `Retired` in `features.md`, note any remaining dead code to clean up, remove obsolete wireframes/stories from active sections, and prune from `pm/current.md`. |

### Step 3 · Distill into Governance & Pointer Files (Strict `<120-Line` Cap on `pm/current.md`)

| Target | Modality & Rules |
| :--- | :--- |
| `pm/product/*.md` | **Living product & UI truth** — updated in place per Step 2 (`README.md`, `ui-strategy.md`, `features.md`, `user-stories.md`, `wireframes.md`) using management-facing STE-100 Plain English. |
| `pm/current.md` | **Crisp live snapshot (`<120 lines` hard cap)** — rewrite/prune in place rather than appending PR dumps! Keep only current `Live Now` truth (pointing to `pm/product/` and `pm/log/` for history), active `Next Up` waves, and real `Blockers / Open Items`. Immediately delete shipped or `Retired` items from `Next Up`. |
| `pm/log/YYYY-MM-DD-<slug>.md` | **Chronological session log** — dated, factual bullets citing PRs, commit SHAs, `FEAT-XX` deltas, and harvested docs. Append to today's topic log when matching. |
| `pm/decisions.md` | **Append-only decision record** — append `- **YYYY-MM-DD · Title**: Rationale & outcome.` Never erase prior decisions; append a superseding entry when direction changes. |
| `RESOURCES.md` | **Partner toolchain manifest** — reproducible macOS/Linux install steps for new CLIs, packages, plugins, or env var names (never commit secret values). |
| `notes/managed-agents/` · `agents/` · `ideas/` · `data/` | **Playbooks, agent specs, explorations & schemas** — file reusable technical patterns in `notes/managed-agents/` and keep `agents/README.md` aligned with deployed packages. |
| `PROJECT.md` (`Recent sessions`) | **LRU Working Memory (max 12)** — `- YYYY-MM-DD · <workstream> · <≤15 word summary> → <key paths>`. Move existing workstream to top or insert and drop 13th entry; never edit `## Focus` without explicit owner direction. |

### Step 4 · Sync via `main-sync` (`Track A · Docs Sync` Only) & Report Back
1. Verify `wc -l pm/current.md` is strictly `< 120` lines, then sync straight to `origin/main`:
   ```bash
   python3 .agents/scripts/sync_main.py --docs-only -m "docs(pm): <concise summary>"
   ```
   - Never pass `--code` or `--all`. If `git push` fails offline, confirm `committed: true` locally and report the exact push error.
2. Return a concise report covering: (a) harvested artifacts, (b) `FEAT-XX` version transitions applied in `pm/product/`, (c) updated Steward files + `pm/current.md` line count, and (d) synced `main` commit SHA.
