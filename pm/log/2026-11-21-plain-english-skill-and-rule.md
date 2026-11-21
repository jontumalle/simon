# 2026-11-21 — Plain-English Repo Skill & Adaptive Execution Gate

## What Happened
- **Repo-Level `plain-english` Skill Added (`0ef97f2`, `45e4405`)**:
  - Created [`.agents/skills/plain-english/SKILL.md`](../../.agents/skills/plain-english/SKILL.md) (`name: plain-english`), implementing Simplified Technical English (STE-100), William Zinsser's four principles (clarity, simplicity, brevity, humanity), **Visual First · Mermaid Preferred** diagrams, Socratic/dialectical trade-off framing, and two on-command workflows (**Mode A · Rewrite or Audit Content** and **Mode B · Stress-Test a Plan or Decision**).
  - Indexed `plain-english` in [PROJECT.md](../../PROJECT.md) (`.agents/` skills map) and [RESOURCES.md](../../RESOURCES.md) (Section 6) strictly as an on-command repo skill (keeping personal `always_on` user rules local-only outside the repository).
  - Paired the protocol with an **Adaptive Exploration vs. Execution Gate**: propose trade-offs and ask up to 2 questions when intent has ambiguity, and execute immediately on explicit commands or inside background subagents so autonomous workers never stall.
- **Artifact Check**:
  - Checked `/Users/kevinquizhpi/.gemini/antigravity/brain/b2a966c3-5377-4db5-9cbd-22ede23b178d`; the session wrote all durable files directly to the repository and user config without leaving standalone brain artifacts.
- **Worktree Sync Process Note**:
  - When running inside a git worktree on a non-`main` branch (`content_alignment_skill_rule`), `python3 .agents/scripts/sync_main.py --docs-only` rebases `HEAD` cleanly onto `origin/main`, and running `PATH="$HOME/.local/bin:$PATH" git push origin HEAD:main` immediately afterward lands the Steward commit on `origin/main` (logged in [`pm/process/observations.md`](../process/observations.md) as `OBS-2026-11-21-06`).
