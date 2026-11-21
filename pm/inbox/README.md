# Inbox — Friction-Free Capture

Drop raw meeting notes, Wispr Flow transcripts, scratchpad dumps, or unsorted links here when you want them tracked in git before distillation (keep private/sensitive raw files in gitignored `local/` instead).

## Routing Rules (Steward / `project-manager` skill)
Nothing lives in `pm/inbox/` permanently. Once reviewed with the owner, route each item into its permanent home and remove the raw inbox file:

| Item Type | Destination |
| :--- | :--- |
| Factual session or milestone event | `pm/log/YYYY-MM-DD-<slug>.md` |
| Product, architecture, or scope decision | `pm/decisions.md` |
| Live sprint status or blocker change | `pm/current.md` |
| Managed Agents architecture or API how-to | `notes/managed-agents/` |
| Deployable specialist agent prompt/config | `agents/<agent-id>/` |
| Future vertical, source idea, or pitch concept | `ideas/` |
| Required CLI, SDK, plugin, or env var | `RESOURCES.md` |
