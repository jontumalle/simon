# `signal-forensics` (`simon-signal-forensics`)

- **Phase:** B (Runs concurrently with `footprint-profiler` and `track-record-mapper`)
- **Pattern:** Hybrid — fetch public text once (generic), classify in 1 pass using merged generic + domain buckets
- **Input:** `IdentityBundle` from `identity-resolver`
- **Output:** `comment_intent_counts`, `notable_commenters[]`, `process_trace[]`, `missing_fields[]`
- **Isolated Eval:** `python3 -m unittest tests.test_investigator_evals.TestSignalForensicsEval`
