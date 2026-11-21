#!/usr/bin/env python3
"""Sandbox & CI verifier for Stage 1 DiscoveryHandoff (v1.0.0) payloads.

Runs inside the Managed Agent's `code_execution` sandbox (stdlib only) and in
Simon's eval harness (`tests/eval_discovery.py`) to:
1. Validate strict schema compliance with `data/discovery_investigator_contract.json`
   (`DiscoveryHandoff` v1.0.0, `additionalProperties: false`, required fields & enums).
2. Canonicalize YouTube URLs and optionally verify liveness via YouTube oEmbed (`--verify-oembed`).
3. Deduplicate `leads[]` by normalized `stage_name`, merging `seed_sources[]` and
   preserving `attribution_status: "uncertain"` whenever any merged source is uncertain.
4. Detect and fail on subjective ranking/scoring language in `context_snippet`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

CONTRACT_VERSION = "1.0.0"

SEED_SOURCE_CHANNELS = {
    "youtube_live_session",
    "diy_venue_calendar",
    "diy_venue_flyer_ocr",
    "bandcamp_local_arrival",
    "open_mic_lineup",
    "bgv_or_session_credit_graph",
    "event_listing",
    "other",
}

DISCOVERED_SOURCE_CHANNELS = SEED_SOURCE_CHANNELS | {"musicbrainz"}
ATTRIBUTION_STATUSES = {"verified", "uncertain"}
DISCOVERED_BY_VALUES = {"stage_1_discovery", "stage_2_investigator"}

HANDOFF_ALLOWED_KEYS = {
    "contract_version",
    "run_id",
    "search_brief",
    "requested_count",
    "generated_at",
    "leads",
    "discovered_sources",
}
LEAD_ALLOWED_KEYS = {
    "lead_id",
    "stage_name",
    "seed_sources",
    "attribution_status",
    "context_snippet",
}
SEED_SOURCE_ALLOWED_KEYS = {
    "url",
    "source_channel",
    "seed_query_or_venue_node",
    "discovered_at",
    "notes",
}
DISCOVERED_SOURCE_ALLOWED_KEYS = {
    "url",
    "source_channel",
    "title_or_node",
    "why_useful",
    "discovered_by",
}

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
RANKING_OR_SCORING_RE = re.compile(
    r"(?:"
    r"\b(?:top\s+pick|best\s+fit|strongest\s+fit|must[- ]sign|highly\s+recommended|"
    r"rank\s*#?\d+|ranked\s+#?\d+|tier\s*[1-3]|grade\s*[a-f][+-]?)\b"
    r"|(?<!\w)#\s*[1-9]\b"
    r"|\b\d+(?:\.\d+)?\s*/\s*(?:10|100)\b"
    r"|\bscore\s*[:=]\s*\d+"
    r")",
    re.IGNORECASE,
)


def normalize_artist_key(stage_name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (stage_name or "").strip().lower())
    cleaned = re.sub(r"^the\s+", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9 ]+", "", cleaned)
    return cleaned.strip() or "unknown-artist"


def is_valid_http_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_youtube_video_id(url: str) -> Optional[str]:
    if not isinstance(url, str):
        return None
    raw = url.strip()
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower().removeprefix("www.").removeprefix("m.")
    candidate: Optional[str] = None
    if host == "youtu.be":
        parts = [p for p in parsed.path.split("/") if p]
        candidate = parts[0] if parts else None
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            vals = parse_qs(parsed.query).get("v")
            candidate = vals[0] if vals else None
        else:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
                candidate = parts[1]
    if candidate and VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def canonicalize_url(url: str) -> str:
    cleaned = (url or "").strip()
    vid = extract_youtube_video_id(cleaned)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return cleaned


def verify_youtube_oembed(url: str, timeout: int = 8) -> bool:
    vid = extract_youtube_video_id(url)
    if not vid:
        return True  # Not a YouTube video URL; skip YouTube oEmbed check
    watch_url = f"https://www.youtube.com/watch?v={vid}"
    endpoint = f"https://www.youtube.com/oembed?{urlencode({'url': watch_url, 'format': 'json'})}"
    req = Request(endpoint, headers={"User-Agent": "SimonDiscoveryVerifier/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (HTTPError, URLError, TimeoutError, ValueError):
        return False


def has_ranking_or_scoring_language(text: Optional[str]) -> bool:
    if not text or not isinstance(text, str):
        return False
    return bool(RANKING_OR_SCORING_RE.search(text))


def clean_and_dedupe_handoff(
    payload: Dict[str, Any],
    verify_oembed: bool = False,
) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize URLs, deduplicate leads, and validate strict DiscoveryHandoff v1.0.0."""
    errors: List[str] = []
    if not isinstance(payload, dict):
        return {}, ["Payload root must be a JSON object."]

    extra_top = set(payload.keys()) - HANDOFF_ALLOWED_KEYS
    if extra_top:
        errors.append(f"Unexpected top-level keys (additionalProperties=false): {sorted(extra_top)}")

    if payload.get("contract_version") != CONTRACT_VERSION:
        errors.append(f"contract_version must be {CONTRACT_VERSION!r}, got {payload.get('contract_version')!r}")

    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("run_id must be a non-empty string.")

    search_brief = payload.get("search_brief")
    if not isinstance(search_brief, str) or not search_brief.strip():
        errors.append("search_brief must be a non-empty string.")

    requested_count = payload.get("requested_count")
    if isinstance(requested_count, bool) or not isinstance(requested_count, int) or requested_count < 1:
        errors.append(f"requested_count must be an integer >= 1, got {requested_count!r}")

    raw_leads = payload.get("leads")
    if not isinstance(raw_leads, list):
        errors.append("leads must be an array.")
        raw_leads = []

    merged_by_key: Dict[str, Dict[str, Any]] = {}
    lead_order: List[str] = []

    for idx, lead in enumerate(raw_leads):
        if not isinstance(lead, dict):
            errors.append(f"leads[{idx}] must be an object.")
            continue
        extra_lead = set(lead.keys()) - LEAD_ALLOWED_KEYS
        if extra_lead:
            errors.append(f"leads[{idx}] has unexpected keys: {sorted(extra_lead)}")

        stage_name = str(lead.get("stage_name") or "").strip()
        if not stage_name:
            errors.append(f"leads[{idx}].stage_name must be a non-empty string.")
            continue

        lead_id = str(lead.get("lead_id") or "").strip()
        if not lead_id:
            errors.append(f"leads[{idx}].lead_id must be a non-empty string.")

        status = lead.get("attribution_status", "uncertain")
        if status not in ATTRIBUTION_STATUSES:
            errors.append(f"leads[{idx}].attribution_status invalid: {status!r}")
            status = "uncertain"

        snippet = lead.get("context_snippet")
        if snippet is not None and not isinstance(snippet, str):
            errors.append(f"leads[{idx}].context_snippet must be string or null.")
        elif has_ranking_or_scoring_language(snippet):
            errors.append(
                f"leads[{idx}].context_snippet contains subjective ranking/scoring language: {snippet!r}"
            )

        raw_seeds = lead.get("seed_sources")
        if not isinstance(raw_seeds, list) or len(raw_seeds) == 0:
            errors.append(f"leads[{idx}].seed_sources must be a non-empty array.")
            continue

        cleaned_seeds: List[Dict[str, Any]] = []
        seen_seed_urls = set()
        for s_idx, seed in enumerate(raw_seeds):
            if not isinstance(seed, dict):
                errors.append(f"leads[{idx}].seed_sources[{s_idx}] must be an object.")
                continue
            extra_seed = set(seed.keys()) - SEED_SOURCE_ALLOWED_KEYS
            if extra_seed:
                errors.append(f"leads[{idx}].seed_sources[{s_idx}] has unexpected keys: {sorted(extra_seed)}")

            raw_url = str(seed.get("url") or "").strip()
            if not is_valid_http_url(raw_url):
                errors.append(f"leads[{idx}].seed_sources[{s_idx}].url invalid URI: {raw_url!r}")
                continue

            ch = seed.get("source_channel")
            if ch not in SEED_SOURCE_CHANNELS:
                errors.append(f"leads[{idx}].seed_sources[{s_idx}].source_channel invalid: {ch!r}")
                continue

            canon_url = canonicalize_url(raw_url)
            if ch == "youtube_live_session" and extract_youtube_video_id(canon_url) is None:
                errors.append(
                    f"leads[{idx}].seed_sources[{s_idx}].url is not a valid YouTube video URL for youtube_live_session: {raw_url!r}"
                )
                continue

            if verify_oembed and not verify_youtube_oembed(canon_url):
                errors.append(
                    f"leads[{idx}].seed_sources[{s_idx}].url failed YouTube oEmbed check: {canon_url!r}"
                )
                continue

            if canon_url in seen_seed_urls:
                continue
            seen_seed_urls.add(canon_url)

            cleaned_seed: Dict[str, Any] = {"url": canon_url, "source_channel": ch}
            for opt_key in ("seed_query_or_venue_node", "discovered_at", "notes"):
                if opt_key in seed:
                    cleaned_seed[opt_key] = seed[opt_key]
            cleaned_seeds.append(cleaned_seed)

        if not cleaned_seeds:
            errors.append(f"leads[{idx}] ({stage_name}) has zero valid seed_sources after verification.")
            continue

        artist_key = normalize_artist_key(stage_name)
        if artist_key not in merged_by_key:
            merged_lead: Dict[str, Any] = {
                "lead_id": lead_id or f"lead_{len(lead_order) + 1:02d}",
                "stage_name": stage_name,
                "seed_sources": cleaned_seeds,
                "attribution_status": status,
                "context_snippet": snippet,
            }
            merged_by_key[artist_key] = merged_lead
            lead_order.append(artist_key)
        else:
            existing = merged_by_key[artist_key]
            existing_urls = {s["url"] for s in existing["seed_sources"]}
            for s in cleaned_seeds:
                if s["url"] not in existing_urls:
                    existing["seed_sources"].append(s)
                    existing_urls.add(s["url"])
            if status == "uncertain":
                existing["attribution_status"] = "uncertain"

    # Validate discovered_sources
    raw_disc = payload.get("discovered_sources", [])
    cleaned_disc: List[Dict[str, Any]] = []
    if not isinstance(raw_disc, list):
        errors.append("discovered_sources must be an array.")
    else:
        seen_disc_urls = set()
        for d_idx, entry in enumerate(raw_disc):
            if not isinstance(entry, dict):
                errors.append(f"discovered_sources[{d_idx}] must be an object.")
                continue
            extra_d = set(entry.keys()) - DISCOVERED_SOURCE_ALLOWED_KEYS
            if extra_d:
                errors.append(f"discovered_sources[{d_idx}] has unexpected keys: {sorted(extra_d)}")
            d_url = str(entry.get("url") or "").strip()
            if not is_valid_http_url(d_url):
                errors.append(f"discovered_sources[{d_idx}].url invalid URI: {d_url!r}")
                continue
            d_ch = entry.get("source_channel")
            if d_ch not in DISCOVERED_SOURCE_CHANNELS:
                errors.append(f"discovered_sources[{d_idx}].source_channel invalid: {d_ch!r}")
                continue
            why = str(entry.get("why_useful") or "").strip()
            if not why:
                errors.append(f"discovered_sources[{d_idx}].why_useful must be non-empty.")
                continue
            disc_by = entry.get("discovered_by", "stage_1_discovery")
            if disc_by not in DISCOVERED_BY_VALUES:
                errors.append(f"discovered_sources[{d_idx}].discovered_by invalid: {disc_by!r}")
                continue
            if d_url in seen_disc_urls:
                continue
            seen_disc_urls.add(d_url)
            cleaned_entry: Dict[str, Any] = {
                "url": d_url,
                "source_channel": d_ch,
                "why_useful": why,
                "discovered_by": disc_by,
            }
            if "title_or_node" in entry:
                cleaned_entry["title_or_node"] = entry["title_or_node"]
            cleaned_disc.append(cleaned_entry)

    cleaned_handoff: Dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id if isinstance(run_id, str) else "",
        "search_brief": search_brief if isinstance(search_brief, str) else "",
        "requested_count": requested_count if isinstance(requested_count, int) else 0,
        "leads": [merged_by_key[k] for k in lead_order],
        "discovered_sources": cleaned_disc,
    }
    if "generated_at" in payload and payload["generated_at"] is not None:
        cleaned_handoff["generated_at"] = payload["generated_at"]

    return cleaned_handoff, errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify & clean a Stage 1 DiscoveryHandoff v1.0.0 JSON file.")
    parser.add_argument("input_path", help="Path to draft DiscoveryHandoff JSON.")
    parser.add_argument("--out", help="Optional output path to write cleaned/deduped JSON.")
    parser.add_argument("--verify-oembed", action="store_true", help="Verify YouTube URLs live via oEmbed.")
    args = parser.parse_args(argv)

    raw = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
    cleaned, errors = clean_and_dedupe_handoff(raw, verify_oembed=args.verify_oembed)

    if args.out and not errors:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")

    result = {
        "ok": len(errors) == 0,
        "lead_count": len(cleaned.get("leads", [])),
        "discovered_sources_count": len(cleaned.get("discovered_sources", [])),
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
