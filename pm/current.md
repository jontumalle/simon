# Current State — Simon

*Updated: 2026-11-21*

## Live Now
- **Starter Pipeline & Tests Passing**: `python3 -m simon` demo pipeline and `tests/` suite (`test_smoke.py` + expanded 6-method `test_auto_approve_hook.py` under Python 3.9+) passing; GitHub `origin/main` push sync (`jontumalle/simon`) live.
- **Dual-Track `main-sync`, Cross-Window Steward & Auto-Approval Active**:
  - [AGENTS.md](../AGENTS.md) and [main-sync/SKILL.md](../.agents/skills/main-sync/SKILL.md) enforce strict separation between **Track A · Docs & Knowledge Sync (`--docs-only`)** (used by `Project Manager (Steward)`, auto-approved for both doc file writes and direct `origin/main` sync while leaving dirty `simon/` or `tests/` code untouched) and **Track B · Code Sync (`--code --paths <files...>`)** (enforcing pre-commit `unittest` + `python -m simon` smoke + `ruff check --select E9,F`, explicit slice staging, and optional `--branch feat/<slug>` + PR; `--skip-verify` and unscoped `--all` stay gated).
  - [.agents/hooks.json](../.agents/hooks.json) runs `SessionStart` (`session_start.py`), `PreToolUse` (`auto_approve_toolchain.py` — auto-approves safe `RESOURCES.md` toolchain commands, Steward doc writes, and verified syncs while gating destructive/token-exfiltrating/unverified commands), and `Stop` (`stop_doc_sync.py`); `.gitignore` and `sync_main.py` block `.pytest_cache/` and `.ruff_cache/`.
- **Local macOS (`arm64`) Toolchain Ready**:
  - Installed: `uv 0.13.9`, `Python 3.12.16`, `gcloud 594.0.0`, `gemini-api 0.5.0`, `gh 2.105.0`, plus `.venv` (`google-genai 3.6.1`, `pydantic 2.14.4`, `pyyaml 6.0.4`, `pytest 9.2.0`, `ruff 0.17.6`).
  - Antigravity plugins & MCP servers active: `gemini-api` (`antigravity-plugins-official/plugin/gemini-api`), `wispr-flow`, and global `excalidraw` MCP App (`https://mcp.excalidraw.com/mcp`, documented in [RESOURCES.md](../RESOURCES.md)).
- **Managed Agents Playbook & Seeded Blueprints**:
  - Playbook in [notes/managed-agents/playbook.md](../notes/managed-agents/playbook.md); curated specs in [agents/](../agents/README.md) (`performance-critic`, `booking-critic`, `showcase-producer`).
- **Audition Classifier Research (DSPy + Gemini Decisions API)**:
  - Researched 2-phase compile + inference architecture pairing DSPy (`Signatures`, `Modules`, `MIPROv2` / `BootstrapFewShot` compiled JSON rubrics) with `v1beta` `client.decisions.create` (`gemini-decision-1` calibrated `noul` / `choice` / `score` judgments at 0 output tokens); distilled in [pm/log/2026-11-21-dspy-decisions-and-excalidraw.md](./log/2026-11-21-dspy-decisions-and-excalidraw.md).

## Next Up
1. Run `gcloud auth login && gcloud auth application-default login` in terminal (optional unless mounting GCS buckets) and export `GEMINI_API_KEY` + `SIMON_AGENT_PREFIX="kevin-"`.
2. Implement `simon` agent sync & runtime orchestration against `/v1beta/agents`, `/v1beta/environments`, and `/v1beta/interactions`.

## Blockers / Open Items
- **Bucket Placement Question (Setup-Stage Guardrail)**: Confirm owner preference on whether standalone DSPy + Gemini Decisions API engineering playbooks/diagrams should live under `notes/` (e.g., alongside `notes/managed-agents/`) or `ideas/`.
