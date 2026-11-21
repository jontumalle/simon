# Simon — Shared Resources & Toolchain Manifest

> **For Teammates & Coding Agents:** Read this file after `git pull` to ensure your local machine has every CLI, runtime, SDK, plugin, and environment variable needed to develop, test, and deploy Simon's Managed Agents.
> **Rule:** Never commit raw API keys or tokens here — document variable names and setup commands only.

---

## 1. Quick Agent Verification Command

Run this check first to see what is already installed vs. missing on your machine:

```sh
export PATH="$HOME/.local/bin:$HOME/google-cloud-sdk/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
for cmd in git gh uv gcloud gemini-api python3 ffmpeg yt-dlp jq; do
  printf "%-12s : %s\n" "$cmd" "$(command -v $cmd || echo 'MISSING')"
done
```

---

## 2. Core & Optional CLIs

| Resource | Required? | Purpose | Reproducible Install (macOS Apple Silicon `arm64`) |
| :--- | :---: | :--- | :--- |
| **GitHub CLI (`gh`)** | **Core** | Repo sync, PRs, repo-mounted Managed Agent checks (`jontumalle/simon`) | `~/.local/bin/gh` (`v2.105.0`), then `gh auth login && gh auth setup-git` |
| **`uv` + Python 3.12** | **Core** | Fast virtualenv/lockfile manager + Python ≥3.10 runtime (`v0.13.9` + `Python 3.12.16`) | `curl -LsSf https://astral.sh/uv/install.sh \| sh && ~/.local/bin/uv python install 3.12` |
| **Gemini API CLI (`gemini-api`)** | **Core** | Create/list/run `/v1beta/agents`, manage `environments` & `credentials`, YouTube/audio `analyze` (`v0.5.0`) | `GEMINI_VERSION="$(~/.local/bin/gh api repos/google-gemini/gemini-api-cli/releases/latest --jq .tag_name)" sh -c 'curl -fsSL https://raw.githubusercontent.com/google-gemini/gemini-api-cli/main/scripts/install.sh \| sh'` *(uses `gh` auth to avoid shared hackathon Wi-Fi 403 rate limits)* |
| **Google Cloud CLI (`gcloud`)** | **Core** | GCP auth, GCS bucket mounts (`sources: [{type: "gcs"}]`), optional Cloud Run / Vertex ops (`v594.0.0`) | Extract `google-cloud-cli-darwin-arm.tar.gz` to `~/google-cloud-sdk`, set `export CLOUDSDK_PYTHON="$(~/.local/bin/uv python find 3.12)"`, run `~/google-cloud-sdk/install.sh --quiet --path-update true`, then `gcloud auth login && gcloud auth application-default login` |
| **`ffmpeg` (`ffprobe`)** | Recommended | Trim, normalize, inspect sample rate/channels, convert `.m4a`/`.mov` → `.mp3`/`.wav` (<10 MB) | `brew install ffmpeg` or static `arm64` binary in `~/.local/bin/ffmpeg` |
| **`yt-dlp`** | Optional | Local helper for downloading opt-in public live-session clips into gitignored `local/` | `~/.local/bin/uv tool install yt-dlp` (no Homebrew needed!) |
| **`jq`** | Optional | Fast JSON inspection of `showcase.json` and `gemini-api -o json` outputs | `/usr/bin/jq` (preinstalled on macOS 15+) or `brew install jq` |

---

## 3. Python SDKs & Libraries

Create a `uv`-managed Python 3.12 virtual environment (`.venv/` is gitignored):

```sh
~/.local/bin/uv venv --python 3.12 .venv
~/.local/bin/uv pip install --python .venv/bin/python -U \
  google-genai \
  dspy \
  pydantic \
  pyyaml \
  soundfile \
  numpy \
  scipy \
  mutagen \
  pytest \
  pytest-asyncio \
  ruff \
  google-antigravity
```

| Package Group | Packages | Why We Need It |
| :--- | :--- | :--- |
| **Managed Agents & Decisions** | `google-genai`, `dspy`, `pydantic`, `pyyaml` | `v1beta` `client.decisions.create` (`gemini-decision-1`), `client.agents`, `interactions` + DSPy rubric compilation & strict schemas |
| **Audio Forensics** | `soundfile`, `numpy`, `scipy`, `mutagen` | Crest-factor, clipping, silence/layering heuristics, and duration/MIME validation locally & inside sandboxes |
| **Dev, Test & Local Agent** | `pytest`, `pytest-asyncio`, `ruff`, `google-antigravity` | Fast unit/contract suites, linting, and optional local interactive producer review harness |

