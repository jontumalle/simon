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

from .scout import DEFAULT_TASTE_BRIEF, load_dotenv_if_present, run_scout
from .store import SimonStore


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
        <span id="serverKeyBadge" class="pill">Checking API status…</span>
        <select id="historySelect" class="key-input" style="width:auto;" title="Saved SQLite Scout Runs">
          <option value="">Recent saved runs…</option>
        </select>
      </div>
    </header>

    <div id="statusBanner" class="status-banner"></div>

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

    init();
  </script>
</body>
</html>
"""


def dispatch_http_request(
    store: SimonStore,
    method: str,
    path: str,
    raw_body: bytes = b"",
) -> tuple[int, str, bytes]:
    """Pure HTTP routing dispatcher returning (status_code, content_type, response_bytes)."""
    parsed = urlparse(path)

    if method == "GET":
        if parsed.path == "/":
            return (HTTPStatus.OK, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))

        if parsed.path == "/api/status":
            load_dotenv_if_present()
            payload = {
                "ok": True,
                "has_api_key": bool(os.environ.get("GEMINI_API_KEY")),
                "default_brief": DEFAULT_TASTE_BRIEF,
            }
            return (
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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
            status, content_type, body = dispatch_http_request(store, "GET", self.path)
            self._write(status, content_type, body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            status, content_type, body = dispatch_http_request(store, "POST", self.path, raw_body)
            self._write(status, content_type, body)

    return SimonHTTPHandler


def serve_web(host: str = "127.0.0.1", port: int = 8765, store: Optional[SimonStore] = None) -> None:
    load_dotenv_if_present()
    active_store = store or SimonStore()
    server = ThreadingHTTPServer((host, port), create_handler(active_store))
    print(f"Simon Taste-Brief Vocal Scout running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
