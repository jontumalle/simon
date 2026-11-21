# Session Log — Cloud Run + Firestore Platform Deploy & Control Plane

*Date: 2026-11-21*

## What Shipped
- **PR #4 Merged (`feat/cloudrun-firestore-cicd` → `main` at `b2057e8`)**:
  - **Firestore Store & Factory (`simon/firestore_store.py`, `simon/store.py`)**: Added `FirestoreStore` and `create_store()` supporting `SIMON_STORE_BACKEND=firestore` (Cloud Run) and local SQLite.
  - **Agent Run Schema, Registry & Seeding (`data/agent_run_schema.json`, `simon/registry.py`, `simon/__main__.py`)**: Added `python3 -m simon seed` CLI plus `/api/sources`, `/api/sources/seed`, and `/api/agent-runs` endpoints.
  - **Platform Control Plane UI (`simon/web.py`)**: Added Agent Runs & Traces inspector and Source Registry table to the Web Studio UI.
  - **Agent DB Gateway (`simon/db_tools.py`)**: Added `source_registry` and `agent_runs` to `ALLOWED_AGENT_COLLECTIONS`.
  - **Container & CI/CD (`Dockerfile`, `requirements.txt`, `cloudbuild.yaml`, `.github/workflows/deploy-platform.yml`)**: Automated Cloud Run builds and deployments.
  - **Repeatable Seeding Skill (`.agents/skills/seed-reference-data/SKILL.md`)**: Documented idempotent validation and seeding of `data/reference/` into Firestore and local SQLite.

## GCP Provisioning & Live Verification
- Provisioned GCP project `gemini4nyc26nyc-2203` (`us-east1`): Firestore Native DB `(default)` (`freeTier: true`), Artifact Registry repo `simon`, and Secret Manager secret `GEMINI_API_KEY` bound to the Cloud Run compute service account.
- Live-deployed `simon-staging` at `https://simon-staging-139550420825.us-east1.run.app` via `cloudbuild.yaml`.
- Seeded all **36 curated music sources** from `data/reference/discovery_sources_seed.json` into live Firestore `source_registry`.
- Verified live `agent_runs` trace writes in Firestore (`run_e61f31bf39` / `arun_c393ecb80c`).
