import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from .gemini import Gemini


STAGES = {
    "performance": (
        "Independently review each audition's performance evidence. Explain one distinctive "
        "musical choice and one uncertainty per artist. Use timestamps where available."
    ),
    "booking": (
        "Independently review each audition against this event brief. Identify practical fit "
        "and the most important detail to confirm. Treat unknowns as open questions."
    ),
    "producer": (
        "Compare the independent reviews for this event. Surface meaningful disagreements, "
        "propose one callback with the specific evidence behind it, and draft an optional "
        "invitation using the event brief and its stated guarantee. Mark it pending producer "
        "approval. Ask the artist to confirm availability and setup. Avoid inventing commitments."
    ),
}

DEMO_REPORTS = {
    "performance": (
        "a01: The dynamic change at 0:18 carries across a single take. "
        "a02: The harmony at 0:15 is distinctive. The layered clip leaves live execution open."
    ),
    "booking": (
        "a01 has an original song and a two-person setup. Confirm availability and input needs. "
        "a02 has an original song and would benefit from a live clip or a simple stage plan."
    ),
    "producer": (
        "Recommend a01 for a callback. Both reviews support the fit. a02's harmony stands out, "
        "and a live take would help evaluate the setup for this bill.\n\n"
        "Draft invitation, pending producer approval: We'd love to discuss a 15-minute opening "
        "set at First Listen NYC with a $250 artist guarantee. Are you interested, and what "
        "would you and your guitarist need on stage?"
    ),
}


def run_showcase(manifest, live):
    with manifest.open(encoding="utf-8") as file:
        data = json.load(file)
    brief = data["brief"]
    eligible = [entry for entry in data["auditions"] if entry.get("consent") is True]
    if not eligible:
        raise ValueError("Include at least one artist who opted in to audition review.")

    gemini = Gemini() if live else None
    audio_reports = {}
    auditions = []
    for entry in eligible:
        audition_id = entry["id"]
        if not isinstance(audition_id, str) or not audition_id or audition_id in audio_reports:
            raise ValueError("Every eligible audition needs a unique, nonempty string ID.")
        audio_reports[audition_id] = None
        if gemini and entry.get("audio"):
            audio_reports[audition_id] = gemini.listen(manifest.parent / entry["audio"])
        auditions.append({
            "id": audition_id,
            "performance_notes": entry.get("performance_notes", ""),
            "artist_notes": entry.get("artist_notes", ""),
            "audio_observations": audio_reports[audition_id],
        })

    if gemini:
        with ThreadPoolExecutor(max_workers=2) as pool:
            performance = pool.submit(gemini.review, STAGES["performance"], auditions)
            booking = pool.submit(gemini.review, STAGES["booking"], {
                "brief": brief,
                "auditions": [
                    {"id": row["id"], "artist_notes": row["artist_notes"]}
                    for row in auditions
                ],
            })
            reviews = {"performance": performance.result(), "booking": booking.result()}
        reviews["producer"] = gemini.review(STAGES["producer"], {"brief": brief, "reviews": reviews})
    else:
        reviews = {stage: {"report": report} for stage, report in DEMO_REPORTS.items()}

    return {
        "mode": "live" if live else "fictional_demo",
        "brief": brief,
        "audition_ids": [entry["id"] for entry in auditions],
        "audio_evidence": {key: value for key, value in audio_reports.items() if value},
        "reviews": reviews,
        "decision_status": "pending_human_review",
    }


def main():
    parser = argparse.ArgumentParser(description="Run Simon's showcase scouting graph.")
    parser.add_argument("--live", type=Path, metavar="MANIFEST",
                        help="Run Gemini on a local JSON manifest of opt-in auditions.")
    args = parser.parse_args()
    demo = Path(__file__).resolve().parents[1] / "examples" / "showcase.json"
    try:
        result = run_showcase(args.live or demo, live=args.live is not None)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"Simon could not complete the run: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
