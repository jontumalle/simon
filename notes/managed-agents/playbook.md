# Gemini Managed Agents & "Agent as a Repo" Playbook

Comprehensive architectural & implementation reference for building, curating, testing, and deploying Simon's Managed Agents (`v1beta` Control Plane & Runtime).

---

## 1. Why This Unlocks "Best Use of Managed Agents" ($5,000)

The starter in [simon/gemini.py](../../simon/gemini.py) calls `POST /v1beta/interactions` with `"agent": "antigravity-preview-09-2026"`, `"store": False`, and `"tools": []` — treating Managed Agents like a stateless text endpoint. Upgrading to the full Managed Agents architecture unlocks:

1. **Persistent Named Agents (`/v1beta/agents`)**: Curated blueprints (`simon-acoustic-scout`, `simon-performance-critic`, `simon-booking-critic`, `simon-showcase-producer`) with model specialization (`gemini-4-hydrogen` for fast parallel critics; `gemini-4-carbon` for Producer arbitration & deal math; `deep-research-preview-04-2026` for scene/open-mic discovery).
2. **"Agent as a Repo" (`base_environment.sources`)**: `antigravity-preview-09-2026` natively discovers `.agents/AGENTS.md` and `.agents/skills/<name>/SKILL.md` inside its remote Linux container! Mounting our repo (or inline `.agents/` rules + Python acoustic scripts) lets critics execute real waveform/clipping/dynamic-range forensics inside the sandbox.
3. **Shared Sandbox & Epistemic Independence (`/v1beta/environments` + Files API)**: Upload audition clips once via `environments.files.upload`, share `environment_id` so scripts/artifacts persist on disk, **omit** `previous_interaction_id` between `performance-critic` and `booking-critic` so neither sees the other's chain of thought, and pull structured outputs (`callback_packet.json`) via `environments.files.download`.
4. **Zero-Trust Sandbox Security (`network` + `/v1beta/credentials`)**: Run artist-audio critics with `"network": "disabled"` (zero exfiltration of unreleased demos), and inject external API tokens on-the-wire via the egress proxy (`Credentials API`) only where needed.
5. **Async Background Runs (`background=True`)**: Avoid 180s HTTP socket timeouts on multi-step Python/research runs (note: requires `store=True`, whereas starter `simon/gemini.py` sets `store: False`).

---

## 2. Control Plane & Runtime API Reference (`v1beta`)

Base URL: `https://generativelanguage.googleapis.com/v1beta`
Headers: `x-goog-api-key: $GEMINI_API_KEY`, `Api-Revision: 2026-05-20`, `Content-Type: application/json`

### 2.1 Base Harnesses & Models
- **`antigravity-preview-09-2026`**: Full Linux container (Bash, Python 3.12, Node 22, file/search tools) with automatic `.agents/AGENTS.md` + `.agents/skills/` progressive disclosure.
  - Configure model via `agent_config`:
    - `{"type": "antigravity", "model": "gemini-4-hydrogen"}` (default — fast multimodal & parallel critics)
    - `{"type": "antigravity", "model": "gemini-4-carbon"}` (frontier deep reasoning — Producer synthesis)
- **`deep-research-preview-04-2026`**: Long-horizon multi-source web research harness (discovering NYC open-mic lineups, listening rooms, and emerging artist press kits).

### 2.2 Registering Custom Agents (`google-genai` SDK)

```python
from google import genai

client = genai.Client(http_options={"api_version": "v1beta"})

producer = client.agents.create(
    id="simon-showcase-producer",
    base_agent="antigravity-preview-09-2026",
    agent_config={
        "type": "antigravity",
        "model": "gemini-4-carbon",
    },
    system_instruction=(
        "You are Simon's Lead Showcase Producer for First Listen NYC. "
        "Compare independent performance and booking reviews, surface real disagreements, "
        "verify artist guarantee math, and draft human-gated callback invitations."
    ),
    tools=[{"type": "code_execution"}],
    base_environment={
        "type": "remote",
        "sources": [
            {
                "type": "repository",
                "source": "https://github.com/jontumalle/simon",
                "target": "/workspace/simon",
            },
            {
                "type": "inline",
                "target": ".agents/AGENTS.md",
                "content": "# Producer Rules\n- Cite audition IDs and timestamps.\n- Never invent commitments.\n",
            },
        ],
        "network": "disabled",
    },
)
```

