---
name: dossier-audience
description: >-
  Shared Stage 3 screening input skill for evaluating organic listener pull,
  release/live-show request intent, spam ratio, and peer/curator co-signs
  (listener_pull_cosigns: 0..2) from an InvestigatorDossier.
---

# `dossier-audience` — Listener Pull & Co-Sign Forensics Skill

Evaluates `comment_forensics` (plus relevant `missing_fields`) from a Stage 2 `InvestigatorDossier` and produces a deterministic `0..2` score, grounded `pros[]`, `cons[]`, and `missing[]` flags for `listener_pull_cosigns`.

## Scoring Rubric (`listener_pull_cosigns` · `0..2`)
- **`2` — Strong Organic Pull & Peer Co-Signs:** `sample_size >= 15`, low spam (`jokes_or_spam < 35%`), high actionable listener intent (`release_requests + live_show_requests >= 35%` of sample or `>= 12` requests), AND `>= 1` `notable_commenters` peer/curator co-sign.
- **`1` — Moderate Positive Signal Without Co-Signs (or Small Sample):** Positive listener sentiment (`jokes_or_spam < 50%`) with genuine praise or release/show requests, or >=1 notable co-sign on a small comment sample.
- **`0` — Spam-Heavy, Zero-Intent, or Unsampled Comments:** `jokes_or_spam >= 50%` of comments, near-zero genuine pull with zero notable co-signs, or `sample_size == 0` with zero notable co-signs.

## CLI Usage (Inside Sandbox)
```sh
python3 .agents/skills/dossier-audience/scripts/score_audience.py --dossier /workspace/in/dossier.json
```

## Python Library Usage
```python
import sys
sys.path.insert(0, ".agents/skills/dossier-audience/scripts")
from score_audience import evaluate

result = evaluate(dossier)
```
