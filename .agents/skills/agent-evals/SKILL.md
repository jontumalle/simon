---
name: agent-evals
description: >-
  Repeatable runbook and interactive walkthrough for designing 3-layer rubrics,
  setting up golden datasets, running offline or Vertex AI Gen AI Evaluation
  Service checks on any specific Simon Managed Agent, storing results in
  data/evals/ and Firestore eval_runs, and checking regressions on live runs.
  Activate whenever creating rubrics, onboarding a new agent to evals, running
  agent evaluations, or auditing live-run regressions.
---

# Agent Evals & Rubrics (`agent-evals`)

Use this skill to design rubrics, set up eval files, run offline or **Vertex AI Gen AI Evaluation Service** checks on any Simon agent (`agents/<agent>/`), and compare live runs for regressions.

---

## 1. Simon Eval Defaults (Do Not Re-Ask Unless Overriding)

| Setting | Default Value |
| :--- | :--- |
| **GCP Project** | `gemini4nyc26nyc-2203` |
| **GCP Region** | `us-east1` |
| **Vertex AI Judge** | Vertex AI Gen AI Evaluation Service (`vertexai.evaluation.EvalTask` + `PointwiseMetric`) |
| **Platform Staging URL** | `https://simon-staging-139550420825.us-east1.run.app` |
| **Platform Evals UI** | `/evals` (backed by `/api/eval-runs` and `/api/evals/rubrics`) |
| **Rubric Pattern** | 3-Layer: **Layer 1** Hard Code Gates (100% blocking) -> **Layer 2** Process & Skill Trajectory (`0_to_2`, target >= 75%) -> **Layer 3** Vertex AI Quality & Safety (`pass_fail` / `1_to_5`, target >= 80%) |
| **Reference Agent** | `discovery-scout` ([discovery_rubrics.json](../../../data/evals/discovery_rubrics.json)) |

---

## 2. Where Everything Is Stored

Keep eval definitions, live scorecards, and local scratch files in their designated buckets:

| Artifact | Location | Tracked in Git? | Purpose |
| :--- | :--- | :---: | :--- |
| **Rubric Specs** | `data/evals/<agent>_rubrics.json` | Yes (Track A) | Canonical 3-layer rubrics & Vertex AI pointwise judge templates for one agent |
| **Golden Eval Cases** | `data/evals/<agent>_eval_cases.json` | Yes (Track A) | Offline deterministic fixtures & edge cases for CI |
| **Rubric Starter Template** | `data/evals/agent_rubrics_template.json` | Yes (Track A) | Copy-and-fill scaffold when onboarding a new agent |
| **Eval Run Schema** | `data/evals/eval_run_schema.json` | Yes (Track A) | Canonical `SimonEvalRun` schema for platform storage |
| **Live Scorecards** | Firestore `eval_runs` / SQLite `agent_documents` | No (DB) | Displayed on `/evals`; written via `POST /api/eval-runs` or `--save-local` |
| **Local Snapshots** | `local/evals/<agent>-<date>.json` | No (gitignored) | Ad-hoc local JSON reports & diffing |
| **Vertex AI Experiments** | GCP Vertex AI (`simon-<agent>-eval-YYYYMMDD`) | No (GCP) | Longitudinal charts & judge rationales in Cloud Console |
| **CI Workflows** | `.github/workflows/eval-<agent>-vertex.yml` | Yes (Track B) | Automated PR gates + nightly Vertex AI runs |

---

## 3. Walkthrough A · Set Up Rubrics & Evals for a Specific Agent

When the user asks to set up evals for `<agent>` (e.g., `discovery-scout`, `identity-resolver`, `footprint-profiler`, `signal-forensics`, `track-record-mapper`, `performance-critic`, `booking-critic`, `synthesis-scout`, `showcase-producer`):

1. **Inspect the agent's contract, process, and skills:**
   - Read `agents/<agent>/agent.yaml` (check `shared_skills`, `tools`, `model`).
   - Read `agents/<agent>/SYSTEM.md` (extract Core Invariants, step-by-step process, and Final Output Contract).
   - Read every skill listed under `agents/<agent>/skills/` and `agents/_shared/skills/<skill>/SKILL.md`.
