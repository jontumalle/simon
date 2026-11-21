# Session Log — 2026-11-21 · Label-Signing Recall Eval Dataset (Option C)

## Summary
- Created a 10-artist Option C two-bucket recall benchmark at [data/evals/label_signing_recall_eval.json](../../data/evals/label_signing_recall_eval.json) built from real 2025–2026 record-label signings under 100k followers across YouTube subscribers (200–100k range) and Spotify monthly listeners (<100k).
- Registered the benchmark in [data/README.md](../../data/README.md).

## Dataset Structure
- **In-map extraction recall (6 artists):** Real signings touching active seeded NYC/session sources in `data/reference/discovery_sources_seed.json` (`Starcleaner Reunion` · Mexican Summer, `Renny Conti` · Mom+Pop / Domino Publishing, `Maria BC` · Sacred Bones, `Hello Mary` · Frenchkiss / Fire Talk, `YHWH Nailgun` · AD 93, `Lip Critic` · Partisan).
- **Out-of-map cold source discovery (4 artists):** Real signings outside the seeded NYC/US session map to test cold discovery via search (`RÓIS` · Domino, `The Sophs` · Rough Trade, `Deux Visages` · Pure Noise, `Ami Taf Ra` · Brainfeeder).
- **Leakage-free run briefs (3 briefs):** `brief_nyc_indie_rooms`, `brief_ambient_folk_vocal`, and `brief_cold_global_discovery` omit record labels and artist names while targeting each bucket.

## Files Updated
- `data/evals/label_signing_recall_eval.json` — Added v1.0.0 10-artist Option C recall eval dataset with verified watch-page metadata, sample videos, and overlapping seed source IDs.
- `data/README.md` — Registered `evals/label_signing_recall_eval.json` under Evaluation Benchmarks.
- `PROJECT.md` — Updated `Recent sessions` LRU cache.
