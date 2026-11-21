"""Daily & on-demand Source Hunter engine + `/v1beta/triggers` cron sync (pure stdlib)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import uuid

from .db_tools import VALID_SOURCE_CHANNELS, list_agent_documents, save_agent_document
from .gemini import _extract_interaction_text, extract_json_object

INTERACTIONS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
TRIGGERS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/triggers"
DEFAULT_API_REVISION = "2026-05-20"
DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "reference" / "discovery_sources_seed.json"
)

DAILY_SCHEDULE_META: Dict[str, str] = {
    "cron": "0 9 * * *",
    "timezone": "America/New_York",
    "frequency": "Daily at 9:00 AM ET",
}

_TRACKING_PARAMS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "si"}
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_FOCUS_ALIASES: Dict[str, str] = {
    "dc": "washington dc",
    "d.c.": "washington dc",
    "dmv": "washington dc",
    "philly": "philadelphia",
    "bay area": "oakland",
    "sf": "oakland",
    "san francisco": "oakland",
    "east bay": "oakland",
    "twin cities": "minneapolis",
    "motown": "detroit",
    "rnb": "r&b",
}

# 28 authentic grassroots music sources across 14 underserved US & Canadian scenes,
# spanning open_mic_lineup, youtube_live_session, diy_venue_calendar,
# bandcamp_local_arrival, event_listing, and bgv_or_session_credit_graph.
CURATED_EXPANSION_POOL: List[Dict[str, Any]] = [
    # --- Detroit ---
    {
        "source_id": "sh_detroit_cliff_bells",
        "name": "Cliff Bell's Live Calendar (Detroit)",
        "url": "https://cliffbells.com/shows/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Detroit", "area": "Downtown Detroit, MI", "country": "US"},
        "genre_tags": ["jazz", "soul", "r&b", "singer-songwriter"],
        "why_useful": "Intimate Detroit jazz and soul listening room spotlighting emerging regional vocalists.",
    },
    {
        "source_id": "sh_detroit_bandcamp_soul",
        "name": "Bandcamp Discover — Detroit Soul & R&B",
        "url": "https://bandcamp.com/discover/r-b-soul/detroit?s=new",
        "source_channel": "bandcamp_local_arrival",
        "location": {"scope": "city", "city": "Detroit", "area": "Metro Detroit, MI", "country": "US"},
        "genre_tags": ["soul", "r&b", "neo-soul", "gospel"],
        "why_useful": "Surfaces self-released Detroit vocal soul and gospel-rooted arrivals before label contact.",
    },
    # --- Minneapolis ---
    {
        "source_id": "sh_mpls_the_current_sessions",
        "name": "89.3 The Current — In-Studio Sessions (Minneapolis)",
        "url": "https://www.youtube.com/@TheCurrent",
        "source_channel": "youtube_live_session",
        "location": {"scope": "city", "city": "Minneapolis", "area": "Twin Cities, MN", "country": "US"},
        "genre_tags": ["indie", "soul", "folk", "singer-songwriter", "r&b"],
        "why_useful": "Minnesota Public Radio live vocal and band sessions with full performer credits.",
    },
    {
        "source_id": "sh_mpls_icehouse_calendar",
        "name": "Icehouse MPLS Live Music Calendar",
        "url": "https://www.icehousempls.com/events",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Minneapolis", "area": "Whittier, Minneapolis, MN", "country": "US"},
        "genre_tags": ["soul", "jazz", "indie", "singer-songwriter"],
        "why_useful": "Premier Twin Cities artist-development room hosting residencies and local vocal openers.",
    },
    # --- Philadelphia ---
    {
        "source_id": "sh_philly_wxpn_key_studio",
        "name": "WXPN / The Key Studio Sessions (Philadelphia)",
        "url": "https://xpn.org/category/the-key-studio-sessions/",
        "source_channel": "youtube_live_session",
        "location": {"scope": "city", "city": "Philadelphia", "area": "West Philadelphia, PA", "country": "US"},
        "genre_tags": ["indie", "soul", "r&b", "folk", "rock"],
        "why_useful": "Curated public-radio sessions focused exclusively on rising Greater Philadelphia acts.",
    },
    {
        "source_id": "sh_philly_world_cafe_open_mic",
        "name": "Philly Songwriters & World Cafe Lounge Lineups",
        "url": "https://worldcafelive.org/events/",
        "source_channel": "open_mic_lineup",
        "location": {"scope": "city", "city": "Philadelphia", "area": "University City, PA", "country": "US"},
        "genre_tags": ["singer-songwriter", "soul", "folk", "r&b"],
        "why_useful": "Frequent local acoustic nights and emerging vocalist co-bills in West Philly.",
    },
    # --- Boston ---
    {
        "source_id": "sh_boston_club_passim",
        "name": "Club Passim Open Mic & Discovery Calendar (Boston)",
        "url": "https://www.passim.org/live-music/",
        "source_channel": "open_mic_lineup",
        "location": {"scope": "metro", "city": "Boston", "area": "Harvard Square, Cambridge, MA", "country": "US"},
        "genre_tags": ["folk", "singer-songwriter", "americana", "acoustic"],
        "why_useful": "Historic Cambridge acoustic listening room and Tuesday open mic launching solo vocalists.",
    },
    {
        "source_id": "sh_boston_berklee_red_room",
        "name": "Berklee Red Room at Cafe 939 & Student Vocal Credits",
        "url": "https://www.youtube.com/@Berklee",
        "source_channel": "bgv_or_session_credit_graph",
        "location": {"scope": "city", "city": "Boston", "area": "Back Bay, Boston, MA", "country": "US"},
        "genre_tags": ["r&b", "soul", "jazz", "pop", "gospel"],
        "why_useful": "Full lead and backing-vocal ensemble credits for pre-signed conservatory vocalists.",
    },
    # --- Denver ---
    {
        "source_id": "sh_denver_indie_1023_lounge",
        "name": "Indie 102.3 Colorado Public Radio Live Sessions",
        "url": "https://www.cpr.org/indie1023/live-performances/",
        "source_channel": "youtube_live_session",
        "location": {"scope": "city", "city": "Denver", "area": "Front Range, CO", "country": "US"},
        "genre_tags": ["indie", "folk", "soul", "singer-songwriter"],
        "why_useful": "Stripped studio performances featuring unsigned Denver and Front Range vocalists.",
    },
    {
        "source_id": "sh_denver_hi_dive_calendar",
        "name": "Hi-Dive Denver Local Show Calendar",
        "url": "https://hi-dive.com/events/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Denver", "area": "South Broadway, Denver, CO", "country": "US"},
        "genre_tags": ["indie", "rock", "alt-pop", "folk"],
        "why_useful": "Grassroots 250-cap South Broadway room with dense local opener lineups.",
    },
    # --- Portland ---
    {
        "source_id": "sh_portland_kmhd_opb_music",
        "name": "OPB Music & KMHD Jazz/Soul Studio Sessions (Portland)",
        "url": "https://www.opb.org/opbmusic/",
        "source_channel": "youtube_live_session",
        "location": {"scope": "city", "city": "Portland", "area": "Portland, OR", "country": "US"},
        "genre_tags": ["jazz", "soul", "indie", "folk"],
        "why_useful": "Oregon Public Broadcasting live room captures of Pacific Northwest vocalists.",
    },
    {
        "source_id": "sh_portland_mississippi_studios",
        "name": "Polaris Hall & Mississippi Studios Calendar (Portland)",
        "url": "https://www.mississippistudios.com/calendar/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Portland", "area": "North Portland, OR", "country": "US"},
        "genre_tags": ["singer-songwriter", "indie", "folk", "soul"],
        "why_useful": "Artist-run Portland rooms where local vocalists graduate from opener to headliner.",
    },
    # --- Oakland / Bay Area ---
    {
        "source_id": "sh_oakland_the_list_foopee",
        "name": "The List — Bay Area DIY & Club Concert Guide",
        "url": "http://www.foopee.com/punk/the-list/",
        "source_channel": "event_listing",
        "location": {"scope": "metro", "city": "Oakland", "area": "Oakland / Bay Area, CA", "country": "US"},
        "genre_tags": ["indie", "diy", "soul", "rock", "singer-songwriter"],
        "why_useful": "Legendary weekly grassroots calendar indexing every East Bay and SF small-room bill.",
    },
    {
        "source_id": "sh_oakland_starline_bandcamp",
        "name": "Bandcamp Discover — Oakland Soul, R&B & Indie",
        "url": "https://bandcamp.com/discover/oakland?s=new",
        "source_channel": "bandcamp_local_arrival",
        "location": {"scope": "city", "city": "Oakland", "area": "Oakland / Bay Area, CA", "country": "US"},
        "genre_tags": ["soul", "r&b", "neo-soul", "indie"],
        "why_useful": "Direct-to-fan East Bay vocal and neo-soul releases with show links and band credits.",
    },
    # --- Miami ---
    {
        "source_id": "sh_miami_lagniappe_house",
        "name": "Lagniappe House Live Nightly Lineups (Miami)",
        "url": "https://lagniappehouse.com/live-music/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Miami", "area": "Midtown / Wynwood, FL", "country": "US"},
        "genre_tags": ["jazz", "soul", "latin", "r&b", "acoustic"],
        "why_useful": "Nightly Miami listening courtyard featuring bilingual soul, jazz, and acoustic vocalists.",
    },
    {
        "source_id": "sh_miami_prism_event_listing",
        "name": "Prism Creative Group & Sweat Records Miami Gigs",
        "url": "https://prismcreativegroup.com/events/",
        "source_channel": "event_listing",
        "location": {"scope": "city", "city": "Miami", "area": "Little Haiti / Miami Beach, FL", "country": "US"},
        "genre_tags": ["indie", "r&b", "latin", "alt-pop", "soul"],
        "why_useful": "Curated South Florida indie and R&B showcase bills with local support acts.",
    },
    # --- Memphis ---
    {
        "source_id": "sh_memphis_b_side_hernandos",
        "name": "B-Side Memphis & Crosstown Arts Live Music Calendar",
        "url": "https://crosstownarts.org/calendar/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Memphis", "area": "Midtown Memphis, TN", "country": "US"},
        "genre_tags": ["soul", "gospel", "blues", "r&b", "singer-songwriter"],
        "why_useful": "Nonprofit Memphis listening room surfacing raw Southern soul and gospel-trained vocalists.",
    },
    {
        "source_id": "sh_memphis_royal_stax_credits",
        "name": "WYXR 91.7 FM Memphis Live & Session Vocal Credits",
        "url": "https://wyxr.org/",
        "source_channel": "bgv_or_session_credit_graph",
        "location": {"scope": "city", "city": "Memphis", "area": "Memphis, TN", "country": "US"},
        "genre_tags": ["soul", "gospel", "r&b", "americana"],
        "why_useful": "Community radio sessions tracking Memphis backing and studio vocalists stepping out solo.",
    },
    # --- Asheville ---
    {
        "source_id": "sh_asheville_grey_eagle",
        "name": "The Grey Eagle Patio & Listening Room (Asheville)",
        "url": "https://www.thegreyeagle.com/calendar/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Asheville", "area": "River Arts District, NC", "country": "US"},
        "genre_tags": ["folk", "americana", "singer-songwriter", "soul"],
        "why_useful": "Appalachian acoustic and roots showcase calendar rich with touring and local openers.",
    },
    {
        "source_id": "sh_asheville_isis_open_mic",
        "name": "Asheville Guitar Bar & Citizen Vinyl Open Mic Nights",
        "url": "https://citizenvinyl.com/events/",
        "source_channel": "open_mic_lineup",
        "location": {"scope": "city", "city": "Asheville", "area": "Downtown Asheville, NC", "country": "US"},
        "genre_tags": ["folk", "singer-songwriter", "indie", "soul"],
        "why_useful": "Studio-pressing cafe hosting intimate Western NC songwriter circles and live sessions.",
    },
    # --- Baltimore ---
    {
        "source_id": "sh_baltimore_wtmd_first_thursday",
        "name": "WTMD 89.7 Live Lunch & Studio Sessions (Baltimore)",
        "url": "https://wtmd.org/radio/",
        "source_channel": "youtube_live_session",
        "location": {"scope": "city", "city": "Baltimore", "area": "Towson / Station North, MD", "country": "US"},
        "genre_tags": ["soul", "indie", "r&b", "folk"],
        "why_useful": "Public radio performance archive spotlighting Mid-Atlantic independent vocalists.",
    },
    {
        "source_id": "sh_baltimore_ottobar_metro_gallery",
        "name": "Metro Gallery Baltimore Show Calendar",
        "url": "https://themetrogallery.net/events/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Baltimore", "area": "Station North, Baltimore, MD", "country": "US"},
        "genre_tags": ["indie", "r&b", "alt-pop", "rock"],
        "why_useful": "175-cap Station North arts venue booking unrepresented Baltimore and DMV openers.",
    },
    # --- Montreal ---
    {
        "source_id": "sh_montreal_casa_del_popolo",
        "name": "Casa del Popolo & La Sala Rossa Calendar (Montreal)",
        "url": "https://casadelpopolo.com/en/events",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Montreal", "area": "Mile End, QC", "country": "CA"},
        "genre_tags": ["indie", "folk", "singer-songwriter", "experimental", "soul"],
        "why_useful": "Iconic 60-cap Mile End grassroots room incubating bilingual indie and soul vocalists.",
    },
    {
        "source_id": "sh_montreal_bandcamp_arrivals",
        "name": "Bandcamp Discover — Montreal New Releases",
        "url": "https://bandcamp.com/discover/montreal?s=new",
        "source_channel": "bandcamp_local_arrival",
        "location": {"scope": "city", "city": "Montreal", "area": "Montreal, QC", "country": "CA"},
        "genre_tags": ["indie", "r&b", "soul", "folk", "alt-pop"],
        "why_useful": "Fresh English and French vocal releases from Montreal's independent bedroom-to-stage scene.",
    },
    # --- Toronto ---
    {
        "source_id": "sh_toronto_cameron_house",
        "name": "The Cameron House & Burdock Music Hall (Toronto)",
        "url": "https://www.thecameron.com/shows",
        "source_channel": "open_mic_lineup",
        "location": {"scope": "city", "city": "Toronto", "area": "Queen West, ON", "country": "CA"},
        "genre_tags": ["singer-songwriter", "folk", "soul", "americana"],
        "why_useful": "Back-room Queen West residencies where emerging Canadian vocalists test raw material.",
    },
    {
        "source_id": "sh_toronto_wavelength_listings",
        "name": "Wavelength Music Series & Exclaim! Toronto Show Listings",
        "url": "https://www.wavelengthmusic.ca/events/",
        "source_channel": "event_listing",
        "location": {"scope": "city", "city": "Toronto", "area": "West End Toronto, ON", "country": "CA"},
        "genre_tags": ["indie", "r&b", "soul", "alt-pop"],
        "why_useful": "Curated non-profit grassroots festival and monthly showcase bills across Toronto.",
    },
    # --- Washington DC ---
    {
        "source_id": "sh_dc_songbyrd_music_house",
        "name": "Songbyrd Music House & Record Cafe (Washington DC)",
        "url": "https://songbyrddc.com/events/",
        "source_channel": "diy_venue_calendar",
        "location": {"scope": "city", "city": "Washington DC", "area": "Union Market, DC", "country": "US"},
        "genre_tags": ["r&b", "soul", "indie", "singer-songwriter"],
        "why_useful": "Intimate DC showcase room and open-mic hub for DMV neo-soul and indie vocalists.",
    },
    {
        "source_id": "sh_dc_busboys_open_mic_credits",
        "name": "Busboys and Poets DC Vocal & Acoustic Open Mic Lineups",
        "url": "https://www.busboysandpoets.com/events/",
        "source_channel": "bgv_or_session_credit_graph",
        "location": {"scope": "city", "city": "Washington DC", "area": "U Street / Anacostia, DC", "country": "US"},
        "genre_tags": ["soul", "r&b", "gospel", "spoken-word", "jazz"],
        "why_useful": "Tracks featured DMV vocalists, choir leads, and house-band session singers on weekly bills.",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonicalize_source_url(raw_url: str) -> str:
    cleaned = (raw_url or "").strip()
    if not cleaned:
        return ""
    parts = urlsplit(cleaned)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if scheme not in ("http", "https") or not netloc or "." not in netloc:
        return ""
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    return urlunsplit((scheme, netloc, path, urlencode(kept, doseq=True), ""))


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("_", (text or "").lower()).strip("_")
    return slug[:36] or "source"


def _http_json(
    method: str,
    url: str,
    api_key: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 45,
) -> Tuple[int, Dict[str, Any]]:
    headers = {
        "Api-Revision": DEFAULT_API_REVISION,
        "x-goog-api-key": api_key,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8").strip()
            return resp.status, (json.loads(raw) if raw else {})
    except HTTPError as exc:
        with exc:
            raw = exc.read().decode("utf-8", errors="replace").strip()
            try:
                err_obj = json.loads(raw) if raw else {}
            except ValueError:
                err_obj = {"message": raw or str(exc.reason)}
        return exc.code, err_obj
    except (URLError, TimeoutError, OSError) as exc:
        return 599, {"message": str(exc)}


def collect_known_urls(
    store: Any,
    existing_urls: Optional[Iterable[str]] = None,
    seed_path: Optional[Path] = None,
) -> Set[str]:
    """Gather canonical + raw URLs from seed JSON, discovered_sources, source_registry, and caller."""
    known: Set[str] = set()

    def _add(url_val: Any) -> None:
        s = str(url_val or "").strip()
        if not s:
            return
        known.add(s)
        canon = canonicalize_source_url(s)
        if canon:
            known.add(canon)

    for u in existing_urls or ():
        _add(u)

    resolved_seed = seed_path if seed_path is not None else DEFAULT_SEED_PATH
    if resolved_seed.is_file():
        try:
            seed_data = json.loads(resolved_seed.read_text(encoding="utf-8"))
            for src in seed_data.get("sources") or []:
                if isinstance(src, dict):
                    _add(src.get("url"))
        except (OSError, ValueError):
            pass

    if store is not None:
        for collection in ("discovered_sources", "source_registry"):
            try:
                docs = list_agent_documents(store, collection, limit=100)
            except Exception:  # noqa: BLE001
                docs = []
            for row in docs:
                doc = row.get("data") if isinstance(row, dict) and isinstance(row.get("data"), dict) else row
                if isinstance(doc, dict):
                    _add(doc.get("url"))

    return known


def _is_known_url(url: str, known_urls: Set[str]) -> bool:
    s = (url or "").strip()
    if not s:
        return True
    canon = canonicalize_source_url(s)
    if not canon:
        return True
    return s in known_urls or canon in known_urls


def _mark_known_url(url: str, known_urls: Set[str]) -> None:
    s = (url or "").strip()
    if s:
        known_urls.add(s)
    canon = canonicalize_source_url(s)
    if canon:
        known_urls.add(canon)


def _normalize_candidate_doc(raw: Dict[str, Any], now_iso: str) -> Optional[Dict[str, Any]]:
    url = str(raw.get("url") or "").strip()
    if not canonicalize_source_url(url):
        return None
    channel = str(raw.get("source_channel") or "").strip()
    if channel not in VALID_SOURCE_CHANNELS:
        channel = "other" if channel else ""
    if not channel:
        return None
    name = str(raw.get("name") or raw.get("title_or_node") or "").strip()
    why_useful = str(raw.get("why_useful") or "").strip()
    if not name or not why_useful:
        return None

    loc_raw = raw.get("location")
    if isinstance(loc_raw, dict):
        location = {
            "scope": str(loc_raw.get("scope") or "city"),
            "city": loc_raw.get("city"),
            "area": loc_raw.get("area"),
            "country": loc_raw.get("country") or "US",
        }
    elif isinstance(loc_raw, str) and loc_raw.strip():
        location = {"scope": "city", "city": loc_raw.strip(), "area": None, "country": "US"}
    else:
        location = {"scope": "global", "city": None, "area": None, "country": None}

    raw_genres = raw.get("genre_tags")
    if isinstance(raw_genres, list) and raw_genres:
        genre_tags = [str(g).strip().lower() for g in raw_genres if str(g).strip()]
    elif isinstance(raw_genres, str) and raw_genres.strip():
        genre_tags = [g.strip().lower() for g in raw_genres.split(",") if g.strip()]
    else:
        genre_tags = ["all"]

    city_slug = _slugify(str(location.get("city") or "global"))
    source_id = str(raw.get("source_id") or "").strip() or f"sh_{city_slug}_{_slugify(name)[:22]}"

    return {
        "source_id": source_id,
        "name": name,
        "url": url,
        "source_channel": channel,
        "source_type": "discovered",
        "location": location,
        "genre_tags": genre_tags or ["all"],
        "career_tier": "emerging",
        "access_method": "public_web",
        "why_useful": why_useful,
        "discovered_by": "stage_1_discovery",
        "added_by_agent": "simon-source-hunter",
        "status": "active",
        "last_checked_at": now_iso,
    }


def _score_pool_item(item: Dict[str, Any], focus: str) -> int:
    cleaned = (focus or "").strip().lower()
    if not cleaned:
        return 1
    expanded = cleaned
    for alias, target in _FOCUS_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", expanded):
            expanded = f"{expanded} {target}"

    loc = item.get("location") or {}
    haystack = " ".join(
        [
            str(item.get("name") or ""),
            str(item.get("source_channel") or "").replace("_", " "),
            str(loc.get("city") or ""),
            str(loc.get("area") or ""),
            str(loc.get("country") or ""),
            " ".join(str(g) for g in (item.get("genre_tags") or [])),
            str(item.get("why_useful") or ""),
        ]
    ).lower()

    score = 0
    city_lc = str(loc.get("city") or "").lower()
    if city_lc and city_lc in expanded:
        score += 10
    for token in re.findall(r"[a-z0-9&+-]{2,}", expanded):
        if token in {"find", "new", "sources", "music", "live", "local", "the", "and", "for", "in"}:
            continue
        if token in haystack:
            score += 3
    return score


def _pick_from_curated_pool(
    count: int,
    focus: str,
    known_urls: Set[str],
    now_iso: str,
) -> List[Dict[str, Any]]:
    available: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, raw in enumerate(CURATED_EXPANSION_POOL):
        if _is_known_url(str(raw.get("url") or ""), known_urls):
            continue
        available.append((_score_pool_item(raw, focus), idx, raw))

    if not available or count <= 0:
        return []

    has_focus = bool((focus or "").strip())
    if has_focus:
        matched = [t for t in available if t[0] > 0]
        unmatched = [t for t in available if t[0] == 0]
        matched.sort(key=lambda t: (-t[0], t[1]))
        ordered_pool = [t[2] for t in matched] + _diversify_pool([t[2] for t in unmatched])
    else:
        ordered_pool = _diversify_pool([t[2] for t in available])

    picked: List[Dict[str, Any]] = []
    for raw in ordered_pool:
        if len(picked) >= count:
            break
        if _is_known_url(str(raw.get("url") or ""), known_urls):
            continue
        norm = _normalize_candidate_doc(raw, now_iso)
        if norm is not None:
            _mark_known_url(norm["url"], known_urls)
            picked.append(norm)
    return picked


def _diversify_pool(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Interleave items so consecutive picks span distinct cities and source_channel values."""
    remaining = list(items)
    ordered: List[Dict[str, Any]] = []
    used_cities: Set[str] = set()
    used_channels: Set[str] = set()

    while remaining:
        best_idx = 0
        best_rank = -1
        for idx, cand in enumerate(remaining):
            city = str((cand.get("location") or {}).get("city") or "")
            ch = str(cand.get("source_channel") or "")
            rank = (2 if city not in used_cities else 0) + (1 if ch not in used_channels else 0)
            if rank > best_rank:
                best_rank = rank
                best_idx = idx
                if rank == 3:
                    break
        chosen = remaining.pop(best_idx)
        city = str((chosen.get("location") or {}).get("city") or "")
        ch = str(chosen.get("source_channel") or "")
        if city:
            used_cities.add(city)
        if ch:
            used_channels.add(ch)
        if len(used_cities) >= 12:
            used_cities.clear()
        if len(used_channels) >= 5:
            used_channels.clear()
        ordered.append(chosen)
    return ordered


