# Data & Fixtures Guide (`data/`, `examples/`, `local/`)

Simon separates data into three clear locations so private artist info and large media never leak into git:

| Directory | Tracked in Git? | What Belongs Here |
| :--- | :---: | :--- |
| **`data/`** | Yes | JSON schemas (e.g., manifest & agent report schemas), rubric definitions, anonymized evaluation benchmarks |
| **`examples/`** | Yes | Small, fictional or explicitly public sample fixtures (`examples/showcase.json`) used by `python3 -m simon` |
| **`local/`** | **No** (`.gitignore`) | Real artist submissions, `.mp3`/`.wav` audio files, artist contact details, raw meeting transcripts (`local/transcript.md`), and live run outputs |

## Canonical Schemas in `data/`
- **[discovery_investigator_contract.json](./discovery_investigator_contract.json)** — Active Stage 1 (Kevin · Discovery) → Stage 2 (JT · Scout Investigator) boundary contract: unranked lead handoff + 22 feasible, objective factual datapoints and process trace (zero ranking/scoring).
- **[screening_contract.json](./screening_contract.json)** — Stage 2 (`InvestigatorDossier`) → Stage 3 (`ScreeningPacket` v1.0.0, `ScreeningLabel`, `JudgingModelPolicy`, `ScreeningBatch`) adversarial screening & DSPy / `gemini-decision-1` calibration contract (paired with `examples/screening_demo.json`).
- **[agent_report_schema.json](./agent_report_schema.json)** — Human-first Field News & Scouting Report contract (`stage` in `discovery | investigator | critic | synthesis | screening | custom`, zero telemetry IDs).
- **[source_registry_schema.json](./source_registry_schema.json)** — Queryable `source_registry` data model for discovery sources (`location`, `source_channel`, `source_type`, `career_tier`, `access_method`, `status`), extending `SourceDiscoveryEntry` so agents can pull sources from the DB and append newly discovered ones.
- **[talent_profile_schema.json](./talent_profile_schema.json)** — Full 4-stage Agentic Talent Agency JSON Schema (`Stage1BasicProfile` → `Stage2MediaDigestion` → `Stage3ScoutEnrichment` → `Stage4TasteAssessment` + `EnrichmentTask`).
- **[mvp_contracts.json](./mvp_contracts.json)** — Vertical-slice v0 input/output contracts for the Taste-Brief YouTube Vocal Scout MVP.

## Reference Data (`data/reference/` — Database Seeds)
Versioned, non-sensitive reference datasets used to seed Simon's database tables for agent tools:
- **[reference/discovery_sources_seed.json](./reference/discovery_sources_seed.json)** — Curated music discovery source registry (36 sources across all 9 `source_channel` values, tagged by `location`, `source_type`, `career_tier`, `access_method`, and `status`). Seed directly into the `source_registry` table once the DB is up.

## Evaluation Benchmarks & Rubrics (`data/evals/`)
- **[evals/README.md](./evals/README.md)** — Guide for running offline baseline and live Vertex AI Gen AI Evaluation Service runs.
- **[evals/discovery_rubrics.json](./evals/discovery_rubrics.json)** — 3-layer evaluation rubrics for `simon-discovery-scout` (Layer 1 Hard Code Gates, Layer 2 Process & Skill Trajectory covering `simon-db`, `music`, `youtube`, `source-discovery`, and `field-reporting`, Layer 3 Vertex AI Quality & Safety).
- **[evals/screening_rubrics.json](./evals/screening_rubrics.json)** — 3-layer evaluation rubrics for Stage 3 `gemini-4-neon` screening (`dossier-identity`, `dossier-media`, `dossier-footprint`, `dossier-audience`, `dossier-track-record`, missing-field abstention, and Advocate/Skeptic/Judge calibration).
- **[evals/eval_run_schema.json](./eval_run_schema.json)** — Canonical JSON Schema for `eval_runs` stored in Firestore/SQLite and rendered on `/evals`.
- **[evals/discovery_eval_cases.json](./evals/discovery_eval_cases.json)** — Offline golden eval cases for Stage 1 discovery (`url_hygiene`, `attribution_accuracy`, `dedup_and_grouping`, `contract_validity`, `second_take_coverage`).
- **[evals/label_signing_recall_eval.json](./evals/label_signing_recall_eval.json)** — Option C two-bucket recall benchmark of 10 real 2025–2026 record-label signings (200–100k YouTube subs & <100k Spotify monthly listeners): 6 in-map NYC/session signings + 4 out-of-map cold-discovery signings.
