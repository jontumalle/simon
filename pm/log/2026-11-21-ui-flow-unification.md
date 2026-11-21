# 2026-11-21 — UI Drift, Discovery Sub-Flow & Plain-English Pass (PRs #30 & #31)

## What Happened
- **Discovery Sub-Flow Strip & Plain-English Pass (`b1ae6b8`, PR #31)**:
  - Added a persistent **Discovery Sub-Flow Strip** (`1. Sources & Dispatch -> 2. Field News -> 3. Scouting Reports | Next: Investigate ->`) across `/?tab=discovery`, `/discovery`, `/field-news`, and `/reports` with automatic `?batch=` query sync.
  - Applied `/plain-english` (STE-100 + Zinsser) rules to UI states, headers, phase descriptions, and Field News step copy across `simon/discovery_ui.py`, `simon/phases.py`, `simon/screening_ui.py`, `simon/taste_profile_ui.py`, and `simon/static/index.html`.
  - Added the `Plain-English Output Standard (STE-100 + Zinsser)` to `agents/_shared/skills/field-reporting/SKILL.md` and all 12 curated `agents/*/SYSTEM.md` prompts.
  - Verified **113/113** unit tests passing (`tests/test_agency_studio_ui.py`).
- **Unified 5-Stage Primary Navigation (`cc2154e`, PR #30)**:
  - Unified the 5-stage primary topbar across `/` (`simon/static/index.html`) and all standalone pages (`simon/discovery_ui.py`), adding the missing `Taste Profile` tab to `/` and removing duplicate `Pipeline Stepper` / `Agent Lab` links from the `/` Tools menu.
- **Discovery Parity & Stage-to-Stage Lead Handoffs**:
  - Brought `/?tab=discovery` to full parity with `/discovery`: added the `Start fresh (archive old runs)` toggle (`reset_previous`), `Clear Old Runs` (`POST /api/demo/reset`), `Next: Investigate Discovered Leads ->` (`/investigate?autorun=1`), and direct `Investigator Desk ->` links on lead cards.
  - Connected `/investigate` lead cards with stored dossiers directly to `/screen?lead=...` and preserved `?batch=` on Discovery Report links.
- **Studio Handoff & Pipeline Stepper Fixes (`simon/static/app.js`)**:
  - Fixed `/?tab=review&subtab=screened&lead=...` to focus and auto-cue the selected artist's clip.
  - Preserved the full Stage 3 screening packet (`screening_verdict`, `advocate_case`, `skeptic_case`, `judge_decision`, `human_review`) on Phase 4 Producer handoffs from both `/screen` and `Talent Review -> Screened & Elevated`.
  - Updated Pipeline Stepper to sync `?phase=` to the URL, refresh screening packets after `3_screening`, and surface post-run CTAs for Phases 1, 3, and 4.
- **Verification**:
  - Added cross-screen parity and handoff tests in `tests/test_agency_studio_ui.py` (**112/112** unit tests passing).
