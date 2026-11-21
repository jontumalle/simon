---
name: simon-db
description: >-
  Shared Simon database tool for reading and writing schema-validated scouting leads,
  discovered sources, and investigator dossiers in Firestore (via Simon's Cloud Run API).
---

# `simon-db` — Shared Database Tool for Simon Managed Agents

Use `scripts/simon_db.py` (as a Python library or CLI) to pull prior scouting context and save contract-validated outputs when completing an assignment.

> Auth is injected automatically on the wire by Google's egress proxy (`credential: simon-db-token`) when calling `SIMON_DB_URL`. Never log or hardcode tokens.

## Allowed Collections & Required Fields
1. **`discovered_sources`** — Shared Source Discovery Log
   - Required: `url`, `source_channel`, `why_useful`
2. **`leads`** — Individual unranked `DiscoveryLead` records
   - Required: `lead_id`, `stage_name`, `seed_sources` (non-empty list of `{url, source_channel}`)
3. **`discovery_handoffs`** — Stage 1 `DiscoveryHandoff` batch
   - Required: `contract_version` (`"1.0.0"`), `run_id`, `search_brief`, `requested_count` (>=1), `leads`
4. **`investigator_dossiers`** — Stage 2 objective factual dossier (no ranking/scoring)
   - Required: `lead_id`, `stage_name`

## CLI Usage (Inside Sandbox)
```sh
# Pull shared sources before searching
python3 .agents/skills/simon-db/scripts/simon_db.py list discovered_sources --limit 25

# Pull leads waiting for investigation
python3 .agents/skills/simon-db/scripts/simon_db.py list leads --limit 20

# Fetch a single record by ID
python3 .agents/skills/simon-db/scripts/simon_db.py get leads lead_01

# Save a validated JSON file back to Firestore
python3 .agents/skills/simon-db/scripts/simon_db.py save discovery_handoffs @/workspace/out/handoff.json
python3 .agents/skills/simon-db/scripts/simon_db.py save investigator_dossiers @/workspace/out/dossier.json
```

## Python Library Usage (Inside Sandbox)
```python
import sys
sys.path.insert(0, ".agents/skills/simon-db/scripts")
from simon_db import SimonDB

db = SimonDB()
sources = db.list_docs("discovered_sources", limit=25)
db.save_doc("discovered_sources", {
    "url": "https://www.youtube.com/@SofarSounds",
    "source_channel": "youtube_live_session",
    "why_useful": "Live vocal sessions with clear artist attribution.",
})
```
