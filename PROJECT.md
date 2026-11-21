# Simon — Project Root Index

Top of the repository pointer chain (modeled after Life OS). Loaded at session start so every human and agent knows **where things live**, **what is in focus**, and **what changed recently**. Keep this file concise — detail lives in the buckets below.

**Navigate:** `PROJECT.md` → bucket `README.md` or `pm/` head files → specific note, agent spec, or module.
Governance rules: [AGENTS.md](./AGENTS.md) · Partner toolchain & dependencies: [RESOURCES.md](./RESOURCES.md).

---

## Knowledge & Code Map

| Path | Role | Contents |
| :--- | :--- | :--- |
| **[RESOURCES.md](./RESOURCES.md)** | Toolchain Manifest | Running list of CLIs, SDKs, plugins, and env vars for all teammates & agents |
| **[pm/](./pm/)** | Governance & PM | `current.md`, `scope.md`, `decisions.md`, `log/` (session logs), `process/` (workflow telemetry & improvements), `inbox/` |
| **[notes/managed-agents/](./notes/managed-agents/README.md)** | How-To & Architecture | Playbooks for Gemini Managed Agents, repo-mounted sandboxes, Credentials/Files APIs, deployment |
| **[agents/](./agents/README.md)** | Curated Agents | Versioned definitions, prompts, environment specs, and deploy configs for Simon's Managed Agents |
| **[simon/](./simon/)** | Product Code | Python runtime, multimodal audio listener (`gemini-4-hydrogen`), Managed Agent orchestrator |
| **[data/](./data/README.md)** | Data & Schemas | Manifest schemas, evaluation datasets (paired with `examples/` fixtures and gitignored `local/`) |
| **[ideas/](./ideas/README.md)** | Ideas & Verticals | Product riffing, discovery sources, future verticals, and pitch framing |
| **[tests/](./tests/)** | Verification | Unit tests, fixture smoke tests, and agent evaluation harnesses |
| **[.agents/](./.agents/)** | Repo Agent Ops | Antigravity skills (`plain-english`, `project-manager`, `process-observer`, `main-sync`, `knowledge-governance`, `managed-agents-curator`) & hooks |

---

## Focus
1. **Gemini 4 NYC Hackathon — Best Use of Managed Agents ($5,000)**: Evolve Simon from single-script starter calls into a curated, repo-backed fleet of specialized Managed Agents.
2. **Knowledge & Toolchain Sync**: Keep [RESOURCES.md](./RESOURCES.md), `notes/managed-agents/`, and `agents/` synchronized on `origin/main` so both teammates' agents can install, build, and deploy seamlessly.
3. **End-to-End Pilot Demo (*First Listen NYC*)**: Ingest real/opt-in vocalist clips, run parallel Critic/Validator Managed Agents + Producer synthesis, and output an actionable paid-slot callback.

---

## Recent sessions
*Working memory (LRU pointer cache, max 12, most recent first). Maintained by the `project-manager` skill/subagent.*

- 2026-11-21 · taste-brief youtube mvp · shipped 3-unit YouTube vocal scout MVP, SQLite store, web studio & Wispr alignment → `simon/`, `agents/`, `data/`, `pm/`
- 2026-11-21 · plain-english alignment · added STE-100/Zinsser skill, global rule, and adaptive execution gate → `.agents/skills/plain-english/`, `pm/`
- 2026-11-21 · managed-agents pipeline · added workforce packaging, deploy pipeline, and cron/webhook trigger blueprint → `notes/managed-agents/`, `pm/`
- 2026-11-21 · process-observer · added process-observer skill, inspect_sessions.py telemetry, and non-binary pm/process/ records → `.agents/skills/process-observer/`, `pm/process/`
- 2026-11-21 · dspy & decisions api · prototyped Part 1 Decisions+DSPy 3.5 triage, 4-table DB & Excalidraw arch → `pm/`, `RESOURCES.md`
- 2026-11-21 · main-sync & toolchain · split dual-track Docs vs Code sync, auto-approved Steward doc writes, verified hooks → `AGENTS.md`, `.agents/`, `RESOURCES.md`, `tests/`
- 2026-11-21 · agent-ops permissions · added PreToolUse toolchain auto-approve hook, 34 unit tests, RESOURCES.md docs → `.agents/`, `tests/`, `RESOURCES.md`, `pm/`
- 2026-11-21 · governance & onboarding · established Life OS knowledge model, skills, RESOURCES.md, distilled kickoff transcript → `PROJECT.md`, `pm/`, `RESOURCES.md`, `.agents/`
