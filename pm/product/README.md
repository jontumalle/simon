# Simon Product, UI & Feature Truth (`pm/product/`)

This folder holds the single source of truth for Simon's product behavior, UI architecture, user stories, wireframes, and feature lifecycle.

Every human teammate (Kevin and JT) and every coding agent reads this folder before changing routes, screens, or user-facing features.

---

## Bucket Index

| File | Purpose | Primary Owner | Update Trigger |
| :--- | :--- | :--- | :--- |
| **[README.md](./README.md)** | Bucket map, version contract, and locked terminology | `Project Manager (Steward)` | When product lifecycle rules or terms change |
| **[ui-strategy.md](./ui-strategy.md)** | SPA vs. SSR diagnosis, canonical 5-stage spine, layout/copy rules, state machines, and trade-off decisions | `Project Manager (Steward)` | When routes, navigation, layout shell, or state contracts change |
| **[features.md](./features.md)** | Versioned registry of all features (`FEAT-01`–`FEAT-22`) with PR provenance, contracts, and drift | `Project Manager (Steward)` | Every feature add, change, proposal, or retirement |
| **[user-stories.md](./user-stories.md)** | Persona stories and acceptance criteria mapped to routes and PRs | `Project Manager (Steward)` | When user flows or acceptance criteria change |
| **[wireframes.md](./wireframes.md)** | Screen-to-screen Mermaid flow, URL handoffs, and ASCII wireframes for all 8 routes | `Project Manager (Steward)` | When page zones, cards, controls, or URL params change |

---

## Steward Version-Maintenance Contract

`Project Manager (Steward)` owns this folder as part of its standard documentation sync (`--docs-only` to `origin/main`). We do **not** add a separate technical-writer subagent because one Steward already distills session logs, decisions, and `pm/current.md`. Splitting product truth from Steward would re-introduce doc drift across parallel chats.

### Feature Version Lifecycle

Every entry in `features.md`, `user-stories.md`, and `wireframes.md` carries an explicit version and lifecycle status:

| Tag | Meaning | Required Steward Action |
| :--- | :--- | :--- |
| **`v1.0`** | First shipped release of a feature or screen | Add entry to `features.md`, map stories in `user-stories.md`, add route wireframe in `wireframes.md`. |
| **`v1.x`** | Incremental change to an active feature (new filter, copy pass, model swap, bug fix) | Update the existing entry in place and append one line to its `Version History`. |
| **`v2.0`** | Major remodel of layout, data contract, or primary user flow | Replace current-state description in place, record prior behavior in `Version History`, and update `wireframes.md`. |
| **`Proposed`** | Requested in chat or triage, not yet merged on `main` | Record scope, source chat/PR, and target wave under `Proposed / Backlog`. |
| **`Split-UI`** | Feature exists in both SPA and SSR with divergent behavior | Flag exact missing controls on each surface until consolidation lands. |
| **`Retired`** | Removed from active UI or pipeline (for example, PR #33 MVP removal) | Move out of active sections into `Retired`, list remaining dead code, and remove from `pm/current.md` `Next Up`. |

### Pre-Code Spec Check & Engineer Delta Handoff

1. **Before writing UI or feature code:** Engineers (`simon-feature-engineer` or teammates) read `ui-strategy.md`, `wireframes.md`, and `features.md`. Confirm which shell owns the route before editing `simon/static/` or `simon/*_ui.py`.
2. **After merging a feature PR:** Report one delta line per touched feature to Steward using this format:
   `FEAT-XX: v1.1 -> v1.2 | PR #NN | Summary of user-visible change or retirement`
3. **On every Steward run:** Steward updates `pm/product/*.md` in place, prunes resolved or retired items from `pm/current.md` (keeping it under 120 lines), and syncs via `python3 .agents/scripts/sync_main.py --docs-only`.

---

## Locked Terminology (One Term Per Concept)

Use the canonical term in UI copy, specs, wireframes, and agent outputs. Never mix legacy or internal terms in user-facing surfaces.

| Canonical Term | Do Not Use | Scope |
| :--- | :--- | :--- |
| **Discovery** (`1. Discovery`) | `Scouting`, `Discovery Dashboard` (as primary tab) | Stage 1 source selection, presets, Source Hunter, and scout dispatch |
| **Field News** | `Traces`, `Live Telemetry` | Stage 1 live scout activity feed (`/field-news`, alias `/traces`) |
| **Scouting Reports** | `AgentReport v1.0.0`, `Raw Reports` | Stage 1 stored lead reports (`/reports`) |
| **Investigate** (`2. Investigate`) | `Forensics Desk`, `Phase 2` (in primary UI) | Stage 2 4-agent lead verification and unranked dossiers (`/investigate`) |
| **Screening** (`3. Screening`) | `Shortlist`, `Phase 3B`, `Evaluation Deck` | Stage 3 Advocate/Skeptic/Judge single-card review (`/screen`) |
| **Taste Profile** (`4. Taste Profile`) | `policy_v*`, `DSPy Model`, `Decision Policy` | Stage 4 learned agency priorities and override log (`/taste-profile`) |
| **Talent Review** (`5. Talent Review`) | `Vocal Studio`, `Top-3 Shortlist` | Stage 5 play-first video verification of elevated artists (`/?tab=review`) |
| **Moment Verifier** | `Video Widget`, `Clip Box` | Embedded YouTube player with clickable proof moments |
| **Pipeline Runner** | `Phase Stepper` (outside `Tools ▾`) | 6-phase manual orchestrator (`/?tab=pipeline`) |
| **Agent Lab** | `Eval Sandbox` | Interactive single-agent JSON prompt runner (`/?tab=lab`) |
| **Agent Evals** | `Offline Harness` | 3-layer rubric and Vertex AI scorecard runner (`/evals`) |
| **Candidate** / **Artist** | `lead_id`, `subject_entity`, `record` | Management-facing name for a scouted vocalist |
| **Screened & Elevated** | `ELEVATE_PACKETS`, `Top 3` | Artists promoted by Stage 3 screening or human override |
| **Quality Check** | `0-output-token`, `dspy.BootstrapFewShot`, `P(elevate)` | Plain-English label for automated rubric or taste checks |
