---
name: youtube
description: >-
  Shared YouTube Data API v3 tool for Simon Managed Agents. Fetches structured video metadata,
  channel profiles, recent channel uploads, public comments, and search results using zero-trust
  header auth (X-Goog-Api-Key via credential youtube-api-key).
---

# `youtube` — Shared YouTube Data API v3 Tool for Simon Managed Agents

Use `scripts/youtube_api.py` (as a CLI or Python library) whenever you need exact, structured YouTube data without HTML scraping or audio decoding.

> Auth is injected automatically on the wire by Google's egress proxy (`credential: youtube-api-key`) into the `X-Goog-Api-Key` header for `www.googleapis.com`. Never log, print, or hardcode API keys.

## Quota-Aware Command Guide (Daily Default: 10,000 Units)

| Command | Quota Cost | Best Used By | What It Returns |
| :--- | :---: | :--- | :--- |
| `video <id_or_url...>` | **1 unit** (up to 50 IDs) | All scouts | Exact title, channel, description, tags, ISO + seconds duration, views, likes, comment count |
| `channel <@handle\|UC...\|url>` | **1 unit** | `identity-resolver`, `footprint-profiler` | Canonical channel URL, description (for link graph/contact), country, subscribers, total views, video count |
| `channel-videos <ref>` | **3 units** | `footprint-profiler`, `track-record-mapper`, `discovery-scout` | Channel profile + recent uploads with full view/like/comment/duration stats (avoids 100-unit `search`) |
| `comments <id_or_url>` | **1 unit** | `signal-forensics` | Up to 50 public top-level comments (`author`, `text`, `like_count`, `reply_count`); returns `comments_disabled: true` cleanly if disabled |
| `search "<query>" [--enrich]` | **100 units** (+1 with `--enrich`) | `discovery-scout` (only when `google_search` or `channel-videos` is insufficient) | Matching videos; use `--enrich` to attach exact views and duration |

**Quota Rule:** Prefer `channel-videos` (3 units) and batched `video` calls (1 unit for up to 50 URLs) over `search` (100 units).

## CLI Usage (Inside Sandbox)
```sh
# 1. Inspect 1..50 video URLs or IDs in a single 1-unit batch
python3 .agents/skills/youtube/scripts/youtube_api.py video \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 2. Resolve a channel by @handle, UC... ID, or URL
python3 .agents/skills/youtube/scripts/youtube_api.py channel "@SofarSounds"

# 3. Pull recent uploads + exact stats for concentration math or live-footage check
python3 .agents/skills/youtube/scripts/youtube_api.py channel-videos "@SofarSounds" --max-results 15

# 4. Pull up to 50 public comments for signal-forensics intent bucketing
python3 .agents/skills/youtube/scripts/youtube_api.py comments "dQw4w9WgXcQ" --max-results 50

# 5. Search live vocal sessions (use sparingly — 100 quota units)
python3 .agents/skills/youtube/scripts/youtube_api.py search "NYC live vocal session acoustic" --max-results 10 --enrich
```

## Python Library Usage (Inside Sandbox)
```python
import sys
sys.path.insert(0, ".agents/skills/youtube/scripts")
from youtube_api import YouTubeAPI

yt = YouTubeAPI()
profile = yt.channel("@SofarSounds")
uploads = yt.channel_videos("@SofarSounds", max_results=15)
thread = yt.comments("dQw4w9WgXcQ", max_results=50)
```
