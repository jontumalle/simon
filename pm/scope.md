# Scope — Simon

Guiding guardrails for humans and agents working in this repository.

## What Simon Is
- **A talent-scouting and live-showcase production system** powered by multimodal Gemini 4 audio/video understanding (`gemini-4-hydrogen`) and **Google Managed Agents** (`antigravity-preview-09-2026`).
- **Pilot Vertical (*First Listen NYC*)**: Discovering overlooked vocalists, evaluating performance evidence independently from practical booking fit, surfacing reviewer disagreements, and drafting human-approved paid showcase invitations.
- **Modular Scouting Engine**: Built as a curated fleet of task-specific agents ("agent as a repo") whose rubrics and modalities can be swapped to scout other scenes, geographies (e.g., Hudson County / NYC local scenes), or talent verticals.
- **Hackathon Target**: **Gemini 4 NYC Hackathon** — primary focus on **Best Use of Managed Agents ($5,000)**.

## What Simon Is Not (Guardrails)
- **No forced e-commerce / dropshipping shoehorning**: Early ideation tested Shopify/merch/dropshipping angles and explicitly rejected them because they dilute the core scouting & Managed Agents story.
- **No autonomous artist commitments or unconsented publishing**: Agents evaluate evidence, surface uncertainties, and draft invitations marked `pending_human_review`. A human producer confirms terms and contacts artists; private contact details stay outside public manifests.
- **No monolithic prompt**: Keep stages modular (Scout/Ingest → Independent Critics/Validators → Producer Synthesizer) so Managed Agents can run in parallel, challenge each other, and trace every claim to evidence.
