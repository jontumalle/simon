# 2026-11-21 — Wispr Flow Pipeline Alignment & Taste-Brief YouTube Vocal Scout MVP

## What Happened
- **Wispr Flow Team Alignment (`"Minimal Agent Development Pipeline"`)**:
  - Distilled shared Wispr Flow meeting note recorded 2026-11-21 11:56 AM–12:00 PM EST (`Hackathon` folder, shared by Kevin Quizhpi: `https://notes.wisprflow.ai/shared/KXKIPjyzPKvAGOJd4rbw8G9KvFVLM6ZjnJHdWXQ4KGo`).
  - **Workstream Split**:
    - **Kevin Quizhpi**: Building the minimal Managed Agent factory, automated CI checks, and GitHub Actions deployment loop.
    - **Jonathan Tumalle**: Prototyping the end-to-end scouting & human-verification workflow while abstractly documenting stage inputs/outputs across 3 clean pipeline units so both workstreams integrate cleanly:
      1. **Unit 1 — Video Discovery & Info Extraction**: Public performance discovery, URL/timestamp canonicalization, attribution verification, and timestamped multimodal vocal observations.
      2. **Unit 2 — Decision/Synthesis & Thin-Evidence Loop**: Multi-clip assessment, automatic second-take search when initial evidence is thin/uncertain, and capped shortlist synthesis (`<= 3` singers).
      3. **Unit 3 — SQLite Evidence Storage & Shortlist Verification UI**: Normalized relational persistence (`local/simon.db`) retaining original source URLs and timestamped playback links alongside an interactive human verification player.
- **Shipped End-to-End Taste-Brief Vocal Scout MVP (`318e9e8` on `origin/main`)**:
  - **Public Zero-Signup YouTube Connector ([simon/youtube.py](../../simon/youtube.py))**:
    - Implemented public YouTube search + oEmbed verification, URL/timestamp canonicalization, performer grouping, and `uncertain` attribution flags for third-party, venue, or collaborative uploads.
    - Selected **public YouTube over SoundCloud** because Gemini (`gemini-4-hydrogen`) natively accepts public YouTube URLs for direct multimodal video/audio listening while SoundCloud API terms explicitly prohibit feeding API tracks into AI models.
  - **Typed Domain Records & Normalized SQLite Store ([simon/models.py](../../simon/models.py), [simon/store.py](../../simon/store.py))**:
    - Added typed models and SQLite persistence (`local/simon.db`) across 5 normalized tables: `scout_runs`, `artist_leads`, `clip_evidence`, `clip_observations`, and `artist_assessments`.
    - Every observation retains both the canonical `source_url` and a timestamp-anchored `play_url` so producers can verify claims immediately.
  - **Managed Agent Discovery, Multimodal Listening & Thin-Evidence Second-Take Loop ([simon/gemini.py](../../simon/gemini.py), [simon/scout.py](../../simon/scout.py))**:
    - Wired `simon-discovery-scout` Managed Agent + `gemini-4-hydrogen` direct YouTube video evaluator (`1-2` timestamped observations per clip across phrasing, dynamics, interpretation, and arrangement, plus `live | studio | unclear` recording context).
    - Added the **Thin-Evidence Second-Take Loop** (automatically seeking a corroborating clip when initial evidence is single-clip, studio-heavy, or uncertain) and `simon-synthesis-scout` Managed Agent outputting `<= 3` shortlisted vocalists with Play-First links and explicit single-clip caution flags.
  - **Interactive Scouting Studio Web Demo & CLI ([simon/web.py](../../simon/web.py), [simon/__main__.py](../../simon/__main__.py))**:
    - Shipped `python3 -m simon serve --port 8765` with an embedded timestamped **YouTube Moment Verifier** player, Managed Agent trace inspector, Play-First shortlist cards, and SQLite evidence viewer.
    - Added `python3 -m simon scout` CLI while keeping default `python3 -m simon` showcase mode backward-compatible with `main-sync` smoke gates.
  - **Curated Agent Specs, Pipeline Contracts, Fixtures & Tests**:
    - Added curated Managed Agent definitions in [agents/discovery-scout/](../../agents/discovery-scout/README.md) and [agents/synthesis-scout/](../../agents/synthesis-scout/README.md) (registered in [agents/README.md](../../agents/README.md)), plus `SIMON_DISCOVERY_AGENT` and `SIMON_SYNTHESIS_AGENT` in [RESOURCES.md](../../RESOURCES.md).
    - Published machine-readable 3-unit stage input/output contracts in [data/mvp_contracts.json](../../data/mvp_contracts.json) and an oEmbed-verified public YouTube demo fixture in [examples/taste_brief_demo.json](../../examples/taste_brief_demo.json).
    - Verified 10 passing test suites (`tests/test_mvp_scout.py`, `tests/test_smoke.py`, and cross-machine `Path.home()` portability fix in `tests/test_auto_approve_hook.py`); skipped transient `scratch/verify_yt.py` artifact per Steward rules.
