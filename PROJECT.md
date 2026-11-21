# Simon — Project Root Index

Top of the repository pointer chain (modeled after Life OS). Loaded at session start so every human and agent knows **where things live**, **what is in focus**, and **what changed recently**. Keep this file concise — detail lives in the buckets below.

**Navigate:** `PROJECT.md` → bucket `README.md` or `pm/` head files → specific note, agent spec, or module.
Governance rules: [AGENTS.md](./AGENTS.md) · Partner toolchain & dependencies: [RESOURCES.md](./RESOURCES.md).

---

## Knowledge & Code Map

| Path | Role | Contents |
| :--- | :--- | :--- |
| **[RESOURCES.md](./RESOURCES.md)** | Toolchain Manifest | Running list of CLIs, SDKs, plugins, and env vars for all teammates & agents |
| **[governance/](./governance/README.md)** | Operating Charters | Durable charters: `git-flow.md`, `pipeline-domains.md`, `agent-ops-and-safety.md`, `knowledge-and-stewardship.md` |
| **[pm/](./pm/)** | Project Management | `current.md`, `scope.md`, `decisions.md`, `log/` (session logs), `process/` (workflow telemetry & improvements), `inbox/` |
| **[notes/managed-agents/](./notes/managed-agents/README.md)** | How-To & Architecture | Playbooks for Gemini Managed Agents, repo-mounted sandboxes, Credentials/Files APIs, deployment |
| **[agents/](./agents/README.md)** | Curated Agents | Versioned definitions, prompts, environment specs, and deploy configs for Simon's Managed Agents |
| **[simon/](./simon/)** | Product Code | Python runtime, multimodal audio listener (`gemini-4-hydrogen`), Managed Agent orchestrator |
| **[data/](./data/README.md)** | Data & Schemas | Manifest schemas, evaluation datasets (paired with `examples/` fixtures and gitignored `local/`) |
| **[ideas/](./ideas/README.md)** | Ideas & Verticals | Product riffing, discovery sources, future verticals, and pitch framing |
| **[tests/](./tests/)** | Verification | Unit tests, fixture smoke tests, and agent evaluation harnesses |
| **[.agents/](./.agents/)** | Repo Agent Ops | Antigravity rules (`plain-english`), skills (`project-manager`, `process-observer`, `main-sync`, `knowledge-governance`, `managed-agents-curator`) & hooks |

---

## Focus
1. **Gemini 4 NYC Hackathon — Best Use of Managed Agents ($5,000)**: Evolve Simon from single-script starter calls into a curated, repo-backed fleet of specialized Managed Agents.
2. **Knowledge & Toolchain Sync**: Keep [RESOURCES.md](./RESOURCES.md), `notes/managed-agents/`, and `agents/` synchronized on `origin/main` so both teammates' agents can install, build, and deploy seamlessly.
3. **End-to-End Pilot Demo (*First Listen NYC*)**: Ingest real/opt-in vocalist clips, run parallel Critic/Validator Managed Agents + Producer synthesis, and output an actionable paid-slot callback.

---

## Recent sessions
*Working memory (LRU pointer cache, max 12, most recent first). Maintained by the `project-manager` skill/subagent.*

- 2026-11-21 · ui flow unification · unified 5-stage topbar, discovery parity, Stage 3→4 screening handoffs & 112/112 tests (PR #30, `cc2154e`) → `pm/log/2026-11-21-ui-flow-unification.md`, `simon/static/`, `simon/discovery_ui.py`
- 2026-11-21 · screening, taste & demo flow · shipped Stage 3 Screening Fleet, `/screen`, `/taste-profile` & clean staging demo (PRs #24/#28) → `pm/log/2026-11-21-screening-taste-and-demo-flow.md`, `simon/screening.py`, `simon/demo_flow.py`
- 2026-11-21 · label-signing recall eval · live 3-worker recall run (192k tokens, 24 leads), `/evals` trace selector & honest offline scoring (`602a30c`) → `pm/log/2026-11-21-label-signing-recall-eval.md`, `simon/vertex_eval.py`, `agents/discovery-scout/`
- 2026-11-21 · multi-agent vertex evals · merged PR #20 (runner, /evals UI, 65/65 tests) & 9-agent 3-layer rubrics baseline (119 rubrics) → `pm/log/2026-11-21-discovery-vertex-evals.md`, `simon/vertex_eval.py`, `data/evals/`
- 2026-11-21 · discovery dashboard ui · removed redundant section 3, expanded source selector with search/genres/chips/tray (PR #18) → `pm/log/2026-11-21-discovery-dashboard-ui.md`, `simon/discovery_ui.py`
- 2026-11-21 · agency studio ui remodel · remodeled `/` into 3-tab studio (Talent Review, Phase Runner, Agent Lab), unified theme & phase runner API (PR #16) → `pm/log/2026-11-21-agency-studio-ui.md`, `simon/static/`, `simon/phases.py`
- 2026-11-21 · reporting layer & two-stage ui · merged PRs #13/#14 (`AgentReport` v1.0.0, shared field-reporting/source-discovery skills, 2-stage UI) → `pm/log/2026-11-21-reporting-layer-two-stage-ui.md`, `data/agent_report_schema.json`, `agents/_shared/skills/`
- 2026-11-21 · staging fleet smoke test · verified 9/9 staging managed agents live via concurrent /api/fleet/run (0 failures) → `pm/log/2026-11-21-staging-fleet-smoke-test.md`
- 2026-11-21 · cloud run & firestore · merged PR #4 (`b2057e8`), deployed `simon-staging`, seeded 36 sources & live traces → `pm/log/2026-11-21-cloudrun-firestore-platform.md`, `simon/`, `data/`, `.agents/`
- 2026-11-21 · shared youtube skill · enabled YouTube Data API v3, synced `/v1beta/credentials` & wired skill into 5 agents (PR #11, 40/40) → `pm/log/2026-11-21-shared-youtube-skill.md`, `agents/_shared/skills/youtube/`, `tests/`
- 2026-11-21 · discovery agent & evals · upgraded Stage 1 discovery scout (PR #7), source registry seed & 37/37 evals → `agents/discovery-scout/`, `data/`, `notes/managed-agents/`, `tests/`
- 2026-11-21 · managed-agents deploy & ci · merged PR #2 (deploy CLI, fleet API, Actions CI) & live-deployed 5 staging agents → `pm/log/2026-11-21-managed-agents-deploy-ci.md`, `simon/`, `.github/`
