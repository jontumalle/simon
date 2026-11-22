# Current State — Simon

*Updated: 2026-11-21 · Concise live snapshot (`<120 lines`). Living product specs, wireframes & `FEAT-01`–`FEAT-22` live in [pm/product/](./product/README.md); historical PR details live in [pm/log/](./log/).*

## Live Now (`origin/main` through PR `#35`, Cloud Run `simon-staging`)

- **Staging Platform & Persistence (`FEAT-14`, `FEAT-15`)**:
  - Public Cloud Run service live at `https://simon-staging-139550420825.us-east1.run.app` (`simon-staging-00017-4rx`, GCP `gemini4nyc26nyc-2203`) backed by Firestore Native `(default)` + local SQLite fallback (`simon/store.py`, `simon/firestore_store.py`) and Bearer-authenticated `/api/db/*` gateway (`13` collections, PII & telemetry scrubbing).
  - Zero-dependency deployer & fleet dispatcher (`simon/deploy.py`, `simon/fleet.py`) with zero-trust `/v1beta/credentials` (`SIMON_AGENT_DB_TOKEN`, `YOUTUBE_API_KEY`) and 9 shared skills under `agents/_shared/skills/`.
- **Deployed Managed Agent Fleet (`agents/`, 9 JSON+YAML Remote Agents + Stage 4 Producer)**:
  - **Stage 0 · Source Expansion (`FEAT-02`)**: `source-hunter` (`gemini-4-hydrogen`, `64k`) with live `/v1beta/triggers` daily `9:00 AM ET` cron (`e0afa4e1-4464-42c8-bd0c-bcdc9c4e58b1`), `.github/workflows/daily-source-hunter.yml`, and on-demand `POST /api/sources/hunt`.
  - **Stage 1 · Discovery (`FEAT-01`, `FEAT-03`, `FEAT-04`)**: `discovery-scout` (`gemini-4-hydrogen`, `192k`) scouting **42 curated sources across 8 US regions** (NYC, Nashville, Atlanta, Austin, Chicago, New Orleans, LA, Seattle) into sanitized `Field News` (`/field-news`) and `Scouting Reports` (`/reports`).
  - **Stage 2 · Investigation (`FEAT-05`)**: `identity-resolver` → parallel `footprint-profiler`, `signal-forensics`, and `track-record-mapper` (`gemini-4-argon`, `64k`, zero-ranking unranked dossiers on `/investigate`).
  - **Stage 3 · Adversarial Screening & Taste Profile (`FEAT-07`, `FEAT-08`, `FEAT-09`)**: Parallel `screen-advocate` + `screen-skeptic` (`gemini-4-carbon`, `64k`) → `screening-judge` (`gemini-4-neon`, `64k`) + 5 `dossier-*` skills, paired with `DSPy` `compile_judging_model()` (`2x` weight on human overrides) and 0-output-token `gemini-decision-1` scoring on `/screen` and `/taste-profile`.
  - **Stage 4 · Showcase Producer (`FEAT-12`)**: `showcase-producer` (`gemini-4-carbon`) drafting `pending_human_review` showcase callbacks from active Screening Packets via `/?tab=pipeline&phase=4_producer`.
- **5-Stage Studio UI, Plain-English Copy & Active `Split-UI` State (`FEAT-03`, `FEAT-06`, `FEAT-10`–`FEAT-13`)**:
  - Unified `56px` sticky topbar (`1320px` width, Editorial Light / Studio Dark theme) across all 8 routes (`1. Discovery` → `2. Investigate` → `3. Screening` → `4. Taste Profile` → `5. Talent Review` + `Tools ▾`: `Pipeline Runner`, `Agent Lab`, `Agent Evals`), overhauled to management-facing STE-100 copy (PRs `#30–#34`).
  - Legacy MVP Top-3 shortlist UI, New Brief drawer, `agents/synthesis-scout/`, and Phase 3B critics retired in PRs `#29` & `#33` (`FEAT-18`, `FEAT-19`); `/?tab=review` defaults directly to `Screened & Elevated` with the sticky YouTube Moment Verifier.
  - **Known `Split-UI` (`FEAT-03` / `FEAT-20`)**: PR `#35` shipped `★ American Idol · Nationwide Search`, `⚡ Run Full Pipeline Cascade`, 8-card Source Explorer, and `🔍 Find New Sources` toast on SSR `/discovery`, while primary tab `1. Discovery` still links to SPA `/?tab=discovery` (tracked for consolidation in Wave 1).
- **Evals, Verification & Version-Aware Governance (`FEAT-16`, `FEAT-17`)**:
  - **117/117** Python `unittest` checks passing (`3.0s`), **132** 3-layer rubrics across `data/evals/`, trace-targeted `/evals` dashboard with honest offline gating, and 10-artist label-signing recall benchmark (`25%` cold out-of-map recall on `Ami Taf Ra`).
  - Canonical product & UI specs established in [pm/product/](./product/README.md) (`README.md`, `ui-strategy.md`, `features.md`, `user-stories.md`, `wireframes.md`), maintained in place by Version-Aware `simon-steward` + Pre-Code Spec Check in `ui-flow-audit` and `simon-feature-engineer`.

## Next Up (Sequenced Execution Waves — see [pm/product/ui-strategy.md](./product/ui-strategy.md))

1. **Wave 1 · UI Consolidation & Demo Cohesion (`FEAT-20`)**:
   - Point primary topbar tab `1. Discovery` to SSR `/discovery`, port `Recent Runs` + `Discovered Artists` from `/?tab=discovery`, and retire the duplicate SPA Discovery tab.
   - Fix `/screen` YouTube iframe reload on verdict pill clicks (Continuous Playback Invariant), fix `/evals` `--bad` → `--warn` CSS variables, remove dead SPA drawers/DOM IDs (`#profileDrawer`, `#traceDrawer`, `5. Vocal Studio` label), and merge or close open PR `#1`.
2. **Wave 2 · Live Vertex AI Eval Proof & Play-First Precision (`FEAT-21`, `FEAT-22`)**:
   - Run live `--mode vertex` LLM judge scorecards via Workload Identity Federation or local ADC, add dedicated rubrics for `source-hunter`, `screen-advocate`, and `screen-skeptic` (pruning retired agent rubrics), audit the 6 in-map NYC signings for recall, and restore `@ MM:SS` clickable vocal moment chips.
3. **Wave 3 · Post-Demo Calibration & Legacy Quarantine Cleanup (`FEAT-22`)**:
   - Run offline DSPy `MIPROv2` training on 20–50 labeled auditions and retire legacy `simon/scout.py` / `POST /api/scout` once `tests/test_mvp_scout.py` callers migrate.

## Blockers / Open Items
- **UI Consolidation Sign-Off (`pm/product/ui-strategy.md`)**: Confirm Kevin & JT alignment on **Decisions 1–3 (Option A)** to execute Wave 1 (`FEAT-20`).
- **GitHub Actions Vertex Auth (`eval-discovery-vertex.yml`)**: GCP org policy `constraints/iam.disableServiceAccountKeyCreation` blocks static `GCP_SA_KEY` creation; requires Workload Identity Federation or local `gcloud auth application-default login` to execute `--mode vertex`.
- **Open PR `#1` (`feat/enforce-feature-branches`)**: Unmerged since initial setup; reconcile with current `.agents/scripts/sync_main.py` and merge or close.
