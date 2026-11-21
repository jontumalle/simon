"""Zero-dependency HTTP server and interactive Scouting Studio UI for Simon's MVP demo.

Launch with:
    python3 -m simon serve --port 8765
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse
import uuid

from .db_tools import (
    ALLOWED_AGENT_COLLECTIONS,
    get_agent_document,
    list_agent_documents,
    save_agent_document,
    verify_agent_db_auth,
)
from .deploy import compile_agent_package, list_agent_packages
from .discovery_ui import (
    DISCOVERY_HTML,
    TRACES_HTML,
    dispatch_discovery_batch,
    list_discovery_batches,
    load_source_registry,
    refresh_discovery_batch,
)
from .fleet import dispatch_fleet
from .registry import (
    AGENT_RUNS_COLLECTION,
    append_agent_trace,
    list_agent_runs,
    new_run_id,
    query_discovery_sources,
    record_agent_run,
    record_fleet_agent_runs,
    seed_discovery_sources,
    upsert_discovery_source,
)
from .scout import DEFAULT_TASTE_BRIEF, load_dotenv_if_present, run_scout
from .store import SimonStore, create_store


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · Taste-Brief Vocal Scout MVP</title>
  <style>
    :root {
      --bg: #0b0d12;
      --panel: #131722;
      --panel-2: #191f2e;
      --border: #262f45;
      --text: #eef2ff;
      --muted: #9aa5c4;
      --accent: #f59e0b;
      --accent-hover: #fbbf24;
      --teal: #2dd4bf;
      --warn: #fb7185;
      --amber-bg: rgba(245, 158, 11, 0.12);
      --warn-bg: rgba(251, 113, 133, 0.14);
      --teal-bg: rgba(45, 212, 191, 0.12);
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: radial-gradient(circle at top right, #172036 0%, var(--bg) 48%);
      color: var(--text);
      font-family: var(--sans);
      line-height: 1.5;
    }
    a { color: var(--teal); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .wrap { max-width: 1240px; margin: 0 auto; padding: 28px 22px 64px; }
    header {
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start;
      gap: 16px; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px;
    }
    .brand h1 { margin: 0; font-size: 1.75rem; letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }
    .brand p { margin: 6px 0 0; color: var(--muted); font-size: 0.96rem; max-width: 700px; }
    .pill {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 10px; border-radius: 999px; font-size: 0.76rem; font-weight: 600;
      border: 1px solid var(--border); background: var(--panel-2); color: var(--muted);
    }
    .pill.live { color: var(--teal); border-color: rgba(45,212,191,0.4); background: var(--teal-bg); }
    .pill.warn { color: var(--warn); border-color: rgba(251,113,133,0.4); background: var(--warn-bg); }
    .pill.amber { color: var(--accent); border-color: rgba(245,158,11,0.4); background: var(--amber-bg); }

    .brief-box {
      background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
      padding: 20px; margin-bottom: 24px; box-shadow: 0 12px 32px rgba(0,0,0,0.28);
    }
    .brief-box label { display: block; font-weight: 600; margin-bottom: 8px; font-size: 0.92rem; }
    textarea {
      width: 100%; min-height: 76px; resize: vertical;
      background: #0d1018; color: var(--text); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 14px; font-family: inherit; font-size: 0.98rem;
    }
    textarea:focus, input:focus, select:focus { outline: none; border-color: var(--accent); }
    .preset-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .preset-btn {
      background: var(--panel-2); color: var(--muted); border: 1px solid var(--border);
      border-radius: 8px; padding: 6px 10px; font-size: 0.8rem; cursor: pointer;
    }
    .preset-btn:hover { color: var(--text); border-color: var(--accent); }
    .controls-row {
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
      gap: 12px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border);
    }
    .mode-group { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
    .key-input {
      background: #0d1018; color: var(--text); border: 1px solid var(--border);
      border-radius: 8px; padding: 8px 11px; font-size: 0.84rem; width: 250px; font-family: var(--mono);
    }
    .run-btn {
      background: var(--accent); color: #111318; font-weight: 700; border: none;
      border-radius: 10px; padding: 11px 20px; font-size: 0.95rem; cursor: pointer;
      transition: background 0.15s ease;
    }
    .run-btn:hover { background: var(--accent-hover); }
    .run-btn:disabled { opacity: 0.55; cursor: wait; }

    .grid-top {
      display: grid; grid-template-columns: 1.35fr 1fr; gap: 20px; margin-bottom: 26px;
    }
    @media (max-width: 960px) { .grid-top { grid-template-columns: 1fr; } }

    .player-card, .trace-card {
      background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 18px;
    }
    .section-title {
      margin: 0 0 12px; font-size: 1.05rem; font-weight: 700;
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
    }
    .video-frame {
      position: relative; width: 100%; padding-top: 56.25%;
      background: #07090d; border-radius: 10px; overflow: hidden; border: 1px solid var(--border);
    }
    .video-frame iframe {
      position: absolute; inset: 0; width: 100%; height: 100%; border: 0;
    }
    .now-playing {
      margin-top: 12px; display: flex; flex-wrap: wrap; justify-content: space-between;
      align-items: center; gap: 10px; font-size: 0.88rem; color: var(--muted);
    }
    .yt-ext-btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 7px 12px; border-radius: 8px; font-weight: 600; font-size: 0.83rem;
      background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
    }
    .yt-ext-btn:hover { border-color: var(--teal); text-decoration: none; }

    .trace-list { display: flex; flex-direction: column; gap: 10px; }
    .trace-step {
      background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px;
    }
    .trace-head {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
      font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--accent);
    }
    .trace-actor { font-size: 0.8rem; color: var(--muted); font-family: var(--mono); margin-top: 2px; }
    .trace-summary { font-size: 0.88rem; margin-top: 6px; color: var(--text); }
    .trace-meta { margin-top: 6px; font-size: 0.76rem; color: var(--muted); font-family: var(--mono); }

    .shortlist-grid {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-bottom: 30px;
    }
    @media (max-width: 1020px) { .shortlist-grid { grid-template-columns: 1fr; } }

    .singer-card {
      background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
      padding: 20px; display: flex; flex-direction: column; justify-content: space-between;
    }
    .singer-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
    .rank-badge {
      background: var(--amber-bg); color: var(--accent); border: 1px solid rgba(245,158,11,0.4);
      font-weight: 800; font-size: 0.82rem; padding: 3px 9px; border-radius: 8px;
    }
    .singer-name { margin: 8px 0 6px; font-size: 1.32rem; letter-spacing: -0.01em; }
    .badge-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }

    .play-first-btn {
      width: 100%; display: flex; justify-content: space-between; align-items: center;
      background: linear-gradient(135deg, #f59e0b, #fbbf24); color: #111318;
      border: none; border-radius: 10px; padding: 11px 14px; font-weight: 800;
      font-size: 0.92rem; cursor: pointer; margin-bottom: 8px; text-align: left;
    }
    .play-first-btn:hover { filter: brightness(1.05); }
    .clip-caption { font-size: 0.8rem; color: var(--muted); margin-bottom: 14px; }

    .field-block { margin-bottom: 12px; }
    .field-label {
      font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em;
      color: var(--muted); font-weight: 700; margin-bottom: 3px;
    }
    .field-body { font-size: 0.91rem; color: var(--text); }

    .evidence-panel {
      background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 20px;
    }
    .lead-record {
      border-top: 1px solid var(--border); padding: 16px 0;
    }
    .lead-record:first-of-type { border-top: none; padding-top: 4px; }
    .obs-chip {
      display: inline-flex; align-items: center; gap: 6px;
      background: var(--panel-2); border: 1px solid var(--border); color: var(--teal);
      padding: 4px 9px; border-radius: 7px; font-family: var(--mono); font-size: 0.8rem;
      cursor: pointer; margin-right: 8px;
    }
    .obs-chip:hover { border-color: var(--teal); }
    .obs-row {
      background: #0f131d; border: 1px solid var(--border); border-radius: 9px;
      padding: 10px 12px; margin-top: 8px; font-size: 0.88rem;
    }
    .status-banner {
      padding: 10px 14px; border-radius: 10px; margin-bottom: 16px; font-size: 0.9rem; display: none;
    }
    .status-banner.error { display: block; background: var(--warn-bg); border: 1px solid var(--warn); color: #fecdd3; }
    .status-banner.info { display: block; background: var(--amber-bg); border: 1px solid var(--accent); color: #fde68a; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill amber">Taste-Brief Vocal Scout MVP</span></h1>
        <p>Enter a taste brief to scout public YouTube vocal performances, extract timestamped musical choices with <strong>Gemini 4 Hydrogen</strong>, and synthesize a human-verifiable listening shortlist via <strong>Gemini Managed Agents</strong>.</p>
      </div>
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <a href="/discovery" class="pill amber" style="text-decoration:none;">1. Discovery &amp; Sources</a>
        <a href="/traces" class="pill live" style="text-decoration:none;">2. Agent Traces</a>
        <span id="serverKeyBadge" class="pill">Checking API status…</span>
        <select id="historySelect" class="key-input" style="width:auto;" title="Saved SQLite Scout Runs">
          <option value="">Recent saved runs…</option>
        </select>
      </div>
    </header>

    <div id="statusBanner" class="status-banner"></div>

    <section class="brief-box" style="margin-bottom:22px;">
      <div class="section-title" style="margin-bottom:12px;">
        <span>Platform Control Plane · Agent Runs, Traces &amp; Source Registry</span>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <span id="storeBackendBadge" class="pill">store: —</span>
          <button id="refreshRunsBtn" class="preset-btn" type="button">Refresh Runs</button>
          <button id="seedSourcesBtn" class="preset-btn" type="button">Seed Reference Sources</button>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: 1.25fr 1fr; gap:16px; margin-bottom:16px;">
        <div>
          <div style="display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
            <select id="fleetAgentSelect" class="key-input" style="flex:1; min-width:180px;"></select>
            <input id="fleetTargetInput" class="key-input" style="flex:1.4; min-width:180px;" placeholder="Target / assignment (e.g. NYC indie soul vocalists)" />
            <label style="display:inline-flex; align-items:center; gap:5px; font-size:0.82rem; color:var(--muted);">
              <input type="checkbox" id="fleetDryRunToggle" checked /> Dry run
            </label>
            <button id="dispatchFleetBtn" class="run-btn" type="button" style="padding:8px 14px; font-size:0.84rem;">Run Agent</button>
          </div>
          <div style="overflow:auto; max-height:260px; border:1px solid var(--border); border-radius:10px;">
            <table style="width:100%; border-collapse:collapse; font-size:0.82rem;">
              <thead>
                <tr style="background:var(--panel-2); color:var(--muted); text-align:left;">
                  <th style="padding:8px;">Run ID</th>
                  <th style="padding:8px;">Agent</th>
                  <th style="padding:8px;">Target</th>
                  <th style="padding:8px;">Status</th>
                  <th style="padding:8px;">Traces</th>
                </tr>
              </thead>
              <tbody id="agentRunsBody">
                <tr><td colspan="5" style="padding:10px; color:var(--muted);">Loading agent runs…</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div style="border:1px solid var(--border); border-radius:10px; padding:12px; background:var(--panel-2); max-height:315px; overflow:auto;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="font-size:0.88rem;">Selected Agent Run Trace</strong>
            <span id="selectedRunMeta" class="pill">Select a run</span>
          </div>
          <div id="agentTraceInspector" style="font-size:0.82rem; color:var(--muted);">
            Click any row on the left to inspect its <code>run_id</code>, <code>interaction_id</code>, step-by-step trace spans, and output payload.
          </div>
        </div>
      </div>

      <details style="border-top:1px solid var(--border); padding-top:12px;">
        <summary style="cursor:pointer; font-weight:600; font-size:0.9rem; display:flex; align-items:center; justify-content:space-between;">
          <span>Discovery Source Registry (Reference Data) · <span id="sourcesCountBadge" class="pill">0 sources</span></span>
        </summary>
        <div style="display:flex; gap:8px; margin:10px 0; flex-wrap:wrap;">
          <input id="sourceCityFilter" class="key-input" style="width:180px;" placeholder="Filter city (e.g. New York)" />
          <select id="sourceChannelFilter" class="key-input" style="width:200px;">
            <option value="">All channels</option>
            <option value="diy_venue_calendar">diy_venue_calendar</option>
            <option value="youtube_live_session">youtube_live_session</option>
            <option value="open_mic_lineup">open_mic_lineup</option>
            <option value="event_listing">event_listing</option>
            <option value="bandcamp_local_arrival">bandcamp_local_arrival</option>
            <option value="diy_venue_flyer_ocr">diy_venue_flyer_ocr</option>
            <option value="bgv_or_session_credit_graph">bgv_or_session_credit_graph</option>
            <option value="musicbrainz">musicbrainz</option>
            <option value="other">other</option>
          </select>
          <button id="filterSourcesBtn" class="preset-btn" type="button">Filter</button>
        </div>
        <div style="overflow:auto; max-height:240px; border:1px solid var(--border); border-radius:10px;">
          <table style="width:100%; border-collapse:collapse; font-size:0.8rem;">
            <thead>
              <tr style="background:var(--panel-2); color:var(--muted); text-align:left;">
                <th style="padding:7px;">Source</th>
                <th style="padding:7px;">Channel</th>
                <th style="padding:7px;">Location</th>
                <th style="padding:7px;">Tier</th>
                <th style="padding:7px;">Status</th>
              </tr>
            </thead>
            <tbody id="sourcesBody">
              <tr><td colspan="5" style="padding:10px; color:var(--muted);">Loading sources…</td></tr>
            </tbody>
          </table>
        </div>
      </details>
    </section>

    <section class="brief-box">
      <label for="briefInput">1. Taste Brief — Describe the sound and musical choices to scout for</label>
      <textarea id="briefInput"></textarea>
      <div class="preset-row">
        <button class="preset-btn" type="button" data-brief="Find singers who reinterpret familiar songs through distinctive phrasing, micro-dynamics, or stripped-back live arrangements.">Preset: Reinterpreting familiar songs via phrasing</button>
        <button class="preset-btn" type="button" data-brief="Stripped-back soul vocalists in live rooms who shift effortlessly from whispered intimacy to chest-voice power without heavy studio polish.">Preset: Stripped-back soul &amp; live room dynamics</button>
        <button class="preset-btn" type="button" data-brief="Acoustic session or open-mic singers with elastic behind-the-beat pocket and sparse guitar or piano accompaniment.">Preset: Behind-the-beat acoustic pocket</button>
      </div>
      <div class="controls-row">
        <div class="mode-group">
          <label style="display:inline-flex; align-items:center; gap:7px; font-size:0.9rem; cursor:pointer;">
            <input type="checkbox" id="liveToggle" />
            <span>Run Live (<strong>Gemini Managed Agents + Gemini 4 Hydrogen + Public YouTube</strong>)</span>
          </label>
          <input type="password" id="apiKeyInput" class="key-input" placeholder="Optional GEMINI_API_KEY override…" />
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
          <button id="demoBtn" class="preset-btn" type="button" style="padding:10px 14px; font-weight:600;">Load Instant Demo</button>
          <button id="scoutBtn" class="run-btn" type="button">Scout Singers &amp; Build Shortlist</button>
        </div>
      </div>
    </section>

    <div class="grid-top">
      <section class="player-card">
        <h2 class="section-title">
          <span>Moment Verifier Player</span>
          <span id="playerTimestampBadge" class="pill live">Click any timestamped moment</span>
        </h2>
        <div class="video-frame">
          <iframe id="ytPlayer" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>
        <div class="now-playing">
          <div id="nowPlayingCaption">Select a <strong>Play First</strong> button below to jump straight to the musical choice Simon identified.</div>
          <a id="openOnYoutubeLink" class="yt-ext-btn" href="https://www.youtube.com" target="_blank" rel="noopener noreferrer">Open on YouTube ↗</a>
        </div>
      </section>

      <section class="trace-card">
        <h2 class="section-title">
          <span>Managed Agent &amp; Evaluator Trace</span>
          <span id="runModeBadge" class="pill">—</span>
        </h2>
        <div id="traceContainer" class="trace-list"></div>
      </section>
    </div>

    <section>
      <h2 class="section-title" style="font-size:1.25rem; margin-bottom:14px;">
        <span>Listening Shortlist (Up to 3 Singers)</span>
        <span style="font-size:0.84rem; font-weight:400; color:var(--muted);">Every claim links to an exact timestamped public YouTube performance</span>
      </h2>
      <div id="shortlistContainer" class="shortlist-grid"></div>
    </section>

    <section class="evidence-panel">
      <h2 class="section-title" style="font-size:1.15rem;">
        <span>Stored Artist Leads, Clip Evidence &amp; Assessments (SQLite Record Store)</span>
        <span id="recordCountBadge" class="pill">0 records</span>
      </h2>
      <div id="evidenceContainer"></div>
    </section>
  </div>

  <script>
    const briefInput = document.getElementById('briefInput');
    const liveToggle = document.getElementById('liveToggle');
    const apiKeyInput = document.getElementById('apiKeyInput');
    const scoutBtn = document.getElementById('scoutBtn');
    const ytPlayer = document.getElementById('ytPlayer');
    const nowPlayingCaption = document.getElementById('nowPlayingCaption');
    const openOnYoutubeLink = document.getElementById('openOnYoutubeLink');
    const playerTimestampBadge = document.getElementById('playerTimestampBadge');
    const shortlistContainer = document.getElementById('shortlistContainer');
    const traceContainer = document.getElementById('traceContainer');
    const evidenceContainer = document.getElementById('evidenceContainer');
    const runModeBadge = document.getElementById('runModeBadge');
    const recordCountBadge = document.getElementById('recordCountBadge');
    const serverKeyBadge = document.getElementById('serverKeyBadge');
    const statusBanner = document.getElementById('statusBanner');
    const historySelect = document.getElementById('historySelect');

    function esc(str) {
      const div = document.createElement('div');
      div.textContent = str == null ? '' : String(str);
      return div.innerHTML;
    }

    function setBanner(msg, kind) {
      if (!msg) {
        statusBanner.style.display = 'none';
        statusBanner.className = 'status-banner';
        return;
      }
      statusBanner.textContent = msg;
      statusBanner.className = 'status-banner ' + (kind || 'info');
      statusBanner.style.display = 'block';
    }

    function playMoment(embedUrl, watchUrl, label, autoplay) {
      const sep = embedUrl.includes('?') ? '&' : '?';
      ytPlayer.src = autoplay ? (embedUrl + sep + 'autoplay=1') : embedUrl;
      openOnYoutubeLink.href = watchUrl;
      openOnYoutubeLink.textContent = 'Open on YouTube (' + label + ') ↗';
      playerTimestampBadge.textContent = label;
      nowPlayingCaption.textContent = 'Verifying: ' + label + ' — if embedded playback is restricted by the label, click "Open on YouTube" to jump straight to ' + label + '.';
    }

    function renderRun(run) {
      briefInput.value = run.brief.prompt;
      runModeBadge.textContent = run.mode === 'live' ? 'LIVE GEMINI 4 + MANAGED AGENTS' : 'VERIFIED YOUTUBE DEMO';
      runModeBadge.className = 'pill ' + (run.mode === 'live' ? 'live' : 'amber');

      // Cue #1 shortlist moment without noisy autoplay on initial load
      if (run.shortlist && run.shortlist.length > 0) {
        const first = run.shortlist[0];
        playMoment(
          first.play_first_embed_url,
          first.play_first_url,
          first.stage_name + ' @ ' + first.play_first_timestamp,
          false
        );
      }

      // Trace panel
      traceContainer.innerHTML = (run.trace || []).map(step => `
        <div class="trace-step">
          <div class="trace-head">
            <span>${esc(step.stage.replace(/_/g, ' '))}</span>
            <span>${esc(step.duration_ms)} ms</span>
          </div>
          <div class="trace-actor">${esc(step.actor)}</div>
          <div class="trace-summary">${esc(step.summary)}</div>
          <div class="trace-meta">interaction_id: ${esc(step.interaction_id || 'n/a')}</div>
        </div>
      `).join('');

      // Shortlist cards (up to 3)
      shortlistContainer.innerHTML = (run.shortlist || []).map(item => {
        const badges = [];
        badges.push(`<span class="pill ${item.recording_context === 'live' ? 'live' : ''}">Context: ${esc(item.recording_context)}</span>`);
        if (item.single_clip_flag) {
          badges.push(`<span class="pill warn">⚠ Single-Clip Assessment</span>`);
        } else {
          badges.push(`<span class="pill live">Multi-Clip Verified</span>`);
        }
        if (item.uncertain_attribution_flag) {
          badges.push(`<span class="pill warn">⚠ Uncertain Attribution</span>`);
        }

        const nextLinkHtml = item.listen_next_url
          ? `<div style="margin-top:6px;"><a href="${esc(item.listen_next_url)}" target="_blank" rel="noopener noreferrer">Open next-listen take on YouTube ↗</a></div>`
          : '';

        return `
          <article class="singer-card">
            <div>
              <div class="singer-head">
                <span class="rank-badge">Shortlist #${esc(item.rank)}</span>
                <a href="${esc(item.play_first_url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem;">Direct YT link ↗</a>
              </div>
              <h3 class="singer-name">${esc(item.stage_name)}</h3>
              <div class="badge-row">${badges.join('')}</div>

              <button class="play-first-btn" type="button"
                data-embed="${esc(item.play_first_embed_url)}"
                data-watch="${esc(item.play_first_url)}"
                data-label="${esc(item.stage_name + ' @ ' + item.play_first_timestamp)}">
                <span>▶ Play First Moment</span>
                <span>@ ${esc(item.play_first_timestamp)}</span>
              </button>
              <div class="clip-caption">${esc(item.play_first_clip_title)}</div>

              <div class="field-block">
                <div class="field-label">Why This Moment Fits the Brief</div>
                <div class="field-body">${esc(item.why_it_fits)}</div>
              </div>
            </div>

            <div class="field-block" style="margin-bottom:0; padding-top:10px; border-top:1px solid var(--border);">
              <div class="field-label">What a Scout Should Listen to Next</div>
              <div class="field-body">${esc(item.what_to_hear_next)}${nextLinkHtml}</div>
            </div>
          </article>
        `;
      }).join('');

      shortlistContainer.querySelectorAll('.play-first-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          playMoment(btn.dataset.embed, btn.dataset.watch, btn.dataset.label, true);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });
      });

      // Full Artist & Evidence records
      const clipsByLead = {};
      (run.clip_evidence || []).forEach(c => {
        (clipsByLead[c.lead_id] = clipsByLead[c.lead_id] || []).push(c);
      });
      const assessByLead = {};
      (run.assessments || []).forEach(a => { assessByLead[a.lead_id] = a; });

      recordCountBadge.textContent = `${(run.artist_leads || []).length} leads · ${(run.clip_evidence || []).length} clips`;

      evidenceContainer.innerHTML = (run.artist_leads || []).map(lead => {
        const assess = assessByLead[lead.lead_id] || {};
        const clips = clipsByLead[lead.lead_id] || [];
        const attrBadge = lead.attribution_status === 'uncertain'
          ? `<span class="pill warn">⚠ Uncertain Attribution</span>`
          : `<span class="pill live">Verified Performer</span>`;
        const singleBadge = assess.single_clip_flag
          ? `<span class="pill warn">1 Clip Only</span>`
          : `<span class="pill">${clips.length} Clips</span>`;

        const clipsHtml = clips.map(clip => {
          const obsHtml = (clip.observations || []).map(obs => `
            <div class="obs-row">
              <button type="button" class="obs-chip"
                data-embed="${esc(obs.embed_url)}"
                data-watch="${esc(obs.play_url)}"
                data-label="${esc(lead.stage_name + ' @ ' + obs.timestamp)}">
                ▶ @ ${esc(obs.timestamp)} · ${esc(obs.dimension)}
              </button>
              <span>${esc(obs.musical_choice)}</span>
              <div style="margin-top:4px; font-size:0.77rem; color:var(--muted); font-family:var(--mono);">
                Original source link: <a href="${esc(obs.source_url)}" target="_blank" rel="noopener noreferrer">${esc(obs.source_url)}</a>
                · Timestamp link: <a href="${esc(obs.play_url)}" target="_blank" rel="noopener noreferrer">${esc(obs.play_url)}</a>
              </div>
            </div>
          `).join('');

          return `
            <div style="margin-top:10px; padding-left:12px; border-left:2px solid var(--border);">
              <div style="font-size:0.9rem; font-weight:600;">
                ${esc(clip.title || clip.source_url)}
                <span class="pill" style="margin-left:6px;">${esc(clip.recording_context)}</span>
              </div>
              <div style="font-size:0.8rem; color:var(--muted);">${esc(clip.recording_context_notes)}</div>
              ${obsHtml}
            </div>
          `;
        }).join('');

        const questionsHtml = (assess.open_questions || []).map(q => `<li>${esc(q)}</li>`).join('');

        return `
          <div class="lead-record">
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; align-items:center;">
              <div style="font-size:1.08rem; font-weight:700;">
                ${esc(lead.stage_name)} <span style="color:var(--muted); font-size:0.82rem; font-family:var(--mono);">(${esc(lead.lead_id)})</span>
              </div>
              <div style="display:flex; gap:6px; flex-wrap:wrap;">${attrBadge}${singleBadge}</div>
            </div>
            <div style="font-size:0.82rem; color:var(--muted); margin-top:3px;">${esc(lead.attribution_notes)}</div>
            <div style="font-size:0.89rem; margin-top:8px;"><strong>Brief Assessment:</strong> ${esc(assess.fit_rationale || '')}</div>
            ${questionsHtml ? `<ul style="margin:6px 0 8px 18px; color:var(--muted); font-size:0.84rem;">${questionsHtml}</ul>` : ''}
            ${clipsHtml}
          </div>
        `;
      }).join('');

      evidenceContainer.querySelectorAll('.obs-chip').forEach(chip => {
        chip.addEventListener('click', () => {
          playMoment(chip.dataset.embed, chip.dataset.watch, chip.dataset.label, true);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });
      });
    }

    async function refreshHistory() {
      const res = await fetch('/api/runs');
      if (!res.ok) return;
      const data = await res.json();
      const opts = ['<option value="">Saved SQLite runs (' + data.runs.length + ')…</option>'];
      data.runs.forEach(r => {
        opts.push(`<option value="${esc(r.run_id)}">[${esc(r.mode)}] ${esc(r.brief_prompt.slice(0, 48))}…</option>`);
      });
      historySelect.innerHTML = opts.join('');
    }

    async function init() {
      const statusRes = await fetch('/api/status');
      const status = await statusRes.json();
      briefInput.value = status.default_brief;
      if (status.has_api_key) {
        serverKeyBadge.textContent = 'GEMINI_API_KEY Ready (Live Enabled)';
        serverKeyBadge.className = 'pill live';
        liveToggle.checked = true;
      } else {
        serverKeyBadge.textContent = 'Demo Mode Ready (Set GEMINI_API_KEY for Live Calls)';
        serverKeyBadge.className = 'pill amber';
        liveToggle.checked = false;
      }

      // If SQLite already has a saved run (e.g., a real live run), load the newest one first!
      const runsRes = await fetch('/api/runs');
      if (runsRes.ok) {
        const runsData = await runsRes.json();
        if (runsData.runs && runsData.runs.length > 0) {
          const latestId = runsData.runs[0].run_id;
          const latestRes = await fetch('/api/runs?id=' + encodeURIComponent(latestId));
          if (latestRes.ok) {
            renderRun(await latestRes.json());
            await refreshHistory();
            historySelect.value = latestId;
            return;
          }
        }
      }

      // Otherwise seed with the verified public YouTube demo run
      const demoRes = await fetch('/api/scout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brief: status.default_brief, live: false })
      });
      if (demoRes.ok) {
        const run = await demoRes.json();
        renderRun(run);
        await refreshHistory();
      }
    }

    document.querySelectorAll('.preset-btn').forEach(btn => {
      btn.addEventListener('click', () => { briefInput.value = btn.dataset.brief; });
    });

    historySelect.addEventListener('change', async () => {
      const id = historySelect.value;
      if (!id) return;
      const res = await fetch('/api/runs?id=' + encodeURIComponent(id));
      if (res.ok) {
        renderRun(await res.json());
      }
    });

    document.getElementById('demoBtn').addEventListener('click', async () => {
      setBanner('Loading verified public YouTube demo fixture…', 'info');
      const res = await fetch('/api/scout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brief: briefInput.value, live: false })
      });
      if (res.ok) {
        setBanner('', 'info');
        renderRun(await res.json());
        await refreshHistory();
      }
    });

    scoutBtn.addEventListener('click', async () => {
      const wantLive = liveToggle.checked;
      const keyOverride = apiKeyInput.value.trim();
      setBanner(
        wantLive
          ? 'Running Discovery Managed Agent -> YouTubeConnector -> Gemini 4 Hydrogen video evaluation -> Synthesis Managed Agent… (may take 20-50s)'
          : 'Loading verified public YouTube performances & shortlist…',
        'info'
      );
      scoutBtn.disabled = true;
      try {
        const res = await fetch('/api/scout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            brief: briefInput.value,
            live: wantLive,
            api_key: keyOverride || null
          })
        });
        const payload = await res.json();
        if (!res.ok) {
          setBanner(payload.error || 'Scout run failed.', 'error');
          return;
        }
        setBanner('', 'info');
        renderRun(payload);
        await refreshHistory();
      } catch (err) {
        setBanner('Network error talking to local Simon server: ' + err, 'error');
      } finally {
        scoutBtn.disabled = false;
      }
    });

    async function loadPlatformControlPlane() {
      try {
        const [stRes, agRes] = await Promise.all([fetch('/api/status'), fetch('/api/agents')]);
        const st = await stRes.json();
        const ag = await agRes.json();
        const backendEl = document.getElementById('storeBackendBadge');
        if (backendEl) backendEl.textContent = 'store: ' + (st.store_backend || 'sqlite');
        const sel = document.getElementById('fleetAgentSelect');
        if (sel && Array.isArray(ag.agents)) {
          sel.innerHTML = ag.agents.map(a =>
            `<option value="${a.deployed_id}">${a.deployed_id} (${a.model || 'default'})</option>`
          ).join('');
        }
      } catch (e) {}
      await Promise.all([refreshAgentRuns(), refreshSources()]);
    }

    async function refreshAgentRuns() {
      const tbody = document.getElementById('agentRunsBody');
      if (!tbody) return;
      try {
        const res = await fetch('/api/agent-runs');
        const data = await res.json();
        const runs = data.agent_runs || [];
        if (!runs.length) {
          tbody.innerHTML = '<tr><td colspan="5" style="padding:10px; color:var(--muted);">No agent runs recorded yet. Dispatch an agent above.</td></tr>';
          return;
        }
        tbody.innerHTML = runs.map(r => `
          <tr data-arun="${r.agent_run_id}" style="cursor:pointer; border-top:1px solid var(--border);">
            <td style="padding:7px;"><code>${r.run_id || '—'}</code><div style="font-size:0.72rem; color:var(--muted);">${r.agent_run_id}</div></td>
            <td style="padding:7px;">${r.agent_id || '—'}</td>
            <td style="padding:7px;">${(r.target || '—').slice(0, 42)}</td>
            <td style="padding:7px;"><span class="pill">${r.status || '—'}</span></td>
            <td style="padding:7px;">${(r.traces || []).length} steps</td>
          </tr>
        `).join('');
        tbody.querySelectorAll('tr[data-arun]').forEach(tr => {
          tr.addEventListener('click', () => inspectAgentRun(tr.getAttribute('data-arun')));
        });
      } catch (e) {
        tbody.innerHTML = '<tr><td colspan="5" style="padding:10px; color:var(--warn);">Failed to load agent runs.</td></tr>';
      }
    }

    async function inspectAgentRun(agentRunId) {
      const box = document.getElementById('agentTraceInspector');
      const meta = document.getElementById('selectedRunMeta');
      if (!box) return;
      const res = await fetch('/api/agent-runs/' + encodeURIComponent(agentRunId));
      const r = await res.json();
      if (meta) meta.textContent = `${r.run_id || ''} · ${r.status || ''}`;
      const tracesHtml = (r.traces || []).map(t => `
        <div style="border-left:2px solid var(--accent); padding:4px 8px; margin:6px 0; background:rgba(255,255,255,0.02);">
          <div><strong>${t.step_id}</strong> <span class="pill">${t.kind}</span> <span style="color:var(--muted); font-size:0.74rem;">${t.timestamp || ''}</span></div>
          <div>${t.summary || ''}</div>
        </div>
      `).join('') || '<div style="color:var(--muted);">No trace spans recorded.</div>';
      box.innerHTML = `
        <div style="margin-bottom:8px;">
          <div><strong>run_id:</strong> <code>${r.run_id || '—'}</code></div>
          <div><strong>agent_run_id:</strong> <code>${r.agent_run_id || '—'}</code></div>
          <div><strong>interaction_id:</strong> <code>${r.interaction_id || 'none (dry-run)'}</code></div>
          <div><strong>agent:</strong> ${r.agent_id || '—'} · <strong>stage:</strong> ${r.stage || '—'}</div>
        </div>
        ${tracesHtml}
        ${r.output ? `<pre style="margin-top:8px; padding:8px; background:#0b0d12; border-radius:8px; overflow:auto; max-height:140px;">${JSON.stringify(r.output, null, 2)}</pre>` : ''}
      `;
    }

    async function refreshSources() {
      const tbody = document.getElementById('sourcesBody');
      const badge = document.getElementById('sourcesCountBadge');
      if (!tbody) return;
      const city = (document.getElementById('sourceCityFilter')?.value || '').trim();
      const channel = (document.getElementById('sourceChannelFilter')?.value || '').trim();
      const params = new URLSearchParams();
      if (city) params.set('city', city);
      if (channel) params.set('channel', channel);
      const res = await fetch('/api/sources' + (params.toString() ? '?' + params.toString() : ''));
      const data = await res.json();
      const sources = data.sources || [];
      if (badge) badge.textContent = `${sources.length} sources`;
      if (!sources.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="padding:10px; color:var(--muted);">No sources seeded yet. Click "Seed Reference Sources" above.</td></tr>';
        return;
      }
      tbody.innerHTML = sources.map(s => {
        const loc = s.location || {};
        const locLabel = [loc.city, loc.area, loc.scope].filter(Boolean).join(' · ') || '—';
        return `<tr style="border-top:1px solid var(--border);">
          <td style="padding:6px;"><a href="${s.url}" target="_blank" rel="noopener noreferrer" style="color:var(--teal);">${s.name}</a><div style="font-size:0.72rem; color:var(--muted);">${s.source_id}</div></td>
          <td style="padding:6px;"><code>${s.source_channel}</code></td>
          <td style="padding:6px;">${locLabel}</td>
          <td style="padding:6px;">${s.career_tier || '—'}</td>
          <td style="padding:6px;"><span class="pill">${s.status || 'active'}</span></td>
        </tr>`;
      }).join('');
    }

    document.getElementById('refreshRunsBtn')?.addEventListener('click', refreshAgentRuns);
    document.getElementById('filterSourcesBtn')?.addEventListener('click', refreshSources);
    document.getElementById('seedSourcesBtn')?.addEventListener('click', async () => {
      const res = await fetch('/api/sources/seed', { method: 'POST' });
      const data = await res.json();
      setBanner(`Seeded ${data.seeded_count || 0} curated sources into ${data.collection || 'source_registry'}.`, 'info');
      await refreshSources();
    });
    document.getElementById('dispatchFleetBtn')?.addEventListener('click', async () => {
      const agent = document.getElementById('fleetAgentSelect')?.value || '';
      const target = (document.getElementById('fleetTargetInput')?.value || '').trim() || 'NYC indie soul vocalists';
      const dryRun = Boolean(document.getElementById('fleetDryRunToggle')?.checked);
      setBanner(`Dispatching ${agent} (${dryRun ? 'dry-run' : 'live'})…`, 'info');
      const res = await fetch('/api/fleet/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent, assignments: [target], dry_run: dryRun })
      });
      const data = await res.json();
      if (!res.ok) {
        setBanner(data.error || 'Agent dispatch failed.', 'error');
        return;
      }
      setBanner(`Dispatched run ${data.run_id} (${data.dispatched}/${data.total} workers).`, 'info');
      await refreshAgentRuns();
      const firstId = (data.agent_run_ids || [])[0];
      if (firstId) await inspectAgentRun(firstId);
    });

    init();
    loadPlatformControlPlane();
  </script>
</body>
</html>
"""


