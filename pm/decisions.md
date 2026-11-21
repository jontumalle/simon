# Decisions — Simon

*Append-only, dated record of product, technical, and governance decisions.*

- **2026-11-21 · Project Name & Core Thesis**: Named the project **Simon** — a multimodal talent-scouting and live-showcase production system starting with emerging vocalists (*First Listen NYC*), designed as a reusable scouting/critic engine across scenes and modalities.
- **2026-11-21 · Hackathon Track Selection**: Prioritize **Best Use of Managed Agents ($5,000)** at the Gemini 4 NYC Hackathon; skip forced Shopify/merch/dropshipping integration because it does not naturally fit the scouting product.
- **2026-11-21 · Critic / Validator Multi-Agent Pattern**: Use independent specialist Managed Agents ("critics/validators" for musical performance vs. practical booking fit) followed by a Producer synthesis agent that highlights disagreements rather than averaging scores.
- **2026-11-21 · Life OS Repo Knowledge Model**: Adopted the Life OS-inspired repo structure (`PROJECT.md`, `RESOURCES.md`, `pm/`, `notes/managed-agents/`, `agents/`, `simon/`, `data/`, `examples/`, `local/`, `ideas/`, `tests/`, `.agents/`) with setup-stage filing confirmation and a background Project Manager (Steward) subagent.
- **2026-11-21 · Shared Partner Sync (`RESOURCES.md` + `origin/main`)**: Maintain a root `RESOURCES.md` and commit/push updates to `origin/main` (`jontumalle/simon`) so both teammates' agents can pull and self-install required tools.
