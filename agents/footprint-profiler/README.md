# `footprint-profiler` (`simon-footprint-profiler`)

- **Model:** `gemini-4-argon` (`max_total_tokens: "64000"`)
- **Phase:** B (Runs concurrently with `signal-forensics` and `track-record-mapper`)
- **Pattern:** Parallel generic + domain tools inside, joined by deterministic Python math
- **Input:** `IdentityBundle` from `identity-resolver`
- **Output:** `media_links[]`, `public_reach`, `footprint_regime`, `top_release_view_share_pct`, `process_trace[]`, `missing_fields[]`
- **Isolated Eval:** `python3 -m unittest tests.test_investigator_evals.TestFootprintProfilerEval`
