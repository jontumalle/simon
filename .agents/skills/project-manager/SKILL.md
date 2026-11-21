---
name: project-manager
description: >-
  Distills and files session work, decisions, live status, inbox captures, and partner resources
  into the Simon repository's Life OS-inspired knowledge model, and updates the Recent sessions
  working memory in PROJECT.md. Activate this skill when wrapping up substantive work in a chat
  session, when launching or acting as the background Project Manager (Steward) subagent, or when
  processing items from pm/inbox/ or raw transcripts.
---

# Simon Project Manager (Steward) Skill

This skill implements the **Steward / Project Manager** role for the Simon repository (modeled after Life OS). Its job is to turn completed work, research, and confirmed decisions into crisp, accurately placed files without cluttering the primary coding session.

## 1. Running in the Background (For Primary Agent)

Whenever a work block, feature, research investigation, or decision session wraps up, launch a background subagent via `invoke_subagent`:
- **`TypeName`**: `"self"`
- **`Role`**: `"Project Manager (Steward)"`
- **`Prompt`**: Pass:
  1. Instruction to read `.agents/skills/project-manager/SKILL.md`, `PROJECT.md`, `pm/scope.md`, and `pm/current.md`.
  2. Concise summary of what happened, what files changed, any decisions confirmed by the owner, and any new tools/dependencies introduced.
  3. Whether to commit & push governance updates to `origin/main` (per owner preference).

---

## 2. Distillation & Filing Procedure (For Project Manager Agent)

Before writing, read `PROJECT.md`, `pm/scope.md`, `pm/current.md`, and `pm/decisions.md`.

### Step A · Respect Bucket Modalities
| Target | Modality & Rules |
| :--- | :--- |
| `pm/log/YYYY-MM-DD-<slug>.md` | **What happened** — dated, factual, concise bullets referencing changed files/commits. Prefer appending to today's topic log over creating duplicate files. |
| `pm/decisions.md` | **Decisions confirmed** — append `- **YYYY-MM-DD · Title**: Rationale & outcome.` Never rewrite past decisions unless superseded (add a new dated line instead). |
| `pm/current.md` | **State right now** — rewrite `Live Now`, `Next Up`, and `Blockers / Open Items` so they reflect reality today, and set `*Updated: YYYY-MM-DD*`. |
| `RESOURCES.md` | **Partner toolchain sync** — add any newly adopted CLI, Python package, plugin, or env var name (never commit secret values!). |
| `notes/managed-agents/` | **How-to engineering knowledge** — architecture, SDK/REST patterns, sandbox environment & deployment guides. |
| `agents/<agent-id>/` | **Curated Managed Agents** — declarative agent specs (`agent.json`), `SYSTEM.md` prompts, and usage docs. |
| `ideas/` | **Explorations & future verticals** — unscheduled product ideas, scouting sources, calibration concepts. |

### Step B · Update `Recent sessions` in `PROJECT.md` (LRU Cache)
Maintain the `## Recent sessions` list at the bottom of `PROJECT.md`:
- Format: `- YYYY-MM-DD · <workstream> · <≤15 word summary> → <key paths>`
- **Touch, don't duplicate**: If an entry for the same workstream already exists, update its date/summary and move it to the top.
- **Max 12 entries**: Drop the oldest line if adding a 13th (detail already lives in `pm/log/` and bucket files).
- **Never edit `## Focus`** unless the owner explicitly changed priorities.

### Step C · Setup-Stage Guardrail
- Never invent new top-level folders.
- Never overwrite authored application code (`simon/`) during a PM pass.
- If an item's destination is genuinely ambiguous, flag it clearly in your report back rather than guessing.

### Step D · Report Back
Return a brief summary listing every file updated and a one-line description of what changed.
