# `screen-skeptic` (`simon-screen-skeptic`)

**Stage 3 Parallel Screening Critic — Talent Skeptic (`gemini-4-carbon`)**

Audits all 5 blocks of a Stage 2 `InvestigatorDossier` for concrete risks and dealbreakers (one-clip view concentration `>85%`, studio-only media, `uncertain` attribution, `contact_route_type == "none"`, major label lockup, spam comments), preserves `missing_fields` inside `missing_evidence_flags` without inventing fake flaws, posts Field News (`--stage critic`), validates with `verify_skeptic.py`, and returns `skeptic_case` JSON.

## Sandbox Configuration
- **Base Agent**: `antigravity-preview-09-2026`
- **Model**: `gemini-4-carbon` (`max_total_tokens: "64000"`)
- **Tools**: `code_execution`
- **Shared Skills**: `simon-db`, `field-reporting` (plus `dossier-*` domain lenses post-merge)
- **Local Skill**: `skills/skeptic-rubric/` (`verify_skeptic.py`)

## Input -> Output
- **Input**: Stage 2 `InvestigatorDossier` JSON (`data/discovery_investigator_contract.json`).
- **Output**: Verified `skeptic_case` JSON:
  ```json
  {
    "lead_id": "lead_001",
    "stage_name": "Maya Vance",
    "headline": "...",
    "cons": [{"skill": "dossier-footprint", "title": "...", "evidence": "..."}],
    "missing_evidence_flags": ["..."],
    "dealbreakers_checked": ["one_clip_view_concentration_gt_85pct", "studio_only_media", "uncertain_attribution", "contact_route_none", "major_label_lockup", "spam_comments"]
  }
  ```

## Local Verification
```bash
.venv/bin/python -m simon deploy --agent screen-skeptic --prefix staging- --dry-run --out-dir /tmp/simon_screen_build
python3 agents/screen-skeptic/skills/skeptic-rubric/scripts/verify_skeptic.py /tmp/sample_skeptic.json
```
