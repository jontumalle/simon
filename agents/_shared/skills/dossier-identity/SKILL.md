---
name: dossier-identity
description: >-
  Shared Stage 3 screening input skill for evaluating artist identity clarity,
  platform link graph, and direct business reachability (identity_reachability: 0..2)
  from an InvestigatorDossier.
---

# `dossier-identity` — Identity & Reachability Screening Skill

Evaluates `identity_and_contact` (plus relevant `missing_fields`) from a Stage 2 `InvestigatorDossier` and produces a deterministic `0..2` score, grounded `pros[]`, `cons[]`, and `missing[]` flags for Stage 3 Advocate, Skeptic, and Judge agents.

## Scoring Rubric (`identity_reachability` · `0..2`)
- **`2` — Direct Reachability & Resolved Identity:** Verified `stage_name`, concrete `project_type` (`solo_vocalist`, `duo`, `band`, or `collective`), >=2 active `platform_urls`, and direct business contact (`has_public_business_contact: true` with `contact_route_type` in `bio_email` or `mgmt_email`).
- **`1` — Partial Reachability or Outreach Friction:** Resolved `stage_name` with >=1 platform URL reachable via `open_dm`, OR direct business email with incomplete identity metadata (`project_type: "unknown"` or <2 platform URLs).
- **`0` — Unreachable or Unresolved Identity:** `contact_route_type: "none"` (without public business contact), blank `stage_name`, or zero resolved platform URLs.

## Abstention Rule
Fields listed in `missing_fields` (such as `identity_and_contact.musicbrainz_mbid` or `identity_and_contact.home_city`) are recorded in `missing[]` as unknowns — never turned into fabricated flaws.

## CLI Usage (Inside Sandbox)
```sh
python3 .agents/skills/dossier-identity/scripts/score_identity.py --dossier /workspace/in/dossier.json
```

## Python Library Usage
```python
import sys
sys.path.insert(0, ".agents/skills/dossier-identity/scripts")
from score_identity import evaluate

result = evaluate(dossier)
```
