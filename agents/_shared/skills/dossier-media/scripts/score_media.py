#!/usr/bin/env python3
"""Deterministic Stage 3 input skill scorer for live vocal media proof.

Reads `source_and_media_queue` (and `missing_fields`) from a Stage 2
`InvestigatorDossier` and emits grounded pros, cons, missing flags, and a 0..2
score for `live_vocal_proof`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUBRIC_KEY = "live_vocal_proof"
SKILL_NAME = "dossier-media"

LIVE_KEYWORDS = (
    "live",
    "session",
    "sofar",
    "mahogany",
    "lounge",
    "tiny desk",
    "audiotree",
    "kexp",
    "open mic",
    "acoustic",
    "unplugged",
    "room",
    "bedroom",
    "balcony",
    "showcase",
)
STUDIO_ONLY_KEYWORDS = (
    "official audio",
    "visualizer",
    "lyric video",
    "official music video",
    "official video",
)
LIVE_CHANNELS = {"youtube_live_session", "open_mic_lineup"}
MEDIA_MISSING_KEYS = {
    "source_and_media_queue",
    "source_and_media_queue.bio_text",
    "source_and_media_queue.primary_genre",
    "source_and_media_queue.media_links",
    "bio_text",
    "primary_genre",
    "media_links",
}


def _unwrap_dossier(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("dossier_snapshot"), dict):
        return payload["dossier_snapshot"]
    return payload if isinstance(payload, dict) else {}


def _load_json_arg(raw_path: str) -> Dict[str, Any]:
    cleaned = raw_path.lstrip("@").strip()
    if cleaned == "-":
        return json.load(sys.stdin)
    return json.loads(Path(cleaned).read_text(encoding="utf-8"))


def _is_valid_embeddable(clip: Dict[str, Any]) -> bool:
    if clip.get("oembed_live_embeddable") is not True:
        return False
    dur = clip.get("duration_seconds")
    if isinstance(dur, int) and (dur < 20 or dur >= 3600):
        return False
    return bool(str(clip.get("url") or "").strip())


def _is_live_clip(clip: Dict[str, Any], source_channel: str) -> bool:
    title = str(clip.get("title") or "").lower()
    uploader = str(clip.get("uploader_channel") or "").lower()
    haystack = f"{title} {uploader}"
    if any(k in title for k in STUDIO_ONLY_KEYWORDS) and "live" not in title:
        return False
    if any(k in haystack for k in LIVE_KEYWORDS):
        return True
    return source_channel in LIVE_CHANNELS


def evaluate(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate `source_and_media_queue` and return standardized skill score dict."""
    doc = _unwrap_dossier(dossier)
    smq = doc.get("source_and_media_queue")
    if not isinstance(smq, dict):
        smq = {}

    raw_missing = [str(m) for m in (doc.get("missing_fields") or []) if m]
    missing: List[str] = []
    for item in raw_missing:
        if item.startswith("source_and_media_queue") or item in MEDIA_MISSING_KEYS:
            if item not in missing:
                missing.append(item)

    attribution = str(smq.get("attribution_status") or "uncertain").strip()
    source_channel = str(smq.get("source_channel") or "other").strip()
    seed_url = str(smq.get("seed_source_url") or "").strip()
    primary_genre = smq.get("primary_genre")
    raw_links = [m for m in (smq.get("media_links") or []) if isinstance(m, dict)]

    if primary_genre is None and "source_and_media_queue.primary_genre" not in missing:
        missing.append("source_and_media_queue.primary_genre")

    embeddable_clips = [m for m in raw_links if _is_valid_embeddable(m)]
    live_clips = [m for m in embeddable_clips if _is_live_clip(m, source_channel)]

    pros: List[Dict[str, str]] = []
    cons: List[Dict[str, str]] = []

    if attribution == "verified":
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Verified vocal attribution",
                "evidence": (
                    f"attribution_status='verified' via {source_channel}"
                    + (f" ({seed_url})." if seed_url else ".")
                ),
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Uncertain vocal attribution",
                "evidence": (
                    f"attribution_status='uncertain' on {source_channel}"
                    + (f" ({seed_url});" if seed_url else ";")
                    + " performer credit requires human check."
                ),
            }
        )

    if len(embeddable_clips) >= 2 and len(live_clips) >= 1:
        sample_titles = "; ".join(
            f"'{m.get('title')}' ({m.get('url')})" for m in embeddable_clips[:2]
        )
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Multi-clip embeddable vocal proof",
                "evidence": (
                    f"{len(embeddable_clips)} embeddable clips ({len(live_clips)} live-context): "
                    f"{sample_titles}."
                ),
            }
        )
    elif len(embeddable_clips) == 1 and len(live_clips) == 1:
        clip = live_clips[0]
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Embeddable live vocal take queued",
                "evidence": f"Live-context clip '{clip.get('title')}' ({clip.get('url')}).",
            }
        )
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Single-clip live sample",
                "evidence": (
                    "Only 1 embeddable live clip queued; a second live take is needed to "
                    "confirm vocal consistency across rooms."
                ),
            }
        )
    elif len(embeddable_clips) >= 1 and len(live_clips) == 0:
        clip = embeddable_clips[0]
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Studio-only media without live vocal proof",
                "evidence": (
                    f"{len(embeddable_clips)} embeddable clip(s) queued (e.g. '{clip.get('title')}' "
                    f"at {clip.get('url')}), but 0 live/unplugged vocal sessions observed."
                ),
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Zero embeddable media proof",
                "evidence": f"0 valid oembed_live_embeddable clips out of {len(raw_links)} media_links.",
            }
        )

    if attribution == "verified" and len(embeddable_clips) >= 2 and len(live_clips) >= 1:
        score = 2
        note = (
            f"Verified attribution with {len(embeddable_clips)} embeddable clips "
            f"({len(live_clips)} live session take(s))."
        )
    elif len(embeddable_clips) == 0 or (attribution == "uncertain" and len(live_clips) == 0):
        score = 0
        note = (
            f"Insufficient live vocal proof: attribution={attribution}, "
            f"{len(live_clips)} live clip(s), {len(embeddable_clips)} embeddable clip(s)."
        )
    else:
        score = 1
        note = (
            f"Partial vocal proof: attribution={attribution}, "
            f"{len(embeddable_clips)} embeddable clip(s) ({len(live_clips)} live)."
        )

    return {
        "rubric_key": RUBRIC_KEY,
        "skill": SKILL_NAME,
        "score": score,
        "max_score": 2,
        "note": note,
        "pros": pros,
        "cons": cons,
        "missing": missing,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score Stage 3 live_vocal_proof from an InvestigatorDossier."
    )
    parser.add_argument(
        "--dossier",
        required=True,
        help="Path to InvestigatorDossier (or ScreeningPacket) JSON file.",
    )
    args = parser.parse_args(argv)
    dossier = _load_json_arg(args.dossier)
    result = evaluate(dossier)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
