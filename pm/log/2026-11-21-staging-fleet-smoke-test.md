# Session Log — 9/9 Staging Managed Agent Live Interaction Verification

*Date: 2026-11-21*

## Target Endpoint
- **Cloud Run URL**: `https://simon-staging-139550420825.us-east1.run.app`
- **Pre-flight Status (`GET /api/status`)**:
  - `has_api_key`: `true`
  - `store_backend`: `firestore`
- **Fleet Inventory (`GET /api/agents`)**: returned 9 deployed `staging-` Managed Agents.

## Smoke Test Method
- Concurrent `POST /api/fleet/run` (`wait: true`) across all 9 deployed staging Managed Agents.

## Results
- **9/9 HTTP 200 `completed`** (0 failures, 0 timeouts):

| Agent | Latency | Interaction ID |
| :--- | :--- | :--- |
| `staging-simon-booking-critic` | 11.22s | `v1_ChduQWdDYTZiak1ibXd5dE1QbDlMdG9RURIXbkFnQ2E2YmpNYm13eXRNUGw5THRvUVE` |
| `staging-simon-performance-critic` | 15.79s | `v1_ChduQWdDYTlmN0o2N2xpTE1QMi1uRHlBZxIXbkFnQ2E5ZjdKNjdsaUxNUDItbkR5QWc` |
| `staging-simon-identity-resolver` | 42.75s | `v1_ChZuUWdDYTlIaEZZbU95dE1QcnNDVFdBEhZuUWdDYTlIaEZZbU95dE1QcnNDVFdB` |
| `staging-simon-discovery-scout` | 60.48s | `v1_ChduUWdDYS1qUUpvdVF5dE1QdkxlTXdRVRIXblFnQ2EtalFKb3VReXRNUHZMZU13UVU` |
| `staging-simon-track-record-mapper` | 60.75s | `v1_ChduUWdDYTdYNElkWFp5dE1QeUxtRDJRcxIXblFnQ2E3WDRJZFhaeXRNUHlMbUQyUXM` |
| `staging-simon-signal-forensics` | 79.94s | `v1_ChduUWdDYTRuWUVmcXN1TVlQbWVLazhBMBIXblFnQ2E0bllFZnFzdU1ZUG1lS2s4QTA` |
| `staging-simon-footprint-profiler` | 91.04s | `v1_ChduUWdDYTltTUhhVGk1Tm9QeWJDRTBRNBIXblFnQ2E5bU1IYVRpNU5vUHliQ0UwUTQ` |
| `staging-simon-synthesis-scout` | 104.62s | `v1_ChduQWdDYTVHRk9QLUZ5dE1QbWN6RG9RRRIXbkFnQ2E1R0ZPUC1GeXRNUG1jekRvUUU` |
| `staging-simon-showcase-producer` | 135.39s | `v1_ChduUWdDYTlPWU9JbmowX2dQNGZxYW1BMBIXblFnQ2E5T1lPSW5qMF9nUDRmcWFtQTA` |

## Contract Verification & Guardrail Adherence
All 9 interactions returned non-empty structured outputs confirming their respective `SYSTEM.md` behavioral rules and domain contracts:
- `staging-simon-footprint-profiler`: Strict zero-media-decoding enforced (metadata only, no audio/video decoding).
- `staging-simon-signal-forensics`: 50-comment sentiment and intent categorized into mutually exclusive buckets.
- `staging-simon-showcase-producer`: Producer synthesis generated with required `pending_human_review` safety flag.
- `staging-simon-synthesis-scout`: Candidate synthesis correctly applied the `single_clip_flag` guardrail.
- `staging-simon-track-record-mapper`: Factual career history and discography returned strictly with verifiable `source_url` citations.
