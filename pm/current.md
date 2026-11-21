# Current State — Simon

*Updated: 2026-11-21*

## Live Now
- **Starter Pipeline & Tests Passing**: `python3 -m simon` demo pipeline and `tests/` suite (`test_smoke.py` + 34-case `test_auto_approve_hook.py` under Python 3.9+) passing.
- **Continuous `main` Sync, Cross-Window Steward & Toolchain Auto-Approval Active**:
  - [AGENTS.md](../AGENTS.md) enforces zero-repercussion direct `main` pushing for all Markdown/knowledge files, frequent `main` sync, and launching a background `Project Manager (Steward)` subagent across every chat window.
  - [.agents/scripts/sync_main.py](../.agents/scripts/sync_main.py) + [main-sync/SKILL.md](../.agents/skills/main-sync/SKILL.md) handle safe `--docs-only` / `--all` staging, `git pull --rebase --autostash origin main`, and `git push origin main`.
  - [.agents/hooks.json](../.agents/hooks.json) runs `SessionStart` (`session_start.py`), `PreToolUse` (`auto_approve_toolchain.py` — auto-approves safe `RESOURCES.md` toolchain commands while gating destructive/token-exfiltrating/untrusted commands), and `Stop` (`stop_doc_sync.py` — catches uncommitted docs before turn end); documented in Section 6 of [RESOURCES.md](../RESOURCES.md).
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
