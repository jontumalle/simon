#!/usr/bin/env python3
"""Deterministic Stage 3 input skill scorer for listener pull & peer co-signs.

Reads `comment_forensics` (and `missing_fields`) from a Stage 2
`InvestigatorDossier` and emits grounded pros, cons, missing flags, and a 0..2
score for `listener_pull_cosigns`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUBRIC_KEY = "listener_pull_cosigns"
SKILL_NAME = "dossier-audience"
AUDIENCE_MISSING_KEYS = {
    "comment_forensics",
    "comment_forensics.comment_intent_counts",
    "comment_forensics.notable_commenters",
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
    """Evaluate `comment_forensics` and return standardized skill score dict."""
    doc = _unwrap_dossier(dossier)
    cf = doc.get("comment_forensics")
    if not isinstance(cf, dict):
        cf = {}

    raw_missing = [str(m) for m in (doc.get("missing_fields") or []) if m]
    missing: List[str] = []
    for item in raw_missing:
        if item.startswith("comment_forensics") or item in AUDIENCE_MISSING_KEYS:
            if item not in missing:
                missing.append(item)

    counts = cf.get("comment_intent_counts")
    if not isinstance(counts, dict):
        counts = {}

    sample_size = int(counts.get("sample_size") or 0)
    release_req = int(counts.get("release_requests") or 0)
    live_req = int(counts.get("live_show_requests") or 0)
    praise = int(counts.get("genuine_praise") or 0)
    spam = int(counts.get("jokes_or_spam") or 0)

    notable = [
        n
        for n in (cf.get("notable_commenters") or [])
        if isinstance(n, dict) and str(n.get("handle") or "").strip()
    ]

    if sample_size == 0 and "comment_forensics.comment_intent_counts" not in missing:
        missing.append("comment_forensics.comment_intent_counts")

    high_intent = release_req + live_req
    intent_ratio = (high_intent / sample_size) if sample_size > 0 else 0.0
    spam_ratio = (spam / sample_size) if sample_size > 0 else 0.0

    pros: List[Dict[str, str]] = []
    cons: List[Dict[str, str]] = []

    if sample_size > 0:
        if high_intent >= 10 or (sample_size >= 10 and intent_ratio >= 0.30):
            pros.append(
                {
                    "skill": SKILL_NAME,
                    "title": "High listener demand for releases and live shows",
                    "evidence": (
                        f"{high_intent}/{sample_size} sampled comments ({intent_ratio:.0%}) request "
                        f"releases ({release_req}) or live dates ({live_req})."
                    ),
                }
            )
        elif praise >= 5 and spam_ratio < 0.50:
            pros.append(
                {
                    "skill": SKILL_NAME,
                    "title": "Positive listener reception",
                    "evidence": (
                        f"{praise}/{sample_size} genuine_praise comments with "
                        f"{high_intent} direct release/show requests."
                    ),
                }
            )

        if spam_ratio >= 0.50:
            cons.append(
                {
                    "skill": SKILL_NAME,
                    "title": "Spam-heavy or meme-skewed comments",
                    "evidence": (
                        f"jokes_or_spam={spam}/{sample_size} ({spam_ratio:.0%}), "
                        f"drowning out organic listener pull ({high_intent} intent comments)."
                    ),
                }
            )
        elif intent_ratio < 0.15 and high_intent < 4:
            cons.append(
                {
                    "skill": SKILL_NAME,
                    "title": "Modest actionable listener demand",
                    "evidence": (
                        f"Only {high_intent}/{sample_size} comments ask for releases or live shows."
                    ),
                }
            )

    if len(notable) >= 1:
        handles_summary = "; ".join(
            f"{n.get('handle')} ({n.get('role_or_context')})" for n in notable[:3]
        )
        pros.append(
            {
                "skill": SKILL_NAME,
                "title": "Peer or curator co-signs in comments",
                "evidence": f"{len(notable)} notable commenter(s): {handles_summary}.",
            }
        )
    elif sample_size > 0:
        cons.append(
            {
                "skill": SKILL_NAME,
                "title": "Zero notable peer co-signs observed",
                "evidence": "notable_commenters is empty across sampled comments.",
            }
        )

    if (
        sample_size >= 15
        and spam_ratio < 0.35
        and (intent_ratio >= 0.35 or high_intent >= 12)
        and len(notable) >= 1
    ):
        score = 2
        note = (
            f"Strong pull ({high_intent}/{sample_size} release/live requests, "
            f"{spam_ratio:.0%} spam) plus {len(notable)} notable co-sign(s)."
        )
    elif (
        (sample_size == 0 and len(notable) == 0)
        or spam_ratio >= 0.50
        or (high_intent == 0 and praise <= 2 and len(notable) == 0)
    ):
        score = 0
        if sample_size == 0:
            note = "No public comment sample or notable co-signs available."
        else:
            note = (
                f"Weak or spam-heavy comment signal ({spam}/{sample_size} jokes/spam, "
                f"{high_intent} intent requests, 0 co-signs)."
            )
    else:
        score = 1
        note = (
            f"Moderate audience signal ({high_intent}/{sample_size} intent requests, "
            f"{praise} praise, {len(notable)} co-sign(s))."
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
        description="Score Stage 3 listener_pull_cosigns from an InvestigatorDossier."
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
