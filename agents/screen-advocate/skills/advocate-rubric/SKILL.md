---
name: advocate-rubric
description: Upside thesis construction rules and stdlib JSON contract validator for Simon's Stage 3 Talent Advocate (`simon-screen-advocate`).
---

# Advocate Rubric & Output Validator (`advocate-rubric`)

Use this skill inside `simon-screen-advocate` to turn a Stage 2 `InvestigatorDossier` into a rigorous, evidence-backed `advocate_case` JSON payload.

## 1. Upside Extraction Checklist (All 5 Dossier Blocks)

Check all 5 blocks before selecting your strongest `pros` (`1` to `5` items, ordered strongest-first):

| Dossier Block | Default `skill` Tag (if `dossier-*` unmounted) | High-Signal Upside Indicators |
| :--- | :--- | :--- |
| `identity_and_contact` | `dossier-identity` | Clear local scene anchor (`home_city` / `home_neighborhood`), active cross-platform links, direct `bio_email` or `mgmt_email` outreach path. |
| `source_and_media_queue` | `dossier-media` | `attribution_status == "verified"`, live session / DIY venue origin, >=2 `oembed_live_embeddable: true` clips ready for human listening. |
| `public_footprint` | `dossier-footprint` | `pre_dsp_underground` or `early_dsp_inflection` timing, Bandcamp supporter base, healthy catalog distribution (`top_release_view_share_pct <= 85`). |
| `comment_forensics` | `dossier-comments` | Unprompted `release_requests` + `live_show_requests`, strong `genuine_praise` share, peer/venue/producer `notable_commenters`. |
| `live_history_and_credits` | `dossier-live-history` | Verified `show_history` / `upcoming_shows` in credible rooms, billing slot growth, `collaborator_credits`, and unsigned/indie label whitespace. |

> When `.agents/skills/dossier-*/SKILL.md` skills are mounted in the sandbox, prefer the exact directory/frontmatter name of the matching `dossier-*` skill for `pros[].skill`.

## 2. Output Schema (`advocate_case`)

```json
{
  "lead_id": "lead_001",
  "stage_name": "Maya Vance",
  "headline": "Unsigned Ridgewood vocalist with 3 embeddable live sessions, 9 release requests, and active Brooklyn club momentum.",
  "pros": [
    {
      "skill": "dossier-media",
      "title": "Repeatable live-room video proof",
      "evidence": "Verified attribution on youtube_live_session seed plus 3 oembed_live_embeddable clips spanning 195s-248s."
    },
    {
      "skill": "dossier-comments",
      "title": "Organic listener demand and venue co-sign",
      "evidence": "9 release_requests and 5 live_show_requests out of 42 sampled comments (only 1 spam), plus co-sign from @alphavillebk."
    }
  ],
  "standout_hook": "Pulling repeat release requests and live room bookings before any label or booking agent lockup."
}
```

### Hard Constraints
- `pros` MUST contain at least 1 item (`len(pros) >= 1`), and every item MUST cite real dossier facts (never invent flaws or praise).
- Zero forbidden keys (`interaction_id`, `environment_id`, `sandbox_id`, `session_id`, `api_key`, `simon_agent_db_token`) anywhere in the payload or Field News post.

## 3. Mandatory Verification Command

Always validate your JSON file before returning:

```bash
python3 .agents/skills/advocate-rubric/scripts/verify_advocate.py /tmp/advocate_case.json
```
