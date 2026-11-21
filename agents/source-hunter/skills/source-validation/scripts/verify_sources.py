#!/usr/bin/env python3
"""Stdlib validator and URL deduplicator for simon-source-hunter candidate sources."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

VALID_SOURCE_CHANNELS = frozenset(
    {
        "youtube_live_session",
        "diy_venue_calendar",
        "diy_venue_flyer_ocr",
        "bandcamp_local_arrival",
        "open_mic_lineup",
        "bgv_or_session_credit_graph",
        "musicbrainz",
        "event_listing",
        "other",
    }
)

VALID_SCOPES = frozenset({"hyper_local", "city", "metro", "national", "global"})
TRACKING_PARAMS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "si"}
)
SLUG_RE = re.compile(r"[^a-z0-9]+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonicalize_url(raw_url: str) -> str:
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
    kept_query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(kept_query, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _slugify(text: str) -> str:
    slug = SLUG_RE.sub("_", (text or "").lower()).strip("_")
    return slug[:40] or "source"


def extract_urls_from_payload(payload: Any) -> Set[str]:
    urls: Set[str] = set()
    items: Iterable[Any] = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("sources")
            or payload.get("documents")
            or payload.get("added_sources")
            or []
        )
    for item in items:
        doc = item.get("data") if isinstance(item, dict) and isinstance(item.get("data"), dict) else item
        if isinstance(doc, dict) and doc.get("url"):
            canon = canonicalize_url(str(doc["url"]))
            if canon:
                urls.add(canon)
    return urls


def validate_and_normalize_source(
    raw: Any,
    seen_urls: Set[str],
    now_iso: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    if not isinstance(raw, dict):
        return None, ["Candidate entry must be a JSON object."]

    errors: List[str] = []
    raw_url = str(raw.get("url") or "").strip()
    canon_url = canonicalize_url(raw_url)
    if not canon_url:
        errors.append(f"Invalid http/https URL: {raw_url!r}.")
    elif canon_url in seen_urls:
        errors.append(f"Duplicate URL already in registry or batch: {raw_url}.")

    channel = str(raw.get("source_channel") or "").strip()
    if channel not in VALID_SOURCE_CHANNELS:
        errors.append(
            f"Invalid source_channel {channel!r}; expected one of {sorted(VALID_SOURCE_CHANNELS)}."
        )

    name = str(raw.get("name") or raw.get("title_or_node") or "").strip()
    if not name:
        errors.append("Missing non-empty 'name'.")

    raw_loc = raw.get("location")
    if isinstance(raw_loc, str) and raw_loc.strip():
        city_val: Optional[str] = raw_loc.strip()
        location = {"scope": "city", "city": city_val, "area": None, "country": "US"}
    elif isinstance(raw_loc, dict):
        scope = str(raw_loc.get("scope") or "city").strip().lower()
        if scope not in VALID_SCOPES:
            scope = "city"
        city_raw = raw_loc.get("city")
        city_val = str(city_raw).strip() if city_raw else None
        area_raw = raw_loc.get("area")
        area_val = str(area_raw).strip() if area_raw else None
        country_raw = raw_loc.get("country")
        country_val = str(country_raw).strip() if country_raw else None
        if scope in ("hyper_local", "city", "metro") and not city_val:
            errors.append(f"location.city is required when location.scope is '{scope}'.")
        location = {
            "scope": scope,
            "city": city_val,
            "area": area_val,
            "country": country_val,
        }
    else:
        errors.append("Missing 'location' object ({scope, city, area, country}).")
        location = {"scope": "global", "city": None, "area": None, "country": None}

    raw_genres = raw.get("genre_tags")
    if isinstance(raw_genres, str) and raw_genres.strip():
        genre_tags = [g.strip().lower() for g in raw_genres.split(",") if g.strip()]
    elif isinstance(raw_genres, list):
        genre_tags = [str(g).strip().lower() for g in raw_genres if str(g).strip()]
    else:
        genre_tags = []
    if not genre_tags:
        errors.append("Missing non-empty 'genre_tags' list.")

    why_useful = str(raw.get("why_useful") or "").strip()
    if len(why_useful) < 10:
        errors.append("Field 'why_useful' must explain scouting value (>= 10 chars).")

    if errors:
        return None, errors

    seen_urls.add(canon_url)
    ts = now_iso or utc_now_iso()
    city_slug = _slugify(str(location.get("city") or "global"))
    source_id = str(raw.get("source_id") or "").strip() or f"sh_{city_slug}_{_slugify(name)[:24]}"

    normalized: Dict[str, Any] = {
        "source_id": source_id,
        "name": name,
        "url": raw_url,
        "source_channel": channel,
        "source_type": str(raw.get("source_type") or "discovered"),
        "location": location,
        "genre_tags": genre_tags,
        "career_tier": str(raw.get("career_tier") or "emerging"),
        "access_method": str(raw.get("access_method") or "public_web"),
        "why_useful": why_useful,
        "discovered_by": str(raw.get("discovered_by") or "stage_1_discovery"),
        "added_by_agent": str(raw.get("added_by_agent") or "simon-source-hunter"),
        "status": str(raw.get("status") or "active"),
        "last_checked_at": str(raw.get("last_checked_at") or ts),
    }
    if raw.get("notes"):
        normalized["notes"] = str(raw["notes"]).strip()
    return normalized, []


def verify_candidates_payload(
    raw_payload: Any,
    existing_urls: Optional[Iterable[str]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    seen: Set[str] = set()
    for u in existing_urls or ():
        canon = canonicalize_url(str(u))
        if canon:
            seen.add(canon)

    if isinstance(raw_payload, list):
        candidates = raw_payload
        summary = ""
    elif isinstance(raw_payload, dict):
        candidates = (
            raw_payload.get("added_sources")
            or raw_payload.get("sources")
            or raw_payload.get("candidates")
            or []
        )
        summary = str(raw_payload.get("summary") or "").strip()
    else:
        return {"added_sources": [], "summary": ""}, ["Input must be a JSON object or array."]

    if not isinstance(candidates, list) or not candidates:
        return {"added_sources": [], "summary": summary}, ["No candidate sources provided."]

    verified: List[Dict[str, Any]] = []
    all_errors: List[str] = []
    now_iso = utc_now_iso()
    for idx, item in enumerate(candidates):
        norm, errs = validate_and_normalize_source(item, seen, now_iso=now_iso)
        if errs:
            for e in errs:
                all_errors.append(f"candidates[{idx}]: {e}")
        elif norm is not None:
            verified.append(norm)

    if not verified and not all_errors:
        all_errors.append("Zero candidate sources passed validation.")

    if not summary and verified:
        cities = sorted({str((s.get("location") or {}).get("city") or "Global") for s in verified})
        summary = f"Verified {len(verified)} new grassroots sources across {', '.join(cities[:4])}."

    return {"added_sources": verified, "summary": summary}, all_errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and deduplicate candidate discovery sources.")
    parser.add_argument("input_json", help="Path to candidate sources JSON.")
    parser.add_argument(
        "--existing",
        action="append",
        default=[],
        help="Path(s) to existing discovered_sources or source_registry JSON dumps for URL dedup.",
    )
    parser.add_argument("--out", default="", help="Optional path to write verified output JSON.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Keep valid non-duplicate entries when at least 1 candidate passes.",
    )
    args = parser.parse_args(argv)

    existing_urls: Set[str] = set()
    for ex_path in args.existing:
        p = Path(ex_path)
        if p.is_file():
            existing_urls |= extract_urls_from_payload(json.loads(p.read_text(encoding="utf-8")))

    raw_in = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    out_obj, errors = verify_candidates_payload(raw_in, existing_urls=existing_urls)

    if errors and not (args.allow_partial and out_obj["added_sources"]):
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    rendered = json.dumps(out_obj, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
