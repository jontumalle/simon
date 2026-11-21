# `simon-discovery-scout` (Stage 1 Discovery Agent)

Two-layer Gemini Managed Agent (`antigravity-preview-09-2026` · `gemini-4-hydrogen`) for **Stage 1 (Lead Generation / Discovery)**. Pulls active sources from `simon-db`, searches across music discovery channels (`youtube_live_session`, `diy_venue_calendar`, `bandcamp_local_arrival`, `open_mic_lineup`, `event_listing`, `bgv_or_session_credit_graph`), verifies and deduplicates leads in its Linux sandbox, emits a strict **`DiscoveryHandoff` (`v1.0.0`)** payload with zero ranking or scoring, and persists handoffs, leads, and newly discovered sources back to `simon-db` on every online run.

## Package Layout (Auto-Mounted by `simon/deploy.py`)
- `agent.json` / `agent.yaml` — Managed Agent control-plane spec (`max_total_tokens: "64000"`, `SIMON_DOMAIN: "music"`, `SIMON_DB_URL`, `shared_skills: ["simon-db"]`).
- `SYSTEM.md` — **Layer 1 (Domain-Agnostic Process)**: pull `simon-db` sources → load Layer 2 skill → harvest `N` distinct subjects → run sandbox verifier → save to `simon-db`.
- `skills/music/SKILL.md` — **Layer 2 (Music Domain Skill Pack)**: per-source process playbooks aligned to [discovery_investigator_contract.json](../../data/discovery_investigator_contract.json).
- `skills/music/scripts/verify_handoff.py` — Stdlib sandbox verifier (URL canonicalization, optional YouTube oEmbed check, cross-source artist dedup, strict `DiscoveryHandoff v1.0.0` schema validation, zero-ranking check).

## Commands
```sh
# Validate the sandbox verifier against JT's handoff fixture
python3 agents/discovery-scout/skills/music/scripts/verify_handoff.py examples/discovery_handoff_demo.json

# Run full Stage 1 Discovery eval suite (v0 baseline + DiscoveryHandoff v1.0.0 contract evals)
python3 tests/eval_discovery.py

# Dry-run Managed Agent deploy payload compilation
python3 -m simon deploy --agent discovery-scout --dry-run
```
