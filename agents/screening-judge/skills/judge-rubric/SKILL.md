---
name: judge-rubric
description: 5-dimension 0-2 rubric scoring specification, Advocate vs. Skeptic arbitration rules, and ScreeningPacket v1.0.0 validator for Simon's Stage 3 Screening Judge (`simon-screening-judge`).
---

# Screening Judge Rubric & Validator (`judge-rubric`)

Use this skill inside `simon-screening-judge` to score all 5 `0–2` rubrics (`0..10` total), arbitrate `advocate_case` vs. `skeptic_case`, and validate `ScreeningPacket` v1.0.0 JSON before persisting to `simon-db` (`screening_packets`) and publishing the synthesis Scouting Report (`--stage synthesis`).

## 1. Five `0–2` Rubrics (`total_score` = `0..10`)

| Rubric Key | Dossier Block | `0` (Weak / Blocked) | `1` (Partial / Emerging) | `2` (Strong / Verified) |
| :--- | :--- | :--- | :--- | :--- |
| `identity_reachability` | `identity_and_contact` | Conflicting identity or `contact_route_type == "none"` | Coherent identity + `open_dm` | Verified identity, city anchor + `bio_email` / `mgmt_email` |
| `live_vocal_proof` | `source_and_media_queue` | Studio-only, unembeddable, or `uncertain` sole clip | 1 verified embeddable live/session clip | >=2 verified embeddable live/room clips |
| `early_window_depth` | `public_footprint` | `established_streaming`, `>85%` one-clip fluke, or empty | Early/pre-DSP window with `70-85%` top-clip share | Early/pre-DSP window with `<=70%` share or multi-release depth |
| `listener_pull_cosigns` | `comment_forensics` | Empty or spam-heavy comments, 0 requests/co-signs | Positive praise + >=1 request or co-sign | >=3 release/show requests (low spam) and/or credible co-signs |
| `stage_momentum_whitespace` | `live_history_and_credits` | Major-label lockup or 0 shows + 0 credits | Unsigned whitespace + 1-2 early shows/credits | Unsigned whitespace + >=2 real room billings & collaborator network |

## 2. Verdict Bands & Dealbreaker Overrides

- **`"elevate"`**: `total_score >= 7`, verified attribution, reachable contact (`bio_email` / `mgmt_email` / `open_dm`), and no major-label lockup.
- **`"watch"`**: `total_score` `4..6`, OR `total_score >= 7` held back by `"uncertain"` attribution, `contact_route_type == "none"`, `>85%` single-clip concentration, or major `missing_evidence_flags`.
- **`"pass"`**: `total_score <= 3`, OR hard dealbreaker (major-label lockup, `established_streaming` saturation, or studio-only spam channel).

## 3. Canonical `ScreeningPacket` v1.0.0 Schema

```json
{
  "schema_version": "1.0.0",
  "packet_id": "sp_run_01_lead_001",
  "run_id": "run_01",
  "lead_id": "lead_001",
  "stage_name": "Maya Vance",
  "screened_at": "2026-11-21T21:55:00Z",
  "verdict": "elevate",
  "confidence": 0.86,
  "total_score": 8,
  "rubric_scores": {
    "identity_reachability": 2,
    "live_vocal_proof": 2,
    "early_window_depth": 1,
    "listener_pull_cosigns": 2,
    "stage_momentum_whitespace": 1
  },
  "rationale": "Maya Vance pairs 3 verified embeddable live sessions and 14 combined release/show requests with direct bio_email reachability and unsigned Brooklyn club momentum; top-clip share (78%) warrants watching next release follow-through.",
  "advocate_case": {
    "lead_id": "lead_001",
    "stage_name": "Maya Vance",
    "headline": "...",
    "pros": [{"skill": "dossier-media", "title": "...", "evidence": "..."}],
    "standout_hook": "..."
  },
  "skeptic_case": {
    "lead_id": "lead_001",
    "stage_name": "Maya Vance",
    "headline": "...",
    "cons": [{"skill": "dossier-footprint", "title": "...", "evidence": "..."}],
    "missing_evidence_flags": [],
    "dealbreakers_checked": ["one_clip_view_concentration_gt_85pct", "studio_only_media", "uncertain_attribution", "contact_route_none", "major_label_lockup", "spam_comments"]
  }
}
```

## 4. Mandatory Verification Command

```bash
python3 .agents/skills/judge-rubric/scripts/verify_judgment.py /tmp/screening_packet.json
```
