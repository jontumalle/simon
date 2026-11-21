---
name: dossier-track-record
description: >-
  Shared Stage 3 screening input skill for evaluating live show momentum,
  venue cap progression, collaborator credits, unsigned A&R whitespace, and
  strict missing_fields abstention (stage_momentum_whitespace: 0..2).
---

# `dossier-track-record` — Stage Momentum & A&R Whitespace Skill

Evaluates `live_history_and_credits` and `missing_fields` from a Stage 2 `InvestigatorDossier` and produces a deterministic `0..2` score, grounded `pros[]`, `cons[]`, and `missing[]` flags for `stage_momentum_whitespace`.

## Scoring Rubric (`stage_momentum_whitespace` · `0..2`)
- **`2` — Proven Stage Momentum + Unsigned Whitespace:** Unsigned (`public_team_mentions.label` has no major label), >=3 documented `show_history` gigs, AND >=1 `upcoming_shows` date or `highest_venue_cap_observed >= 300`.
- **`1` — Early Stage Activity or Unsigned Whitespace With Unverified/Abstained Shows:** Unsigned (`label` is null or indie/DIY) with 1–2 past shows, upcoming dates, or collaborator credits — including cases where `show_history` is listed in `missing_fields` and properly abstained rather than penalized as a failed live draw.
- **`0` — Major-Label Lockup or Zero Momentum Without Evidence/Abstention:** Major-label mention in `public_team_mentions.label` (hard A&R whitespace dealbreaker), or zero shows, zero upcoming dates, zero credits, and no abstained missing show fields.

## Strict Abstention Rule
When `live_history_and_credits.show_history` (or `upcoming_shows`) appears in `missing_fields`, treat empty gig arrays strictly as unverified unknowns in `missing[]` — never fabricate claims of poor live draw or cancelled tours.

## CLI Usage (Inside Sandbox)
```sh
python3 .agents/skills/dossier-track-record/scripts/score_track_record.py --dossier /workspace/in/dossier.json
```

## Python Library Usage
```python
import sys
sys.path.insert(0, ".agents/skills/dossier-track-record/scripts")
from score_track_record import evaluate

result = evaluate(dossier)
```
