---
name: project-manager
description: >-
  Harvests session documents and brain artifacts across chat windows, distills decisions, live
  status, session logs, and partner resources into the Simon repository's Life OS-inspired
  knowledge model, updates the Recent sessions LRU cache in PROJECT.md, and continuously syncs
  documentation directly to origin/main. Activate this skill in every chat window whenever
  documents, research, artifacts, plans, or code milestones are produced, or when processing items
  from pm/inbox/ or raw transcripts.
---

# Simon Project Manager (Steward) Skill — Cross-Window Harvesting & `main` Sync

This skill implements the **Steward / Project Manager** role for the Simon repository (modeled after Life OS). Its job in **every chat window** is to rescue reusable documents/artifacts from ephemeral chat contexts, distill completed work and decisions into the repository's Knowledge Model, and push documentation updates straight to `origin/main` with zero repercussions.

## 1. Launching in the Background (For Primary Agent — Every Chat Window)

Whenever a chat window produces documents, research, brain artifacts, plans, architectural decisions, or code milestones, launch a background subagent via `invoke_subagent`:
- **`TypeName`**: `"self"`
- **`Role`**: `"Project Manager (Steward)"`
- **`Prompt`**: Pass:
  1. Instruction to read `.agents/skills/project-manager/SKILL.md`, `.agents/skills/main-sync/SKILL.md`, `PROJECT.md`, `pm/scope.md`, and `pm/current.md`.
  2. The session's artifact directory path (`<appDataDir>/brain/<conversation-id>`) and paths to any standalone markdown docs, notes, or transcripts produced in the session so none stay trapped in the chat window.
  3. Concise summary of what happened, what code/files changed, confirmed owner decisions, and any new CLIs/SDKs/plugins/env vars introduced.
  4. Instruction to delegate synchronization to the **`main-sync` skill (`Track A · Docs & Knowledge Sync`, `--docs-only`)** — noting that documentation file writes and `--docs-only` sync are auto-approved by `.agents/hooks.json`, and the Steward must **never** sync runtime code (`--code` belongs exclusively to coding agents).

---

## 2. Cross-Window Document Harvesting & `main` Sync Runbook (For Steward Agent)

Before writing, read `.agents/skills/main-sync/SKILL.md`, `PROJECT.md`, `pm/scope.md`, `pm/current.md`, and `pm/decisions.md`.

### Step 1 · Harvest Session Documents & Artifacts
Check whether the chat session produced any standalone markdown documents, research reports, architecture notes, plans, transcripts, `pm/inbox/` captures, or Antigravity brain artifacts (`<appDataDir>/brain/<conversation-id>/*.md`) whose knowledge belongs in the repository:
- Copy or distill reusable documents into the appropriate established bucket (`notes/managed-agents/`, `ideas/`, `agents/`, `pm/`, `data/`) so context is never trapped or lost inside a single chat window or ephemeral artifact directory.
- Skip purely transient scratch files or internal task checklists that add no durable repo value once distilled into `pm/log/` and `pm/current.md`.
- **Setup-Stage Guardrail**: Never invent new top-level folders or overwrite authored product runtime code (`simon/`). Established buckets go straight into the model; only flag genuinely unmapped items back to the caller/user rather than guessing.

### Step 2 · Distill into Steward Files & `PROJECT.md`
Update the repository's governance and pointer files while respecting bucket modalities:

| Target | Modality & Rules |
| :--- | :--- |
| `pm/log/YYYY-MM-DD-<slug>.md` | **What happened** — dated, factual, concise bullets referencing changed files/commits and harvested docs. Prefer appending to today's topic log over creating duplicate files. |
| `pm/decisions.md` | **Decisions confirmed** — append `- **YYYY-MM-DD · Title**: Rationale & outcome.` Never rewrite past decisions unless superseded (append a new dated entry instead). |
| `pm/current.md` | **State right now** — refresh `Live Now`, `Next Up`, and `Blockers / Open Items` to match reality today, and set `*Updated: YYYY-MM-DD*`. |
| `RESOURCES.md` | **Partner toolchain sync** — add reproducible macOS/Linux install instructions for any newly adopted CLI, Python package, MCP server, plugin, or env var name (never commit secret values!). |
| `notes/managed-agents/` | **How-to engineering knowledge** — architecture, SDK/REST patterns, sandbox environment & deployment playbooks. |
| `agents/<agent-id>/` | **Curated Managed Agents** — declarative agent specs (`agent.json`), `SYSTEM.md` prompts, and usage docs. |
| `ideas/` · `data/` | **Explorations, schemas & datasets** — product discovery/verticals (`ideas/`) and manifest schemas or eval benchmarks (`data/`). |
| `PROJECT.md` (`Recent sessions`) | **LRU Working Memory (max 12)** — `- YYYY-MM-DD · <workstream> · <≤15 word summary> → <key paths>`. Touch & move to top if the workstream already exists; drop oldest if >12; never edit `## Focus` unless the owner explicitly changed priorities. |

### Step 3 · Sync via `main-sync` Skill (`Track A · Docs Sync` Only)
Follow [`.agents/skills/main-sync/SKILL.md`](../main-sync/SKILL.md) (**Track A · Docs & Knowledge Sync**). Creating/editing documentation in established buckets and running `--docs-only` sync are **auto-approved** by `.agents/scripts/auto_approve_toolchain.py` (`PreToolUse`):
1. Run:
   ```bash
   python3 .agents/scripts/sync_main.py --docs-only -m "docs(pm): <concise summary>"
   ```
   - **Strict Separation from Code Sync**: Never pass `--code` or `--all` from the Steward. Unfinished `simon/` or `tests/` code in the working tree stays untouched (`--docs-only` unstages non-doc paths and rebases with `--autostash`), because code changes follow `main-sync` **Track B (`--code`)** with mandatory test/smoke gates and `--paths` / `--branch` controls.
2. **Graceful Fallback**: If the remote `git push` fails (e.g., offline or network error), verify that the **local commit on `main` succeeded** (`committed: true`) and report the exact remote push status/error clearly.

### Step 4 · Report Back
Return (via `send_message` when running as a subagent) a concise summary covering:
1. Harvested session/brain artifacts and where they were filed (plus any unmapped items flagged for the user),
2. Every Steward / Knowledge Model file updated with a one-line description, and
3. Exact `main` commit and `origin/main` push status.