---

## 4. Environment Variables (`.env` / Shell — Gitignored)

Keep secret values in `.env` (gitignored):

```sh
# Required: Paid / Hackathon Tier-3 Google AI Studio key for Managed Agents & Gemini 4 models
export GEMINI_API_KEY="your-api-key"

# Recommended: Namespace /v1beta/agents/{id} during dev so teammates don't overwrite each other
export SIMON_AGENT_PREFIX="kevin-"   # e.g. "kevin-", "jt-", or "prod-"

# Model & harness defaults
export GEMINI_AGENT="antigravity-preview-09-2026"
export SIMON_DISCOVERY_AGENT="antigravity-preview-09-2026"   # or deployed simon-discovery-scout ID
export SIMON_SYNTHESIS_AGENT="antigravity-preview-09-2026"   # or deployed simon-synthesis-scout ID
export GEMINI_AUDIO_MODEL="gemini-4-hydrogen"
export GEMINI_PRODUCER_MODEL="gemini-4-carbon"

# Optional: GCP project ID when using gcloud / GCS mounts
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
```

---

## 5. Antigravity Plugins & MCP Servers

Add/enable from the Antigravity Marketplace UI:
- **Gemini API** (`antigravity-plugins-official/plugin/gemini-api`) — Official skills & live schemas for Interactions API, Managed Agents, and `gemini-api` CLI.
- **Wispr Flow** (`antigravity-plugins-partners/plugin/wispr-flow`) — Pull meeting transcripts, voice notes, and scratchpads into `pm/inbox/`.
- **Google Cloud Developer** (`antigravity-plugins-official/plugin/google-cloud-developer`) — GCP auth validation and Google Developer Knowledge MCP.
- **Gmail / Google Sheets** (`gmail`, `gsheets` — *optional*) — Human-approved artist callback email drafts and showcase budget tracking.

Configure global MCP servers in `~/.gemini/config/mcp_config.json`:
- **Excalidraw MCP App** (`excalidraw`) — Official Streamable HTTP server for inline hand-drawn architecture diagrams (`{"mcpServers": {"excalidraw": {"url": "https://mcp.excalidraw.com/mcp"}}}`).

---

## 6. Repo-Scoped Antigravity Hooks & `main-sync` Skill (`.agents/`)

Checked into Git so every teammate gets them automatically after `git pull`:
- **`simon-toolchain-permissions` (`PreToolUse` → `.agents/scripts/auto_approve_toolchain.py`)** — Auto-approves (`"decision": "auto_approve"`) both **Knowledge Model / Steward documentation writes** (`PROJECT.md`, `AGENTS.md`, `RESOURCES.md`, `pm/**`, `notes/**`, `ideas/**`, `data/**`, `agents/**`, `.agents/**`, `*.md`) and safe invocations of the CLIs in this manifest (`git`, `gh`, `uv`, `python3`, `pytest`, `ruff`, `gemini-api`, `gcloud`, `ffmpeg`/`ffprobe`, `yt-dlp`, `jq`), while falling back to Antigravity's default permission prompt on runtime code writes outside default policy, `--skip-verify` / `--all` syncs, destructive flags, or unrecognized binaries.
- **`main-sync` Skill (`.agents/skills/main-sync/SKILL.md` → `.agents/scripts/sync_main.py`)** — Separates immediate **Docs Sync** (`--docs-only`, used by the `Project Manager (Steward)` straight to `origin/main`) from gated **Code Sync** (`--code --paths <files...>`, enforcing unit/smoke/ruff verification before commit and supporting `--branch feat/<slug>` PR workflows).
- **`plain-english` Skill (`.agents/skills/plain-english/SKILL.md`)** — On-command thought-partner alignment, Mermaid visualization, and STE-100 + Zinsser content rewriting/auditing skill.
- **`simon-session-context` (`SessionStart` → `.agents/scripts/session_start.py`)** — Injects `PROJECT.md` orientation at session start.
