# Current State — Simon

*Updated: 2026-11-21*

## Live Now
- **Taste-Brief YouTube Vocal Scout MVP & Scouting Studio Live (`318e9e8`)**:
  - **CLI & Web Studio**: `python3 -m simon scout` and `python3 -m simon serve --port 8765` (Scouting Studio with embedded timestamped YouTube Moment Verifier player, Play-First shortlist cards `<= 3` singers, Managed Agent trace inspector, and SQLite evidence viewer) live alongside backward-compatible `python3 -m simon` showcase mode; 10 test suites passing (`test_mvp_scout.py`, `test_smoke.py`, `test_auto_approve_hook.py`).
  - **3-Unit Architecture & Contracts ([data/mvp_contracts.json](../data/mvp_contracts.json))**: (1) Zero-signup `YouTubeConnector` (`simon/youtube.py`, oEmbed verification + `uncertain` attribution flags) + `simon-discovery-scout` + direct `gemini-4-hydrogen` timestamped video evaluation (`live | studio | unclear`), (2) Thin-Evidence Second-Take Loop + `simon-synthesis-scout` shortlist synthesis (`simon/scout.py`, `simon/gemini.py`), and (3) 5-table normalized SQLite store (`local/simon.db` via `simon/store.py`: `scout_runs`, `artist_leads`, `clip_evidence`, `clip_observations`, `artist_assessments`) with oEmbed-verified demo fixture [examples/taste_brief_demo.json](../examples/taste_brief_demo.json).
  - **Team Workstream Alignment (Wispr Flow)**: Jonathan shipped the 3-unit scouting MVP, contracts, and human verification UI; Kevin is building the minimal Managed Agent factory, CI checks, and GitHub Actions deployment loop against those stage contracts.
- **Dual-Track `main-sync`, Cross-Window Steward & Auto-Approval Active**:
  - [AGENTS.md](../AGENTS.md) and [main-sync/SKILL.md](../.agents/skills/main-sync/SKILL.md) enforce strict separation between **Track A · Docs & Knowledge Sync (`--docs-only`)** (used by `Project Manager (Steward)`, auto-approved for both doc file writes and direct `origin/main` sync while leaving dirty `simon/` or `tests/` code untouched) and **Track B · Code Sync (`--code --paths <files...>`)** (enforcing pre-commit `unittest` + `python -m simon` smoke + `ruff check --select E9,F`, explicit slice staging, and optional `--branch feat/<slug>` + PR; `--skip-verify` and unscoped `--all` stay gated).
  - [.agents/hooks.json](../.agents/hooks.json) runs `SessionStart` (`session_start.py`), `PreToolUse` (`auto_approve_toolchain.py` — auto-approves safe `RESOURCES.md` toolchain commands, Steward doc writes, and verified syncs while gating destructive/token-exfiltrating/unverified commands), and `Stop` (`stop_doc_sync.py`); `.gitignore` and `sync_main.py` block `.pytest_cache/` and `.ruff_cache/`.
- **Local macOS (`arm64`) Toolchain Ready**:
  - Installed: `uv 0.13.9`, `Python 3.12.16`, `gcloud 594.0.0`, `gemini-api 0.5.0`, `gh 2.105.0`, plus `.venv` (`google-genai 3.6.1`, `dspy 3.5.0`, `pydantic 2.14.4`, `pyyaml 6.0.4`, `pytest 9.2.0`, `ruff 0.17.6`).
  - Antigravity plugins & MCP servers active: `gemini-api` (`antigravity-plugins-official/plugin/gemini-api`), `wispr-flow`, and global `excalidraw` MCP App (`https://mcp.excalidraw.com/mcp`, documented in [RESOURCES.md](../RESOURCES.md)).
- **Managed Agents Fleet, Playbooks & Trigger Architecture**:
  - Curated specs in [agents/](../agents/README.md): `discovery-scout`, `synthesis-scout`, `performance-critic`, `booking-critic`, and `showcase-producer` (`SIMON_DISCOVERY_AGENT` & `SIMON_SYNTHESIS_AGENT` documented in [RESOURCES.md](../RESOURCES.md)).
  - Core sandbox playbook in [notes/managed-agents/playbook.md](../notes/managed-agents/playbook.md) and workforce packaging / deploy / webhook trigger blueprint in [notes/managed-agents/deployment-and-triggers.md](../notes/managed-agents/deployment-and-triggers.md).
- **Part 1 Operational Triage Prototype Verified (DSPy 3.5 + Gemini Decisions API)**:
  - Verified `client.decisions.create(model="gemini-decision-1")` (`NoulQuestion`, `ChoiceQuestion`, `ScoreQuestion`) + `dspy.BootstrapFewShot` (`rubric_v1`) prototype and `dspy.Module.deepcopy()` client-isolation rule in [pm/log/2026-11-21-dspy-decisions-and-excalidraw.md](./log/2026-11-21-dspy-decisions-and-excalidraw.md).

## Next Up
1. Integrate Kevin's **Minimal Agent Factory, CI checks & GitHub Actions deployment pipeline** (`simon agents sync` / `/v1beta/agents` reconciliation) with the 3-unit contracts in [data/mvp_contracts.json](../data/mvp_contracts.json) and curated specs (`discovery-scout`, `synthesis-scout`, critics, producer).
2. Run live end-to-end scouting passes (`GEMINI_API_KEY` + deployed `SIMON_DISCOVERY_AGENT` / `SIMON_SYNTHESIS_AGENT`) in `python3 -m simon serve --port 8765` to capture real *First Listen NYC* shortlists and verify timestamped YouTube playback + Thin-Evidence second-take traces for the hackathon demo.
3. Wire optional calibrated Decisions API + DSPy rubric triage (`gemini-decision-1`) or async webhook/cron triggers (`notes/managed-agents/deployment-and-triggers.md`) into the scouting loop as needed.

## Blockers / Open Items
- **Bucket Placement Question (Setup-Stage Guardrail)**: Confirm owner preference on whether standalone DSPy + Gemini Decisions API engineering playbooks/diagrams should live under `notes/` (e.g., alongside `notes/managed-agents/`) or `ideas/`.
