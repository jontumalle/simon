#!/usr/bin/env python3
"""Deterministic Stage 3 input skill scorer for early window & catalog depth.

Reads `public_footprint` (and `missing_fields`) from a Stage 2
`InvestigatorDossier` and emits grounded pros, cons, missing flags, and a 0..2
score for `early_window_depth`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUBRIC_KEY = "early_window_depth"
SKILL_NAME = "dossier-footprint"
EARLY_REGIMES = {"pre_dsp_underground", "early_dsp_inflection"}
CONCENTRATION_THRESHOLD_PCT = 80.0
FOOTPRINT_MISSING_KEYS = {
    "public_footprint",
    "public_footprint.top_release_view_share_pct",
    "public_footprint.public_reach",
    "public_footprint.public_reach.youtube_subscribers",
    "public_footprint.public_reach.top_video_views",
    "public_footprint.public_reach.bandcamp_releases_count",
    "public_footprint.public_reach.bandcamp_supporters_count",
    "public_footprint.public_reach.released_tracks_count",
    "top_release_view_share_pct",
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


def evaluate(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate `public_footprint` and return standardized skill score dict."""
    doc = _unwrap_dossier(dossier)
    pf = doc.get("public_footprint")
    if not isinstance(pf, dict):
        pf = {}

    raw_missing = [str(m) for m in (doc.get("missing_fields") or []) if m]
    missing: List[str] = []
    for item in raw_missing:
        if item.startswith("public_footprint") or item in FOOTPRINT_MISSING_KEYS:
            if item not in missing:
                missing.append(item)

    regime = str(pf.get("footprint_regime") or "unknown").strip()
    reach = pf.get("public_reach")
    if not isinstance(reach, dict):
        reach = {}

    yt_subs = reach.get("youtube_subscribers")
    top_views = reach.get("top_video_views")
    bc_releases = reach.get("bandcamp_releases_count")
    bc_supporters = reach.get("bandcamp_supporters_count")
    released_tracks = reach.get("released_tracks_count")
    top_share = pf.get("top_release_view_share_pct")

    if top_share is None and "public_footprint.top_release_view_share_pct" not in missing:
        missing.append("public_footprint.top_release_view_share_pct")
    if (
        released_tracks is None
        and bc_releases is None
        and "public_footprint.public_reach.released_tracks_count" not in missing
    ):
        missing.append("public_footprint.public_reach.released_tracks_count")

    in_early_window = regime in EARLY_REGIMES
    catalog_count = max(int(released_tracks or 0), int(bc_releases or 0))
    supporters_count = int(bc_supporters or 0)
    has_catalog_depth = catalog_count >= 3 or supporters_count >= 20
    high_concentration = (
        isinstance(top_share, (int, float)) and float(top_share) >= CONCENTRATION_THRESHOLD_PCT
    )

    pros: List[Dict[str, str]] = []
    cons: List[Dict[str, str]] = []

    if in_early_window:
        metrics_parts = [f"regime='{regime}'"]
        if yt_subs is not None:
            metrics_parts.append(f"youtube_subscribers={yt_subs}")
        if top_views is not None:
            metrics_parts.append(f"top_video_views={top_views}")
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Actionable early A&R discovery window",
                "evidence": ", ".join(metrics_parts) + ".",
            }
        )
    elif regime == "established_streaming":
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Past ground-floor streaming window",
                "evidence": (
                    f"footprint_regime='established_streaming' "
                    f"(youtube_subscribers={yt_subs}, top_video_views={top_views})."
                ),
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Unclassified public footprint",
                "evidence": "footprint_regime='unknown' with insufficient public reach telemetry.",
            }
        )

    if has_catalog_depth:
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Multi-release catalog depth",
                "evidence": (
                    f"released_tracks_count={released_tracks}, "
                    f"bandcamp_releases_count={bc_releases}, "
                    f"bandcamp_supporters_count={bc_supporters}."
                ),
            }
        )
    elif catalog_count > 0:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Shallow released catalog",
                "evidence": (
                    f"Only {catalog_count} documented track/release(s); limited body of work "
                    "beyond initial upload."
                ),
            }
        )

    if high_concentration:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Extreme single-clip view concentration",
                "evidence": (
                    f"top_release_view_share_pct={float(top_share):.1f}% (>=80% threshold); "
                    "audience attention is heavily concentrated on one clip."
                ),
            }
        )
    elif isinstance(top_share, (int, float)) and catalog_count >= 2:
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Balanced multi-clip view distribution",
                "evidence": (
                    f"top_release_view_share_pct={float(top_share):.1f}% across "
                    f"{catalog_count} releases."
                ),
            }
        )

    if in_early_window and has_catalog_depth and not high_concentration:
        score = 2
        share_str = f"{float(top_share):.1f}%" if isinstance(top_share, (int, float)) else "n/a"
        note = (
            f"Early window ({regime}) with {catalog_count} releases and balanced "
            f"top-clip share ({share_str})."
        )
    elif (regime == "unknown" and catalog_count == 0 and int(top_views or 0) == 0) or (
        regime == "established_streaming" and (high_concentration or not has_catalog_depth)
    ):
        score = 0
        note = (
            f"Outside target early-depth profile: regime={regime}, "
            f"catalog_count={catalog_count}, top_share={top_share}."
        )
    else:
        score = 1
        share_str = f"{float(top_share):.1f}%" if isinstance(top_share, (int, float)) else "unknown"
        note = (
            f"Mixed footprint signal: regime={regime}, catalog_count={catalog_count}, "
            f"top_release_view_share_pct={share_str}."
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
        description="Score Stage 3 early_window_depth from an InvestigatorDossier."
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
