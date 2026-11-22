---
name: music
description: >-
  Layer 2 Music Domain Skill Pack for Simon's Stage 2 Scout Investigator agents
  (identity-resolver, footprint-profiler, signal-forensics, track-record-mapper).
  Defines music-specific public sources, 22 feasible zero-decode factual datapoints,
  comment intent buckets, and strict abstention/no-ranking rules.
---

# Layer 2 Domain Skill Pack — Music Lead Profiling

Load this skill alongside Layer 1's domain-agnostic investigation process whenever profiling a **music artist / vocalist** from a Stage 1 `DiscoveryLead`.

## 1. Core Invariants (Never Violate)
1. **Zero Ranking or Scoring:** Emit objective, factual data only. Never output scores, tiers, grades, or booking recommendations (`no_ranking_or_scoring: true`).
2. **Zero Audio/Video Decoding (v1):** Use public text, metadata, oEmbed, APIs, bios, calendars, credits, and comments only.
3. **No PII Leakage:** Record `has_public_business_contact` (bool) and `contact_route_type` (`bio_email` | `mgmt_email` | `open_dm` | `none`), never raw private email addresses or phone numbers.
4. **Honest Abstention:** If a public source returns nothing, set the field to `null` or `[]` and append the field name to `missing_fields[]`. Never guess.
5. **Log High-Signal Sources:** Whenever you discover a reusable venue calendar, live-session channel, or artist directory, append it to `newly_discovered_sources[]`.

---

## 2. Music Domain Extensions by Agent

### Agent 1 · `identity-resolver` (Sequential: `1a Generic → 1b Music`)
- **1a Generic:** Canonical `stage_name`, `aliases[]`, `pronouns`, `home_city`, `home_neighborhood`, `bio_text`, general links (YouTube, IG, TikTok, Linktree), `has_public_business_contact`, `contact_route_type`.
- **1b Music (depends on 1a):**
  - Extract `project_type` (`solo_vocalist` | `duo` | `band` | `collective` | `unknown`), `primary_genre`, `subgenres[]`.
  - Collect music-platform URLs (`spotify`, `apple_music`, `soundcloud`, `bandcamp`) from Linktree/bio.
  - Query public MusicBrainz WS/2 API using `stage_name` + `home_city` for `musicbrainz_mbid` and verified `aliases[]`.

### Agent 2 · `footprint-profiler` (Parallel Tools Inside)
- **Generic Tool:** Verify public `media_links[]` via oEmbed (`url`, `title`, `uploader_channel`, `duration_seconds`, `oembed_live_embeddable`) and read public YouTube subscribers + top video views.
- **Music Tool:** Read public Bandcamp release count, Bandcamp supporter count, and public released track count.
- **Python Code Execution:** Compute `top_release_view_share_pct` (top video views ÷ total sampled video views, or `null` if `< 2` videos) and `footprint_regime` (`pre_dsp_underground` | `early_dsp_inflection` | `established_streaming` | `unknown`).

### Agent 3 · `signal-forensics` (Fetch Once → 1-Pass Merged Classifier)
- **Fetch (Generic):** Sample up to 50 public comments from the artist's top 1–2 YouTube videos or Bandcamp releases.
- **Classify (1-Pass Merged Buckets):**
  - Generic buckets: `genuine_praise`, `jokes_or_spam`
  - Music buckets: `release_requests` (*"drop this on Spotify"*, *"studio version?"*), `live_show_requests` (*"come to NYC"*, *"tour dates?"*)
- **Notable Commenters:** Record only verified channels, venues, producers, or credited peers with `handle`, `channel_url`, `role_or_context`, and `comment_excerpt`.

### Agent 4 · `track-record-mapper` (Parallel Tools Inside)
- **Generic Tool:** Parse bios, Linktree, YouTube descriptions, and `℗`/`©` copyright lines for explicit `public_team_mentions` (`management`, `booking_agent`, `label`, `distributor`). Leave `null` if not explicitly written.
- **Music Tool:** Gather `show_history[]` and `upcoming_shows[]` from public event listings (Bandsintown, Songkick, Dice, venue calendars, YouTube live titles), look up `highest_venue_cap_observed` for verified venues, and extract `collaborator_credits[]` (producers, writers, engineers) from YouTube descriptions, Bandcamp, and MusicBrainz.
