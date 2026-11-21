---
name: source-discovery
description: >-
  End-to-end Discovery Process playbook for Simon Stage 1 Discovery agents.
  Defines how agents pull known sources, explore live venues/channels for new
  sources and emerging leads, report Field News in motion, and store verified
  DiscoveryHandoff outputs and Scouting Reports.
---

# `source-discovery` — Actual Stage 1 Discovery Process

Use this playbook on every Stage 1 Discovery assignment so scouting is repeatable, transparent in **Field News**, and stored cleanly in **Scouting Reports**.

## 5-Stage Discovery Process

### 1. Orient & Announce (`looking_at`)
- Read the `search_brief`, `requested_count`, and any `assigned_sources` passed from the Discovery Dashboard.
- Pull existing active sources from `simon-db` (`discovered_sources`) if you need additional coverage.
- Post your first **Field News** step via `field-reporting` stating which sources/channels you are inspecting.

### 2. Probe Assigned Sources & Discover New Ones (`looking_at` → `finding`)
- Inspect each assigned source using `youtube` (for YouTube live sessions/channels), `url_context`, or `google_search`.
- Whenever you uncover a new high-signal venue calendar, open-mic series, live session channel, or local directory not yet in `discovered_sources`, log it to `discovered_sources` via `simon-db`.
- Post a **Field News** `finding` step describing what you actually saw on the bill/channel and who stood out as a verifiable subject.

### 3. Verify & Deduplicate (`analysis`)
- Never rank, score, or editorialize. Keep notes strictly objective (where found, format, bill/channel).
- Verify public URLs and clear artist attribution; merge duplicate sightings of the same subject into one `DiscoveryLead`.
- Run `verify_handoff.py` inside `code_execution` until it exits `0`.
- Post an `analysis` step via `field-reporting` explaining how many leads passed verification and why any weak/unverified candidates were excluded.

### 4. Persist Discovery Artifacts (`simon-db`)
- Save the verified `DiscoveryHandoff` v1.0.0 payload to `discovery_handoffs`.
- Save each verified lead to `leads`.
- Save each newly discovered reusable source to `discovered_sources`.

### 5. Publish Final Scouting Report (`field-reporting`)
- Call `field_report.py finish` with a plain-English `headline` and `--output @/workspace/out/handoff_verified.json` so the **Scouting Reports** screen displays both the human summary and the stored structured output.
