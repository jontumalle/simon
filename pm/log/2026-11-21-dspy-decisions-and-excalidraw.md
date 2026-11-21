# 2026-11-21 — DSPy + Gemini Decisions API Research & Excalidraw MCP Setup

## What Happened
- **DSPy + Gemini Decisions API Architecture Research**:
  - Investigated pairing **DSPy** (`Signatures`, `Modules`, and `Optimizers` such as `MIPROv2` and `BootstrapFewShot`) with the **Gemini Decisions API** (`gemini-decision-1` via `google-genai >= 3.2.0` `client.decisions.create` on `v1beta`) to train, compile, and version Simon's audition readiness classifier without hand-tuning brittle prompt strings:
    - **Phase 1 — Offline Compile (`Train`)**: Curate labeled producer audition examples (`brief`, `evidence` → `callback` | `need_live_clip` | `pass`) + a Python metric, run `dspy.MIPROv2` / `BootstrapFewShot` to optimize rubric instructions and few-shot demos, and serialize the winning program to a versioned JSON artifact (e.g., `classifier_v1.json`).
    - **Phase 2 — Calibrated Runtime (`Inference`)**: Load the compiled rubric instructions into a `dspy.Module` backed by `client.decisions.create(model="gemini-decision-1", ...)` returning calibrated `noul` / `choice` / `score` answers and confidence probabilities with **0 output tokens** over text or audio inputs.
- **Interactive Architecture Diagrams**:
  - Produced an interactive Generative UI HTML widget (`dspy_diagram.html` in conversation brain `e376eb31-6d97-495e-a0ab-3fa2e9763d4c`) inspecting all 6 compile/inference nodes (`Signature`, `Module`, `Decisions API`, `Gold Data + Metric`, `Optimizer`, `Compiled JSON`).
  - Connected the official **Excalidraw MCP App** (`https://mcp.excalidraw.com/mcp`) in `~/.gemini/config/mcp_config.json`, documented it in Section 5 of [RESOURCES.md](../../RESOURCES.md), and rendered an interactive 2-phase Excalidraw architecture diagram in chat.
- **Official Gemini API Plugin Enabled**:
  - Installed and activated `antigravity-plugins-official/plugin/gemini-api` (recorded in Section 5 of [RESOURCES.md](../../RESOURCES.md)), exposing live `gemini-api-docs` MCP search and `gemini-api-dev` / `gemini-api-cli` skills.
- **Setup-Stage Guardrail Check**:
  - Held off on creating a new subfolder for standalone DSPy + Decisions API notes/artifacts pending owner confirmation on bucket placement (`notes/` vs. `ideas/`); captured distilled architectural details here in `pm/log/` and flagged the open question in [pm/current.md](../current.md).
- **Installed `dspy==3.5.0` & Designed Part 1 Operational Architecture (`8e19edd`)**:
  - Installed `dspy==3.5.0` into `.venv` (`Python 3.12.16`) alongside `google-genai==3.6.1` and recorded `dspy` in [RESOURCES.md](../../RESOURCES.md).
  - Designed the **Part 1 Operational & Deployment Architecture** (Gemini Decisions API + DSPy rubric compiler + relational DB + local/cloud parity) and rendered it via the Excalidraw MCP App (`checkpointId: eaa2076dc41743f49f`).
  - Defined a portable **4-table relational schema** shared across local SQLite and deployed Postgres:
    1. `events` (`id`, `name`, `slot`, `fit_brief`, `artist_guarantee_usd`)
    2. `auditions` (`id`, `event_id`, `artist_alias`, `consent`, `audio_uri`, `performance_notes`, `artist_notes`)
    3. `rubric_versions` (`version_id`, `created_by`, `instructions_json`, `demos_json`, `val_accuracy`, `is_active`)
    4. `decision_evaluations` (`id`, `audition_id`, `rubric_version_id`, `live_viable_prob`, `vocal_score`, `triage_choice`, `choice_probs_json`, `confidence`, `human_label`) — storing producer feedback (`human_label`) so future `dspy` runs compile `rubric_v2+`.
- **Verified End-to-End Part 1 Prototype (`scratch/try_part1_decisions_dspy.py`)**:
  - Validated exact `google-genai==3.6.1` `client.decisions.create(model="gemini-decision-1", ...)` (`v1beta`) Pydantic question & answer schemas:
    - **`NoulQuestion`**: `{"type": "noul", "instructions": str, "criteria": {"true_description": str, "false_description": str}}` → `answer.noul` (`float` calibrated $P(\text{yes})$), `answer.confidence`.
    - **`ChoiceQuestion`**: `{"type": "choice", "instructions": str, "criteria": dict[str, str]}` → `answer.choice`, `answer.probabilities` (`dict[str, float]`), `answer.confidence`.
    - **`ScoreQuestion`**: `{"type": "score", "instructions": str, "criteria": list[str]}` (ordered rubric anchors `0..N-1`) → `answer.score`, `answer.legend`, `answer.probabilities`, `answer.confidence`.
  - Compiled `rubric_v1` via `dspy.BootstrapFewShot`, persisted instructions + bootstrapped demos into `rubric_versions`, and scored `examples/showcase.json`:
    - `a01` (*Mara Vance*) → `callback_shortlist` (`P(yes)=0.93`, `vocal_score=3.45/4.00`, `confidence=0.90`) → triggers downstream Critic Managed Agents (`performance-critic` + `booking-critic`).
    - `a02` (*Devon Vale*) → `request_live_clip` (`P(yes)=0.41`, `vocal_score=2.95/4.00`, `confidence=0.87`) → auto-drafts raw single-take live clip request without invoking heavy Managed Agents.
  - **DSPy + `google-genai` Engineering Gotcha**: Do **not** store `genai.Client` as an instance attribute on a `dspy.Module` subclass — `dspy.Module.deepcopy()` deep-copies all module fields during compilation (`BootstrapFewShot` / `MIPROv2`), which breaks or mishandles underlying `httpx` client/socket state. Inject/resolve `genai.Client` via an external getter/context or exclude it in `__deepcopy__`.
