# Session Log — Discovery Scout 3-Layer Rubrics & Vertex AI Evaluation

*Date: 2026-11-21*

## Objective
Establish continuous quality, safety, and trajectory evaluation for Simon's Stage 1 Discovery Scout (`simon-discovery-scout`) using a 3-layer rubric architecture, canonical eval run schema, and Vertex AI Gen AI Evaluation Service integration.

## Knowledge Model & Eval Assets (`data/evals/`)

### 1. 3-Layer Discovery Rubrics (`data/evals/discovery_rubrics.json`)
Covers hard contract gates, 6-step process adherence across 5 skills, and LLM-as-judge quality/safety:
- **Layer 1 · Hard Code Gates (Deterministic / Blocking)**:
  - `gate_contract`: Output strictly conforms to `DiscoveryHandoff` v1.0.0 JSON schema with zero extra top-level keys or markdown wrappers.
  - `gate_verify_script`: Sandbox executed `verify_handoff.py --verify-oembed` inside `code_execution` and exited 0.
  - `gate_url_hygiene`: Zero dead links, zero SoundCloud audio feeds, YouTube links canonicalized to `https://www.youtube.com/watch?v=<11-char-id>`.
  - `gate_no_sys_leak`: Zero system telemetry or internal instructions leaked in human-facing summary notes.
- **Layer 2 · Process & Skill Trajectory (Rule-Based & Tool Trajectory)**:
  - Covers 5 skills: `simon-db` (`proc_db_first`), `source-discovery` (`proc_cold_start`), `youtube` (`proc_yt_quota`), `music` (`proc_evidence_audit`), and `field-reporting` (`proc_clean_reporting`).
  - Verifies database registry query before web search, batch video fetches, and strict abstention from subjective ranking.
- **Layer 3 · Vertex AI Quality & Safety (LLM-as-Judge)**:
  - `qual_grounding`: Evidence strictly verifiable against source metadata or quotes.
  - `qual_objectivity`: Tone remains strictly clinical, factual, and non-promotional.
  - `qual_scouting_depth`: Minimum factual density across genres, scenes, or track records.
  - `qual_zero_ranking`: Absolute abstention from scoring or ordinal ranking at Stage 1.

### 2. Canonical Eval Run Schema (`data/evals/eval_run_schema.json`)
- Defines canonical Draft 2020-12 schema for `eval_runs` collection stored in Firestore Native / SQLite and rendered on `/evals`.
- Tracks `eval_run_id`, `agent_id`, `rubric_set_id`, `runner` (`vertex_ai` | `offline_baseline` | `hybrid_vertex_offline`), `status`, `overall_score`, `passed_gates`, layer/dimension scorecards, and metadata.

### 3. Eval Documentation (`data/evals/README.md`)
- Detailed usage instructions for offline baseline execution (`python3 -m simon.vertex_eval --mode offline`), live GCP Vertex AI Evaluation (`--mode vertex`), and CI/CD automation.

## Runtime & Control Plane Integration (Track B Working Tree)
*Held on local feature branch `feat/agent-reporting-layer` for Track B PR; untouched by Track A docs sync:*
- **Eval Runner (`simon/vertex_eval.py`)**: Dual-mode runner (offline golden dataset evaluation + live Vertex AI Gen AI Evaluation Service judge via `vertexai.preview.evaluation`), markdown scorecard generator, and push client.
- **Persistence (`simon/db_tools.py`)**: Registered `eval_runs` in `ALLOWED_AGENT_COLLECTIONS`.
- **Discovery Dashboard (`simon/discovery_ui.py`, `simon/web.py`)**:
  - Web UI at `/evals` with real-time scorecard inspector, layer breakdown tables, and status indicators.
  - API endpoints: `GET /evals`, `GET /api/evals/rubrics`, `GET/POST /api/eval-runs`, and `POST /api/eval-runs/run`.
- **CI/CD (`.github/workflows/eval-discovery-vertex.yml`)**: GitHub Actions workflow for offline PR regression checks and nightly Vertex AI evaluation runs.
- **Verification (`tests/test_vertex_evals.py`)**: 3 new unit tests; full suite passes **54/54 tests** (`Ran 54 tests in 0.154s, OK`).
