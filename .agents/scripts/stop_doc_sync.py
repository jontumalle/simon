#!/usr/bin/env python3
"""Disabled Antigravity Stop hook (kept as a no-op for backward compatibility).

Previously returned `{"decision": "continue", ...}` when uncommitted docs existed.
That forced a second post-reply turn, which caused Antigravity to collapse the
agent's actual response into the "Worked for Xm >" dropdown and also bled across
parallel chat windows (OBS-2026-11-21-01). Doc sync is handled instead by explicit
`sync_main.py --docs-only` calls and the background Project Manager (Steward).
"""

import sys


def main() -> None:
    sys.stdin.read()
    print("{}")


if __name__ == "__main__":
    main()
