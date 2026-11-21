# `screening-judge` (`simon-screening-judge`)

**Stage 3 Screening Judge & Synthesis Arbitrator (`gemini-4-neon`)**

Consumes `(InvestigatorDossier + advocate_case + skeptic_case)`, scores the 5 `0–2` rubrics (`identity_reachability`, `live_vocal_proof`, `early_window_depth`, `listener_pull_cosigns`, `stage_momentum_whitespace` -> `0..10` total), arbitrates Advocate Pros vs. Skeptic Cons, assigns `verdict` (`"elevate" | "watch" | "pass"`), `confidence` (`0..1`), and `rationale`, validates via `verify_judgment.py`, saves the `ScreeningPacket` to `simon-db` (`screening_packets`), publishes the final Scouting Report (`--stage synthesis`), and outputs `ScreeningPacket` v1.0.0 JSON.

## Sandbox Configuration
- **Base Agent**: `antigravity-preview-09-2026`
- **Model**: `gemini-4-neon` (`max_total_tokens: "64000"`)
- **Tools**: `code_execution`
- **Shared Skills**: `simon-db`, `field-reporting` (plus `dossier-*` domain lenses post-merge)
- **Local Skill**: `skills/judge-rubric/` (`verify_judgment.py`)

## Input -> Output
- **Input**: Stage 2 `InvestigatorDossier` + `advocate_case` + `skeptic_case` JSON.
- **Output**: Verified `ScreeningPacket` v1.0.0 JSON (`schema_version: "1.0.0"`, `total_score: 0..10`, `verdict: "elevate" | "watch" | "pass"`).

## Local Verification
```bash
.venv/bin/python -m simon deploy --agent screening-judge --prefix staging- --dry-run --out-dir /tmp/simon_screen_build
python3 agents/screening-judge/skills/judge-rubric/scripts/verify_judgment.py /tmp/sample_packet.json
```
