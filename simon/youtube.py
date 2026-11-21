"""Public YouTube discovery, URL canonicalization, oEmbed verification, and performer grouping.

Note on platform choice: Gemini supports public YouTube URLs natively as video inputs,
whereas SoundCloud's API terms prohibit feeding API-accessed tracks into AI models.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse
from urllib.request import Request, urlopen

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_INITIAL_DATA_RE = re.compile(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL)

# Common venue, live-session, and open-mic channels where the uploader is not the solo artist.
SESSION_CHANNEL_KEYWORDS = (
    "sofar",
    "mahogany",
    "tiny desk",
    "npr music",
    "colors",
    "audiotree",
    "paste",
    "kexp",
    "la blogothèque",
    "blogotheque",
    "open mic",
    "live at",
    "sessions",
    "lounge",
    "venue",
    "festival",
    "collective",
    "radio",
    "tv",
    "magazine",
    "records",
    "studio",
)

TITLE_NOISE_PATTERNS = (
    r"\|.*$",
    r"\((?:official|live|acoustic|stripped|mahogany|sofar|tiny desk|audio|video|session|cover)[^)]*\)",
    r"\[(?:official|live|acoustic|stripped|mahogany|sofar|tiny desk|4k|hd)[^\]]*\]",
)


def extract_video_id(url: str) -> Optional[str]:
    """Extract an 11-character YouTube video ID from watch, youtu.be, shorts, or embed URLs."""
    if not isinstance(url, str):
        return None
    raw = url.strip()
    if VIDEO_ID_RE.match(raw):
        return raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]

    candidate: Optional[str] = None
    if host == "youtu.be":
        parts = [p for p in parsed.path.split("/") if p]
        candidate = parts[0] if parts else None
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            vals = qs.get("v")
            candidate = vals[0] if vals else None
        else:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
                candidate = parts[1]

    if candidate and VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def canonical_watch_url(url: str) -> str:
    """Return canonical https://www.youtube.com/watch?v=<id> URL, or raise ValueError."""
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"Invalid public YouTube URL: {url!r}")
    return f"https://www.youtube.com/watch?v={video_id}"


def timestamp_to_seconds(timestamp: Any) -> int:
    """Parse 'MM:SS', 'HH:MM:SS', '42s', or int seconds into non-negative integer seconds."""
    if isinstance(timestamp, bool):
        return 0
    if isinstance(timestamp, (int, float)):
        return max(0, int(timestamp))
    if not isinstance(timestamp, str):
        return 0
    cleaned = timestamp.strip().lstrip("@").strip()
    if not cleaned:
        return 0
    if cleaned.endswith("s") and cleaned[:-1].isdigit():
        return max(0, int(cleaned[:-1]))
    if cleaned.isdigit():
        return max(0, int(cleaned))

    # Extract first MM:SS or HH:MM:SS token if embedded in prose
    match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", cleaned)
    if not match:
        return 0
    if match.group(3) is not None:
        hours, minutes, seconds = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    minutes, seconds = int(match.group(1)), int(match.group(2))
    return minutes * 60 + seconds


