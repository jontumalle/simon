# 2026-11-21 — UI Drift, Discovery Sub-Flow & Plain-English Overhaul (PRs #30, #31 & #32)

## What Happened
- **Management-Facing Plain-English UI Copy Overhaul (`76cf37f`, PR #32 — 6-agent swarm)**:
  - **`/taste-profile` (`simon/taste_profile_ui.py`)**: Replaced `policy_v*`, `0-output-token gemini-decision-1`, `dspy.BootstrapFewShot`, `questions_config`, `demos[]`, `screening_labels`, `human_override`, `simon-*`, `pros[]/cons[]/missing_fields`, and snake_case reviewer/metric keys with plain A&R management copy and display formatters.
  - **`/screen` (`simon/screening_ui.py`)**: Replaced `DSPy`, `gemini-decision-1 · 0 tok`, `P(elevate)`, `questions_config`, `gemini-4-neon`, `policy_v1`, and raw `lead_id:` labels with management-facing buttons, pills, and formatters.
  - **`/discovery`, `/field-news`, `/reports`, `/investigate`, `/evals` (`simon/discovery_ui.py`)**: Replaced `simon-discovery-scout`, `stage=investigator`, `DiscoveryHandoff v1.0.0`, raw `lead_id:` lines, and snake_case fields with readable Title Case.
  - **Agency Studio `/` & Pipeline Stepper (`simon/static/index.html`, `simon/static/app.js`, `simon/phases.py`)**: Replaced `simon-discovery-scout`, raw `lead_id:` / `interaction_id:` / `phase_run_id`, and `DiscoveryHandoff v1.0.0 Valid` with plain English.
  - **Verification**: **113/113** unit tests passing.
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
