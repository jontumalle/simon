# 2026-11-21 · Process Audit, Dedicated Subagents, Env Rule & Workflow Skills

- **Audit Scope**: Full workspace telemetry scan across `53` sessions (`21` root chats, `32` subagents, `168` friction signals) logged to `pm/process/observations.md` (`OBS-2026-11-21-07` through `11`) and `pm/process/synthesis.md` (`e5e167d`).
- **Workspace Plugin Created (`.agents/plugins/simon-ops/`)**:
  - `simon-steward` (`16×` empirical Steward flow)
  - `simon-feature-engineer` (`10×` isolated `Workspace: "share"` build flow)
  - `simon-eval-author` (`4×` parallel 3-layer rubric & eval flow)
  - `simon-agent-deployer` (Managed Agent `python3 -m simon deploy` & staging smoke flow)
  - `simon-system-improver` (non-binary hook/rule/skill calibration from `pm/process/`)
- **Rule Added**: `.agents/rules/python-and-worktree-env.md` — addresses ~47 recurring friction hits (`python3` 3.9 vs `.venv` 3.12, worktree `.venv` resolution, pre-sync `ruff check --fix`, `gcloud` path, absent `node`/`rg`, zsh URL quoting, re-read before `edit_file`).
- **Skills Added**:
  - `.agents/skills/cloudrun-deploy-and-verify/SKILL.md`
  - `.agents/skills/ui-flow-audit/SKILL.md`
