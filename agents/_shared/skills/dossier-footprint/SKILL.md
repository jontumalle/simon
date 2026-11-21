---
name: dossier-footprint
description: >-
  Shared Stage 3 screening input skill for evaluating early discovery window,
  catalog depth, and single-clip view concentration (early_window_depth: 0..2)
  from an InvestigatorDossier.
---

# `dossier-footprint` — Early Window & Catalog Depth Screening Skill

Evaluates `public_footprint` (plus relevant `missing_fields`) from a Stage 2 `InvestigatorDossier` and produces a deterministic `0..2` score, grounded `pros[]`, `cons[]`, and `missing[]` flags for `early_window_depth`.

## Scoring Rubric (`early_window_depth` · `0..2`)
- **`2` — Early Window + Multi-Release Depth + Healthy Spread:** `footprint_regime` in `pre_dsp_underground` or `early_dsp_inflection`, catalog depth (>=3 released tracks/Bandcamp releases or >=20 Bandcamp supporters), and no extreme single-clip concentration (`top_release_view_share_pct < 80%`).
- **`1` — Mixed Window, Thin Catalog, or High Single-Clip Concentration:** Early-window act with `top_release_view_share_pct >= 80%` (viral 1-clip skew) or <3 releases, OR `established_streaming` act with multi-release catalog depth.
- **`0` — Past Window Without Depth or Empty Unclassified Footprint:** `footprint_regime == "unknown"` with zero documented tracks/views, or `established_streaming` combined with thin catalog or >=80% single-clip skew.

## CLI Usage (Inside Sandbox)
```sh
python3 .agents/skills/dossier-footprint/scripts/score_footprint.py --dossier /workspace/in/dossier.json
```

## Python Library Usage
```python
import sys
sys.path.insert(0, ".agents/skills/dossier-footprint/scripts")
from score_footprint import evaluate

result = evaluate(dossier)
```
