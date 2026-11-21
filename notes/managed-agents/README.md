# Managed Agents — Playbooks & Architecture (`notes/managed-agents/`)

This section holds **how-to engineering knowledge** for building, testing, mounting repositories into, and deploying Google Managed Agents (`antigravity-preview-09-2026` and `deep-research-preview-04-2026` via the Gemini API `v1beta` Control & Runtime planes).

> Looking for the actual deployable agents we maintain for Simon? See **[agents/](../../agents/README.md)**.

## Playbooks
- **[playbook.md](./playbook.md)** — Complete architecture & API reference:
  - `/v1beta/agents` persistent blueprints (`gemini-4-hydrogen` vs `gemini-4-carbon` vs `deep-research-preview-04-2026`)
  - "Agent as a Repo" (`base_environment.sources` mounting GitHub repos + inline `.agents/AGENTS.md` & `.agents/skills/`)
  - Shared sandbox state (`/v1beta/environments` + Files API) & epistemic critic independence
  - Zero-trust security (`network: "disabled"` for artist demos + `Credentials API` egress proxy)
  - `background=True` async execution (`store=True` requirement) & `gemini-api` CLI commands
  - Teammate namespacing (`SIMON_AGENT_PREFIX`) so parallel dev never collides
