# 2026-11-21 — Stage 3 Screening Fleet, Taste Profile & Clean Staging Demo Flow

## What Happened
- **Stage 3 Screening Fleet, Input Skills & Taste Engine (`6e7a1f2` PR #24, `92251bf` PR #26)**:
  - Merged `decision/screening-layer` adding 3 curated Stage 3 Managed Agents (`agents/screen-advocate/`, `agents/screen-skeptic/`, `agents/screening-judge/`, all running `gemini-4-carbon`) plus 5 shared dossier-scoring skills under `agents/_shared/skills/` (`dossier-identity`, `dossier-media`, `dossier-footprint`, `dossier-audience`, `dossier-track-record`).
  - Added `data/screening_contract.json`, `data/evals/screening_rubrics.json` (wired into `simon/vertex_eval.py`), and `examples/screening_demo.json`.
  - Built `/screen` (`7. Screening Deck`, `simon/screening_ui.py` + `simon/screening.py` + `simon/web.py`) as a non-swiping, 1-card-at-a-time profile report displaying Advocate Pros vs. Skeptic Cons, 5 input-skill rubric bars, human-in-the-loop `Elevate / Watch / Pass` decisions with structured override reasons, DSPy `compile_judging_model()`, and live 0-output-token `gemini-decision-1` scoring via `POST /api/screening/taste-score`.
- **Taste Profile Screen & Unified 4-Stage Studio Flow (`2899a28` PR #27, `83a0866` PR #28, `f75d51f` PR #29)**:
  - Added `/taste-profile` (`8. Taste Profile`, `simon/taste_profile_ui.py`) presenting *1. Where We Are*, *2. What We Care About* (including the *"What You Taught Us"* HITL override learning box), and *3. Our Methodology*.
  - Added `simon/demo_flow.py` with `POST /api/demo/reset` (archiving stale pipeline runs across all 6 collections without deleting reference/audit data), `POST /api/investigate/run`, and a checked-by-default `"Start fresh"` toggle on `/discovery`.
  - Unified 4-stage Studio navigation, URL state, and stage-to-stage handoffs (`simon/discovery_ui.py`, `simon/phases.py`, `simon/static/app.js`), replacing legacy Phase 3B critics with Active Screening and grounding `agents/showcase-producer` in Screening Packets.
- **Live Cloud Run & `/v1beta/agents` Deployment + Clean 4-Artist Verification**:
  - Deployed live to Cloud Run (`https://simon-staging-139550420825.us-east1.run.app`) and synced `/v1beta/agents` (`staging-simon-screen-advocate`, `staging-simon-screen-skeptic`, `staging-simon-screening-judge` bundled with all 5 `dossier-*` shared skills).
  - Archived **96 stale staging records** via `/api/demo/reset` and verified a clean 4-artist end-to-end flow live on staging.
