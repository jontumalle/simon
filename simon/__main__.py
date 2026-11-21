import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

from .deploy import deploy_agents
from .fleet import dispatch_fleet
from .gemini import Gemini
from .scout import DEFAULT_TASTE_BRIEF, load_dotenv_if_present, run_scout
from .store import SimonStore
from .web import serve_web


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
    load_dotenv_if_present()
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


def main(argv=None):
    raw_args = list(sys.argv[1:] if argv is None else argv)

    if raw_args and raw_args[0] == "scout":
        parser = argparse.ArgumentParser(
            prog="python3 -m simon scout",
            description="Run Simon's Taste-Brief YouTube Scouting workflow.",
        )
        parser.add_argument(
            "--brief",
            default=DEFAULT_TASTE_BRIEF,
            help="Taste brief describing the sound and musical choices to scout for.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Call Gemini Managed Agents, public YouTube search, and Gemini 4 Hydrogen live.",
        )
        parser.add_argument(
            "--db",
            type=Path,
            default=None,
            help="Optional SQLite database path (defaults to local/simon.db).",
        )
        args = parser.parse_args(raw_args[1:])
        try:
            store = SimonStore(args.db) if args.db else SimonStore()
            run = run_scout(brief_prompt=args.brief, live=args.live, store=store)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            parser.exit(1, f"Simon scout failed: {exc}\n")
        print(json.dumps(run.to_dict(), indent=2, ensure_ascii=False))
        return

    if raw_args and raw_args[0] == "deploy":
        parser = argparse.ArgumentParser(
            prog="python3 -m simon deploy",
            description="Compile agents/<name>/ packages and deploy them to Gemini /v1beta/agents.",
        )
        parser.add_argument(
            "--agent",
            action="append",
            dest="agents",
            help="Agent folder name under agents/ (repeatable). Omit or pass --all for all packages.",
        )
        parser.add_argument("--all", action="store_true", help="Deploy all packages in agents/.")
        parser.add_argument(
            "--prefix",
            default=None,
            help="Agent ID prefix (overrides SIMON_AGENT_PREFIX, e.g. kevin-, staging-, prod-).",
        )
        parser.add_argument(
            "--model-override",
            default=None,
            help="Optional model override for agent_config.model (e.g. gemini-3.8-flash or gemini-4-argon).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compile payloads offline without calling the Gemini API.",
        )
        parser.add_argument(
            "--no-recreate",
            action="store_true",
            help="Skip agents that already exist instead of deleting and recreating them.",
        )
        parser.add_argument(
            "--out-dir",
            type=Path,
            default=None,
            help="Optional directory to write compiled <agent>.json payloads for gemini-api CLI.",
        )
        args = parser.parse_args(raw_args[1:])
        load_dotenv_if_present()
        try:
            summary = deploy_agents(
                agent_names=None if args.all else args.agents,
                prefix=args.prefix,
                model_override=args.model_override,
                dry_run=args.dry_run,
                recreate=not args.no_recreate,
                out_dir=args.out_dir,
            )
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            parser.exit(1, f"Simon deploy failed: {exc}\n")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if raw_args and raw_args[0] == "fleet":
        parser = argparse.ArgumentParser(
            prog="python3 -m simon fleet",
            description="Scale one deployed Managed Agent across N targets in parallel.",
        )
        parser.add_argument("--agent", required=True, help="Deployed Managed Agent ID.")
        parser.add_argument(
            "--targets",
            nargs="+",
            required=True,
            help="One or more targets/lanes to fan out across isolated sandboxes.",
        )
        parser.add_argument(
            "--prompt-template",
            default="Investigate and return objective factual data for: {target}",
            help="Prompt template with {target} placeholder.",
        )
        parser.add_argument(
            "--max-concurrency",
            type=int,
            default=5,
            help="Maximum concurrent workers (1-20, default: 5).",
        )
        parser.add_argument(
            "--webhook-url",
            default=None,
            help="Optional HTTPS webhook URL for outbound interaction.completed events.",
        )
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Poll until all fleet workers complete instead of returning immediately.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview fan-out requests offline without calling the Gemini API.",
        )
        args = parser.parse_args(raw_args[1:])
        load_dotenv_if_present()
        try:
            summary = dispatch_fleet(
                agent_id=args.agent,
                targets=args.targets,
                prompt_template=args.prompt_template,
                max_concurrency=args.max_concurrency,
                webhook_url=args.webhook_url,
                wait=args.wait,
                dry_run=args.dry_run,
            )
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            parser.exit(1, f"Simon fleet failed: {exc}\n")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if raw_args and raw_args[0] == "serve":
        parser = argparse.ArgumentParser(
            prog="python3 -m simon serve",
            description="Launch Simon's interactive Taste-Brief Vocal Scout web demo.",
        )
        parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
        parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")
        parser.add_argument("--db", type=Path, default=None, help="Optional SQLite database path.")
        args = parser.parse_args(raw_args[1:])
        store = SimonStore(args.db) if args.db else SimonStore()
        serve_web(host=args.host, port=args.port, store=store)
        return

    parser = argparse.ArgumentParser(
        description=(
            "Run Simon's showcase scouting graph, or use subcommands "
            "`scout` (CLI taste-brief scout) and `serve` (interactive web MVP)."
        )
    )
    parser.add_argument(
        "--live",
        type=Path,
        metavar="MANIFEST",
        help="Run Gemini on a local JSON manifest of opt-in auditions.",
    )
    args = parser.parse_args(raw_args)
    demo = Path(__file__).resolve().parents[1] / "examples" / "showcase.json"
    try:
        result = run_showcase(args.live or demo, live=args.live is not None)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"Simon could not complete the run: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
