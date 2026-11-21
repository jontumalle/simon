# `screen-advocate` (`simon-screen-advocate`)

**Stage 3 Parallel Screening Critic — Talent Advocate (`gemini-4-neon`)**

Inspects all 5 blocks of a Stage 2 `InvestigatorDossier` (`identity_and_contact`, `source_and_media_queue`, `public_footprint`, `comment_forensics`, `live_history_and_credits`), builds the strongest factual upside case (`pros` + `standout_hook`), publishes human-first Field News (`--stage critic`), validates its output with `verify_advocate.py`, and returns `advocate_case` JSON.

## Sandbox Configuration
- **Base Agent**: `antigravity-preview-09-2026`
- **Model**: `gemini-4-neon` (`max_total_tokens: "64000"`)
- **Tools**: `code_execution`
- **Shared Skills**: `simon-db`, `field-reporting` (plus `dossier-*` domain lenses post-merge)
- **Local Skill**: `skills/advocate-rubric/` (`verify_advocate.py`)

## Input -> Output
- **Input**: Stage 2 `InvestigatorDossier` JSON (`data/discovery_investigator_contract.json`).
- **Output**: Verified `advocate_case` JSON:
  ```json
  {
    "lead_id": "lead_001",
    "stage_name": "Maya Vance",
    "headline": "...",
    "pros": [{"skill": "dossier-media", "title": "...", "evidence": "..."}],
    "standout_hook": "..."
  }
  ```

## Local Verification
```bash
.venv/bin/python -m simon deploy --agent screen-advocate --prefix staging- --dry-run --out-dir /tmp/simon_screen_build
python3 agents/screen-advocate/skills/advocate-rubric/scripts/verify_advocate.py /tmp/sample_advocate.json
```
