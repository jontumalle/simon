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

## Runner Merge & Baseline Update
- Merged PR #21 (`e56051b`, `feat(evals): add Option C label-signing recall eval runner`) to `main`, adding `simon/recall_eval.py` and `tests/test_recall_eval.py`.
- Verified compatibility with PR #20 (`f81c258`, Vertex AI multi-agent eval runner & `/evals` UI); 7/7 eval tests pass alongside `tests/test_vertex_evals.py`.
- Saved local baseline run to `local/evals/discovery-label-recall-latest.json`.

## Live Recall Run, Trace Selector & Honest Offline Evals (`3036bf6`, `602a30c`)
- **Discovery Scout Token Budget & Live Recall Verification (`3036bf6`)**: Raised `max_total_tokens` from `64000` to `192000` in `agents/discovery-scout/agent.json` and `agents/discovery-scout/agent.yaml`, redeployed `staging-simon-discovery-scout`, and verified all 3 live recall fleet workers completed (`58–66 steps`, 24 verified leads, cold-discovering `Ami Taf Ra` for 25% out-of-map recall).
- **Trace-Targeted `/evals` Execution (`602a30c`)**: Added `GET /api/evals/traces?agent=<slug>`, trace-targeted `POST /api/eval-runs/run` (`trace_id`, `trace_collection`), and a Trace Selector dropdown on `/evals` across `simon/discovery_ui.py`, `simon/web.py`, and `simon/vertex_eval.py`.
- **Honest Offline Eval Scoring (`602a30c`)**: Removed fake 100% offline scores in `simon/vertex_eval.py` — incomplete/failed traces now fail Layer 1 gates, and LLM-only rubrics require `--mode vertex` instead of auto-passing offline (`18/18` tests passed).
