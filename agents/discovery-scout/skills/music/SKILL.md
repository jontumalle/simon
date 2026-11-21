---
name: music
description: >-
  Layer 2 Music Discovery Skill Pack for Simon's Stage 1 Discovery Agent (simon-discovery-scout).
  Provides per-source discovery playbooks aligned to DiscoveryHandoff v1.0.0 source_channel enums,
  URL hygiene rules, attribution heuristics, and sandbox verification via scripts/verify_handoff.py.
---

# Layer 2 Domain Skill Pack — Music Discovery (Stage 1)

Use this skill with Layer 1 (`SYSTEM.md`) to discover emerging vocalists and musical acts across public sources and emit a clean `DiscoveryHandoff` (`v1.0.0`) for Stage 2 Investigators.

## 1. Allowed `source_channel` Values (Contract Enum)
Only use these exact values on `seed_sources[].source_channel` and `discovered_sources[].source_channel`:
- `youtube_live_session`
- `diy_venue_calendar`
- `bandcamp_local_arrival`
- `open_mic_lineup`
- `event_listing`
- `bgv_or_session_credit_graph`
- `diy_venue_flyer_ocr` *(deferred until vision OCR pipeline is enabled)*
- `musicbrainz` *(allowed in `discovered_sources`)*
- `other`

---

## 2. Per-Source Process Playbooks

### A. `youtube_live_session`
1. **Query:** Combine brief terms with live-room signals (`"Tiny Desk Contest"`, `"Sofar Sounds"`, `"Mahogany Session"`, `"Paste Studio"`, `"Audiotree"`, `"open mic"`, `"live acoustic"`).
2. **Filter Noise:** Skip compilations, playlists, `"best of"`, full albums, and videos `>= 1 hour`.
3. **Verify URL:** Canonicalize to `https://www.youtube.com/watch?v=<11-char-id>` and verify via YouTube oEmbed (`scripts/verify_handoff.py --verify-oembed`). Drop dead or unembeddable links.
4. **Attribution:**
   - `"verified"`: Official session `"Artist - Song | Channel"` or artist's own channel.
   - `"uncertain"`: Third-party audience upload (`"Artist at Venue"`), open-mic compilation, or multi-vocalist collab (`ft.`, `feat.`, `&`, `x`).

### B. `diy_venue_calendar` (NYC & Local Rooms)
1. **Read Calendar:** Use `url_context` on active venue calendars pulled from `simon-db` (e.g., *Oh My Rockness*, *Pete's Candy Store*, *Arlene's Grocery*, *Pianos*, *Mercury Lounge*, *Baby's All Right*, *Silvana*, *White Eagle Hall*).
2. **Extract Acts:** Pull opener and co-bill artist names (avoid headliners who are already major touring acts unless the brief asks for them).
3. **Attach Seed URL:** Store the venue event/calendar URL as `seed_sources[0]` (`source_channel: "diy_venue_calendar"`). When fast, add a second public artist link (YouTube or Bandcamp) if clearly verified.
4. **Attribution:** Mark `"verified"` if the venue page explicitly links the artist; mark `"uncertain"` if only a bare text name appears on the bill.

### C. `bandcamp_local_arrival`
1. **Browse Arrivals:** Use `url_context` or `google_search` on `bandcamp.com/discover/<city>` or `<genre>/<city>` new arrivals.
2. **Filter for Vocalists:** Check release tags/titles to skip pure beat tapes or instrumental-only packs when the brief asks for vocalists.
3. **Attach Seed URL:** Use the artist's canonical `https://<artist>.bandcamp.com/...` URL with `source_channel: "bandcamp_local_arrival"` and `attribution_status: "verified"`.

### D. `open_mic_lineup` & `event_listing`
1. **Read Listings:** Check Eventbrite open-mic/showcase pages, DICE.fm NYC gigs, Bowery Presents, or Songkick local rooms.
2. **Extract Featured Performers:** Capture explicit performer names from lineups (skip generic event titles like `"Tuesday Open Mic"`).
3. **Attribution:** Default to `"uncertain"` unless linked directly to the performer's official page.

### E. `bgv_or_session_credit_graph`
1. **Mine Credits:** Inspect YouTube live-session descriptions (*Tiny Desk*, *KEXP*, *Sofar*) or Bandcamp liner notes for credited backing vocalists (`BGVs`, `backing vocals`, `vocals`).
2. **Emit Lead:** Record the session URL with `source_channel: "bgv_or_session_credit_graph"` and note the exact credit in `context_snippet` (e.g., `"Credited on backing vocals in KEXP live session description."`).

---

## 3. Strict Hygiene Rules
- **No Ranking Words in `context_snippet`:** Never write `"#1"`, `"top pick"`, `"best"`, `"strong fit"`, `"score"`, `"8/10"`, or `"recommended"`. Write plain facts: `"Listed as opener on Arlene's Grocery calendar (Nov 2026)."`
- **No SoundCloud Audio Feeds:** You may record a SoundCloud URL only as a passive artist profile link if discovered on a venue page, never as a media-decoding audio target.
- **Log Reusable Sources:** Whenever a search uncovers a new active venue calendar, showcase series, or open-mic directory not already in `simon-db`, add it to `discovered_sources[]` with `discovered_by: "stage_1_discovery"`.
