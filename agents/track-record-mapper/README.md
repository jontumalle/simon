# `track-record-mapper` (`simon-track-record-mapper`)

- **Model:** `gemini-4-argon` (`max_total_tokens: "64000"`)
- **Phase:** B (Runs concurrently with `footprint-profiler` and `signal-forensics`)
- **Pattern:** Parallel generic + domain tools inside
- **Input:** `IdentityBundle` from `identity-resolver`
- **Output:** `show_history[]`, `upcoming_shows[]`, `highest_venue_cap_observed`, `public_team_mentions`, `collaborator_credits[]`, `process_trace[]`, `missing_fields[]`
- **Isolated Eval:** `python3 -m unittest tests.test_investigator_evals.TestTrackRecordMapperEval`
