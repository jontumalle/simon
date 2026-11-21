---
name: seed-reference-data
description: Repeatable process for updating Simon's curated reference data in data/reference/ and seeding it idempotently into Firestore (Cloud Run) and local SQLite. Activate whenever discovery sources or other reference data files under data/reference/ change.
---

# Seed Reference Data (`data/reference/` -> Simon DB)

Use this skill whenever you add, edit, or retire reference records under `data/reference/` (starting with `data/reference/discovery_sources_seed.json`) and need to sync them into Simon's database.

## 1. Validate Before Seeding
1. Confirm every record in `data/reference/discovery_sources_seed.json` conforms to `data/source_registry_schema.json`:
   - Unique snake_case `source_id` (`^[a-z0-9_]+$`)
   - Valid `source_channel` enum matching `data/discovery_investigator_contract.json`
   - Required fields present (`source_id`, `name`, `url`, `source_channel`, `source_type`, `location`, `genre_tags`, `career_tier`, `access_method`, `why_useful`, `discovered_by`, `status`)
2. Run unit tests to verify seed parsing and store upsert logic:
   ```sh
   python3 -m unittest discover -s tests
   ```

## 2. Seed the Target Database (Idempotent Upsert)
Because `source_id` is the primary key, seeding is safe to re-run at any time.

### Option A — Seed Live Cloud Run / Firestore via API (Recommended)
```sh
curl -sS -X POST https://simon-staging-139550420825.us-east1.run.app/api/sources/seed
```

### Option B — Seed Firestore Directly via CLI (Requires `gcloud auth application-default login` or Cloud Run IAM)
```sh
SIMON_STORE_BACKEND=firestore GOOGLE_CLOUD_PROJECT=gemini4nyc26nyc-2203 \
  python3 -m simon seed
```

### Option C — Seed Local SQLite (`local/simon.db`)
```sh
python3 -m simon seed
```

*(Pass `--file <path>` to seed an alternate JSON file.)*

## 3. Verify Seeded Records
Check the live count and sample filter query:
```sh
curl -sS "https://simon-staging-139550420825.us-east1.run.app/api/sources?city=New+York&status=active" | python3 -m json.tool | head -n 40
```

## 4. Sync Reference Data Changes to Git
Reference data JSON files under `data/reference/` are Track A knowledge/data files (`AGENTS.md`):
```sh
python3 .agents/scripts/sync_main.py --docs-only -m "docs(data): update discovery sources reference data"
```
