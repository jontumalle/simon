# 2026-11-21 — Legacy MVP Shortlist & Brief Removal (PR #33)

## What Happened
- **Removed Legacy MVP Shortlist UI & Brief Drawer (`f80a6f5`, PR #33)**:
  - Stripped the outdated MVP top-3 shortlist cards, legacy shortlist render paths, and the "New Brief" drawer from `simon/static/index.html` and `simon/static/app.js`.
  - Talent Review (`/`) now defaults directly to the **Screened & Elevated** subtab (`?subtab=screened`), presenting live Stage 3 Screening Deck outputs instead of legacy SQLite shortlist cards.
  - Preserved the All Scouted Leads subtab (`?subtab=all`) and sticky YouTube Moment Verifier player for audio/video evidence verification.
- **Removed Legacy `agents/synthesis-scout/` Package**:
  - Deleted the legacy v0 synthesis agent definition (`agents/synthesis-scout/agent.json`, `agent.yaml`, `SYSTEM.md`, `README.md`) and removed its entry in `agents/README.md`.
  - Replaced by Stage 3 Screening Fleet (`screen-advocate`, `screen-skeptic`, `screening-judge`) and Stage 4 Outcome (`showcase-producer`).
- **Cleaned Up Phase Stepper Aliases (`simon/phases.py`)**:
  - Removed legacy `3_shortlist` alias and `synthesis-scout` fallback dispatch.
  - Standardized on canonical `3_screening` (`Phase 3: Critics & Screening Deck`) driving Stage 3 Screening packets into Phase 4 Producer synthesis.
- **Verification**:
  - Updated `tests/test_agency_studio_ui.py` to assert direct default to Screened & Elevated candidates.
  - Verified all **113/113 unit tests** passing (`Ran 113 tests in 1.487s, OK`).
  - Verified all **37/37 offline discovery evaluations** passing.
