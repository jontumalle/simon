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
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .youtube import canonical_watch_url, extract_video_id

USER_AGENT = "SimonScoutInvestigator/1.0 (https://github.com/jontumalle/simon)"

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


def default_text_fetcher(url: str, timeout: float = 8.0) -> Optional[str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None


def default_json_fetcher(url: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    raw = default_text_fetcher(url, timeout=timeout)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


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

    # ------------------------------------------------------------------
    # Agent 1: identity-resolver (1a Generic -> 1b Music Domain)
    # ------------------------------------------------------------------
    def resolve_identity_generic(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        seed_sources = lead.get("seed_sources") or []
        primary_seed = seed_sources[0] if seed_sources else {}
        seed_url = primary_seed.get("url", "")
        stage_name = str(lead.get("stage_name") or "").strip()

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
                raw_bio = html[:4000]
                outbound_urls.extend(URL_RE.findall(html))

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

        mb_data = self.musicbrainz_fixtures.get(stage_name.lower())
        mb_url = (
            "https://musicbrainz.org/ws/2/artist/?"
            + urlencode({"query": f'artist:"{stage_name}"', "fmt": "json", "limit": "3"})
        )
        if mb_data is None and not self.musicbrainz_fixtures:
            mb_data = self.json_fetcher(mb_url)

        if isinstance(mb_data, dict):
            artists = mb_data.get("artists") or []
            if artists:
                top = artists[0]
                mbid = top.get("id")
                mb_status = "ok" if mbid else "empty"
                if mbid:
                    mb_evidence.append(f"https://musicbrainz.org/artist/{quote(str(mbid))}")
                for alias in top.get("aliases") or []:
                    alias_name = alias.get("name") if isinstance(alias, dict) else str(alias)
                    if alias_name and alias_name not in aliases and alias_name.lower() != stage_name.lower():
                        aliases.append(alias_name)

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

        for url in candidate_urls:
            oembed = self.oembed_fixtures.get(url)
            if oembed is None and not self.oembed_fixtures:
                oembed_url = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
                oembed = self.json_fetcher(oembed_url)
            if isinstance(oembed, dict):
                evidence_urls.append(url)
                media_links.append(
                    {
                        "url": url,
                        "title": str(oembed.get("title") or "Untitled video"),
                        "uploader_channel": oembed.get("author_name"),
                        "duration_seconds": oembed.get("duration_seconds"),
                        "oembed_live_embeddable": bool(oembed.get("embeddable", True)),
                    }
                )
                if isinstance(oembed.get("view_count"), int):
                    view_counts.append(oembed["view_count"])

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
        comments = self.comment_fixtures.get(seed_url, [])
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
                "evidence_urls": [seed_url] if counts["sample_size"] > 0 and seed_url else [],
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
        mentions = parse_public_team_mentions(bio_text)
        credits = parse_collaborator_credits(bio_text, seed_url)
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
                "evidence_urls": [seed_url] if seed_url and (any(mentions.values()) or credits) else [],
                "notes": f"Found {sum(1 for v in mentions.values() if v)} team mention(s) and {len(credits)} bio credit(s).",
            },
            "missing_fields": missing,
            "newly_discovered_sources": [],
        }

    def map_track_record_domain(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]:
        stage_name = identity_bundle["identity_and_contact"]["stage_name"]
        fixture = self.show_fixtures.get(stage_name.lower()) or {}
        show_history = list(fixture.get("show_history") or [])
        upcoming_shows = list(fixture.get("upcoming_shows") or [])
        domain_credits = list(fixture.get("collaborator_credits") or [])
        highest_cap = lookup_highest_venue_cap(show_history)

        evidence_urls = [
            s["source_url"]
            for s in (show_history + upcoming_shows + domain_credits)
            if isinstance(s, dict) and s.get("source_url")
        ]
        # Log any discovered venue calendar/listing sources for reuse
        discovered_sources: List[Dict[str, Any]] = []
        seen_src = set()
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