def dispatch_http_request(
    store: SimonStore,
    method: str,
    path: str,
    raw_body: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
) -> tuple[int, str, bytes]:
    """Pure HTTP routing dispatcher returning (status_code, content_type, response_bytes)."""
    parsed = urlparse(path)

    # Permissioned, schema-validated agent DB gateway: /api/db/<collection>[/<doc_id>]
    if parsed.path.startswith("/api/db/"):
        authed, auth_err = verify_agent_db_auth(headers)
        if not authed:
            return (
                HTTPStatus.UNAUTHORIZED,
                "application/json; charset=utf-8",
                json.dumps({"error": auth_err}).encode("utf-8"),
            )
        parts = [p for p in parsed.path[len("/api/db/"):].split("/") if p]
        if not parts:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Collection name required."}).encode("utf-8"),
            )
        collection = parts[0]
        if collection not in ALLOWED_AGENT_COLLECTIONS:
            return (
                HTTPStatus.FORBIDDEN,
                "application/json; charset=utf-8",
                json.dumps(
                    {
                        "error": f"Collection '{collection}' is not permitted for agent access.",
                        "allowed_collections": sorted(ALLOWED_AGENT_COLLECTIONS),
                    }
                ).encode("utf-8"),
            )

        if method == "GET":
            if len(parts) == 2:
                doc = get_agent_document(store, collection, parts[1])
                if doc is None:
                    return (
                        HTTPStatus.NOT_FOUND,
                        "application/json; charset=utf-8",
                        json.dumps({"error": "Document not found."}).encode("utf-8"),
                    )
                return (
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps({"collection": collection, "doc_id": parts[1], "document": doc}, ensure_ascii=False).encode("utf-8"),
                )
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["25"])[0])
            docs = list_agent_documents(store, collection, limit=limit)
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"collection": collection, "count": len(docs), "documents": docs}, ensure_ascii=False).encode("utf-8"),
            )

        if method == "POST" and len(parts) == 1:
            try:
                payload = json.loads((raw_body or b"{}").decode("utf-8"))
            except ValueError:
                return (
                    HTTPStatus.BAD_REQUEST,
                    "application/json; charset=utf-8",
                    json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
                )
            qs = parse_qs(parsed.query)
            doc_id = (qs.get("doc_id") or [None])[0]
            try:
                saved = save_agent_document(store, collection, payload, doc_id=doc_id)
            except ValueError as exc:
                return (
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "application/json; charset=utf-8",
                    json.dumps({"error": str(exc)}).encode("utf-8"),
                )
            return (
                HTTPStatus.CREATED,
                "application/json; charset=utf-8",
                json.dumps(saved, ensure_ascii=False).encode("utf-8"),
            )

        return (
            HTTPStatus.METHOD_NOT_ALLOWED,
            "application/json; charset=utf-8",
            json.dumps({"error": "Method not allowed on /api/db endpoint."}).encode("utf-8"),
        )

    if method == "GET":
        if parsed.path == "/":
            return (HTTPStatus.OK, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))

        if parsed.path in ("/discovery", "/scouting"):
            return (HTTPStatus.OK, "text/html; charset=utf-8", DISCOVERY_HTML.encode("utf-8"))

        if parsed.path == "/traces":
            return (HTTPStatus.OK, "text/html; charset=utf-8", TRACES_HTML.encode("utf-8"))

        if parsed.path in ("/healthz", "/api/health"):
            payload = {
                "ok": True,
                "store_backend": getattr(store, "backend", "sqlite"),
            }
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/discovery/batches":
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["20"])[0])
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"batches": list_discovery_batches(store, limit=limit)}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path.startswith("/api/discovery/batches/"):
            batch_id = parsed.path[len("/api/discovery/batches/"):].strip("/")
            qs = parse_qs(parsed.query)
            wait_flag = (qs.get("wait") or ["0"])[0].lower() in ("1", "true", "yes")
            since_steps = int((qs.get("since_steps") or ["-1"])[0])
            timeout_s = min(25.0, max(1.0, float((qs.get("timeout") or ["15"])[0])))
            load_dotenv_if_present()
            batch = refresh_discovery_batch(
                store,
                batch_id,
                wait=wait_flag,
                since_steps=since_steps,
                timeout_s=timeout_s,
            )
            if batch is None:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": "Discovery batch not found."}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            )
        if parsed.path == "/api/status":
            load_dotenv_if_present()
            payload = {
                "ok": True,
                "has_api_key": bool(os.environ.get("GEMINI_API_KEY")),
                "default_brief": DEFAULT_TASTE_BRIEF,
                "store_backend": getattr(store, "backend", "sqlite"),
            }
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/fleet/runs":
            runs = store.list_documents("fleet_runs", limit=20) if hasattr(store, "list_documents") else []
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"fleet_runs": runs}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/sources":
            qs = parse_qs(parsed.query)
            ch = (qs.get("channel") or [None])[0]
            city = (qs.get("city") or [None])[0]
            tier = (qs.get("tier") or [None])[0]
            status_f = (qs.get("status") or [None])[0]
            limit = int((qs.get("limit") or ["100"])[0])
            registry = load_source_registry(store)
            sources = registry["sources"]
            if ch:
                sources = [s for s in sources if s.get("source_channel") == ch]
            if city:
                sources = [s for s in sources if ((s.get("location") or {}).get("city") or "Global").lower() == city.lower()]
            if tier:
                sources = [s for s in sources if s.get("career_tier") == tier]
            if status_f:
                sources = [s for s in sources if s.get("status") == status_f]
            sources = sources[:limit]
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(
                    {
                        "count": len(sources),
                        "channels": registry["channels"],
                        "cities": registry["cities"],
                        "tiers": registry["tiers"],
                        "sources": sources,
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        if parsed.path == "/api/agent-runs":
            qs = parse_qs(parsed.query)
            runs = list_agent_runs(
                store,
                run_id=(qs.get("run_id") or [None])[0],
                agent_id=(qs.get("agent_id") or [None])[0],
                status=(qs.get("status") or [None])[0],
                limit=int((qs.get("limit") or ["50"])[0]),
            )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"count": len(runs), "agent_runs": runs}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path.startswith("/api/agent-runs/"):
            arun_id = parsed.path[len("/api/agent-runs/"):].strip("/")
            doc = store.get_document(AGENT_RUNS_COLLECTION, arun_id) if hasattr(store, "get_document") else None
            if not doc:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": f"Agent run '{arun_id}' not found."}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(doc, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/agents":
            prefix = os.environ.get("SIMON_AGENT_PREFIX", "")
            items = []
            for pkg_dir in list_agent_packages():
                compiled = compile_agent_package(pkg_dir, prefix=prefix)
                items.append(
                    {
                        "package": compiled["package"],
                        "deployed_id": compiled["deployed_id"],
                        "sha256": compiled["sha256"],
                        "base_agent": compiled["payload"]["base_agent"],
                        "model": compiled["payload"].get("agent_config", {}).get("model"),
                    }
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"prefix": prefix, "agents": items}, ensure_ascii=False).encode("utf-8"),
            )

        if parsed.path == "/api/runs":
            qs = parse_qs(parsed.query)
            run_id = (qs.get("id") or [None])[0]
            if run_id:
                found = store.get_run(run_id)
                if not found:
                    return (
                        HTTPStatus.NOT_FOUND,
                        "application/json; charset=utf-8",
                        json.dumps({"error": "Run not found."}).encode("utf-8"),
                    )
                return (
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps(found, ensure_ascii=False).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"runs": store.list_runs(limit=20)}, ensure_ascii=False).encode("utf-8"),
            )

        return (
            HTTPStatus.NOT_FOUND,
            "application/json; charset=utf-8",
            json.dumps({"error": "Not found."}).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/discovery/dispatch":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        source_ids = req.get("source_ids") or []
        if not isinstance(source_ids, list) or not source_ids:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "`source_ids` must be a non-empty list."}).encode("utf-8"),
            )
        brief = str(req.get("brief") or "").strip()
        leads_per_agent = int(req.get("leads_per_agent") or 2)
        agent_count = int(req.get("agent_count") or len(source_ids))
        live = bool(req.get("live", False))
        api_key = str(req.get("api_key") or "").strip() or None
        load_dotenv_if_present()
        try:
            batch = dispatch_discovery_batch(
                store=store,
                source_ids=[str(s) for s in source_ids],
                brief=brief,
                leads_per_agent=leads_per_agent,
                agent_count=agent_count,
                live=live,
                api_key=api_key,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        http_status = HTTPStatus.ACCEPTED if live else HTTPStatus.OK
        return (
            http_status,
            "application/json; charset=utf-8",
            json.dumps(batch, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/fleet/run":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )

        agent_id = str(req.get("agent") or "").strip()
        raw_assignments = req.get("assignments") if "assignments" in req else req.get("targets")
        if not isinstance(raw_assignments, list) or not raw_assignments:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps(
                    {"error": "`assignments` (or `targets`) must be a non-empty list."}
                ).encode("utf-8"),
            )
        prompt_template = req.get("prompt_template")
        prompt_template_str = str(prompt_template) if prompt_template is not None else None
        max_concurrency = int(req.get("max_concurrency") or 5)
        webhook_url = str(req.get("webhook_url") or "").strip() or None
        wait = bool(req.get("wait", False))
        dry_run = bool(req.get("dry_run", False))
        api_key = str(req.get("api_key") or "").strip() or None
        try:
            summary = dispatch_fleet(
                agent_id=agent_id,
                assignments=raw_assignments,
                prompt_template=prompt_template_str,
                max_concurrency=max_concurrency,
                webhook_url=webhook_url,
                wait=wait,
                dry_run=dry_run,
                api_key=api_key,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        fleet_run_id = f"fleet_{uuid.uuid4().hex[:10]}"
        parent_run_id = str(req.get("run_id") or "").strip() or new_run_id("run")
        stage = str(req.get("stage") or "fleet").strip() or "fleet"
        summary["fleet_run_id"] = fleet_run_id
        summary["run_id"] = parent_run_id
        if hasattr(store, "save_document"):
            created_runs = record_fleet_agent_runs(store, summary, run_id=parent_run_id, stage=stage)
            summary["agent_run_ids"] = [r["agent_run_id"] for r in created_runs]
            store.save_document("fleet_runs", fleet_run_id, summary)
        http_status = HTTPStatus.OK if (wait or dry_run) else HTTPStatus.ACCEPTED
        return (
            http_status,
            "application/json; charset=utf-8",
            json.dumps(summary, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/sources/seed":
        try:
            summary = seed_discovery_sources(store)
        except (OSError, ValueError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        summary["store_backend"] = getattr(store, "backend", "sqlite")
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(summary, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/sources":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
            saved = upsert_discovery_source(store, req)
        except ValueError as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        return (
            HTTPStatus.CREATED,
            "application/json; charset=utf-8",
            json.dumps(saved, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/agent-runs":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )
        if req.get("agent_run_id") and isinstance(req.get("trace"), dict):
            trace = req["trace"]
            updated = append_agent_trace(
                store,
                str(req["agent_run_id"]),
                kind=str(trace.get("kind") or "tool_call"),
                summary=str(trace.get("summary") or ""),
                metadata=trace.get("metadata") if isinstance(trace.get("metadata"), dict) else None,
                status=req.get("status"),
                output_payload=req.get("output"),
                error=req.get("error"),
            )
            if not updated:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json; charset=utf-8",
                    json.dumps({"error": "Agent run not found."}).encode("utf-8"),
                )
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(updated, ensure_ascii=False).encode("utf-8"),
            )
        agent_id = str(req.get("agent_id") or "").strip()
        if not agent_id:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "`agent_id` is required."}).encode("utf-8"),
            )
        saved = record_agent_run(
            store,
            run_id=str(req.get("run_id") or "").strip() or new_run_id("run"),
            agent_id=agent_id,
            stage=str(req.get("stage") or "custom"),
            status=str(req.get("status") or "running"),
            agent_run_id=req.get("agent_run_id"),
            parent_agent_run_id=req.get("parent_agent_run_id"),
            interaction_id=req.get("interaction_id"),
            target=req.get("target"),
            input_payload=req.get("input"),
            output_payload=req.get("output"),
            error=req.get("error"),
            traces=req.get("traces") if isinstance(req.get("traces"), list) else None,
        )
        return (
            HTTPStatus.CREATED,
            "application/json; charset=utf-8",
            json.dumps(saved, ensure_ascii=False).encode("utf-8"),
        )

    if method == "POST" and parsed.path == "/api/scout":
        try:
            req = json.loads((raw_body or b"{}").decode("utf-8"))
        except ValueError:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "Invalid JSON request body."}).encode("utf-8"),
            )

        brief_text = str(req.get("brief") or DEFAULT_TASTE_BRIEF).strip()
        live = bool(req.get("live", False))
        api_key = str(req.get("api_key") or "").strip() or None
        try:
            run = run_scout(brief_prompt=brief_text, live=live, store=store, api_key=api_key)
        except (ValueError, RuntimeError, OSError) as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": str(exc)}).encode("utf-8"),
            )
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            json.dumps(run.to_dict(), ensure_ascii=False).encode("utf-8"),
        )

    return (
        HTTPStatus.NOT_FOUND,
        "application/json; charset=utf-8",
        json.dumps({"error": "Not found."}).encode("utf-8"),
    )


def create_handler(store: SimonStore):
    class SimonHTTPHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _write(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            status, content_type, body = dispatch_http_request(
                store, "GET", self.path, headers=dict(self.headers.items())
            )
            self._write(status, content_type, body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            status, content_type, body = dispatch_http_request(
                store, "POST", self.path, raw_body, headers=dict(self.headers.items())
            )
            self._write(status, content_type, body)

    return SimonHTTPHandler


def serve_web(host: str = "127.0.0.1", port: int = 8765, store: Optional[Any] = None) -> None:
    load_dotenv_if_present()
    active_store = store or create_store()
    server = ThreadingHTTPServer((host, port), create_handler(active_store))
    print(f"Simon platform running at http://{host}:{port} (store={getattr(active_store, 'backend', 'sqlite')})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
