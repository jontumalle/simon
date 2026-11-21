# 2026-11-21 — Kickoff Ideation & Repo Knowledge Model Setup

## What Happened
- **Kickoff Discussion Distilled (`local/transcript.md`)**:
  - Aligned on **Simon** as an AI-driven talent-scouting and live-showcase system ("America's next talent scout") starting with vocalists (*First Listen NYC*).
  - Evaluated and ruled out forced Shopify/merch/dropshipping concepts so the team stays laser-focused on the **Managed Agents ($5,000)** track and Tier 3 / hackathon API credits.
  - Defined the core **Critic / Validator** multi-agent architecture and noted that the same scouting graph can generalize to regional scenes (e.g., Hudson County) and multimodal sources (YouTube, SoundCloud, Instagram, direct submissions).
- **Repository Governance Scaffolded**:
  - Created `PROJECT.md`, `AGENTS.md`, `RESOURCES.md`, `pm/`, `notes/managed-agents/`, `agents/`, `ideas/`, `data/`, `tests/`, and `.agents/` skills/hooks.
  - Launched background agents to (1) install `uv` + Python 3.12 + `gcloud` CLI on macOS `arm64`, and (2) produce the comprehensive Gemini Managed Agents ("agent as a repo") engineering playbook.
- **Continuous `main` Sync, Hooks & Full Toolchain Completed**:
  - Installed `uv 0.13.9`, `Python 3.12.16`, `gcloud 594.0.0`, `gemini-api 0.5.0`, and `.venv` (`google-genai 3.6.1`, `pydantic`, `pyyaml`, `pytest`, `ruff`); enabled `gemini-api` and `wispr-flow` Antigravity plugins.
  - Built `.agents/scripts/sync_main.py`, `.agents/scripts/stop_doc_sync.py` (`Stop` hook), upgraded `.agents/scripts/session_start.py` (`SessionStart` hook), added `.agents/skills/main-sync/SKILL.md`, and updated `AGENTS.md` + `.agents/skills/project-manager/SKILL.md` for cross-window artifact harvesting and zero-repercussion `main` doc pushing.
- **Repo-Scoped `PreToolUse` Toolchain Auto-Approval Hook (`486822e`)**:
  - Owner confirmed adding a repo-scoped Antigravity `PreToolUse` permission hook so both teammates' agents auto-approve safe Simon toolchain commands (`RESOURCES.md`) while keeping destructive, token-exfiltrating, and untrusted commands gated by default policy.
  - Implemented `.agents/scripts/auto_approve_toolchain.py` and wired `"simon-toolchain-permissions"` (`matcher: "run_command"`) in `.agents/hooks.json`.
  - Added 34 unit test cases + CLI contract check in `tests/test_auto_approve_hook.py` (all passing under macOS system Python 3.9 via `python3 -m unittest discover -s tests -v`), and documented repo-scoped hooks in Section 6 of `RESOURCES.md`.
- **Dual-Track `main-sync` Skill (Docs vs. Code) & Steward Auto-Approval (`44bc72c`, pushed to `origin/main`)**:
  - Separated `.agents/skills/main-sync/SKILL.md` and `.agents/scripts/sync_main.py` into **Track A · Docs & Knowledge Sync (`--docs-only`)** (auto-approved doc file creation/edits via `PreToolUse` in `.agents/hooks.json` + `auto_approve_toolchain.py` and zero-ceremony push to `origin/main` without touching dirty `simon/` or `tests/` code) and **Track B · Code Sync (`--code --paths <files...>`)** (enforcing pre-commit `unittest` + `python -m simon` smoke + `ruff check --select E9,F`, explicit slice staging, optional `--branch feat/<slug>` + `gh pr create`, and manual review fallback for `--skip-verify` or unscoped `--all`).
  - Updated `.gitignore` and `sync_main.py` to block `.pytest_cache/` and `.ruff_cache/`, expanded `tests/test_auto_approve_hook.py` to 6 test methods (all passing), and updated `AGENTS.md`, `PROJECT.md`, `RESOURCES.md`, `.agents/skills/main-sync/SKILL.md`, and `.agents/skills/project-manager/SKILL.md`.
