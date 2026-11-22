---
name: ui-flow-audit
description: >-
  Standard workflow for pre-checking pm/product/ route ownership and auditing or fixing Simon's Web
  Studio UI (simon/static/, simon/web.py, simon/discovery_ui.py, simon/screening_ui.py,
  simon/taste_profile_ui.py): pre-code spec check, management-facing Plain-English copy pass,
  explicit 5-state verification, cross-screen flow consistency, Python unittest verification without
  node, and Steward FEAT-XX delta handoff. Activate before editing UI or reviewing UI drift.
---

# Simon UI Flow, Spec Ownership & State-Machine Audit

## 0. Mandatory Pre-Code Spec Check (`pm/product/`)
Before editing **any** UI file (`simon/static/*`, `simon/*_ui.py`, `simon/web.py`, `simon/phases.py`, `simon/demo_flow.py`), read:
1. [pm/product/README.md](../../../pm/product/README.md) — Locked STE-100 terminology and `FEAT-XX` lifecycle tags.
2. [pm/product/ui-strategy.md](../../../pm/product/ui-strategy.md) — Canonical 5-stage spine, SPA vs. SSR route ownership, 5-state contract, and URL handoff rules.
3. [pm/product/wireframes.md](../../../pm/product/wireframes.md) & [pm/product/features.md](../../../pm/product/features.md) — Exact page zones, controls, and active `FEAT-01`–`FEAT-22` specs.

**Hard Route-Ownership Gate:** Confirm whether the target screen belongs to Python SSR (`simon/*_ui.py`) or the `/` SPA (`simon/static/`). Never ship a feature onto one shell while leaving a competing duplicate surface stale; if consolidating a route, delete or redirect the superseded surface in the same PR.

---

## 1. Scope & Files
Simon's UI is served directly by Python (`simon/web.py`, `simon/discovery_ui.py`, `simon/screening_ui.py`, `simon/taste_profile_ui.py`, `simon/static/`). There is **no `node` / npm build step** in this workspace.

Key surfaces to inspect together when auditing cross-screen consistency:
- Shared `56px` sticky topbar (`1320px` width) & `Tools ▾` popover: `simon/discovery_ui.py` + `simon/static/`
- Stage 1 Discovery, Field News & Scouting Reports: `simon/discovery_ui.py` (`/discovery`, `/field-news`, `/reports`)
- Stage 2 Investigate: `simon/discovery_ui.py` (`/investigate`) + `simon/demo_flow.py`
- Stage 3 Screening & Stage 4 Taste Profile: `simon/screening_ui.py` (`/screen`), `simon/taste_profile_ui.py` (`/taste-profile`), `simon/screening.py`
- Stage 5 Talent Review, Pipeline Runner & Agent Lab: `simon/static/{index.html,app.js,app.css}` + `simon/phases.py`
- Agent Evals: `simon/discovery_ui.py` (`/evals`) + `simon/vertex_eval.py`

---

## 2. Four-Point Audit Checklist
1. **Management-Facing Plain-English Copy** (pair with `.agents/rules/plain-english.md` + `pm/product/README.md` Locked Terminology):
   - Replace raw internal keys (`snake_case` field names, `policy_v*`, `0-output-token`, `dspy`, `lead_id`, `interaction_id`, agent slugs, schema versions) with locked A&R labels (`Taste Profile`, `Quality Check`, `Artist`, `Scout Run`, `5. Talent Review`).
   - Keep sentences under 25 words and button labels action-first.
2. **Explicit 5-State Machines & Continuous Playback Invariant**:
   - Every async surface must model explicit states (`idle`, `running`, `ready`, `empty`, `error` using `--warn` / `.pill.warn`, never undefined `--bad`).
   - **Continuous Playback Invariant**: Verdict clicks, override typing, and filter toggles on `/screen` or `/?tab=review` must update targeted DOM nodes without unmounting or reloading the active YouTube Moment Verifier iframe.
   - Remove dead DOM IDs and unpopulated drawers whenever retiring features.
3. **Cross-Screen Flow & URL Handoff Unification**:
   - Confirm all 8 routes render the identical `56px` sticky topbar (`1. Discovery`, `2. Investigate`, `3. Screening`, `4. Taste Profile`, `5. Talent Review` + `Tools ▾`).
   - Confirm URL parameters (`?tab=`, `?subtab=`, `?phase=`, `?batch=`, `?report=`, `?lead=`, `?subject=`, `?packet=`, `?filter=`, `?autorun=1`) use `pushState` on page/tab transitions, `replaceState` on filter/selection updates, and restore cleanly on `popstate`.
4. **Steward Feature-Version Delta Handoff**:
   - Record every user-visible feature or wireframe change as a structured delta line for `Project Manager (Steward)`:
     `FEAT-XX: v1.1 -> v1.2 | PR #NN | Summary of user-visible change or retirement`

---

## 3. Verification (Python `unittest`, Never `node`)
Resolve `.venv` safely (works in both main checkout and `Workspace: "share"` worktrees):

```bash
MAIN_REPO="$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')"
PY="${MAIN_REPO}/.venv/bin/python"
RUFF="${MAIN_REPO}/.venv/bin/ruff"

"$RUFF" check --fix simon/ tests/
"$PY" -m unittest \
  tests/test_agency_studio_ui.py \
  tests/test_discovery_ui.py \
  tests/test_screening_ui.py \
  tests/test_taste_profile_ui.py
```

Before opening a PR (`sync_main.py --code`), run the full suite:
```bash
"$PY" -m unittest discover -s tests -p "test_*.py"
```