### 2.3 Sandbox Files API & Async Interactions

```python
# 1. Upload audition audio into a shared environment
client.environments.files.upload(
    environment=env_id,
    path="workspace/auditions/a01.wav",
    file=open("local/a01.wav", "rb"),
    mime_type="audio/wav",
)

# 2. Launch async background run (store=True is required with background=True)
job = client.interactions.create(
    agent="simon-performance-critic",
    input="Analyze /workspace/auditions/a01.wav and write findings.",
    environment=env_id,
    background=True,
)

# 3. Poll until completed
result = client.interactions.get(job.id)
```

### 2.4 CLI Operations (`gemini-api` v0.5.0)
Google's official `gemini-api` CLI (`github.com/google-gemini/gemini-api-cli`) lets humans and local coding agents inspect, create, and test Managed Agents directly from the shell (note: subcommand is `agent` singular, and `analyze -i` supports local audio AND YouTube URLs directly!):
```sh
gemini-api agent list --page-size 10
gemini-api agent get simon-performance-critic
gemini-api agent create --id simon-performance-critic --base-agent antigravity-preview-09-2026 \
  --system-instruction "Independently evaluate vocal phrasing and live execution."
gemini-api agent run "Review audition a01" --agent simon-performance-critic --background --jq '.id'
gemini-api agent status <run-id> -o json
gemini-api environments files list -e <env-id> -r
gemini-api analyze -i "https://www.youtube.com/watch?v=..." "Describe vocal phrasing and timestamps"
```

---

## 3. Platform Comparison: Which Google Agent Stack Does What?

| Stack | What It Is | Role in Simon |
| :--- | :--- | :--- |
| **Gemini API Managed Agents** (`/v1beta/agents` + `interactions`) | Hosted Linux sandboxes (`antigravity-preview-09-2026`, `deep-research-preview-04-2026`) authenticated via `GEMINI_API_KEY` | **Primary Hackathon Runtime** — directly powers Simon's scouting, critic, and producer Managed Agents |
| **Antigravity Python SDK** (`google-antigravity`) | Local programmatic agent runtime (`LocalAgentConfig`) | Optional local interactive producer review loop or automated local evaluation harness |
| **Vertex AI Agent Engine** (`adk deploy agent_engine` / `gcloud`) | Enterprise GCP serverless hosting for custom Python agent classes | Optional cloud hosting if deploying a public web backend; not required for core Managed Agents API |

---

## 4. Curation & Teammate Sync Pattern (`agents/` → `/v1beta/agents`)

1. **Declarative Source of Truth (`agents/<name>/`)**:
   - `agent.yaml`: Maps 1:1 to `/v1beta/agents` (`id`, `base_agent`, `agent_config.model`, `tools`, `environment` mounts & network policy).
   - `SYSTEM.md`: Core persona, epistemic boundaries, and output contract (also mounted as `.agents/AGENTS.md` inside the remote sandbox).
   - `skills/<skill>/SKILL.md` + `scripts/`: Mounted into `.agents/skills/` inside the remote sandbox so the Managed Agent gets progressive-disclosure skills & executable Python verification scripts!
2. **Teammate Collision Prevention (`SIMON_AGENT_PREFIX`)**:
   - Prefix deployed agent IDs during dev (`SIMON_AGENT_PREFIX=kevin-` vs `SIMON_AGENT_PREFIX=jt-` vs `prod-`) so both teammates can sync and test changes concurrently against the shared hackathon project without overwriting each other's agents.
