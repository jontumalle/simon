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
