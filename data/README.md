# Data & Fixtures Guide (`data/`, `examples/`, `local/`)

Simon separates data into three clear locations so private artist info and large media never leak into git:

| Directory | Tracked in Git? | What Belongs Here |
| :--- | :---: | :--- |
| **`data/`** | Yes | JSON schemas (e.g., manifest & agent report schemas), rubric definitions, anonymized evaluation benchmarks |
| **`examples/`** | Yes | Small, fictional or explicitly public sample fixtures (`examples/showcase.json`) used by `python3 -m simon` |
| **`local/`** | **No** (`.gitignore`) | Real artist submissions, `.mp3`/`.wav` audio files, artist contact details, raw meeting transcripts (`local/transcript.md`), and live run outputs |

## Canonical Schemas in `data/`
- **[discovery_investigator_contract.json](./discovery_investigator_contract.json)** — Active Stage 1 (Kevin · Discovery) → Stage 2 (JT · Scout Investigator) boundary contract: unranked lead handoff + 22 feasible, objective factual datapoints and process trace (zero ranking/scoring).
- **[talent_profile_schema.json](./talent_profile_schema.json)** — Full 4-stage Agentic Talent Agency JSON Schema (`Stage1BasicProfile` → `Stage2MediaDigestion` → `Stage3ScoutEnrichment` → `Stage4TasteAssessment` + `EnrichmentTask`).
- **[mvp_contracts.json](./mvp_contracts.json)** — Vertical-slice v0 input/output contracts for the Taste-Brief YouTube Vocal Scout MVP.
