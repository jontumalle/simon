# Session Log — Multi-Agent 3-Layer Rubrics & Vertex AI Evaluation (PR #20)

*Date: 2026-11-21*

## Objective
Establish continuous quality, safety, and trajectory evaluation for Simon's entire 9-agent Managed Agent fleet using a 3-layer rubric architecture, canonical eval run schema, offline baseline runner, Vertex AI Gen AI Evaluation Service integration, and a unified `/evals` UI dashboard.

## Knowledge Model & Eval Assets (`data/evals/`, `.agents/skills/`)

### 1. Reusable Rubric Framework & Agent Evals Skill (`.agents/skills/agent-evals/`, `3a86c76`)
- **Skill Runbook (`.agents/skills/agent-evals/SKILL.md`)**: Repeatable methodology for designing 3-layer rubrics, setting up golden datasets, running offline or Vertex AI Gen AI Evaluation Service checks on any specific Simon Managed Agent, storing results in `data/evals/` and Firestore `eval_runs`, and auditing regressions on live runs.
- **Canonical Rubric Template (`data/evals/agent_rubrics_template.json`)**: Reusable schema definition for Layer 1 Hard Code Gates, Layer 2 Process & Skill Trajectory, and Layer 3 Vertex AI Quality & Safety.

### 2. Fleet-Wide 3-Layer Rubrics & Golden Cases (`8ea3ef4`)
Complete 3-layer rubrics and golden evaluation cases across all **9 Simon Managed Agents** (119 rubrics total, with 9/9 agents passing Layer 1 hard gates):
1. `discovery-scout`: `discovery_rubrics.json` + `discovery_eval_cases.json`
2. `identity-resolver`: `identity-resolver_rubrics.json` + `identity-resolver_eval_cases.json`
3. `footprint-profiler`: `footprint-profiler_rubrics.json` + `footprint-profiler_eval_cases.json`
4. `signal-forensics`: `signal-forensics_rubrics.json` + `signal-forensics_eval_cases.json`
5. `track-record-mapper`: `track-record-mapper_rubrics.json` + `track-record-mapper_eval_cases.json`
6. `synthesis-scout`: `synthesis-scout_rubrics.json` + `synthesis-scout_eval_cases.json`
7. `performance-critic`: `performance-critic_rubrics.json` + `performance-critic_eval_cases.json`
8. `booking-critic`: `booking-critic_rubrics.json` + `booking-critic_eval_cases.json`
9. `showcase-producer`: `showcase-producer_rubrics.json` + `showcase-producer_eval_cases.json`

Each agent spec covers:
- **Layer 1 · Hard Code Gates (Deterministic / Blocking)**: Strict schema conformity (e.g. `DiscoveryHandoff`, `AgentReport`), sandbox script execution, URL hygiene (canonical YouTube URLs, zero dead links/SoundCloud audio feeds), and zero telemetry/system instruction leakage.
- **Layer 2 · Process & Skill Trajectory (Rule-Based & Tool Trajectory)**: Skill coverage (`simon-db`, `source-discovery`, `youtube`, `music`, `field-reporting`), database-first queries before web search, batch video fetches, and strict abstention from subjective ranking.
- **Layer 3 · Vertex AI Quality & Safety (LLM-as-Judge)**: Grounding against source metadata, clinical non-promotional objectivity, factual scouting density, and stage-appropriate abstention.

### 3. Canonical Eval Run Schema (`data/evals/eval_run_schema.json`)
- Defines canonical Draft 2020-12 schema for `eval_runs` collection stored in Firestore Native / SQLite and rendered on `/evals`.
- Tracks `eval_run_id`, `agent_id`, `rubric_set_id`, `runner` (`vertex_ai` | `offline_baseline` | `hybrid_vertex_offline`), `status`, `overall_score`, `passed_gates`, layer/dimension scorecards, and metadata.

### 4. Eval Documentation (`data/evals/README.md`)
- Detailed usage instructions for multi-agent offline baseline execution (`python3 -m simon.vertex_eval --mode offline [--agent <id>]`), live GCP Vertex AI Evaluation (`--mode vertex`), and CI/CD automation.

## Runtime, Control Plane & UI (PR #20 Merged at `f81c258`)
Merged into `main` via PR #20 (`feat/vertex-agent-evals`):
- **Multi-Agent Eval Runner (`simon/vertex_eval.py`)**: Dual-mode runner (offline golden dataset evaluation + live Vertex AI Gen AI Evaluation Service judge via `vertexai.preview.evaluation`), markdown scorecard generator, and push client supporting all 9 Simon agents.
- **Persistence (`simon/db_tools.py`)**: Registered `eval_runs` in `ALLOWED_AGENT_COLLECTIONS`.
- **Evals UI Dashboard (`simon/discovery_ui.py`, `simon/web.py`)**:
  - Added `6. Evals` tab to shared studio navigation bar at `/evals`.
  - Agent selector dropdown across all 9 Simon Managed Agents.
  - "Run All Agents Baseline" batch trigger button.
  - Real-time scorecard inspector, layer breakdown tables, regression deltas, and Vertex AI Console deep links.
  - API endpoints: `GET /evals`, `GET /api/evals/rubrics`, `GET/POST /api/eval-runs`, and `POST /api/eval-runs/run`.
- **CI/CD (`.github/workflows/eval-discovery-vertex.yml`)**: GitHub Actions workflow for offline PR regression checks and nightly Vertex AI evaluation runs.
- **Verification (`tests/test_vertex_evals.py`)**: Unit tests covering runner modes, score aggregation, schema conformity, and UI endpoints. Full test suite passes **65/65 tests** (`Ran 65 tests in 0.617s, OK`).
