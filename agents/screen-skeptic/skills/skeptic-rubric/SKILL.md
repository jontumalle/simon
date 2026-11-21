---
name: skeptic-rubric
description: Concrete risk audit rules, missing-evidence preservation, and stdlib JSON validator for Simon's Stage 3 Talent Skeptic (`simon-screen-skeptic`).
---

# Skeptic Rubric & Output Validator (`skeptic-rubric`)

Use this skill inside `simon-screen-skeptic` to audit all 5 blocks of a Stage 2 `InvestigatorDossier` for concrete risks, dealbreakers, and missing evidence.

## 1. Concrete Risk & Dealbreaker Matrix

Always audit all 6 standard dealbreakers and list them in `dealbreakers_checked`:

| Risk / Dealbreaker | Dossier Field(s) | Default `skill` Tag | Trigger Condition |
| :--- | :--- | :--- | :--- |
| `one_clip_view_concentration_gt_85pct` | `public_footprint.top_release_view_share_pct` | `dossier-footprint` | `> 85.0` (single-clip concentration skew). |
| `studio_only_media` | `source_and_media_queue.media_links`, `source_channel` | `dossier-media` | Only studio/topic tracks or zero live-room/session clips; or `oembed_live_embeddable == false`. |
| `uncertain_attribution` | `source_and_media_queue.attribution_status` | `dossier-media` | `attribution_status == "uncertain"`. |
| `contact_route_none` | `identity_and_contact.contact_route_type` | `dossier-identity` | `contact_route_type == "none"` or no reachable platform/email route. |
| `major_label_lockup` | `live_history_and_credits.public_team_mentions.label` | `dossier-live-history` | Major label or major-owned imprint already attached (or `established_streaming` saturation). |
| `spam_comments` | `comment_forensics.comment_intent_counts` | `dossier-comments` | High `jokes_or_spam` ratio (`>30%`), `sample_size == 0`, or zero release/show intent. |

> When `.agents/skills/dossier-*/SKILL.md` skills are mounted in the sandbox, prefer the exact directory/frontmatter name of the matching `dossier-*` skill for `cons[].skill`.

## 2. Strict Missing-Evidence Rule (No Fake Flaws)

1. Copy **every** string in `dossier.missing_fields` into `missing_evidence_flags` verbatim.
2. Never invent imaginary criticisms when a metric is clean. If data was simply unavailable (`null` or in `missing_fields`), flag it in `missing_evidence_flags` rather than fabricating negative facts.

## 3. Output Schema (`skeptic_case`)

```json
{
  "lead_id": "lead_001",
  "stage_name": "Maya Vance",
  "headline": "Concentrated top-clip views (88.5%) and missing Bandcamp supporter counts, though attribution and contact are verified.",
  "cons": [
    {
      "skill": "dossier-footprint",
      "title": "High single-video view concentration",
      "evidence": "top_release_view_share_pct is 88.5% (>85% threshold), meaning reach depends heavily on one session upload."
    }
  ],
  "missing_evidence_flags": [
    "public_footprint.public_reach.bandcamp_supporters_count",
    "live_history_and_credits.highest_venue_cap_observed"
  ],
  "dealbreakers_checked": [
    "one_clip_view_concentration_gt_85pct",
    "studio_only_media",
    "uncertain_attribution",
    "contact_route_none",
    "major_label_lockup",
    "spam_comments"
  ]
}
```

## 4. Mandatory Verification Command

```bash
python3 .agents/skills/skeptic-rubric/scripts/verify_skeptic.py /tmp/skeptic_case.json
```
