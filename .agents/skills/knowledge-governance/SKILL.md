---
name: knowledge-governance
description: >-
  Reference guide for the Simon repository's Life OS-inspired knowledge model, folder taxonomy,
  progressive-disclosure navigation, and setup-stage filing rules. Use when deciding where new
  notes, data, tests, ideas, agent definitions, or governance artifacts belong, or when onboarding
  onto the project structure.
---

# Simon Knowledge Governance Skill

Simon adapts the **Life OS** progressive-disclosure control plane to a collaborative hackathon & multi-agent engineering repository.

## 1. Navigation Chain
1. `PROJECT.md` — Root map, owner `Focus`, and `Recent sessions` working memory.
2. `pm/scope.md` & `pm/current.md` — Guardrails (what Simon is/isn't) and live sprint status.
3. Target bucket (`notes/managed-agents/`, `agents/`, `simon/`, `data/`, `ideas/`, `tests/`).

Load only the bucket needed for the current task to keep context sharp.

## 2. Separation of Concerns

```text
simon/ (repo root)
├── PROJECT.md                # Root index + Focus + Recent sessions (LRU max 12)
├── AGENTS.md                 # Always-on Antigravity governance rules
├── RESOURCES.md              # Shared partner/agent CLI, SDK, plugin & env manifest
├── governance/               # Durable charters (git-flow, Intake/Decision/Outcome domains, safety)
├── pm/                       # Live Project Management (Steward & Process Observer layer)
│   ├── scope.md              # Guardrails & non-goals
│   ├── current.md            # Live state, next actions, blockers
│   ├── decisions.md          # Append-only dated decisions
│   ├── log/                  # Factual dated session/milestone logs
│   └── inbox/                # Raw captures awaiting distillation
├── notes/
│   └── managed-agents/       # HOW to build, repo-mount, secure & deploy Managed Agents
├── agents/                   # WHERE we curate Simon's deployable Managed Agents
│   └── <agent-id>/           # agent.json + SYSTEM.md + README.md
├── simon/                    # Python product runtime & orchestration CLI
├── data/                     # Schemas, rubrics & anonymized evaluation benchmarks
├── examples/                 # Deterministic public fixtures (showcase.json)
├── local/                    # Gitignored private inputs, audio, env, raw transcripts
├── ideas/                    # Future verticals, scouting channels & pitch concepts
├── tests/                    # Automated unit, smoke & rubric evaluation tests
└── .agents/                  # Repo-scoped Antigravity skills & SessionStart hook
```

## 3. Setup-Stage Filing Checklist
1. Does the file contain secrets, private artist PII, raw audio, or temporary scratch transcripts? → Put in `local/` (gitignored).
2. Does it clearly match one of the established buckets above? → File it cleanly and let the `project-manager` skill log it.
3. Would saving it require a **new top-level directory** or an **ambiguous bucket choice**? → **Ask the user first** before creating the path.
