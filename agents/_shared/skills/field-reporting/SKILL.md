---
name: field-reporting
description: >-
  Human-first Field News and Scouting Report skill for Simon Managed Agents.
  Lets agents publish live in-motion updates (what they are looking at, what
  they found, and their analysis) and store their final structured output in
  `agent_reports` without raw telemetry, interaction IDs, or system metadata.
---

# `field-reporting` — Human-First Field News & Scouting Reports

Every Simon agent reports its work in plain human language so teammates can watch **Field News** live as agents work and read finished **Scouting Reports** afterward.

## Core Rules
1. **Human-First Only:** Never write `interaction_id`, `environment_id`, raw tool logs, or system `metadata` into a report.
2. **Report While in Motion (Field News):** Post a short step update whenever you start inspecting a source, spot a lead/fact, or finish an analysis check.
3. **Store Your Final Output:** When done, publish the final `AgentReport` with a plain-English `headline`, scannable `findings[]`, and your full structured `output` payload.

## Three Reporting Moments
- **`looking_at`** — What source, channel, or subject you are currently inspecting.
- **`finding`** — Concrete subjects, links, or objective facts you just discovered.
- **`analysis`** — Objective verification notes (attribution check, deduplication, or why a source/lead passed or was skipped).

## CLI Usage (Inside Sandbox)

```sh
# 1. Post a live Field News step while working
python3 .agents/skills/field-reporting/scripts/field_report.py step \
  --report-id "$SIMON_REPORT_ID" \
  --batch-id "$SIMON_BATCH_ID" \
  --agent-name "Discovery Scout 01" \
  --stage discovery \
  --brief "Find emerging NYC solo vocalists" \
  --phase looking_at \
  --title "Scanning Baby's All Right calendar" \
  --looking-at "Upcoming NYC indie & R&B bills at Baby's All Right" \
  --finding "Spotted 2 solo vocalists on this week's local support slots" \
  --analysis "Checking public live video clips to verify clear attribution."

# 2. Add a concrete finding card as soon as you verify it
python3 .agents/skills/field-reporting/scripts/field_report.py finding \
  --report-id "$SIMON_REPORT_ID" \
  --title "Maya Lin" \
  --summary "Solo neo-soul vocalist listed on Thursday acoustic showcase." \
  --source-name "Baby's All Right" \
  --source-channel "diy_venue_calendar" \
  --url "https://babysallright.com/events/..."

# 3. Publish the final Scouting Report + stored output when finished
python3 .agents/skills/field-reporting/scripts/field_report.py finish \
  --report-id "$SIMON_REPORT_ID" \
  --headline "Found 2 verified NYC solo vocalists across 2 active sources." \
  --output @/workspace/out/handoff_verified.json
```
