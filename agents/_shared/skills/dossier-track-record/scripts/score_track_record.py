#!/usr/bin/env python3
"""Deterministic Stage 3 input skill scorer for stage momentum & A&R whitespace.

Reads `live_history_and_credits` and `missing_fields` from a Stage 2
`InvestigatorDossier`, enforces strict missing-field abstention, checks for
major-label lockup, and emits a 0..2 score for `stage_momentum_whitespace`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUBRIC_KEY = "stage_momentum_whitespace"
SKILL_NAME = "dossier-track-record"

MAJOR_LABEL_KEYWORDS = (
    "universal music",
    "sony music",
    "warner music",
    "warner records",
    "columbia",
    "atlantic",
    "interscope",
    "republic",
    "rca",
    "capitol",
    "def jam",
    "epic records",
    "elektra",
    "geffen",
    "polydor",
    "island records",
    "virgin",
    "parlophone",
    "arista",
)

DIY_DISTRIBUTORS = (
    "distrokid",
    "tunecore",
    "cd baby",
    "amuse",
    "unitedmasters",
    "symphonic",
    "ditto",
    "landr",
    "self-released",
)

TRACK_MISSING_KEYS = {
    "live_history_and_credits",
    "live_history_and_credits.show_history",
    "live_history_and_credits.upcoming_shows",
    "live_history_and_credits.highest_venue_cap_observed",
    "live_history_and_credits.public_team_mentions",
    "live_history_and_credits.collaborator_credits",
    "show_history",
    "upcoming_shows",
    "highest_venue_cap_observed",
    "collaborator_credits",
}

SHOW_MISSING_KEYS = {
    "live_history_and_credits",
    "live_history_and_credits.show_history",
    "show_history",
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


def _is_major_label(label: Optional[str]) -> bool:
    if not label:
        return False
    low = label.lower()
    return any(k in low for k in MAJOR_LABEL_KEYWORDS)


def evaluate(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate `live_history_and_credits` + `missing_fields` with strict abstention."""
    doc = _unwrap_dossier(dossier)
    lhc = doc.get("live_history_and_credits")
    if not isinstance(lhc, dict):
        lhc = {}

    raw_missing = [str(m) for m in (doc.get("missing_fields") or []) if m]
    missing: List[str] = []
    for item in raw_missing:
        if item.startswith("live_history_and_credits") or item in TRACK_MISSING_KEYS:
            if item not in missing:
                missing.append(item)

    past_shows = [s for s in (lhc.get("show_history") or []) if isinstance(s, dict)]
    upcoming_shows = [s for s in (lhc.get("upcoming_shows") or []) if isinstance(s, dict)]
    venue_cap = lhc.get("highest_venue_cap_observed")

    team = lhc.get("public_team_mentions")
    if not isinstance(team, dict):
        team = {}
    label = str(team.get("label") or "").strip() or None
    management = str(team.get("management") or "").strip() or None
    booking_agent = str(team.get("booking_agent") or "").strip() or None
    distributor = str(team.get("distributor") or "").strip() or None

    credits = [
        c
        for c in (lhc.get("collaborator_credits") or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    ]

    if venue_cap is None and "live_history_and_credits.highest_venue_cap_observed" not in missing:
        missing.append("live_history_and_credits.highest_venue_cap_observed")

    shows_missing_abstained = any(k in raw_missing for k in SHOW_MISSING_KEYS)
    major_signed = _is_major_label(label)
    unsigned_whitespace = label is None or (
        not major_signed and any(d in label.lower() for d in DIY_DISTRIBUTORS)
    )

    pros: List[Dict[str, str]] = []
    cons: List[Dict[str, str]] = []

    if major_signed:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Major-label signing lockup (dealbreaker)",
                "evidence": (
                    f"public_team_mentions.label='{label}' eliminates unsigned A&R whitespace."
                ),
            }
        )
    elif unsigned_whitespace:
        dist_note = f" (distributor: {distributor})" if distributor else ""
        mgmt_note = f", management: {management}" if management else ", unrepresented"
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Open unsigned A&R whitespace",
                "evidence": f"public_team_mentions.label is null{dist_note}{mgmt_note}.",
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Existing label affiliation",
                "evidence": f"public_team_mentions.label='{label}' requires rights check.",
            }
        )

    total_shows = len(past_shows) + len(upcoming_shows)
    if total_shows > 0:
        venues = [str(s.get("venue")) for s in (past_shows + upcoming_shows)[:3] if s.get("venue")]
        cap_str = f", highest_venue_cap_observed={venue_cap}" if venue_cap is not None else ""
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Documented live room activity",
                "evidence": (
                    f"{len(past_shows)} past show(s) and {len(upcoming_shows)} upcoming show(s) "
                    f"({', '.join(venues)}{cap_str})."
                ),
            }
        )
        if len(past_shows) < 3 and not any(
            s.get("billing_slot") == "headliner" for s in past_shows
        ):
            cons.append(
                {
                    "skill": SKILL_NAME,
                    "title": "Early-stage gig depth (pre-headliner)",
                    "evidence": (
                        f"{len(past_shows)} past gig(s) logged so far without a ticketed "
                        "headliner run."
                    ),
                }
            )
    elif shows_missing_abstained:
        # Strict abstention: record evidentiary gap without inventing negative performance claims.
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Unverified live gig history (abstained)",
                "evidence": (
                    "show_history is listed in missing_fields; no public gig listings were "
                    "indexed (treated as unknown, not a failed live draw)."
                ),
            }
        )
    else:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Zero documented live shows",
                "evidence": "0 past or upcoming shows found across venue and event listings.",
            }
        )

    if len(credits) >= 1:
        credit_names = "; ".join(f"{c.get('name')} ({c.get('role')})" for c in credits[:3])
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Verified collaborator network",
                "evidence": f"{len(credits)} collaborator credit(s): {credit_names}.",
            }
        )

    has_headliner_or_cap = (
        len(upcoming_shows) >= 1
        or (isinstance(venue_cap, int) and venue_cap >= 300)
        or any(s.get("billing_slot") == "headliner" for s in past_shows)
    )

    if major_signed:
        score = 0
        note = f"Major-label affiliation ({label}) removes unsigned A&R whitespace."
    elif unsigned_whitespace and len(past_shows) >= 3 and has_headliner_or_cap:
        score = 2
        note = (
            f"Unsigned whitespace with {len(past_shows)} past shows, "
            f"{len(upcoming_shows)} upcoming date(s), and venue cap up to {venue_cap}."
        )
    elif unsigned_whitespace and (
        total_shows >= 1
        or len(credits) >= 1
        or shows_missing_abstained
        or booking_agent is not None
    ):
        score = 1
        if total_shows >= 1:
            note = (
                f"Unsigned whitespace with early live activity ({len(past_shows)} past, "
                f"{len(upcoming_shows)} upcoming; <3 past shows for max score)."
            )
        elif shows_missing_abstained:
            note = (
                "Unsigned whitespace; live show history is unindexed in missing_fields "
                "(abstained as unknown rather than 0)."
            )
        else:
            note = f"Unsigned whitespace with {len(credits)} collaborator credit(s); 0 shows yet."
    else:
        score = 0
        note = (
            f"Insufficient stage momentum and whitespace: label={label}, "
            f"past_shows={len(past_shows)}, upcoming_shows={len(upcoming_shows)}."
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
        description="Score Stage 3 stage_momentum_whitespace from an InvestigatorDossier."
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