- **Live End-to-End Gemini API + YouTube Verification (`10a043d`, `run_881b5370` in `local/simon.db`)**:
  - Ran `python3 -m simon scout --live --brief "Find singers who reinterpret familiar songs through phrasing or arrangement."` against live `/v1beta/interactions` and public YouTube.
  - **`v1beta/interactions` Runtime Findings & Fixes ([simon/gemini.py](../../simon/gemini.py))**:
    1. **Managed Agents Require `store=True` + Async Polling**: `antigravity-preview-09-2026` rejects `"store": false` with HTTP 400 (`This agent cannot be used with store = false`) and runs asynchronously (`background=True` + polling `GET /v1beta/interactions/{id}` until `status == "completed"`, extracting structured text across both `outputs` and `steps`).
    2. **Traceable Interaction IDs on Direct Model Calls**: Ephemeral `store: false` model calls omit `result["id"]`; enabled `store=True` on `evaluate_youtube_clip` for traceable `v1_...` interaction IDs and added safe ID resolution across all calls.
  - **Live Run Highlights (`run_881b5370`)**:
    - **Discovery Managed Agent** (`v1_ChdyZVFCYTgyekxNWDcwX2dQLW9TRDJBMBIXcmVRQmE4MnpMTVg3MF9nUC1vU0QyQTA`) searched live session series and grouped 16 oEmbed-verified clips into 4 artist leads (`Remy Bond`, `Luna Jinna`, `Blake Whiten`, `Daisy Gray`).
    - **Direct `gemini-4-hydrogen` Video Listening & Second-Take Loop**: Evaluated 6 YouTube URLs directly (`{"type": "video", "uri": ...}`). Notably detected that Remy Bond's `"Don't Speak (Live) | ReImagined"` was actually `recording_context: "studio"` (double-tracked chorus + constant vocal level when pulling away from the mic), automatically triggering the **Second-Take Loop** (`trace_03`) to locate and verify a true live performance (`"No One (Live from Secret Sessions)"`, `recording_context: "live"`).
    - **Synthesis Managed Agent** (`v1_ChdBdVVCYTllZ0w5YWlvX1VQeTVLbDRBdxIXQXVVQmE5ZWdMOWFpb19VUHk1S2w0QXc`) ranked **#1 Luna Jinna** (`watch?v=vk7sOb4Gs-0&t=29s`, 2 live clips), **#2 Remy Bond** (`watch?v=BgJkPrvHwO4&t=158s`, paired with live second take), and **#3 Blake Whiten** (`watch?v=LrbSqBmnPGo&t=45s`, `single_clip_flag: true`), while filtering out Daisy Gray's single lip-synced studio video.
  - **Scouting Studio Auto-Load ([simon/web.py](../../simon/web.py))**: Updated `http://127.0.0.1:8765` to automatically load the latest saved SQLite run (`run_881b5370`) on page open.
