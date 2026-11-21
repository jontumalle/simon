---
name: process-observer
description: >-
  Observes Antigravity chat sessions and subagent transcripts across the Simon workspace, logs skill
  invocations, hook behaviors, permission stalls, parallel-window frictions, and high-leverage
  workflow wins into pm/process/, and synthesizes nuanced, non-binary process improvements for a
  dedicated System Improver agent. Activate whenever auditing how sessions are going, diagnosing
  hook/permission/skill friction, or evolving repository rules, hooks, and skills.
---

# Process Observer & Continuous Improvement Skill

This skill powers **meta-observation and continuous workflow evolution** for the Simon repository (serving as the process-improvement counterpart to the `project-manager` Steward).

> **Core Principle — Non-Binary System Analysis**:
> Never collapse observations or proposals into rigid binary judgments (`working vs. broken`, `pass vs. fail`, or blunt `enable hook vs. disable hook` options). Every rule, hook, skill, and agent behavior has **operating conditions where it creates leverage** and **boundary conditions where it creates drag**. Always capture that full spectrum so the dedicated System Improver agent can tune mechanisms with precision rather than flipping blunt on/off switches.

---

## 1. Gather Empirical Session Evidence First

Run the bundled read-only transcript inspector to scan recent root chat windows and subagents operating in this repository:

```bash
python3 .agents/skills/process-observer/scripts/inspect_sessions.py --limit 25
# Or structured JSON for deeper filtering:
python3 .agents/skills/process-observer/scripts/inspect_sessions.py --limit 25 --format json
```

When a signal in the digest warrants closer inspection (e.g., a repeated `Stop` hook block, a subagent stall, or a skill that was opened vs. bypassed), read only the relevant step range in `<appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl` rather than loading entire raw logs.

---

## 2. Multi-Dimensional Classification Taxonomy (Non-Binary)

Tag each observation with **one or more** facets (facets commonly co-occur) and describe its **Context & Friction/Leverage Profile** rather than assigning a binary pass/fail label:

| Facet Tag | What It Captures |
| :--- | :--- |
| `hook-ergonomics` | How `SessionStart`, `PreToolUse`, and `Stop` hooks shape flow — both helpful guardrails and over-eager triggers or re-entry loops |
| `parallel-concurrency` | Interactions across simultaneous chat windows or concurrent subagents sharing one working tree / git index |
| `skill-adoption` | Which skills (`repo`, `plugin`, `builtin`) agents naturally activate, which get bypassed, and where skill instructions feel crisp vs. heavy |
| `permission-surface` | Where `auto_approve_toolchain.py` or sandbox rules create smooth autonomy vs. unexpected prompts, interactive hangs, or over-broad/under-broad matchers |
| `subagent-orchestration` | Delegation boundaries, file-ownership partitioning, `waiting_for_input` stalls, or long reasoning turns |
| `toolchain-env` | CLI flag subtleties, `PATH` / `.venv` mismatches, rate limits, or auth state friction |
| `velocity-tailwind` | Workflows, scripts, or abstractions that measurably sped up execution or prevented errors — **must be recorded** so future refinements preserve them |

### Required Nuance Fields Per Observation
1. **Observed Signal & Evidence**: Concrete conversation link (`[session](conversation://<id>)`), step index, tool/hook involved, and what actually happened.
2. **Operating Spectrum (Where It Helps vs. Where It Drags)**: State *both* the value the current mechanism provides and the specific condition under which friction appeared.
3. **Graduated Adaptation Space (Never Binary)**: Articulate calibrated ways a System Improver agent can evolve the behavior (e.g., scoping a hook by session-level mutations, adding mtime grace windows, tightening a skill's trigger description, or adding a preflight flag) along with their tradeoffs — never reduce recommendations to an `A vs. B` binary choice.

---

## 3. Running Records in `pm/process/`

All persistent process observations live inside `pm/process/` (part of the established `pm/` governance bucket, auto-approved for Track A `--docs-only` sync):

| File | Purpose & Update Rule |
| :--- | :--- |
| [pm/process/README.md](../../../pm/process/README.md) | Charter and workflow for the Process Observer & dedicated System Improver agent |
| [pm/process/observations.md](../../../pm/process/observations.md) | **Append-only chronological record** of dated session observations (frictions, skill usage, hook blocks, and velocity tailwinds) |
| [pm/process/synthesis.md](../../../pm/process/synthesis.md) | **Living analytical synthesis** organized into: *(1) What Is Working & Why*, *(2) Active Friction Dynamics & Root Causes*, and *(3) Calibrated Evolution Spectrums* for the System Improver agent |

---

## 4. Workflow Execution Steps

1. **Inspect**: Run `inspect_sessions.py` and read existing `pm/process/observations.md` + `pm/process/synthesis.md` to avoid duplicating already-logged events.
2. **Record**: Append newly observed empirical events (both frictions and wins, including skill invocation patterns) to `pm/process/observations.md`.
3. **Synthesize**: Update `pm/process/synthesis.md` — promote recurring signals into systemic themes, note whether recent system changes shifted friction up or down, and lay out non-binary adaptation spectrums.
4. **Sync Docs**: Run `python3 .agents/scripts/sync_main.py --docs-only -m "docs(process): log session observations and synthesis"` so every chat window and the dedicated System Improver agent immediately see the updated record on `origin/main`.
   *(Note: If the dedicated System Improver agent modifies executable `.py` hook/sync scripts or `tests/`, land those via `main-sync` Track B `--code --paths ...` so unit, smoke, and lint gates verify the improvement!)*
