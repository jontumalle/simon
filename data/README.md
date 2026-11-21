# Data & Fixtures Guide (`data/`, `examples/`, `local/`)

Simon separates data into three clear locations so private artist info and large media never leak into git:

| Directory | Tracked in Git? | What Belongs Here |
| :--- | :---: | :--- |
| **`data/`** | Yes | JSON schemas (e.g., manifest & agent report schemas), rubric definitions, anonymized evaluation benchmarks |
| **`examples/`** | Yes | Small, fictional or explicitly public sample fixtures (`examples/showcase.json`) used by `python3 -m simon` |
| **`local/`** | **No** (`.gitignore`) | Real artist submissions, `.mp3`/`.wav` audio files, artist contact details, raw meeting transcripts (`local/transcript.md`), and live run outputs |

## Canonical Schemas in `data/`
- **[discovery_investigator_contract.json](./discovery_investigator_contract.json)** — Active Stage 1 (Kevin · Discovery) → Stage 2 (JT · Scout Investigator) boundary contract: unranked lead handoff + 22 feasible, objective factual datapoints and process trace (zero ranking/scoring).
- **[source_registry_schema.json](./source_registry_schema.json)** — Queryable `source_registry` data model for discovery sources (`location`, `source_channel`, `source_type`, `career_tier`, `access_method`, `status`), extending `SourceDiscoveryEntry` so agents can pull sources from the DB and append newly discovered ones.
- **[talent_profile_schema.json](./talent_profile_schema.json)** — Full 4-stage Agentic Talent Agency JSON Schema (`Stage1BasicProfile` → `Stage2MediaDigestion` → `Stage3ScoutEnrichment` → `Stage4TasteAssessment` + `EnrichmentTask`).
- **[mvp_contracts.json](./mvp_contracts.json)** — Vertical-slice v0 input/output contracts for the Taste-Brief YouTube Vocal Scout MVP.

## Reference Data (`data/reference/` — Database Seeds)
Versioned, non-sensitive reference datasets used to seed Simon's database tables for agent tools:
- **[reference/discovery_sources_seed.json](./reference/discovery_sources_seed.json)** — Curated music discovery source registry (36 sources across all 9 `source_channel` values, tagged by `location`, `source_type`, `career_tier`, `access_method`, and `status`). Seed directly into the `source_registry` table once the DB is up.

## Evaluation Benchmarks (`data/evals/`)
- **[evals/discovery_eval_cases.json](./evals/discovery_eval_cases.json)** — Offline golden eval cases for Stage 1 discovery (`url_hygiene`, `attribution_accuracy`, `dedup_and_grouping`, `contract_validity`, `second_take_coverage`).
