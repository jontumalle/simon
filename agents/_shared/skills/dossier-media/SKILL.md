---
name: dossier-media
description: >-
  Shared Stage 3 screening input skill for evaluating attribution honesty,
  embeddable video liveness, and live vocal session proof (live_vocal_proof: 0..2)
  from an InvestigatorDossier.
---

# `dossier-media` — Live Vocal Proof Screening Skill

Evaluates `source_and_media_queue` (plus relevant `missing_fields`) from a Stage 2 `InvestigatorDossier` and produces a deterministic `0..2` score, grounded `pros[]`, `cons[]`, and `missing[]` flags for `live_vocal_proof`.

## Scoring Rubric (`live_vocal_proof` · `0..2`)
- **`2` — Multi-Clip Verified Live Proof:** `attribution_status == "verified"`, >=2 embeddable clips (`oembed_live_embeddable: true`, valid duration <3600s), and >=1 clip confirming stripped/live vocal performance context.
- **`1` — Single Live Take or Partial Proof:** `attribution_status == "verified"` with a single embeddable clip (or studio-only verified clips), OR `attribution_status == "uncertain"` with >=1 embeddable live-session clip.
- **`0` — Zero Live Vocal Proof or Uncertain Studio Upload:** Zero embeddable media links, OR `attribution_status == "uncertain"` on studio-only / visualizer uploads with no live vocal evidence.

## CLI Usage (Inside Sandbox)
```sh
python3 .agents/skills/dossier-media/scripts/score_media.py --dossier /workspace/in/dossier.json
```

## Python Library Usage
```python
import sys
sys.path.insert(0, ".agents/skills/dossier-media/scripts")
from score_media import evaluate

result = evaluate(dossier)
```
