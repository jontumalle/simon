#!/usr/bin/env python3
"""Injects Simon's PROJECT.md pointer index at SessionStart (Life OS pattern)."""

import json
from pathlib import Path
import sys


def main():
    try:
        _ = sys.stdin.read()
        repo_root = Path(__file__).resolve().parents[2]
        project_md = repo_root / "PROJECT.md"
        if not project_md.is_file():
            print("{}")
            return

        content = project_md.read_text(encoding="utf-8").strip()
        msg = (
            "Simon repository knowledge model active (Life OS pattern).\n"
            "Follow pointers from PROJECT.md below; check RESOURCES.md for shared partner tooling.\n\n"
            f"{content}"
        )
        print(json.dumps({
            "injectSteps": [
                {
                    "systemMessage": {
                        "systemMessage": msg
                    }
                }
            ]
        }))
    except Exception:
        print("{}")


if __name__ == "__main__":
    main()
