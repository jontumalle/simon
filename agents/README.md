# Curated Managed Agents Registry (`agents/`)

This directory is where we **curate, version, test, and deploy** Simon's task-specific Managed Agents ("agent as a repo").

> Looking for *how* Managed Agents work under the hood and how to deploy them? See **[notes/managed-agents/playbook.md](../notes/managed-agents/playbook.md)** and `.agents/skills/managed-agents-curator/SKILL.md`.

---

## Standard Agent Package Layout

Each curated agent lives in its own subdirectory (`agents/<agent-name>/`) and mounts cleanly into an `antigravity-preview-09-2026` remote Linux sandbox:

```text
agents/<agent-name>/
├── agent.yaml        # Control-plane spec -> maps 1:1 to POST /v1beta/agents
├── SYSTEM.md         # System instruction & mounted as .agents/AGENTS.md in sandbox
├── skills/           # Optional sandbox skills -> mounted to .agents/skills/<skill>/
│   └── <skill-name>/
│       ├── SKILL.md
│       └── scripts/  # Executable Python verification helpers inside sandbox
└── README.md         # Purpose, inputs, outputs, and local/live test commands
```

Use `SIMON_AGENT_PREFIX` (`kevin-`, `jt-`, `prod-`) when syncing to `/v1beta/agents` so teammates can test agent changes concurrently without clobbering shared IDs.

---

## Planned & Active Agent Roster

| Directory / Agent | Harness & Model | Network | Role | Status |
| :--- | :--- | :--- | :--- | :--- |
| `acoustic-scout` | `deep-research-preview-04-2026` / `gemini-4-hydrogen` | Allowlisted | Discovers opt-in open-mic/local vocalists & extracts timestamped audio observations | Planned |
| `performance-critic` | `antigravity-preview-09-2026` (`gemini-4-hydrogen`) | `disabled` | Independent vocal phrasing, dynamics, waveform/single-take forensics & performance critique | Planned |
| `booking-critic` | `antigravity-preview-09-2026` (`gemini-4-hydrogen`) | `disabled` | Independent stage setup, slot length, original-song fit & practical open questions | Planned |
| `showcase-producer` | `antigravity-preview-09-2026` (`gemini-4-carbon`) | `disabled` / Allowlisted | Arbitrates critic disagreements, checks showcase unit economics, drafts `pending_human_review` offer | Planned |
