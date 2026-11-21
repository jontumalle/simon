# `simon-source-hunter` (Daily & On-Demand Source Hunter Agent)

Gemini Managed Agent (`antigravity-preview-09-2026` · `gemini-4-hydrogen`) that continuously expands Simon's **Discovery Source Registry**. Runs daily at **9:00 AM ET** (via `/v1beta/triggers` + `.github/workflows/daily-source-hunter.yml`) and on demand from `/api/sources/hunt`.

## What It Does
1. Pulls existing `discovered_sources` and `source_registry` records from `simon-db` so it never re-adds a known URL.
2. Audits geographic, genre, and channel gaps and searches for `3–5` new grassroots sources (open-mic calendars, radio live sessions, DIY venue schedules, Bandcamp city hubs, indie gig directories, and session credit feeds).
3. Validates every candidate with `skills/source-validation/scripts/verify_sources.py` inside `code_execution`.
4. Persists verified sources to `discovered_sources` and publishes human-first **Field News** (`--stage discovery`) via `field-reporting`.

## Package Layout (Auto-Mounted by `simon/deploy.py`)
- `agent.json` / `agent.yaml` — Managed Agent spec (`id: simon-source-hunter`, `max_total_tokens: "64000"`, `shared_skills: ["simon-db", "youtube", "field-reporting", "source-discovery"]`).
- `SYSTEM.md` — 5-step Source Hunter instructions and strict JSON output contract.
- `skills/source-validation/SKILL.md` & `scripts/verify_sources.py` — Stdlib URL canonicalizer, enum checker, and registry deduplicator.

## Commands
```sh
# Dry-run compile Managed Agent payload
python3 -m simon deploy --agent source-hunter --prefix staging- --dry-run --out-dir /tmp/sh_build
```