def seconds_to_timestamp(seconds: int) -> str:
    """Format integer seconds as M:SS or H:MM:SS."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def build_play_first_url(url: str, timestamp: Any) -> str:
    """Build a direct clickable YouTube URL opening at the exact timestamp."""
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"Invalid public YouTube URL: {url!r}")
    secs = timestamp_to_seconds(timestamp)
    if secs > 0:
        return f"https://www.youtube.com/watch?v={video_id}&t={secs}s"
    return f"https://www.youtube.com/watch?v={video_id}"


def build_embed_url(url: str, timestamp: Any = 0, autoplay: bool = False) -> str:
    """Build a privacy-enhanced YouTube embed URL starting at the timestamp."""
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"Invalid public YouTube URL: {url!r}")
    params: Dict[str, str] = {"rel": "0"}
    secs = timestamp_to_seconds(timestamp)
    if secs > 0:
        params["start"] = str(secs)
    if autoplay:
        params["autoplay"] = "1"
    return f"https://www.youtube.com/embed/{video_id}?{urlencode(params)}"


def normalize_artist_key(stage_name: str) -> str:
    """Normalize a performer stage name for deduplication and grouping."""
    cleaned = re.sub(r"\s+", " ", stage_name.strip().lower())
    cleaned = re.sub(r"^the\s+", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9 ]+", "", cleaned)
    return cleaned.strip() or "unknown-artist"


def _clean_stage_name(raw: str) -> str:
    name = raw.strip()
    for pat in TITLE_NOISE_PATTERNS:
        name = re.sub(pat, "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\s*-\s*topic$", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\s+official$", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\s+music$", "", name, flags=re.IGNORECASE).strip()
    return name.strip(" -–—|:\"'")


def infer_performer_and_attribution(title: str, channel_name: str) -> Tuple[str, str, str]:
    """Infer (stage_name, attribution_status, attribution_notes) from YouTube metadata.

    Flags uncertain attribution when:
    - A venue/open-mic/compilation channel uploads a clip without a clear 'Artist - Song' delimiter,
    - Multiple collaborating or featured vocalists appear ('feat.', 'ft.', '&', 'x', 'vs.'), or
    - Neither title nor channel cleanly identifies a single lead vocalist.
    """
    title_clean = (title or "").strip()
    channel_clean = (channel_name or "").strip()
    channel_lower = channel_clean.lower()
    is_session_channel = any(keyword in channel_lower for keyword in SESSION_CHANNEL_KEYWORDS)

    # Split "Artist - Song Title | Session" on common dash delimiters
    dash_parts = re.split(r"\s+(?:[-–—])\s+", title_clean, maxsplit=1)
    has_dash = len(dash_parts) == 2 and len(dash_parts[0].strip()) >= 2

    collab_re = re.compile(r"\b(?:feat\.?|ft\.?|featuring|with)\b|\s+(?:&|x|vs\.?)\s+", re.IGNORECASE)

    if has_dash:
        candidate = _clean_stage_name(dash_parts[0])
        song_part = dash_parts[1]
        if collab_re.search(candidate) or collab_re.search(song_part):
            return (
                candidate or _clean_stage_name(channel_clean) or "Unverified Performer",
                "uncertain",
                f"Multiple performers or featured guests credited across '{title_clean}' ({channel_clean}); verify lead singer identity.",
            )
        if is_session_channel:
            return (
                candidate,
                "verified",
                f"Credited as '{candidate}' on curated live/session channel '{channel_clean}'.",
            )
        # Check if candidate matches channel or channel looks like the artist
        if candidate:
            return (
                candidate,
                "verified",
                f"Performer '{candidate}' credited in title on channel '{channel_clean}'.",
            )

    # No "Artist - Song" dash structure in title
    performs_match = re.match(
        r"^([A-Z0-9][A-Za-z0-9 '&.-]{1,40}?)\s+(?:performs|sings|covers)\s+(.+)$",
        title_clean,
        flags=re.IGNORECASE,
    )
    if performs_match:
        candidate = _clean_stage_name(performs_match.group(1))
        return (
            candidate,
            "verified" if not collab_re.search(performs_match.group(2)) else "uncertain",
            f"Performer '{candidate}' credited in session title on '{channel_clean}'.",
        )

    at_venue_match = re.match(
        r"^([A-Z0-9][A-Za-z0-9 '&.-]{1,40}?)\s+(?:live\s+)?at\s+(.+)$",
        title_clean,
        flags=re.IGNORECASE,
    )
    if at_venue_match:
        candidate = _clean_stage_name(at_venue_match.group(1))
        if normalize_artist_key(candidate) != normalize_artist_key(channel_clean):
            return (
                candidate,
                "uncertain",
                f"Audience or third-party upload on '{channel_clean}' ('{title_clean}'); confirm '{candidate}' is the sole vocalist.",
            )

    if is_session_channel:
        # Try "Artist: Song" or "'Song' by Artist"
        by_match = re.search(r"\bby\s+([A-Z][A-Za-z0-9 '&.-]{1,40})", title_clean)
        if by_match:
            candidate = _clean_stage_name(by_match.group(1))
            return (
                candidate,
                "uncertain",
                f"Uploaded by venue/session channel '{channel_clean}' without standard title credit; verify '{candidate}' is the lead vocalist.",
            )
        fallback = _clean_stage_name(channel_clean) or "Unattributed Open-Mic / Session Singer"
        return (
            fallback,
            "uncertain",
            f"Uploaded by venue/compilation channel '{channel_clean}' ('{title_clean}') without explicit solo performer attribution.",
        )

    # Artist's own channel uploading "Song Title (Live Cover)"
    artist_from_channel = _clean_stage_name(channel_clean)
    if artist_from_channel:
        if collab_re.search(title_clean):
            return (
                artist_from_channel,
                "uncertain",
                f"Uploaded on '{channel_clean}', but title '{title_clean}' credits multiple performers; confirm primary vocalist.",
            )
        return (
            artist_from_channel,
            "verified",
            f"Uploaded directly on artist channel '{channel_clean}'.",
        )

    return (
        "Unknown Vocalist",
        "uncertain",
        "Missing clear channel or title attribution on public YouTube upload.",
    )


class YouTubeConnector:
    """Public YouTube connector using zero-signup search and oEmbed verification."""

    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout: int = 12):
        self.timeout = timeout

    def verify_oembed(self, url: str) -> Optional[Dict[str, str]]:
        """Verify a YouTube video is publicly accessible/embeddable and fetch title + author."""
        try:
            watch_url = canonical_watch_url(url)
        except ValueError:
            return None
        endpoint = f"https://www.youtube.com/oembed?{urlencode({'url': watch_url, 'format': 'json'})}"
        req = Request(endpoint, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                payload = json.load(resp)
        except (HTTPError, URLError, TimeoutError, ValueError):
            return None
        video_id = extract_video_id(watch_url) or ""
        return {
            "video_id": video_id,
            "url": watch_url,
            "title": str(payload.get("title", "")).strip(),
            "channel": str(payload.get("author_name", "")).strip(),
            "channel_url": str(payload.get("author_url", "")).strip(),
            "thumbnail_url": str(payload.get("thumbnail_url", "")).strip(),
        }

    def search_public_videos(self, query: str, max_results: int = 6) -> List[Dict[str, str]]:
        """Search public YouTube performances without an API key or artist signup."""
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp=EgIQAQ%253D%253D"
        req = Request(
            search_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError):
            return []

        match = YT_INITIAL_DATA_RE.search(html)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except ValueError:
            return []

        results: List[Dict[str, str]] = []
        seen_ids = set()
        for renderer in _iter_video_renderers(data):
            vid = renderer.get("videoId", "")
            if not VIDEO_ID_RE.match(vid) or vid in seen_ids:
                continue
            title = _runs_text(renderer.get("title"))
            channel = _runs_text(renderer.get("ownerText") or renderer.get("longBylineText"))
            duration = _runs_text(renderer.get("lengthText"))
            if not title:
                continue
            title_lower = title.lower()
            if any(skip in title_lower for skip in ("compilation", "best of ", "full album", "1 hour", "playlist")):
                continue
            # Skip obvious 1-hour+ compilations/playlists so Gemini evaluates focused song takes
            if duration and duration.count(":") >= 2:
                continue
            seen_ids.add(vid)
            results.append({
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": title,
                "channel": channel,
                "duration": duration,
                "query_used": query,
            })
            if len(results) >= max_results:
                break
        return results

    def group_videos_into_leads(self, videos: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Group discovered YouTube clips by performer stage name and flag uncertain attributions."""
        grouped: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []

        for item in videos:
            try:
                watch_url = canonical_watch_url(item.get("url", ""))
            except ValueError:
                continue
            title = item.get("title", "")
            channel = item.get("channel", "")
            explicit_artist = (item.get("stage_name") or "").strip()
            inferred_name, status, note = infer_performer_and_attribution(title, channel)
            stage_name = explicit_artist or inferred_name
            if item.get("attribution_status") in ("verified", "uncertain"):
                status = item["attribution_status"]
            if item.get("attribution_notes"):
                note = item["attribution_notes"]

            key = normalize_artist_key(stage_name)
            if key not in grouped:
                lead_index = len(order) + 1
                grouped[key] = {
                    "lead_id": f"lead_{lead_index:02d}",
                    "stage_name": stage_name,
                    "attribution_status": status,
                    "attribution_notes": note,
                    "source_links": [],
                    "videos": [],
                }
                order.append(key)

            lead = grouped[key]
            if status == "uncertain":
                lead["attribution_status"] = "uncertain"
                if note and note not in lead["attribution_notes"]:
                    lead["attribution_notes"] = f"{lead['attribution_notes']} | {note}".strip(" |")
            if watch_url not in lead["source_links"]:
                lead["source_links"].append(watch_url)
                lead["videos"].append({
                    "video_id": extract_video_id(watch_url) or "",
                    "url": watch_url,
                    "title": title,
                    "channel": channel,
                    "duration": item.get("duration", ""),
                    "query_used": item.get("query_used", ""),
                })

        return [grouped[k] for k in order]


def _runs_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return str(node["simpleText"]).strip()
    runs = node.get("runs")
    if isinstance(runs, list):
        return "".join(str(part.get("text", "")) for part in runs if isinstance(part, dict)).strip()
    return ""


def _iter_video_renderers(node: Any):
    if isinstance(node, dict):
        if "videoRenderer" in node and isinstance(node["videoRenderer"], dict):
            yield node["videoRenderer"]
        for value in node.values():
            yield from _iter_video_renderers(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_video_renderers(item)
