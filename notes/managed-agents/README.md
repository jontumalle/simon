# Managed Agents — Playbooks & Architecture (`notes/managed-agents/`)

This section holds **how-to engineering knowledge** for building, testing, mounting repositories into, and deploying Google Managed Agents (`antigravity-preview-09-2026` and `deep-research-preview-04-2026` via the Gemini API `v1beta` Control & Runtime planes).

> Looking for the actual deployable agents we maintain for Simon? See **[agents/](../../agents/README.md)**.

## Playbooks
- **[talent-agency-pipeline.md](./talent-agency-pipeline.md)** — **4-Stage Agentic Talent Agency Pipeline & Data Architecture**:
  - Plane A (Progressive Talent Dossier Enrichment: Stage 1 Basic Profile → Stage 2 Metric-Blind Media Digestion → Stage 3 Sparsity-Aware Scout Metadata) vs. Plane B (Stage 4 Mandate-Driven "Taste" & Standout Pipeline)
  - Managed Agent fleet mapping (`gemini-4-hydrogen`, `gemini-4-carbon`, `deep-research-preview-04-2026`, `DSPy + gemini-decision-1`) & epistemic blinding rules
  - Database upgrade path from MVP `simon/store.py` (v0) to the persistent Canonical Talent Graph (v1)
- **[playbook.md](./playbook.md)** — Complete architecture & API reference:
  - `/v1beta/agents` persistent blueprints (`gemini-3.8-flash` / `gemini-4-argon` / `deep-research-preview-04-2026`)
  - "Agent as a Repo" (`base_environment.sources` mounting GitHub repos + inline `.agents/AGENTS.md` & `.agents/skills/`)
  - Shared sandbox state (`/v1beta/environments` + Files API) & epistemic critic independence
  - Zero-trust security (`network: "disabled"` for artist demos + `Credentials API` egress proxy)
  - `background=True` async execution (`store=True` requirement) & `gemini-api` CLI commands
  - Teammate namespacing (`SIMON_AGENT_PREFIX`) so parallel dev never collides
- **[deployment-and-triggers.md](./deployment-and-triggers.md)** — Workforce packaging, 1-command deploy pipeline & trigger topologies:
  - Job Package manifest (`agents/<job-name>/`: `agent.yaml` + `SYSTEM.md` + `skills/` + `dispatch`/`triggers`)
  - Upstream API constraints (immutable blue/green SHA-8 vs recreate deploy since no in-place `agents.update`, locked `agent_config.model`, reserved ID prefixes)
  - Native Cron Triggers (`/v1beta/triggers` / `client.triggers.create`) with persistent cross-run sandbox state
  - Inbound HTTP Job Endpoints & External Webhooks (`POST /jobs/<job>`) vs Outbound Gemini Webhooks (`/v1beta/webhooks` Standard HMAC + per-call `webhook_config` RS256 JWKS) for zero-polling multi-agent DAG fan-in
