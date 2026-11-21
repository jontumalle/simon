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

- 2026-11-21 · discovery vertex evals · 3-layer rubrics, canonical eval_runs schema & Vertex AI eval service integration → `pm/log/2026-11-21-discovery-vertex-evals.md`, `data/evals/`
- 2026-11-21 · label-signing recall eval · added 10-artist Option C recall benchmark (6 in-map, 4 out-of-map) & registered in data/README.md → `pm/log/2026-11-21-label-signing-recall-eval.md`, `data/evals/label_signing_recall_eval.json`
- 2026-11-21 · staging fleet smoke test · verified 9/9 staging managed agents live via concurrent /api/fleet/run (0 failures) → `pm/log/2026-11-21-staging-fleet-smoke-test.md`
- 2026-11-21 · cloud run & firestore · merged PR #4 (`b2057e8`), deployed `simon-staging`, seeded 36 sources & live traces → `pm/log/2026-11-21-cloudrun-firestore-platform.md`, `simon/`, `data/`, `.agents/`
- 2026-11-21 · shared youtube skill · enabled YouTube Data API v3, synced `/v1beta/credentials` & wired skill into 5 agents (PR #11, 40/40) → `pm/log/2026-11-21-shared-youtube-skill.md`, `agents/_shared/skills/youtube/`, `tests/`
- 2026-11-21 · discovery agent & evals · upgraded Stage 1 discovery scout (PR #7), source registry seed & 37/37 evals → `agents/discovery-scout/`, `data/`, `notes/managed-agents/`, `tests/`
- 2026-11-21 · managed-agents deploy & ci · merged PR #2 (deploy CLI, fleet API, Actions CI) & live-deployed 5 staging agents → `pm/log/2026-11-21-managed-agents-deploy-ci.md`, `simon/`, `.github/`
- 2026-11-21 · leadgen & investigator · aligned 2-stage music pipeline (Lead Gen + Generalist Investigator, objective data, 2-layer skills) → `pm/log/2026-11-21-leadgen-investigator-alignment.md`
- 2026-11-21 · governance charters · added top-level governance/ (main + feature-branch code flow, Intake/Decision/Outcome domains, safety) → `governance/`, `AGENTS.md`, `.agents/`
- 2026-11-21 · taste-brief youtube mvp · shipped & live-verified 3-unit YouTube vocal scout MVP (`run_881b5370`), SQLite & web studio → `simon/`, `agents/`, `notes/managed-agents/`, `pm/`
- 2026-11-21 · talent-agency pipeline · designed 4-stage agency data model, JSON schema & dossier research → `data/`, `notes/managed-agents/`, `ideas/`, `pm/`
- 2026-11-21 · plain-english skill · added on-command STE-100, Zinsser, Mermaid, and dialectic alignment skill → `.agents/skills/plain-english/`, `pm/`
