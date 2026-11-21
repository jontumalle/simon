"""Layer 2 Music Domain Pack for Simon's Stage 2 Scout Investigator (Option A).

Provides zero-decode public extraction tools for:
- Agent 1 (`identity-resolver`): 1a Generic Core -> 1b Music Domain Extension
- Agent 2 (`footprint-profiler`): oEmbed media queue + YouTube/Bandcamp reach + Python math
- Agent 3 (`signal-forensics`): <=50 public comment fetch + 1-pass merged intent classifier
- Agent 4 (`track-record-mapper`): bio/description team mentions + public shows, venue caps & credits

Every network-touching helper accepts an injectable `fetcher` so offline unit tests and
process evals run deterministically without live network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import html as html_lib
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

from .youtube import canonical_watch_url, extract_video_id

USER_AGENT = "SimonScoutInvestigator/1.0 (+https://github.com/jontumalle/simon)"

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"https?://[^\s<>'\"()]+")
PRONOUNS_RE = re.compile(
    r"\b(she/her|he/him|they/them|she/they|he/they|xe/xem)\b",
    re.IGNORECASE,
)

# Publicly documented room capacities for common NYC & US showcase rooms.
KNOWN_VENUE_CAPS: Dict[str, int] = {
    "pete's candy store": 60,
    "rockwood music hall stage 1": 75,
    "rockwood music hall": 150,
    "rockwood music hall stage 2": 185,
    "the bitter end": 230,
    "nublu": 200,
    "sultan room": 200,
    "mercury lounge": 250,
    "baby's all right": 280,
    "elsewhere zone one": 250,
    "elsewhere hall": 675,
    "le poisson rouge": 450,
    "bowery ballroom": 575,
    "music hall of williamsburg": 650,
    "public records": 250,
    "national sawdust": 170,
    "berlin under a": 175,
    "arlene's grocery": 150,
    "c'mon everybody": 150,
    "union pool": 150,
}

MUSIC_GENRE_KEYWORDS: Tuple[Tuple[str, str], ...] = (
    ("neo-soul", "Neo-Soul"),
    ("r&b", "R&B"),
    ("indie folk", "Indie Folk"),
    ("folk", "Folk"),
    ("indie rock", "Indie Rock"),
    ("indie pop", "Indie Pop"),
    ("jazz", "Jazz"),
    ("alt-pop", "Alt-Pop"),
    ("dream pop", "Dream Pop"),
    ("singer-songwriter", "Singer-Songwriter"),
    ("bedroom pop", "Bedroom Pop"),
    ("soul", "Soul"),
    ("pop", "Pop"),
    ("rock", "Rock"),
    ("electronic", "Electronic"),
)

PLATFORM_HOSTS: Dict[str, Tuple[str, ...]] = {
    "youtube": ("youtube.com", "youtu.be", "music.youtube.com"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "spotify": ("open.spotify.com", "spotify.com"),
    "apple_music": ("music.apple.com",),
    "soundcloud": ("soundcloud.com",),
    "bandcamp": ("bandcamp.com",),
    "linktree": ("linktr.ee", "beacons.ai", "bio.site", "hoo.be"),
}

RELEASE_REQUEST_MARKERS = (
    "drop this",
    "on spotify",
    "apple music",
    "release this",
    "studio version",
    "when is this coming out",
    "need this on",
    "put this on",
)
LIVE_SHOW_REQUEST_MARKERS = (
    "come to",
    "tour",
    "live show",
    "play in",
    "tickets",
    "nyc",
    "brooklyn",
    "see you live",
)
SPAM_OR_JOKE_MARKERS = (
    "check out my channel",
    "sub for sub",
    "free beats",
    "click my profile",
    "first!",
    "who's here in 202",
    "lol",
    "lmao",
    "meme",
)

TextFetcher = Callable[[str], Optional[str]]
JsonFetcher = Callable[[str], Optional[Dict[str, Any]]]


def default_text_fetcher(url: str, timeout: float = 10.0) -> Optional[str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None


def default_json_fetcher(url: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def extract_clean_bio_from_html(raw_html: str, max_chars: int = 900) -> str:
    """Convert raw HTML into clean, readable meta + visible text (no markup or scripts)."""
    if not raw_html:
        return ""
    if "<html" not in raw_html.lower() and "<!doctype" not in raw_html.lower() and "<body" not in raw_html.lower():
        return re.sub(r"\s+", " ", raw_html).strip()[:max_chars]

    snippets: List[str] = []
    for pat in (
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r"<title[^>]*>([^<]+)</title>",
    ):
        for match in re.finditer(pat, raw_html, re.IGNORECASE):
            cleaned = html_lib.unescape(match.group(1)).strip()
            if cleaned and cleaned not in snippets:
                snippets.append(cleaned)

    body = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html_lib.unescape(re.sub(r"\s+", " ", body)).strip()
    if body:
        snippets.append(body[:600])
    return " | ".join(snippets)[:max_chars]


def extract_hrefs_from_html(raw_html: str, base_url: str) -> List[str]:
    """Extract absolute URLs from both raw URLs and relative href attributes."""
    found: List[str] = list(URL_RE.findall(raw_html or ""))
    for match in re.finditer(r'href=["\']([^"\'#]+)["\']', raw_html or "", re.IGNORECASE):
        href = match.group(1).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        if href.endswith((".css", ".js", ".png", ".jpg", ".ico", ".svg", ".json")):
            continue
        abs_url = urljoin(base_url, href)
        if abs_url.startswith(("http://", "https://")) and abs_url not in found:
            found.append(abs_url)
    return found


def parse_youtube_watch_metadata(raw_html: str) -> Dict[str, Any]:
    """Extract zero-decode public metadata from YouTube watch HTML (ytInitialPlayerResponse)."""
    if not raw_html:
        return {}
    meta: Dict[str, Any] = {}
    views_match = re.search(r'"viewCount"\s*:\s*"(\d+)"', raw_html)
    if views_match:
        meta["view_count"] = int(views_match.group(1))
    len_match = re.search(r'"lengthSeconds"\s*:\s*"(\d+)"', raw_html)
    if len_match:
        meta["duration_seconds"] = int(len_match.group(1))
    desc_match = re.search(r'"shortDescription"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_html)
    if desc_match:
        try:
            meta["description"] = json.loads(f'"{desc_match.group(1)}"')
        except json.JSONDecodeError:
            pass
    sub_match = re.search(r'"subscriberCountText"\s*:\s*\{[^}]*"simpleText"\s*:\s*"([^"]+)"', raw_html)
    if sub_match:
        raw_sub = sub_match.group(1).upper().replace("SUBSCRIBERS", "").strip()
        num_match = re.match(r"([\d.]+)\s*([KM]?)", raw_sub)
        if num_match:
            val = float(num_match.group(1))
            mult = {"K": 1_000, "M": 1_000_000, "": 1}[num_match.group(2)]
            meta["youtube_subscribers"] = int(val * mult)
    return meta


def parse_jsonld_music_events(raw_html: str, source_url: str) -> List[Dict[str, Any]]:
    """Extract schema.org MusicEvent records from public tour/event pages."""
    shows: List[Dict[str, Any]] = []
    if not raw_html:
        return shows
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") != "MusicEvent":
                continue
            loc = item.get("location") if isinstance(item.get("location"), dict) else {}
            addr = loc.get("address") if isinstance(loc.get("address"), dict) else {}
            venue = str(loc.get("name") or item.get("name") or "").strip()
            city = str(addr.get("addressLocality") or "").strip()
            region = str(addr.get("addressRegion") or "").strip()
            city_full = f"{city}, {region}".strip(", ") if city else (region or "Unknown")
            start = str(item.get("startDate") or "")[:10]
            if venue and start:
                shows.append(
                    {
                        "venue": venue,
                        "city": city_full,
                        "date": start,
                        "billing_slot": "unknown",
                        "source_url": str(item.get("url") or source_url),
                    }
                )
    return shows


def parse_iso8601_duration(iso_str: str) -> Optional[int]:
    """Parse YouTube ISO 8601 duration (e.g. PT6M10S, PT1H2M3S) into integer seconds."""
    if not isinstance(iso_str, str):
        return None
    match = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", iso_str.strip().upper())
    if not match or not any(match.groups()):
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def fetch_youtube_video_and_channel_api(
    video_id: str,
    api_key: str,
    json_fetcher: JsonFetcher = default_json_fetcher,
) -> Dict[str, Any]:
    """Fetch official YouTube Data API v3 video + channel statistics (zero audio/video decode)."""
    if not video_id or not api_key:
        return {}
    vid_url = (
        "https://www.googleapis.com/youtube/v3/videos?"
        + urlencode(
            {
                "part": "snippet,contentDetails,statistics",
                "id": video_id,
                "key": api_key,
            }
        )
    )
    vid_data = json_fetcher(vid_url)
    items = (vid_data or {}).get("items") or []
    if not items or not isinstance(items[0], dict):
        return {}
    item = items[0]
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    details = item.get("contentDetails") or {}

    meta: Dict[str, Any] = {
        "title": snippet.get("title"),
        "author_name": snippet.get("channelTitle"),
        "description": snippet.get("description") or "",
        "duration_seconds": parse_iso8601_duration(str(details.get("duration") or "")),
        "embeddable": True,
    }
    if stats.get("viewCount") and str(stats["viewCount"]).isdigit():
        meta["view_count"] = int(stats["viewCount"])

    channel_id = snippet.get("channelId")
    if channel_id:
        ch_url = (
            "https://www.googleapis.com/youtube/v3/channels?"
            + urlencode({"part": "statistics", "id": channel_id, "key": api_key})
        )
        ch_data = json_fetcher(ch_url)
        ch_items = (ch_data or {}).get("items") or []
        if ch_items and isinstance(ch_items[0], dict):
            ch_stats = ch_items[0].get("statistics") or {}
            if ch_stats.get("subscriberCount") and str(ch_stats["subscriberCount"]).isdigit():
                meta["youtube_subscribers"] = int(ch_stats["subscriberCount"])
    return meta


def fetch_youtube_comments_api(
    video_id: str,
    api_key: str,
    json_fetcher: JsonFetcher = default_json_fetcher,
    max_comments: int = 50,
) -> List[Dict[str, Any]]:
    """Fetch up to 50 public top-level comments via official YouTube Data API v3."""
    if not video_id or not api_key:
        return []
    url = (
        "https://www.googleapis.com/youtube/v3/commentThreads?"
        + urlencode(
            {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": str(min(max_comments, 50)),
                "order": "relevance",
                "textFormat": "plainText",
                "key": api_key,
            }
        )
    )
    data = json_fetcher(url)
    items = (data or {}).get("items") or []
    comments: List[Dict[str, Any]] = []
    for item in items:
        top = ((item.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {}
        text = str(top.get("textDisplay") or "").strip()
        if not text:
            continue
        comments.append(
            {
                "text": text,
                "author": str(top.get("authorDisplayName") or "unknown"),
                "channel_url": top.get("authorChannelUrl"),
                "is_verified": False,
                "role_hint": None,
            }
        )
        if len(comments) >= max_comments:
            break
    return comments


def fetch_youtube_comments_keyless(
    watch_url: str,
    text_fetcher: TextFetcher = default_text_fetcher,
    max_comments: int = 50,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """Fetch public YouTube comments without an API key via YouTube's public innertube endpoint."""
    raw_html = text_fetcher(watch_url)
    if not raw_html:
        return []
    key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', raw_html)
    tokens = re.findall(r'"continuationCommand"\s*:\s*\{\s*"token"\s*:\s*"([^"]+)"', raw_html)
    if not key_match or not tokens:
        return []

    api_key = key_match.group(1)
    # Comment continuation tokens are compact (<400 chars); try them first
    candidate_tokens = [t for t in tokens if len(t) < 400] + [t for t in tokens if len(t) >= 400]

    for token in candidate_tokens[:4]:
        payload = json.dumps(
            {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20241101.00.00",
                        "hl": "en",
                        "gl": "US",
                    }
                },
                "continuation": token,
            }
        ).encode("utf-8")
        req = Request(
            f"https://www.youtube.com/youtubei/v1/next?key={quote(api_key)}",
            data=payload,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            continue

        comments: List[Dict[str, Any]] = []
        mutations = (
            (data.get("frameworkUpdates") or {})
            .get("entityBatchUpdate", {})
            .get("mutations")
            or []
        )
        for mut in mutations:
            entity = (mut.get("payload") or {}).get("commentEntityPayload")
            if not isinstance(entity, dict):
                continue
            props = entity.get("properties") or {}
            author_obj = entity.get("author") or {}
            text = ((props.get("content") or {}).get("content") or "").strip()
            if not text:
                continue
            author = str(author_obj.get("displayName") or "unknown")
            channel_id = author_obj.get("channelId")
            comments.append(
                {
                    "text": text,
                    "author": author,
                    "channel_url": f"https://www.youtube.com/channel/{channel_id}" if channel_id else None,
                    "is_verified": bool(author_obj.get("isVerified") or author_obj.get("isCreator")),
                    "role_hint": "creator_or_verified" if (author_obj.get("isVerified") or author_obj.get("isCreator")) else None,
                }
            )
            if len(comments) >= max_comments:
                break
        if comments:
            return comments
    return []


def scrub_emails(text: Optional[str]) -> Optional[str]:
    """Remove raw email addresses from public text so PII never leaks into dossiers."""
    if not text:
        return text
    return EMAIL_RE.sub("[redacted-email]", text)


def detect_contact_route(bio_text: str) -> Tuple[bool, str]:
    """Determine public business contact route without exposing raw PII."""
    lower = (bio_text or "").lower()
    emails = EMAIL_RE.findall(bio_text or "")
    if emails:
        if any(
            token in lower
            for token in ("mgmt", "management", "booking", "agent", "press", "inquiries")
        ):
            for addr in emails:
                if any(k in addr.lower() for k in ("mgmt", "management", "booking", "agent")):
                    return True, "mgmt_email"
            if "mgmt" in lower or "management" in lower:
                return True, "mgmt_email"
        return True, "bio_email"
    if any(token in lower for token in ("dm for booking", "dms open", "dm me", "open dm")):
        return True, "open_dm"
    return False, "none"


def classify_platform_urls(urls: List[str]) -> Dict[str, Optional[str]]:
    """Map discovered public URLs into canonical platform_urls slots."""
    slots: Dict[str, Optional[str]] = {k: None for k in PLATFORM_HOSTS}
    for raw in urls:
        cleaned = raw.rstrip(".,);]")
        lower = cleaned.lower()
        for slot, hosts in PLATFORM_HOSTS.items():
            if slots[slot] is None and any(host in lower for host in hosts):
                slots[slot] = cleaned
                break
    return slots


def extract_city_and_neighborhood(bio_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract objective location mentions from a public bio."""
    if not bio_text:
        return None, None
    neighborhoods = (
        "Bushwick",
        "Williamsburg",
        "Bed-Stuy",
        "Greenpoint",
        "Lower East Side",
        "East Village",
        "Harlem",
        "Astoria",
        "Ridgewood",
        "Crown Heights",
        "Silver Lake",
        "Echo Park",
    )
    found_neighborhood = None
    for hood in neighborhoods:
        if re.search(rf"\b{re.escape(hood)}\b", bio_text, re.IGNORECASE):
            found_neighborhood = hood
            break

    cities = (
        ("New York, NY", (r"\bNYC\b", r"\bNew York City\b", r"\bNew York,\s*NY\b", r"\bBrooklyn\b", r"\bManhattan\b", r"\bQueens\b")),
        ("Los Angeles, CA", (r"\bLos Angeles\b", r"\bLA,\s*CA\b")),
        ("Chicago, IL", (r"\bChicago\b",)),
        ("Nashville, TN", (r"\bNashville\b",)),
        ("London, UK", (r"\bLondon\b",)),
        ("Jersey City, NJ", (r"\bJersey City\b", r"\bHoboken\b")),
    )
    found_city = None
    for canonical, patterns in cities:
        if any(re.search(pat, bio_text, re.IGNORECASE) for pat in patterns):
            found_city = canonical
            break
    if found_neighborhood and not found_city and found_neighborhood not in ("Silver Lake", "Echo Park"):
        found_city = "New York, NY"
    return found_city, found_neighborhood


def detect_project_type(bio_text: str) -> str:
    lower = (bio_text or "").lower()
    if any(tok in lower for tok in ("collective", "ensemble", "choir")):
        return "collective"
    if any(tok in lower for tok in ("duo", "two-piece", "2-piece")):
        return "duo"
    if any(tok in lower for tok in ("four-piece", "three-piece", "band", "quartet", "trio")):
        return "band"
    if any(tok in lower for tok in ("vocalist", "singer", "songwriter", "solo artist")):
        return "solo_vocalist"
    return "unknown"


def extract_genres(bio_text: str) -> Tuple[Optional[str], List[str]]:
    lower = (bio_text or "").lower()
    found: List[str] = []
    for needle, label in MUSIC_GENRE_KEYWORDS:
        if needle in lower and label not in found:
            found.append(label)
    if not found:
        return None, []
    return found[0], found[1:4]


def compute_top_release_view_share_pct(view_counts: List[int]) -> Optional[float]:
    """Deterministic Python math: share of views held by top release (None if < 2 releases)."""
    valid = [int(v) for v in view_counts if isinstance(v, (int, float)) and v >= 0]
    if len(valid) < 2:
        return None
    total = sum(valid)
    if total <= 0:
        return None
    return round((max(valid) / total) * 100.0, 1)


def classify_footprint_regime(
    platform_urls: Dict[str, Optional[str]],
    public_reach: Dict[str, Optional[int]],
) -> str:
    """Sparsity-aware footprint regime from objective public signals only."""
    has_dsp = bool(platform_urls.get("spotify") or platform_urls.get("apple_music"))
    released = public_reach.get("released_tracks_count")
    yt_subs = public_reach.get("youtube_subscribers")
    top_views = public_reach.get("top_video_views")
    bc_releases = public_reach.get("bandcamp_releases_count")

    if not has_dsp and (released in (None, 0)) and (bc_releases in (None, 0)):
        return "pre_dsp_underground"
    if (yt_subs is not None and yt_subs >= 50_000) or (top_views is not None and top_views >= 500_000):
        return "established_streaming"
    if has_dsp or (released and released > 0) or (bc_releases and bc_releases > 0):
        return "early_dsp_inflection"
    if yt_subs is not None or top_views is not None:
        return "pre_dsp_underground"
    return "unknown"


def classify_comments_single_pass(
    comments: List[Dict[str, Any]],
    max_sample: int = 50,
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    """Single-pass merged classifier: generic (praise, spam) + music (release, live) buckets."""
    sampled = comments[:max_sample]
    counts = {
        "sample_size": len(sampled),
        "release_requests": 0,
        "live_show_requests": 0,
        "genuine_praise": 0,
        "jokes_or_spam": 0,
    }
    notable: List[Dict[str, Any]] = []

    for item in sampled:
        text = str(item.get("text") or "").strip()
        lower = text.lower()
        # Mutually exclusive classification order: spam -> release -> live -> genuine praise
        if any(m in lower for m in SPAM_OR_JOKE_MARKERS) or len(text) < 4:
            counts["jokes_or_spam"] += 1
        elif any(m in lower for m in RELEASE_REQUEST_MARKERS):
            counts["release_requests"] += 1
        elif any(m in lower for m in LIVE_SHOW_REQUEST_MARKERS):
            counts["live_show_requests"] += 1
        else:
            counts["genuine_praise"] += 1

        if item.get("is_verified") or item.get("role_hint"):
            notable.append(
                {
                    "handle": str(item.get("author") or "unknown"),
                    "channel_url": item.get("channel_url"),
                    "role_or_context": str(item.get("role_hint") or "verified_channel"),
                    "comment_excerpt": text[:160] if text else None,
                }
            )

    return counts, notable


def parse_public_team_mentions(text: str) -> Dict[str, Optional[str]]:
    """Extract explicit representation/label/distributor mentions only when written in text."""
    mentions: Dict[str, Optional[str]] = {
        "management": None,
        "booking_agent": None,
        "label": None,
        "distributor": None,
    }
    if not text:
        return mentions

    patterns = {
        "management": r"(?:management|mgmt)\s*[:\-]\s*([^\n|•;]+)",
        "booking_agent": r"(?:booking(?:\s+agent)?|agent)\s*[:\-]\s*([^\n|•;]+)",
        "label": r"(?:label|released\s+on)\s*[:\-]\s*([^\n|•;]+)",
        "distributor": r"(?:distributed\s+by|distributor)\s*[:\-]\s*([^\n|•;]+)",
    }
    for key, pat in patterns.items():
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            val = scrub_emails(match.group(1).strip())
            if val and val != "[redacted-email]":
                mentions[key] = val

    # Check common indie distributor names if explicitly referenced
    if not mentions["distributor"]:
        for dist in ("DistroKid", "AWAL", "Stem", "TuneCore", "CD Baby", "UnitedMasters", "Amuse"):
            if re.search(rf"\b{re.escape(dist)}\b", text, re.IGNORECASE):
                mentions["distributor"] = dist
                break

    # Check explicit major/indie label names or copyright lines if label wasn't prefixed
    if not mentions["label"]:
        known_labels = (
            "Sony Music Entertainment",
            "RCA Records",
            "Columbia Records",
            "Atlantic Records",
            "Republic Records",
            "Interscope Records",
            "Universal Music Group",
            "Warner Records",
            "Def Jam",
            "Capitol Records",
            "Sub Pop",
            "4AD",
            "Matador Records",
            "Secretly Canadian",
            "Domino Recording",
            "Ninja Tune",
            "Stones Throw",
        )
        for lbl in known_labels:
            if re.search(rf"\b{re.escape(lbl)}\b", text, re.IGNORECASE):
                mentions["label"] = lbl
                break
    return mentions


def parse_collaborator_credits(text: str, source_url: Optional[str]) -> List[Dict[str, Any]]:
    """Extract explicit collaborator credits (producer, mix, master, writer, etc.) from text."""
    credits: List[Dict[str, Any]] = []
    if not text:
        return credits
    role_patterns = (
        ("producer", r"produced\s+by\s+([^\n|•;.]+)"),
        ("mixer", r"mixed\s+by\s+([^\n|•;.]+)"),
        ("mastering_engineer", r"mastered\s+by\s+([^\n|•;.]+)"),
        ("songwriter", r"written\s+by\s+([^\n|•;.]+)"),
        ("guitarist", r"guitar\s*[:\-]\s*([^\n|•;.]+)"),
    )
    seen = set()
    for role, pat in role_patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            name = match.group(1).strip(" .,-")
            if name and (name.lower(), role) not in seen:
                seen.add((name.lower(), role))
                credits.append({"name": name, "role": role, "source_url": source_url})
    return credits


def lookup_highest_venue_cap(shows: List[Dict[str, Any]]) -> Optional[int]:
    """Look up public room capacity for verified venues in show_history."""
    caps: List[int] = []
    for show in shows:
        venue_raw = str(show.get("venue") or "").strip().lower()
        if not venue_raw:
            continue
        if venue_raw in KNOWN_VENUE_CAPS:
            caps.append(KNOWN_VENUE_CAPS[venue_raw])
            continue
        for known_name, cap in KNOWN_VENUE_CAPS.items():
            if known_name in venue_raw:
                caps.append(cap)
                break
    return max(caps) if caps else None


@dataclass
class MusicDomainPack:
    """Layer 2 Music Domain Pack plugged into Layer 1's 4-agent InvestigatorPipeline."""

    domain: str = "music"
    text_fetcher: TextFetcher = default_text_fetcher
    json_fetcher: JsonFetcher = default_json_fetcher
    # Optional structured fixture overrides for deterministic offline evals
    page_fixtures: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    musicbrainz_fixtures: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    oembed_fixtures: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    bandcamp_fixtures: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    comment_fixtures: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    show_fixtures: Dict[str, Dict[str, List[Dict[str, Any]]]] = field(default_factory=dict)
    # Private per-run hints shared across Phase A -> Phase B (never leaked into dossier schema)
    _runtime_hints: Dict[str, Dict[str, Any]] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Agent 1: identity-resolver (1a Generic -> 1b Music Domain)
    # ------------------------------------------------------------------
    def resolve_identity_generic(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        seed_sources = lead.get("seed_sources") or []
        primary_seed = seed_sources[0] if seed_sources else {}
        seed_url = primary_seed.get("url", "")
        stage_name = str(lead.get("stage_name") or "").strip()
        lead_key = str(lead.get("lead_id") or stage_name).lower()
        hints = self._runtime_hints.setdefault(lead_key, {"tour_urls": [], "extra_credits": [], "extra_desc": ""})

        page = self.page_fixtures.get(seed_url)
        evidence_urls: List[str] = []
        raw_bio = ""
        outbound_urls: List[str] = [s.get("url", "") for s in seed_sources if s.get("url")]

        if page is not None:
            raw_bio = str(page.get("bio_text") or "")
            outbound_urls.extend(page.get("outbound_urls") or [])
            evidence_urls.append(seed_url)
        elif seed_url:
            html = self.text_fetcher(seed_url)
            if html:
                evidence_urls.append(seed_url)
                raw_bio = extract_clean_bio_from_html(html)
                extracted_links = extract_hrefs_from_html(html, seed_url)
                outbound_urls.extend(extracted_links)
                for link in extracted_links:
                    low = link.lower()
                    if any(tok in low for tok in ("/tour", "/shows", "/live", "bandsintown", "songkick", "seated.com")):
                        if link not in hints["tour_urls"]:
                            hints["tour_urls"].append(link)

        # Follow one hop into Linktree / bio aggregator if present
        platform_urls = classify_platform_urls(outbound_urls)
        linktree_url = platform_urls.get("linktree")
        if linktree_url and linktree_url in self.page_fixtures:
            lt_page = self.page_fixtures[linktree_url]
            evidence_urls.append(linktree_url)
            outbound_urls.extend(lt_page.get("outbound_urls") or [])
            if lt_page.get("bio_text"):
                raw_bio = (raw_bio + "\n" + str(lt_page["bio_text"])).strip()
            platform_urls = classify_platform_urls(outbound_urls)
        elif linktree_url and not self.page_fixtures:
            lt_html = self.text_fetcher(linktree_url)
            if lt_html:
                evidence_urls.append(linktree_url)
                outbound_urls.extend(URL_RE.findall(lt_html))
                platform_urls = classify_platform_urls(outbound_urls)

        has_contact, contact_route = detect_contact_route(raw_bio)
        pronouns_match = PRONOUNS_RE.search(raw_bio)
        pronouns = pronouns_match.group(1).lower() if pronouns_match else None
        home_city, home_neighborhood = extract_city_and_neighborhood(raw_bio)

        # Keep Kevin's verified attribution unless uncertain or contradicted
        attribution_status = lead.get("attribution_status", "uncertain")
        if page and page.get("verified_artist_match") is True:
            attribution_status = "verified"
        elif page and page.get("verified_artist_match") is False:
            attribution_status = "uncertain"

        missing: List[str] = []
        if not pronouns:
            missing.append("identity_and_contact.pronouns")
        if not home_city:
            missing.append("identity_and_contact.home_city")
        if not home_neighborhood:
            missing.append("identity_and_contact.home_neighborhood")
        if not raw_bio:
            missing.append("source_and_media_queue.bio_text")

        return {
            "stage_name": stage_name,
            "aliases": list(page.get("aliases") or []) if page else [],
            "pronouns": pronouns,
            "home_city": home_city,
            "home_neighborhood": home_neighborhood,
            "platform_urls": platform_urls,
            "has_public_business_contact": has_contact,
            "contact_route_type": contact_route,
            "bio_text": scrub_emails(raw_bio) if raw_bio else None,
            "raw_bio_for_internal_parse": raw_bio,
            "source_channel": primary_seed.get("source_channel", "other"),
            "seed_source_url": seed_url,
            "attribution_status": attribution_status,
            "trace": {
                "step": "1a_identity_generic",
                "tool": "extract_bio_and_links",
                "status": "ok" if evidence_urls else "empty",
                "evidence_urls": evidence_urls,
                "notes": f"Expanded {len(outbound_urls)} outbound link(s); PII scrubbed.",
            },
            "missing_fields": missing,
            "newly_discovered_sources": [],
        }

    def resolve_identity_domain(
        self, lead: Dict[str, Any], generic_identity: Dict[str, Any]
    ) -> Dict[str, Any]:
        stage_name = generic_identity["stage_name"]
        bio_text = generic_identity.get("bio_text") or ""
        project_type = detect_project_type(bio_text)
        primary_genre, subgenres = extract_genres(bio_text)

        # Query public MusicBrainz WS/2 API using canonical stage_name + home_city from 1a
        mbid: Optional[str] = None
        aliases = list(generic_identity.get("aliases") or [])
        mb_evidence: List[str] = []
        mb_status = "empty"
        lead_key = str(lead.get("lead_id") or stage_name).lower()
        hints = self._runtime_hints.setdefault(lead_key, {"tour_urls": [], "extra_credits": [], "extra_desc": ""})

        mb_data = self.musicbrainz_fixtures.get(stage_name.lower())
        if mb_data is None and not self.musicbrainz_fixtures:
            mb_url = (
                "https://musicbrainz.org/ws/2/artist/?"
                + urlencode({"query": f"artist:{stage_name}", "fmt": "json", "limit": "3"})
            )
            mb_data = self.json_fetcher(mb_url)

        if isinstance(mb_data, dict):
            artists = mb_data.get("artists") or []
            if artists:
                top = artists[0]
                mbid = top.get("id")
                mb_status = "ok" if mbid else "empty"
                if mbid:
                    mb_artist_url = f"https://musicbrainz.org/artist/{quote(str(mbid))}"
                    mb_evidence.append(mb_artist_url)
                # Map MusicBrainz artist type if bio didn't specify project_type
                if project_type == "unknown":
                    mb_type = str(top.get("type") or "").lower()
                    if mb_type == "person":
                        project_type = "solo_vocalist"
                    elif mb_type == "group":
                        project_type = "band"
                # Fallback home_city from MusicBrainz begin-area / area
                if not generic_identity.get("home_city"):
                    begin_area = (top.get("begin-area") or {}).get("name")
                    area = (top.get("area") or {}).get("name")
                    if begin_area:
                        generic_identity["home_city"] = str(begin_area)
                        if "identity_and_contact.home_city" in generic_identity["missing_fields"]:
                            generic_identity["missing_fields"].remove("identity_and_contact.home_city")
                    elif area:
                        generic_identity["home_city"] = str(area)
                        if "identity_and_contact.home_city" in generic_identity["missing_fields"]:
                            generic_identity["missing_fields"].remove("identity_and_contact.home_city")
                # Pull genres/tags from MusicBrainz if bio didn't specify them
                if not primary_genre and top.get("tags"):
                    sorted_tags = sorted(
                        (t for t in top["tags"] if isinstance(t, dict) and t.get("name")),
                        key=lambda t: int(t.get("count") or 0),
                        reverse=True,
                    )
                    tag_names = [str(t["name"]).title() for t in sorted_tags]
                    if tag_names:
                        primary_genre = tag_names[0]
                        subgenres = tag_names[1:4]
                for alias in top.get("aliases") or []:
                    alias_name = alias.get("name") if isinstance(alias, dict) else str(alias)
                    if alias_name and alias_name not in aliases and alias_name.lower() != stage_name.lower():
                        aliases.append(alias_name)

                # Second MusicBrainz lookup for official URL relationships & artist credits (live only)
                if mbid and not self.musicbrainz_fixtures:
                    detail_url = (
                        f"https://musicbrainz.org/ws/2/artist/{quote(str(mbid))}"
                        "?inc=url-rels+artist-rels+tags&fmt=json"
                    )
                    detail = self.json_fetcher(detail_url)
                    if isinstance(detail, dict):
                        rel_urls: List[str] = []
                        for rel in detail.get("relations") or []:
                            if not isinstance(rel, dict):
                                continue
                            if rel.get("url") and isinstance(rel["url"], dict):
                                res_url = rel["url"].get("resource")
                                if isinstance(res_url, str):
                                    rel_urls.append(res_url)
                            elif rel.get("artist") and isinstance(rel["artist"], dict):
                                rel_artist_name = rel["artist"].get("name")
                                rel_type = str(rel.get("type") or "collaborator")
                                if rel_artist_name:
                                    hints["extra_credits"].append(
                                        {
                                            "name": str(rel_artist_name),
                                            "role": rel_type,
                                            "source_url": f"https://musicbrainz.org/artist/{quote(str(mbid))}",
                                        }
                                    )
                        if rel_urls:
                            merged_platforms = classify_platform_urls(rel_urls)
                            for k, v in merged_platforms.items():
                                if v and not generic_identity["platform_urls"].get(k):
                                    generic_identity["platform_urls"][k] = v

        missing: List[str] = []
        if not mbid:
            missing.append("identity_and_contact.musicbrainz_mbid")
        if not primary_genre:
            missing.append("source_and_media_queue.primary_genre")

        return {
            "project_type": project_type,
            "primary_genre": primary_genre,
            "subgenres": subgenres,
            "musicbrainz_mbid": mbid,
            "aliases": aliases,
            "trace": {
                "step": "1b_identity_domain",
                "tool": "query_musicbrainz_and_music_taxonomy",
                "status": mb_status if mb_evidence or primary_genre else "empty",
                "evidence_urls": mb_evidence,
                "notes": f"project_type={project_type}, primary_genre={primary_genre}, mbid={'found' if mbid else 'none'}",
            },
            "missing_fields": missing,
            "newly_discovered_sources": [],
        }

    # ------------------------------------------------------------------
    # Agent 2: footprint-profiler (2a Generic || 2b Music Domain -> Python math)
    # ------------------------------------------------------------------
    def profile_footprint_generic(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]:
        seed_url = identity_bundle["source_and_media_queue"]["seed_source_url"]
        yt_url = identity_bundle["identity_and_contact"]["platform_urls"].get("youtube")
        candidate_urls: List[str] = []
        for u in (seed_url, yt_url):
            if u and extract_video_id(u):
                canon = canonical_watch_url(u)
                if canon not in candidate_urls:
                    candidate_urls.append(canon)
        # Also include any additional YouTube video fixtures keyed under this channel/lead
        page = self.page_fixtures.get(seed_url) or {}
        for extra in page.get("media_urls") or []:
            if extract_video_id(extra):
                canon = canonical_watch_url(extra)
                if canon not in candidate_urls:
                    candidate_urls.append(canon)

        media_links: List[Dict[str, Any]] = []
        view_counts: List[int] = []
        yt_subscribers: Optional[int] = page.get("youtube_subscribers")
        evidence_urls: List[str] = []

        lead_key = str(identity_bundle.get("lead_id") or "").lower()
        hints = self._runtime_hints.setdefault(lead_key, {"tour_urls": [], "extra_credits": [], "extra_desc": ""})
        yt_api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()

        for url in candidate_urls:
            oembed = self.oembed_fixtures.get(url)
            watch_meta: Dict[str, Any] = {}
            if oembed is None and not self.oembed_fixtures:
                vid_id = extract_video_id(url)
                if yt_api_key and vid_id:
                    watch_meta = fetch_youtube_video_and_channel_api(
                        vid_id, yt_api_key, json_fetcher=self.json_fetcher
                    )
                    if watch_meta:
                        oembed = watch_meta
                        if watch_meta.get("description"):
                            hints["extra_desc"] = (hints.get("extra_desc", "") + "\n" + watch_meta["description"]).strip()
                        if yt_subscribers is None and isinstance(watch_meta.get("youtube_subscribers"), int):
                            yt_subscribers = watch_meta["youtube_subscribers"]
                if oembed is None:
                    oembed_url = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
                    oembed = self.json_fetcher(oembed_url)
                    watch_html = self.text_fetcher(url)
                    if watch_html:
                        watch_meta = parse_youtube_watch_metadata(watch_html)
                        if watch_meta.get("description"):
                            hints["extra_desc"] = (hints.get("extra_desc", "") + "\n" + watch_meta["description"]).strip()
                        if yt_subscribers is None and isinstance(watch_meta.get("youtube_subscribers"), int):
                            yt_subscribers = watch_meta["youtube_subscribers"]
            if isinstance(oembed, dict):
                evidence_urls.append(url)
                duration_sec = oembed.get("duration_seconds")
                if duration_sec is None:
                    duration_sec = watch_meta.get("duration_seconds")
                media_links.append(
                    {
                        "url": url,
                        "title": str(oembed.get("title") or "Untitled video"),
                        "uploader_channel": oembed.get("author_name"),
                        "duration_seconds": duration_sec,
                        "oembed_live_embeddable": bool(oembed.get("embeddable", True)),
                    }
                )
                vc = oembed.get("view_count")
                if not isinstance(vc, int):
                    vc = watch_meta.get("view_count")
                if isinstance(vc, int):
                    view_counts.append(vc)

        top_views = max(view_counts) if view_counts else None
        missing: List[str] = []
        if yt_subscribers is None:
            missing.append("public_footprint.public_reach.youtube_subscribers")
        if top_views is None:
            missing.append("public_footprint.public_reach.top_video_views")

        return {
            "media_links": media_links,
            "youtube_subscribers": yt_subscribers,
            "top_video_views": top_views,
            "view_counts": view_counts,
            "trace": {
                "step": "2a_footprint_generic",
                "tool": "collect_youtube_oembed_and_reach",
                "status": "ok" if media_links else "empty",
                "evidence_urls": evidence_urls,
                "notes": f"Verified {len(media_links)} oEmbed media link(s) with zero decoding.",
            },
            "missing_fields": missing,
            "newly_discovered_sources": [],
        }

    def profile_footprint_domain(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]:
        bc_url = identity_bundle["identity_and_contact"]["platform_urls"].get("bandcamp")
        bc_data = self.bandcamp_fixtures.get(bc_url) if bc_url else None
        evidence_urls: List[str] = []
        bc_releases: Optional[int] = None
        bc_supporters: Optional[int] = None
        released_tracks: Optional[int] = None

        if isinstance(bc_data, dict) and bc_url:
            evidence_urls.append(bc_url)
            bc_releases = bc_data.get("bandcamp_releases_count")
            bc_supporters = bc_data.get("bandcamp_supporters_count")
            released_tracks = bc_data.get("released_tracks_count")
        elif bc_url and not self.bandcamp_fixtures:
            html = self.text_fetcher(bc_url)
            if html:
                evidence_urls.append(bc_url)
                bc_releases = len(re.findall(r'class="music-grid-item', html)) or None

        missing: List[str] = []
        if bc_releases is None:
            missing.append("public_footprint.public_reach.bandcamp_releases_count")
        if bc_supporters is None:
            missing.append("public_footprint.public_reach.bandcamp_supporters_count")
        if released_tracks is None:
            missing.append("public_footprint.public_reach.released_tracks_count")

        return {
            "bandcamp_releases_count": bc_releases,
            "bandcamp_supporters_count": bc_supporters,
            "released_tracks_count": released_tracks,
            "trace": {
                "step": "2b_footprint_domain",
                "tool": "collect_bandcamp_public_counts",
                "status": "ok" if evidence_urls else "empty",
                "evidence_urls": evidence_urls,
                "notes": f"bandcamp_url={'present' if bc_url else 'absent'}",
            },
            "missing_fields": missing,
            "newly_discovered_sources": [],
        }

    # ------------------------------------------------------------------
    # Agent 3: signal-forensics (Fetch once -> 1-pass merged classifier)
    # ------------------------------------------------------------------
    def run_signal_forensics(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]:
        seed_url = identity_bundle["source_and_media_queue"]["seed_source_url"]
        yt_url = identity_bundle["identity_and_contact"]["platform_urls"].get("youtube")
        target_url = seed_url

        if self.comment_fixtures:
            comments = self.comment_fixtures.get(seed_url, [])
        else:
            comments = []
            # Prefer a canonical YouTube watch URL for keyless innertube comment fetch
            yt_watch = None
            for candidate in (seed_url, yt_url):
                if candidate and extract_video_id(candidate):
                    yt_watch = canonical_watch_url(candidate)
                    break
            if yt_watch:
                target_url = yt_watch
                yt_api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
                vid_id = extract_video_id(yt_watch)
                if yt_api_key and vid_id:
                    comments = fetch_youtube_comments_api(
                        vid_id, yt_api_key, json_fetcher=self.json_fetcher, max_comments=50
                    )
                if not comments:
                    comments = fetch_youtube_comments_keyless(
                        yt_watch, text_fetcher=self.text_fetcher, max_comments=50
                    )

        counts, notable = classify_comments_single_pass(comments, max_sample=50)
        missing: List[str] = []
        if counts["sample_size"] == 0:
            missing.append("comment_forensics")
        return {
            "comment_intent_counts": counts,
            "notable_commenters": notable,
            "trace": {
                "step": "3_signal_forensics",
                "tool": "classify_comments_single_pass",
                "status": "ok" if counts["sample_size"] > 0 else "empty",
                "evidence_urls": [target_url] if counts["sample_size"] > 0 and target_url else [],
                "notes": f"Classified {counts['sample_size']} comment(s) in 1 pass.",
            },
            "missing_fields": missing,
            "newly_discovered_sources": [],
        }

    # ------------------------------------------------------------------
    # Agent 4: track-record-mapper (4a Generic || 4b Music Domain)
    # ------------------------------------------------------------------
    def map_track_record_generic(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]:
        bio_text = identity_bundle["source_and_media_queue"].get("bio_text") or ""
        seed_url = identity_bundle["source_and_media_queue"].get("seed_source_url")
        yt_url = identity_bundle["identity_and_contact"]["platform_urls"].get("youtube")

        combined_text = bio_text
        evidence_urls: List[str] = []
        if seed_url:
            evidence_urls.append(seed_url)

        # Live YouTube description scan (keyless) when running without fixtures
        if not self.page_fixtures and yt_url and extract_video_id(yt_url):
            yt_watch = canonical_watch_url(yt_url)
            watch_html = self.text_fetcher(yt_watch)
            if watch_html:
                desc = parse_youtube_watch_metadata(watch_html).get("description") or ""
                if desc:
                    combined_text = (combined_text + "\n" + desc).strip()
                    if yt_watch not in evidence_urls:
                        evidence_urls.append(yt_watch)

        mentions = parse_public_team_mentions(combined_text)
        credits = parse_collaborator_credits(combined_text, yt_url or seed_url)
        missing: List[str] = []
        for field_name, value in mentions.items():
            if value is None:
                missing.append(f"live_history_and_credits.public_team_mentions.{field_name}")
        return {
            "public_team_mentions": mentions,
            "collaborator_credits": credits,
            "trace": {
                "step": "4a_track_record_generic",
                "tool": "extract_team_mentions_and_credits",
                "status": "ok" if (any(mentions.values()) or credits) else "empty",
                "evidence_urls": evidence_urls if (any(mentions.values()) or credits) else [],
                "notes": f"Found {sum(1 for v in mentions.values() if v)} team mention(s) and {len(credits)} bio/video credit(s).",
            },
            "missing_fields": missing,
            "newly_discovered_sources": [],
        }

    def map_track_record_domain(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]:
        stage_name = identity_bundle["identity_and_contact"]["stage_name"]
        lead_key = str(identity_bundle.get("lead_id") or stage_name).lower()
        hints = self._runtime_hints.get(lead_key) or {}
        fixture = self.show_fixtures.get(stage_name.lower()) or {}
        show_history = list(fixture.get("show_history") or [])
        upcoming_shows = list(fixture.get("upcoming_shows") or [])
        domain_credits = list(fixture.get("collaborator_credits") or []) + list(hints.get("extra_credits") or [])

        discovered_sources: List[Dict[str, Any]] = []
        seen_src = set()

        # Live tour-page & MusicBrainz recording/event lookups when no show fixtures are provided
        if not self.show_fixtures:
            mbid = identity_bundle["identity_and_contact"].get("musicbrainz_mbid")
            if mbid and not self.musicbrainz_fixtures:
                # 1. Recording-level collaborator credits (producers, writers, engineers, musicians)
                rec_url = (
                    "https://musicbrainz.org/ws/2/recording?"
                    + urlencode({"artist": mbid, "inc": "artist-rels", "limit": "10", "fmt": "json"})
                )
                rec_data = self.json_fetcher(rec_url)
                if isinstance(rec_data, dict):
                    seen_cred = set()
                    for rec in rec_data.get("recordings") or []:
                        rec_id = rec.get("id")
                        rec_src = (
                            f"https://musicbrainz.org/recording/{quote(str(rec_id))}"
                            if rec_id
                            else f"https://musicbrainz.org/artist/{quote(str(mbid))}"
                        )
                        for rel in rec.get("relations") or []:
                            art = rel.get("artist") if isinstance(rel, dict) else None
                            if not isinstance(art, dict):
                                continue
                            name = str(art.get("name") or "").strip()
                            role = str(rel.get("type") or "collaborator").strip()
                            if (
                                name
                                and name.lower() != stage_name.lower()
                                and (name.lower(), role.lower()) not in seen_cred
                            ):
                                seen_cred.add((name.lower(), role.lower()))
                                domain_credits.append(
                                    {"name": name, "role": role, "source_url": rec_src}
                                )
                                if len(domain_credits) >= 15:
                                    break
                        if len(domain_credits) >= 15:
                            break

                # 2. Public MusicBrainz live event history
                evt_url = (
                    "https://musicbrainz.org/ws/2/event?"
                    + urlencode({"artist": mbid, "inc": "place-rels", "limit": "10", "fmt": "json"})
                )
                evt_data = self.json_fetcher(evt_url)
                if isinstance(evt_data, dict):
                    for evt in evt_data.get("events") or []:
                        evt_id = evt.get("id")
                        evt_src = (
                            f"https://musicbrainz.org/event/{quote(str(evt_id))}"
                            if evt_id
                            else f"https://musicbrainz.org/artist/{quote(str(mbid))}"
                        )
                        begin = ((evt.get("life-span") or {}).get("begin") or "").strip()
                        venue_name = str(evt.get("name") or "").strip()
                        city_name = "Unknown"
                        for rel in evt.get("relations") or []:
                            place = rel.get("place") if isinstance(rel, dict) else None
                            if isinstance(place, dict) and place.get("name"):
                                venue_name = str(place["name"])
                                area = place.get("area")
                                if isinstance(area, dict) and area.get("name"):
                                    city_name = str(area["name"])
                                break
                        if venue_name and begin:
                            show_history.append(
                                {
                                    "venue": venue_name,
                                    "city": city_name,
                                    "date": begin,
                                    "billing_slot": "unknown",
                                    "source_url": evt_src,
                                }
                            )

            for tour_url in hints.get("tour_urls") or []:
                tour_html = self.text_fetcher(tour_url)
                if tour_html:
                    parsed_events = parse_jsonld_music_events(tour_html, tour_url)
                    upcoming_shows.extend(parsed_events)
                    if tour_url not in seen_src:
                        seen_src.add(tour_url)
                        discovered_sources.append(
                            {
                                "url": tour_url,
                                "source_channel": "event_listing",
                                "title_or_node": f"{stage_name} Tour Page",
                                "why_useful": "Official artist tour/shows page discovered from seed website.",
                                "discovered_by": "stage_2_investigator",
                            }
                        )

        highest_cap = lookup_highest_venue_cap(show_history)

        evidence_urls = [
            s["source_url"]
            for s in (show_history + upcoming_shows + domain_credits)
            if isinstance(s, dict) and s.get("source_url")
        ]
        if discovered_sources:
            evidence_urls.extend(d["url"] for d in discovered_sources if d.get("url"))

        for show in show_history + upcoming_shows:
            src = show.get("source_url")
            if src and src not in seen_src:
                seen_src.add(src)
                discovered_sources.append(
                    {
                        "url": src,
                        "source_channel": "event_listing",
                        "title_or_node": show.get("venue"),
                        "why_useful": f"Public bill listing for {show.get('venue')} ({show.get('city')}).",
                        "discovered_by": "stage_2_investigator",
                    }
                )

        missing: List[str] = []
        if not show_history:
            missing.append("live_history_and_credits.show_history")
        if not upcoming_shows:
            missing.append("live_history_and_credits.upcoming_shows")
        if highest_cap is None:
            missing.append("live_history_and_credits.highest_venue_cap_observed")

        return {
            "show_history": show_history,
            "upcoming_shows": upcoming_shows,
            "highest_venue_cap_observed": highest_cap,
            "collaborator_credits": domain_credits,
            "trace": {
                "step": "4b_track_record_domain",
                "tool": "query_public_shows_and_venue_caps",
                "status": "ok" if (show_history or upcoming_shows or domain_credits) else "empty",
                "evidence_urls": list(dict.fromkeys(evidence_urls)),
                "notes": f"Found {len(show_history)} past show(s), {len(upcoming_shows)} upcoming, highest_cap={highest_cap}.",
            },
            "missing_fields": missing,
            "newly_discovered_sources": discovered_sources,
        }