def _live_hunt_via_gemini(
    *,
    api_key: str,
    focus: str,
    count: int,
    known_urls: Set[str],
    now_iso: str,
    prefix: str,
    request_fn: Callable[..., Tuple[int, Dict[str, Any]]],
    poll_timeout_s: float = 35.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> List[Dict[str, Any]]:
    focus_clause = (
        f"Focus specifically on: {focus.strip()}."
        if (focus or "").strip()
        else "Focus on underrepresented US & Canadian scenes (e.g., Detroit, Minneapolis, Philadelphia, Boston, Denver, Portland, Oakland, Miami, Memphis, Asheville, Baltimore, Montreal, Toronto, Washington DC)."
    )
    sample_known = sorted(u for u in known_urls if u.startswith("http"))[:40]
    prompt = (
        f"Find {count} real, currently active grassroots music discovery sources. {focus_clause}\n"
        f"Valid source_channel values ONLY: {sorted(VALID_SOURCE_CHANNELS)}.\n"
        f"Never return any URL already in this known list: {json.dumps(sample_known)}.\n"
        "Return ONLY JSON: "
        '{"added_sources": [{"name": "...", "url": "https://...", "source_channel": "...", '
        '"location": {"scope": "city", "city": "...", "area": "...", "country": "US"}, '
        '"genre_tags": ["soul", "indie"], "why_useful": "..."}], "summary": "..."}'
    )

    agent_id = f"{prefix}simon-source-hunter"
    attempts: List[Dict[str, Any]] = [
        {
            "agent": agent_id,
            "environment": {"type": "remote"},
            "background": True,
            "store": True,
            "input": [{"type": "text", "text": prompt}],
        },
        {
            "model": "gemini-4-hydrogen",
            "tools": [{"type": "google_search"}],
            "input": [{"type": "text", "text": prompt}],
        },
    ]

    for req_body in attempts:
        code, resp = request_fn("POST", INTERACTIONS_ENDPOINT, api_key, body=req_body)
        if not (200 <= code < 300):
            continue

        status = str(resp.get("status") or "completed")
        raw_name = str(resp.get("name") or "")
        interaction_id = str(resp.get("id") or (raw_name.split("/")[-1] if raw_name else ""))
        deadline = time.monotonic() + poll_timeout_s
        while status not in ("completed", "failed", "cancelled", "incomplete", "budget_exceeded"):
            if not interaction_id or time.monotonic() >= deadline:
                break
            sleep_fn(1.5)
            p_code, p_resp = request_fn(
                "GET", f"{INTERACTIONS_ENDPOINT}/{interaction_id}", api_key
            )
            if not (200 <= p_code < 300):
                break
            resp = p_resp
            status = str(resp.get("status") or status)

        if status != "completed":
            continue

        text = _extract_interaction_text(resp)
        try:
            parsed = extract_json_object(text)
        except ValueError:
            continue

        raw_list = parsed.get("added_sources") or parsed.get("sources") or []
        if not isinstance(raw_list, list):
            continue

        live_added: List[Dict[str, Any]] = []
        for item in raw_list:
            if len(live_added) >= count:
                break
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if _is_known_url(url, known_urls):
                continue
            norm = _normalize_candidate_doc(item, now_iso)
            if norm is not None:
                _mark_known_url(norm["url"], known_urls)
                live_added.append(norm)

        if len(live_added) >= 1:
            return live_added

    return []


def hunt_new_sources(
    store: Any,
    focus: str = "",
    count: int = 3,
    live: bool = False,
    api_key: Optional[str] = None,
    existing_urls: Optional[Iterable[str]] = None,
    *,
    prefix: Optional[str] = None,
    request_fn: Optional[Callable[..., Tuple[int, Dict[str, Any]]]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Discover, deduplicate, and persist `count` new grassroots sources + a Field News report."""
    target_count = max(1, min(int(count or 3), 20))
    now_iso = _utc_now()
    known_urls = collect_known_urls(store, existing_urls=existing_urls)

    resolved_key = (api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")).strip()
    resolved_prefix = (
        os.environ.get("SIMON_AGENT_PREFIX", "staging-") if prefix is None else prefix
    )
    http_fn = request_fn or _http_json

    candidates: List[Dict[str, Any]] = []
    mode_used = "curated_pool"
    if live and resolved_key and resolved_key != "REPLACE_ME":
        candidates = _live_hunt_via_gemini(
            api_key=resolved_key,
            focus=focus,
            count=target_count,
            known_urls=known_urls,
            now_iso=now_iso,
            prefix=resolved_prefix,
            request_fn=http_fn,
            sleep_fn=sleep_fn,
        )
        if candidates:
            mode_used = "live"

    if len(candidates) < 1:
        candidates = _pick_from_curated_pool(
            count=target_count,
            focus=focus,
            known_urls=known_urls,
            now_iso=now_iso,
        )
        mode_used = "curated_pool"

    added: List[Dict[str, Any]] = []
    for src in candidates[:target_count]:
        save_agent_document(store, "discovered_sources", src, doc_id=src["source_id"])
        added.append(src)

    names = ", ".join(s["name"] for s in added[:4])
    if len(added) > 4:
        names = f"{names}, +{len(added) - 4} more"
    headline = (
        f"Added {len(added)} new scouting sources ({names})."
        if added
        else "Checked Source Registry; all matching grassroots sources are already active."
    )

    report_id = f"rep_sh_{uuid.uuid4().hex[:8]}"
    brief_text = (
        f"Hunt {target_count} grassroots sources ({focus.strip()})"
        if (focus or "").strip()
        else f"Daily source hunt ({target_count} grassroots sources across underrepresented scenes)"
    )
    findings = [
        {
            "title": s["name"],
            "summary": s["why_useful"],
            "source_name": str((s.get("location") or {}).get("city") or "Global"),
            "source_channel": s["source_channel"],
            "url": s["url"],
        }
        for s in added
    ]
    steps = [
        {
            "step_number": 1,
            "phase": "looking_at",
            "title": "Audited active Source Registry for gaps",
            "looking_at": focus.strip() or "Underrepresented US & Canadian music scenes",
            "finding": f"Checked {len(known_urls)} known URLs to prevent duplicates.",
            "analysis": "Filtered out every URL already present in seed and discovered_sources.",
            "status": "done",
            "updated_at": now_iso,
        },
        {
            "step_number": 2,
            "phase": "saved",
            "title": "Saved verified sources to Source Registry",
            "looking_at": "discovered_sources collection",
            "finding": headline,
            "analysis": f"Verified {len(added)} sources with valid channels and public URLs.",
            "status": "done",
            "updated_at": now_iso,
        },
    ]
    report_doc: Dict[str, Any] = {
        "contract_version": "1.0.0",
        "report_id": report_id,
        "batch_id": None,
        "agent_name": "Source Hunter",
        "stage": "discovery",
        "brief": brief_text,
        "status": "completed",
        "headline": headline,
        "current_focus": "Source Registry updated",
        "steps": steps,
        "findings": findings,
        "output": {"added_sources": added, "summary": headline},
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    save_agent_document(store, "agent_reports", report_doc, doc_id=report_id)

    return {
        "ok": True,
        "added_count": len(added),
        "added_sources": added,
        "report_id": report_id,
        "mode": mode_used,
        "schedule": dict(DAILY_SCHEDULE_META),
    }


def sync_daily_source_hunter_trigger(
    api_key: Optional[str] = None,
    prefix: str = "staging-",
    *,
    request_fn: Optional[Callable[..., Tuple[int, Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Idempotently register the daily 9:00 AM ET `/v1beta/triggers` job for `simon-source-hunter`."""
    clean_prefix = prefix or ""
    env_label = clean_prefix.rstrip("-") or "default"
    display_name = f"Simon Daily Source Hunter ({env_label})"
    agent_id = f"{clean_prefix}simon-source-hunter"
    payload: Dict[str, Any] = {
        "display_name": display_name,
        "schedule": "0 9 * * *",
        "time_zone": "America/New_York",
        "interaction": {
            "agent": agent_id,
            "environment": {"type": "remote"},
            "input": [
                {
                    "type": "text",
                    "text": (
                        "Run daily source hunt: find 3 new grassroots live music sources "
                        "in underrepresented US cities and save them to simon-db."
                    ),
                }
            ],
        },
    }

    resolved_key = (api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")).strip()
    if not resolved_key or resolved_key == "REPLACE_ME":
        return {
            "ok": False,
            "status": "skipped_no_api_key",
            "action": "none",
            "display_name": display_name,
            "agent": agent_id,
            "schedule": "0 9 * * *",
            "time_zone": "America/New_York",
            "error": "GEMINI_API_KEY is not configured.",
            "payload": payload,
        }

    http_fn = request_fn or _http_json
    get_code, get_body = http_fn("GET", TRIGGERS_ENDPOINT, resolved_key)
    if 200 <= get_code < 300 and isinstance(get_body, dict):
        for existing in get_body.get("triggers") or []:
            if isinstance(existing, dict) and existing.get("display_name") == display_name:
                return {
                    "ok": True,
                    "status": "active",
                    "action": "existing",
                    "http_status": get_code,
                    "display_name": display_name,
                    "agent": agent_id,
                    "schedule": "0 9 * * *",
                    "time_zone": "America/New_York",
                    "trigger": existing,
                }

    post_code, post_body = http_fn("POST", TRIGGERS_ENDPOINT, resolved_key, body=payload)
    if 200 <= post_code < 300:
        return {
            "ok": True,
            "status": "active",
            "action": "created",
            "http_status": post_code,
            "display_name": display_name,
            "agent": agent_id,
            "schedule": "0 9 * * *",
            "time_zone": "America/New_York",
            "trigger": post_body,
        }

    return {
        "ok": False,
        "status": "error",
        "action": "fallback_github_actions",
        "http_status": post_code,
        "get_http_status": get_code,
        "display_name": display_name,
        "agent": agent_id,
        "schedule": "0 9 * * *",
        "time_zone": "America/New_York",
        "error": post_body,
        "payload": payload,
    }
