---
name: source-validation
description: >-
  Sandbox validation and URL deduplication skill for simon-source-hunter.
  Verifies candidate discovery sources against Simon's Source Registry schema,
  enforces valid source_channel enums, normalizes location and genre_tags, and
  removes URLs already present in discovered_sources or source_registry.
---

# `source-validation` — Candidate Source Schema & Dedup Verifier

Run `scripts/verify_sources.py` inside `code_execution` before saving new sources to `simon-db`.

## What It Checks
1. **`url`** — Valid `http://` or `https://` URL with non-empty host, canonicalized to strip fragments and tracking noise (`utm_*`, `fbclid`, trailing slash).
2. **`source_channel`** — Must match Simon's allowed enum:
   - `youtube_live_session`
   - `diy_venue_calendar`
   - `diy_venue_flyer_ocr`
   - `bandcamp_local_arrival`
   - `open_mic_lineup`
   - `bgv_or_session_credit_graph`
   - `musicbrainz`
   - `event_listing`
   - `other`
3. **`name`** — Non-empty human-readable venue, session series, or directory title.
4. **`location`** — Object containing `scope` (`hyper_local`, `city`, `metro`, `national`, `global`), `city`, `area`, and `country`.
5. **`genre_tags`** — Non-empty list of lowercase genre strings.
6. **`why_useful`** — Concise plain-English explanation (>= 12 chars) of what scouting signal the source provides.
7. **Deduplication** — Rejects duplicate URLs within the batch and filters out any URL already present in `--existing` JSON dumps from `simon-db`.

## CLI Usage
```sh
python3 .agents/skills/source-validation/scripts/verify_sources.py \
  /workspace/out/candidates.json \
  --existing /workspace/out/existing_discovered.json \
  --existing /workspace/out/existing_registry.json \
  --out /workspace/out/verified_sources.json
```
