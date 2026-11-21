# Current State — Simon

*Updated: 2026-11-21*

## Live Now
- **Starter Pipeline Working**: `python3 -m simon` runs the deterministic demo (`examples/showcase.json`), and `python3 -m simon --live local/showcase.json` runs `gemini-4-hydrogen` audio listening + 3 `antigravity-preview-09-2026` Managed Agent calls (`performance`, `booking`, `producer`).
- **Repo Governance Scaffolded**: Life OS-inspired layout (`PROJECT.md`, `AGENTS.md`, `RESOURCES.md`, `pm/`, `notes/managed-agents/`, `agents/`, `ideas/`, `data/`, `tests/`, `.agents/`).
- **Toolchain & Research In Flight**:
  - Installing Python 3.12 (`uv`) + Google Cloud CLI (`gcloud`) on local macOS (`arm64`) and preparing OAuth login.
  - Completing deep-dive playbook on Gemini Managed Agents (`v1beta/agents`, repo-mounted `base_environment`, `Files API`, `Credentials API`, background execution) to populate `notes/managed-agents/` and `agents/`.

## Next Up
1. Complete `gcloud auth login` once `gcloud` + Python 3.12 finishes installing.
2. Land the Managed Agents engineering playbook in `notes/managed-agents/` and finalize the declarative agent spec format in `agents/`.
3. Curate our first deployable Managed Agents in `agents/` (`audio-scout`, `performance-critic`, `booking-critic`, `producer`) and wire deployment/invocation into `simon/`.
4. Gather opt-in pilot clips/sources into `local/` and add unit + rubric tests in `tests/`.

## Blockers / Open Items
- Confirm `GEMINI_API_KEY` (Tier 3 / hackathon credits mentioned in kickoff) is exported locally for live Managed Agent registration and test runs.
- Add Wispr Flow plugin in Antigravity if pulling voice notes directly into `pm/inbox/`.
