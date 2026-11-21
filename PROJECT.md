# Simon — Project Root Index

Top of the repository pointer chain (modeled after Life OS). Loaded at session start so every human and agent knows **where things live**, **what is in focus**, and **what changed recently**. Keep this file concise — detail lives in the buckets below.

**Navigate:** `PROJECT.md` → bucket `README.md` or `pm/` head files → specific note, agent spec, or module.
Governance rules: [AGENTS.md](./AGENTS.md) · Partner toolchain & dependencies: [RESOURCES.md](./RESOURCES.md).

---

## Knowledge & Code Map

| Path | Role | Contents |
| :--- | :--- | :--- |
| **[RESOURCES.md](./RESOURCES.md)** | Toolchain Manifest | Running list of CLIs, SDKs, plugins, and env vars for all teammates & agents |
| **[pm/](./pm/)** | Governance & PM | `current.md`, `scope.md`, `decisions.md`, `log/` (session logs), `inbox/` (raw captures) |
| **[notes/managed-agents/](./notes/managed-agents/README.md)** | How-To & Architecture | Playbooks for Gemini Managed Agents, repo-mounted sandboxes, Credentials/Files APIs, deployment |
| **[agents/](./agents/README.md)** | Curated Agents | Versioned definitions, prompts, environment specs, and deploy configs for Simon's Managed Agents |
| **[simon/](./simon/)** | Product Code | Python runtime, multimodal audio listener (`gemini-4-hydrogen`), Managed Agent orchestrator |
| **[data/](./data/README.md)** | Data & Schemas | Manifest schemas, evaluation datasets (paired with `examples/` fixtures and gitignored `local/`) |
| **[ideas/](./ideas/README.md)** | Ideas & Verticals | Product riffing, discovery sources, future verticals, and pitch framing |
| **[tests/](./tests/)** | Verification | Unit tests, fixture smoke tests, and agent evaluation harnesses |
| **[.agents/](./.agents/)** | Repo Agent Ops | Antigravity skills (`project-manager`, `main-sync`, `knowledge-governance`, `managed-agents-curator`) & hooks |

---

## Focus
1. **Gemini 4 NYC Hackathon — Best Use of Managed Agents ($5,000)**: Evolve Simon from single-script starter calls into a curated, repo-backed fleet of specialized Managed Agents.
2. **Knowledge & Toolchain Sync**: Keep [RESOURCES.md](./RESOURCES.md), `notes/managed-agents/`, and `agents/` synchronized on `origin/main` so both teammates' agents can install, build, and deploy seamlessly.
3. **End-to-End Pilot Demo (*First Listen NYC*)**: Ingest real/opt-in vocalist clips, run parallel Critic/Validator Managed Agents + Producer synthesis, and output an actionable paid-slot callback.

---

## Recent sessions
*Working memory (LRU pointer cache, max 12, most recent first). Maintained by the `project-manager` skill/subagent.*

- 2026-11-21 · dspy & decisions api · researched DSPy + Gemini Decisions classifier, enabled gemini-api plugin & Excalidraw MCP → `pm/`, `RESOURCES.md`
- 2026-11-21 · agent-ops permissions · added PreToolUse toolchain auto-approve hook, 34 unit tests, RESOURCES.md docs → `.agents/`, `tests/`, `RESOURCES.md`, `pm/`
- 2026-11-21 · main-sync & toolchain · added sync_main.py, Stop/SessionStart hooks, cross-window Steward, gemini-api + gcloud → `AGENTS.md`, `.agents/`, `RESOURCES.md`, `notes/managed-agents/`
- 2026-11-21 · governance & onboarding · established Life OS knowledge model, skills, RESOURCES.md, distilled kickoff transcript → `PROJECT.md`, `pm/`, `RESOURCES.md`, `.agents/`
