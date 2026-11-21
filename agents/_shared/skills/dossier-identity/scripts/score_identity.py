#!/usr/bin/env python3
"""Deterministic Stage 3 input skill scorer for identity & reachability.

Reads `identity_and_contact` (and `missing_fields`) from a Stage 2
`InvestigatorDossier` and emits grounded pros, cons, missing flags, and a 0..2
score for `identity_reachability`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUBRIC_KEY = "identity_reachability"
SKILL_NAME = "dossier-identity"
DIRECT_CONTACT_ROUTES = {"bio_email", "mgmt_email"}
IDENTITY_MISSING_KEYS = {
    "identity_and_contact",
    "identity_and_contact.home_city",
    "identity_and_contact.home_neighborhood",
    "identity_and_contact.pronouns",
    "identity_and_contact.musicbrainz_mbid",
    "identity_and_contact.platform_urls",
    "home_city",
    "home_neighborhood",
    "pronouns",
    "musicbrainz_mbid",
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
    """Evaluate `identity_and_contact` and return standardized skill score dict."""
    doc = _unwrap_dossier(dossier)
    ic = doc.get("identity_and_contact")
    if not isinstance(ic, dict):
        ic = {}

    raw_missing = [str(m) for m in (doc.get("missing_fields") or []) if m]
    missing: List[str] = []
    for item in raw_missing:
        if item.startswith("identity_and_contact") or item in IDENTITY_MISSING_KEYS:
            if item not in missing:
                missing.append(item)

    stage_name = str(ic.get("stage_name") or "").strip()
    project_type = str(ic.get("project_type") or "unknown").strip()
    home_city = ic.get("home_city")
    home_neighborhood = ic.get("home_neighborhood")
    mbid = ic.get("musicbrainz_mbid")
    has_contact = bool(ic.get("has_public_business_contact"))
    contact_route = str(ic.get("contact_route_type") or "none").strip()

    platform_urls = ic.get("platform_urls")
    if not isinstance(platform_urls, dict):
        platform_urls = {}
    active_platforms = sorted(
        k for k, v in platform_urls.items() if isinstance(v, str) and v.strip()
    )

    if home_city is None and "identity_and_contact.home_city" not in missing:
        missing.append("identity_and_contact.home_city")
    if mbid is None and "identity_and_contact.musicbrainz_mbid" not in missing:
        missing.append("identity_and_contact.musicbrainz_mbid")

    pros: List[Dict[str, str]] = []
    cons: List[Dict[str, str]] = []

    if has_contact and contact_route in DIRECT_CONTACT_ROUTES:
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Direct business outreach route",
                "evidence": (
                    f"Public business contact confirmed via {contact_route} "
                    f"(has_public_business_contact=true)."
                ),
            }
        )
    elif contact_route == "open_dm":
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "DM-only outreach friction",
                "evidence": (
                    "contact_route_type is 'open_dm' with has_public_business_contact=false; "
                    "no direct booking or management email listed."
                ),
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "No public outreach route",
                "evidence": (
                    f"contact_route_type is '{contact_route}' and "
                    f"has_public_business_contact={str(has_contact).lower()}."
                ),
            }
        )

    if project_type != "unknown" and stage_name:
        loc_detail = (
            f" in {home_neighborhood}, {home_city}"
            if home_neighborhood and home_city
            else (f" in {home_city}" if home_city else "")
        )
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Clear artist format and identity",
                "evidence": f"{stage_name} resolved as {project_type}{loc_detail}.",
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Unresolved project format",
                "evidence": f"project_type is '{project_type}' for stage_name='{stage_name or 'unknown'}'.",
            }
        )

    if len(active_platforms) >= 2:
        mbid_suffix = f" plus MusicBrainz ID {mbid}" if mbid else ""
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Multi-platform identity graph",
                "evidence": (
                    f"{len(active_platforms)} verified platform profiles "
                    f"({', '.join(active_platforms)}){mbid_suffix}."
                ),
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Sparse platform presence",
                "evidence": (
                    f"Only {len(active_platforms)} platform URL(s) resolved "
                    f"({', '.join(active_platforms) if active_platforms else 'none'})."
                ),
            }
        )

    is_direct = has_contact and contact_route in DIRECT_CONTACT_ROUTES
    if not stage_name or len(active_platforms) == 0 or (not has_contact and contact_route == "none"):
        score = 0
        note = (
            f"Unreachable or unresolved identity: route={contact_route}, "
            f"{len(active_platforms)} active platform(s)."
        )
    elif is_direct and project_type != "unknown" and len(active_platforms) >= 2:
        score = 2
        note = (
            f"Direct {contact_route} reachability for {project_type} across "
            f"{len(active_platforms)} platforms."
        )
    else:
        score = 1
        note = (
            f"Partial reachability via {contact_route} ({project_type}, "
            f"{len(active_platforms)} active platform(s))."
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
        description="Score Stage 3 identity_reachability from an InvestigatorDossier."
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
