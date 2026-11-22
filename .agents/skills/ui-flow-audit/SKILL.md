---
name: ui-flow-audit
description: >-
  Standard workflow for auditing and fixing Simon's Web Studio UI (simon/static/, simon/web.py,
  simon/discovery_ui.py, simon/screening.py): management-facing Plain-English copy pass, explicit
  client/server state-machine verification, cross-screen flow consistency, and Python unittest UI
  regression verification without node. Activate whenever reviewing UI drift, copy clarity,
  navigation flows, or frontend state bugs.
---

# Simon UI Flow, Copy & State-Machine Audit

## 1. Scope & Files
Simon's UI is served directly by Python (`simon/web.py`, `simon/discovery_ui.py`, `simon/static/`). There is **no `node` / npm build step** in this workspace.

Key surfaces to inspect together when auditing cross-screen consistency:
- Navigation & stage framing: `simon/static/` + `simon/web.py`
- Stage 1 Discovery & Sources: `simon/discovery_ui.py`
- Stage 2 Investigation & Reports: `simon/web.py` / `simon/phases.py`
- Stage 3 Screening & Taste Profile: `simon/screening.py` / `simon/static/`
- Evals Dashboard: `/evals` routes in `simon/web.py`

---

## 2. Three-Point Audit Checklist
1. **Management-Facing Plain-English Copy** (pair with `.agents/rules/plain-english.md`):
   - Replace raw internal keys (`snake_case` field names, agent slugs, schema jargon, HTTP codes) with plain A&R / management labels.
   - Keep button labels action-first and concise.
2. **Explicit State Machines (No Implicit UI Flags)**:
   - Every async view (Discovery run, Investigation, Screening deck, Eval run) must model explicit states (`idle`, `loading`/`running`, `ready`/`success`, `empty`, `error`) so spinners, buttons, and empty-states never collide.
   - Confirm route transitions preserve active context (selected preset, lead ID, stage tab).
3. **Cross-Screen Flow Unification**:
   - Verify the 5-stage navigation bar, stage numbers, and CTAs (`Discovery → Investigate → Screen → Taste Profile → Evals`) use identical terminology across every template.

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