2. **Draft the 3-layer rubric file (`data/evals/<agent>_rubrics.json`):**
   - Start from [agent_rubrics_template.json](../../../data/evals/agent_rubrics_template.json) (or clone [discovery_rubrics.json](../../../data/evals/discovery_rubrics.json)).
   - **Layer 1 (`layer_1_code_gates`, blocking 100%):** Map every hard invariant that code can check (JSON schema, required fields, URL hygiene, zero forbidden telemetry keys in `agent_reports`, no ranking words if Stage 1/2).
   - **Layer 2 (`layer_2_process_skills`, `0_to_2`):** Add 1 rubric per attached skill (`simon-db`, `youtube`, `field-reporting`, `source-discovery`, domain skill) checking whether the agent used the skill in the right order and respected quotas/rules.
   - **Layer 3 (`layer_3_quality_safety`, `pass_fail` or `1_to_5`):** Add Vertex AI `vertex_prompt_template` rubrics for grounding/anti-hallucination, objectivity, brief alignment, and prompt-injection resistance.
3. **Create offline golden cases (`data/evals/<agent>_eval_cases.json`):**
   - Include at least 3 clean pass cases and 3 edge/failure cases (malformed output, ambiguous attribution, prompt-injection trap, or forbidden ranking language).
4. **Confirm alignment with the user:**
   - Show the drafted rubric table (ID, Layer, Skill, Scale, Pass Criteria) and ask if any criteria or thresholds should change before saving.

---

## 4. Walkthrough B · Run Evals on a Specific Agent

Guide the user through running evals step by step:

### Step 1 · Run Fast Offline Gates (Zero Cost, Local or CI)
```sh
# Discovery Scout example (default)
python3 tests/eval_discovery.py
python3 -m simon.vertex_eval \
  --mode offline \
  --sample-source mixed \
  --save-local \
  --out local/evals/discovery-offline-latest.json \
  --fail-on-gate
```

### Step 2 · Run Live Vertex AI Gen AI Evaluation Service
Verify prerequisites once:
- `pip install "google-cloud-aiplatform[evaluation]" pandas`
- `gcloud auth application-default login` (or `GCP_SA_KEY` / WIF in GitHub Actions)
- `aiplatform.googleapis.com` enabled on `gemini4nyc26nyc-2203` with `roles/aiplatform.user`

Run against live `agent_reports` and push the scorecard to the platform:
```sh
python3 -m simon.vertex_eval \
  --mode vertex \
  --project gemini4nyc26nyc-2203 \
  --region us-east1 \
  --sample-source live_reports \
  --save-local \
  --push-url https://simon-staging-139550420825.us-east1.run.app \
  --out local/evals/discovery-vertex-latest.json \
  --fail-on-gate
```

### Step 3 · Inspect on the Platform (`/evals`)
- Local preview: `python3 -m simon serve --port 8765` -> open `http://127.0.0.1:8765/evals`.
- Staging: open `https://simon-staging-139550420825.us-east1.run.app/evals`.
- You can also trigger runs directly from `/evals` using **Run Eval Now**.

---

## 5. Walkthrough C · Check Regressions on Live Runs

Follow this 4-step loop whenever editing `SYSTEM.md`, a skill, or a model config:

1. **Capture Baseline:** Run a live batch in `/discovery` (or target stage), then run `--mode vertex --sample-source live_reports` and note the baseline `eval_run_id` and per-rubric scores.
2. **Apply Change & Re-Run Live:** Update the prompt/skill, dispatch the same brief on `/discovery`, and run `--mode vertex --sample-source live_reports` again.
3. **Compare for Regressions:**
   - **Hard Gate Failure:** Any drop below 100% on Layer 1 blocks merge (`--fail-on-gate` exits `1`).
   - **Rubric Score Drop:** Compare the new card against the previous card on `/evals` and inspect per-case Vertex AI rationales for which skill or invariant regressed.
   - **Longitudinal Trend:** Click **Open in Vertex AI Console →** on any Vertex eval card to view experiment trends across commits.
4. **Decide:** Keep the change only if Layer 1 is 100% and no Layer 2/3 rubric regressed without an intentional trade-off.

---

## 6. Git Sync Rules (Track A vs. Track B)

- **Rubric JSONs, Golden Cases & This Skill (`data/evals/**`, `.agents/skills/agent-evals/**`):** Track A docs/data sync straight to `main`:
  ```sh
  python3 .agents/scripts/sync_main.py --docs-only -m "docs(evals): add rubrics for <agent>"
  ```
- **Eval Runner Code, Platform UI & GitHub Actions (`simon/**`, `tests/**`, `.github/workflows/**`):** Track B feature-branch PR via `main-sync --code`.
