# Simon Evals (`data/evals/`)

Canonical directory for Simon's evaluation rubrics, golden datasets, and eval-run schemas.

## Files

| File | Purpose |
| :--- | :--- |
| [discovery_rubrics.json](./discovery_rubrics.json) | 3-layer rubrics for `simon-discovery-scout` (Layer 1 Hard Code Gates, Layer 2 Process & Skill Trajectory, Layer 3 Vertex AI Quality & Safety). |
| [discovery_eval_cases.json](./discovery_eval_cases.json) | Offline golden test cases (attribution, URL hygiene, noise filtering, deduplication, second-take loop). |
| [eval_run_schema.json](./eval_run_schema.json) | Canonical JSON Schema for `eval_runs` stored in Firestore/SQLite and shown on `/evals`. |

## Running Evals

### 1. Offline Baseline (Zero API Cost, CI-Safe)
```sh
python3 -m simon.vertex_eval --mode offline --save-local
```

### 2. Vertex AI Gen AI Evaluation Service (Live GCP Judge)
Requires `google-cloud-aiplatform[evaluation]` (or `vertexai`) and GCP credentials with `roles/aiplatform.user` on `gemini4nyc26nyc-2203`:
```sh
python3 -m simon.vertex_eval \
  --mode vertex \
  --project gemini4nyc26nyc-2203 \
  --region us-east1 \
  --sample-source live_reports \
  --push-url https://simon-staging-139550420825.us-east1.run.app
```

### 3. GitHub Actions Workflow
See [.github/workflows/eval-discovery-vertex.yml](../../.github/workflows/eval-discovery-vertex.yml):
- Runs offline gates on PRs touching `agents/discovery-scout/**`, `agents/_shared/skills/**`, or `data/evals/**`.
- Runs Vertex AI Gen AI Evaluation Service on `main`, nightly cron, or manual `workflow_dispatch`, then pushes the scorecard to `POST /api/eval-runs` so it appears on the Discovery Dashboard at **`/evals`**.
