"""Stage 3 Single-Card Screening Deck UI (/screen).

Renders a focused one-candidate-at-a-time A&R profile card (stepper + keyboard navigation,
zero swipe/drag gestures) combining the Stage 2 factual dossier snapshot, embedded YouTube
player, 5-input-skill rubric scoreboard, side-by-side Advocate vs. Skeptic adversarial debate,
gemini-4-neon Judge synthesis, Human-in-the-Loop (HITL) verdict calibration, and a collapsible
3-layer Rubric Eval & compiled `gemini-decision-1` (`questions_config`) inspector.
"""

from __future__ import annotations

from .discovery_ui import _SHARED_CSS, _render_top_nav

_SCREENING_EXTRA_CSS = """
  .control-strip {
    display: flex; flex-direction: column; gap: 14px;
    background: var(--panel);
    border-color: var(--purple);
  }
  .control-row-top, .control-row-bottom {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px;
  }
  .culmination-flow-strip {
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px;
    padding: 9px 12px; border-radius: 10px; background: var(--purple-bg); border: 1px solid var(--border);
    font-size: 0.8rem; color: var(--text);
  }
  .filter-pills { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .filter-pill {
    background: var(--panel-2); color: var(--muted); border: 1px solid var(--border);
    border-radius: 999px; padding: 6px 12px; font-size: 0.81rem; font-weight: 700;
    cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
    transition: border-color 0.14s ease, background 0.14s ease, color 0.14s ease;
  }
  .filter-pill:hover { color: var(--text); border-color: var(--purple); }
  .filter-pill.active {
    background: var(--purple-bg); color: var(--purple); border-color: var(--purple);
  }
  .filter-count {
    font-family: var(--mono); font-size: 0.72rem; padding: 1px 6px; border-radius: 999px;
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
  }
  .fleet-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .btn.neon {
    background: linear-gradient(135deg, #a855f7, #f59e0b); color: #ffffff;
    border: none; font-weight: 800; padding: 9px 16px;
  }
  .btn.neon:hover { filter: brightness(1.08); }
  .btn.taste {
    background: linear-gradient(135deg, #0f766e, #7e22ce); color: #ffffff;
    border: none; font-weight: 800; padding: 9px 15px;
  }
  .btn.taste:hover { filter: brightness(1.08); }
  .btn.dspy {
    border-color: var(--purple); color: var(--purple); background: var(--purple-bg);
  }
  .btn.dspy:hover { filter: brightness(1.05); }

  .stepper-bar {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
    gap: 10px; margin-bottom: 14px; padding: 10px 14px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  }
  .stepper-btn { font-weight: 700; padding: 8px 14px; }
  .jump-pills {
    display: flex; flex-wrap: wrap; gap: 6px; align-items: center; justify-content: center; flex: 1;
  }
  .jump-pill {
    background: var(--panel-2); color: var(--muted); border: 1px solid var(--border);
    border-radius: 8px; padding: 4px 9px; font-size: 0.77rem; font-weight: 600; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px;
  }
  .jump-pill:hover { color: var(--text); border-color: var(--purple); }
  .jump-pill.active {
    background: var(--purple-bg); color: var(--text); border-color: var(--purple); font-weight: 800;
  }
  .verdict-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
  .verdict-dot.ELEVATE { background: var(--teal); }
  .verdict-dot.WATCH { background: var(--accent); }
  .verdict-dot.PASS { background: var(--warn); }
  .verdict-dot.UNSET { background: var(--muted); }

  .profile-deck-card {
    background: var(--panel); border: 1px solid rgba(192, 132, 252, 0.32); border-radius: 18px;
    padding: 24px; margin-bottom: 22px; box-shadow: 0 18px 44px rgba(0, 0, 0, 0.38);
    display: flex; flex-direction: column; gap: 22px;
  }
  .hero-grid {
    display: grid; grid-template-columns: 1.2fr 1fr; gap: 22px;
    padding-bottom: 20px; border-bottom: 1px solid var(--border);
  }
  @media (max-width: 960px) { .hero-grid { grid-template-columns: 1fr; } }

  .hero-stage-name {
    margin: 0; font-size: 1.85rem; letter-spacing: -0.02em; line-height: 1.18;
    display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  }
  .hero-aliases { color: var(--muted); font-size: 0.88rem; margin-top: 4px; }
  .hero-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 12px; }
  .hero-bio {
    font-size: 0.9rem; color: var(--text); background: var(--input-bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 10px 13px; margin-bottom: 12px;
  }
  .reach-grid {
    display: grid; grid-template-columns: repeat(4, minmax(115px, 1fr)); gap: 8px; margin-bottom: 12px;
  }
  @media (max-width: 680px) { .reach-grid { grid-template-columns: repeat(2, 1fr); } }
  .reach-cell {
    background: var(--input-bg); border: 1px solid var(--border); border-radius: 9px; padding: 8px 10px;
  }
  .reach-label {
    font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 700;
  }
  .reach-val { font-size: 0.98rem; font-weight: 800; margin-top: 2px; font-family: var(--mono); color: var(--text); }

  .yt-embed-frame {
    position: relative; width: 100%; padding-top: 56.25%;
    background: #07090d; border-radius: 12px; overflow: hidden; border: 1px solid var(--border);
  }
  .yt-embed-frame iframe {
    position: absolute; inset: 0; width: 100%; height: 100%; border: 0;
  }
  .yt-empty-frame {
    background: #090c13; border: 1px dashed var(--border); border-radius: 12px;
    padding: 28px 18px; text-align: center; color: var(--muted); font-size: 0.88rem;
  }
  .media-queue-list {
    display: flex; flex-direction: column; gap: 6px; margin-top: 10px; max-height: 155px; overflow-y: auto;
  }
  .media-queue-item {
    display: flex; justify-content: space-between; align-items: center; gap: 8px;
    background: var(--input-bg); border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px;
    font-size: 0.82rem;
  }
  .media-queue-item.active { border-color: var(--purple); background: var(--purple-bg); }
  .media-play-btn {
    background: transparent; border: none; color: var(--text); font-weight: 600; cursor: pointer;
    text-align: left; padding: 0; font-size: 0.82rem; flex: 1;
  }
  .media-play-btn:hover { color: var(--purple); }

  .rubric-board {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px;
  }
  .rubric-rows { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
  .rubric-row {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 13px;
  }
  .rubric-row-top {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px;
  }
  .meter-track {
    width: 100%; height: 8px; background: #182032; border-radius: 999px; overflow: hidden; margin: 7px 0 6px;
  }
  .meter-fill { height: 100%; border-radius: 999px; transition: width 0.2s ease; }
  .meter-fill.score-2 { background: linear-gradient(90deg, #14b8a6, #2dd4bf); }
  .meter-fill.score-1 { background: linear-gradient(90deg, #d97706, #fbbf24); }
  .meter-fill.score-0 { background: #fb7185; }
  .rubric-note { font-size: 0.83rem; color: var(--muted); }

  .debate-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 18px;
  }
  @media (max-width: 900px) { .debate-grid { grid-template-columns: 1fr; } }
  .debate-col {
    border-radius: 14px; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px;
  }
  .debate-col.advocate {
    background: rgba(45, 212, 191, 0.05); border: 1px solid rgba(45, 212, 191, 0.32);
  }
  .debate-col.skeptic {
    background: rgba(251, 113, 133, 0.05); border: 1px solid rgba(251, 113, 133, 0.32);
  }
  .debate-headline { font-size: 0.96rem; font-weight: 700; color: var(--text); }
  .debate-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 9px; }
  .debate-item {
    background: var(--panel); border: 1px solid var(--border); border-radius: 9px; padding: 9px 11px; font-size: 0.85rem;
  }
  .standout-hook-box {
    margin-top: auto; background: var(--panel); border: 1px solid var(--teal);
    border-radius: 9px; padding: 9px 12px; font-size: 0.84rem; color: var(--text);
  }
  .missing-flags-box {
    margin-top: auto; padding-top: 8px; border-top: 1px solid var(--border);
  }

  .judge-footer {
    background: var(--panel-2);
    border: 1px solid var(--purple); border-radius: 14px; padding: 18px 20px;
    display: flex; flex-direction: column; gap: 16px;
  }
  .taste-engine-panel {
    background: var(--panel); border: 1px solid var(--purple); border-radius: 12px;
    padding: 14px 16px; display: flex; flex-direction: column; gap: 10px;
  }
  .prob-grid {
    display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 8px;
  }
  @media (max-width: 720px) { .prob-grid { grid-template-columns: repeat(2, 1fr); } }
  .prob-cell {
    background: var(--input-bg); border: 1px solid var(--border); border-radius: 9px; padding: 8px 10px;
  }
  .verdict-badge {
    display: inline-flex; align-items: center; gap: 6px; padding: 5px 13px; border-radius: 999px;
    font-size: 0.84rem; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase;
  }
  .verdict-badge.ELEVATE { background: var(--teal-bg); color: var(--teal); border: 1px solid var(--teal); }
  .verdict-badge.WATCH { background: var(--amber-bg); color: var(--accent); border: 1px solid var(--accent); }
  .verdict-badge.PASS { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn); }

  .hitl-bar {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .hitl-controls-row {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  }
  .verdict-btn-group { display: inline-flex; gap: 6px; flex-wrap: wrap; }
  .verdict-choice-btn {
    background: var(--panel-2); color: var(--muted); border: 1px solid var(--border);
    border-radius: 9px; padding: 8px 14px; font-weight: 800; font-size: 0.84rem; cursor: pointer;
  }
  .verdict-choice-btn:hover { color: var(--text); }
  .verdict-choice-btn[data-verdict="ELEVATE"].selected {
    background: var(--teal-bg); color: var(--teal); border-color: var(--teal);
  }
  .verdict-choice-btn[data-verdict="WATCH"].selected {
    background: var(--amber-bg); color: var(--accent); border-color: var(--accent);
  }
  .verdict-choice-btn[data-verdict="PASS"].selected {
    background: var(--warn-bg); color: var(--warn); border-color: var(--warn);
  }
  .reason-input { flex: 1; min-width: 240px; }

  .inspector-drawer summary {
    cursor: pointer; font-weight: 700; font-size: 0.98rem;
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
    list-style: none;
  }
  .inspector-drawer summary::-webkit-details-marker { display: none; }
  .inspector-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 16px;
  }
  @media (max-width: 900px) { .inspector-grid { grid-template-columns: 1fr; } }
"""


def render_screening_page() -> str:
    """Render the Stage 3 Single-Card Screening Deck HTML (`/screen`)."""
    top_nav = _render_top_nav("/screen")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · 7. Stage 3 Screening Deck</title>
  <style>{_SHARED_CSS}{_SCREENING_EXTRA_CSS}</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill purple">7. Screening Deck</span></h1>
        <p>Review one artist at a time with <strong>Advocate vs. Skeptic</strong> debate, 5-skill scores, <strong>gemini-4-neon</strong> Judge verdict, and your calibration vote.</p>
      </div>
      {top_nav}
    </header>

    <div id="screeningBanner" class="banner"></div>

    <!-- Top Control Strip -->
    <section class="card control-strip" aria-label="Screening Deck Controls">
      <div class="control-row-top">
        <div style="display:flex; flex-wrap:wrap; align-items:center; gap:10px;">
          <span id="deckCounterBadge" class="pill purple" style="font-size:0.84rem;">Artist 0 of 0</span>
          <div id="deckFilterBar" class="filter-pills" role="tablist" aria-label="Filter Screening Deck">
            <button type="button" class="filter-pill active" data-filter="all">All <span class="filter-count" id="countAll">0</span></button>
            <button type="button" class="filter-pill" data-filter="unlabeled">Unlabeled <span class="filter-count" id="countUnlabeled">0</span></button>
            <button type="button" class="filter-pill" data-filter="ELEVATE">Elevate <span class="filter-count" id="countElevate">0</span></button>
            <button type="button" class="filter-pill" data-filter="WATCH">Watch <span class="filter-count" id="countWatch">0</span></button>
            <button type="button" class="filter-pill" data-filter="PASS">Pass <span class="filter-count" id="countPass">0</span></button>
          </div>
        </div>

        <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
          <span id="activeModelBadge" class="pill blue" title="Active compiled gemini-decision-1 judging policy">
            Policy: loading…
          </span>
          <a href="/taste-profile" class="btn dspy" style="padding:5px 11px; font-size:0.78rem;">View Our Taste Profile →</a>
        </div>
      </div>

      <div class="culmination-flow-strip">
        <span><strong>The Culmination Loop:</strong> Stage 2 Dossier → Neon Advocate/Skeptic/Judge → Human Override → DSPy Compile → <strong>Instant Calibrated Taste Engine</strong></span>
        <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
          <span class="pill purple">gemini-decision-1 · 0 output tokens</span>
          <a href="/taste-profile" style="font-weight:700; color:var(--purple); font-size:0.79rem;">Inspect Criteria &amp; Overrides →</a>
        </div>
      </div>

      <div class="control-row-bottom">
        <div class="mono">Single-card executive review · Use buttons or <code>[</code> / <code>]</code> (or Left/Right arrows) to step candidates.</div>
        <div class="fleet-actions">
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:0.83rem; cursor:pointer; color:var(--muted);">
            <input type="checkbox" id="liveScreeningToggle" />
            <span>Live Fleet</span>
          </label>
          <button id="runScreeningBtn" class="btn neon" type="button">Run Neon Screening Fleet</button>
          <button id="trainModelBtn" class="btn dspy" type="button">Compile Judging Model (DSPy)</button>
          <button id="runTasteEngineBtn" class="btn taste" type="button">Run Taste Engine (gemini-decision-1 · 0 tok)</button>
          <button id="runEvalsBtn" class="btn" type="button">Run Rubric Evals</button>
        </div>
      </div>
    </section>

    <!-- Single-Artist Stepper Navigation (Explicitly button/keyboard driven) -->
    <div class="stepper-bar" role="navigation" aria-label="Candidate Stepper">
      <button id="prevCandidateBtn" class="btn stepper-btn" type="button">← Previous Candidate</button>
      <div id="candidateJumpPills" class="jump-pills"></div>
      <button id="nextCandidateBtn" class="btn stepper-btn" type="button">Next Candidate →</button>
    </div>

    <!-- Focused Single-Artist Profile Card (1 Person on Screen at a Time) -->
    <article id="profileCardContainer" class="profile-deck-card" aria-live="polite">
      <div class="mono">Loading Stage 3 screening packets…</div>
    </article>

    <!-- Collapsible Rubric Eval Results & Active gemini-decision-1 Policy Inspector -->
    <details id="policyInspectorDrawer" class="card inspector-drawer">
      <summary>
        <span>▸ Rubric Eval Results &amp; Active <code>gemini-decision-1</code> Policy Inspector</span>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <span id="evalSummaryBadge" class="pill amber">3-Layer Evals: Not run yet</span>
          <span id="policySummaryBadge" class="pill purple">gemini-decision-1: baseline</span>
        </div>
      </summary>
      <div class="inspector-grid">
        <div class="worker-card">
          <div class="section-head" style="margin-bottom:6px;">
            <h2 style="font-size:0.98rem;">3-Layer Rubric Evaluation Score</h2>
            <span class="pill ok">Layer 1 · Layer 2 · Layer 3</span>
          </div>
          <div id="evalBreakdownBox" class="mono">Click <strong>Run Rubric Evals</strong> above to verify deterministic schema, adversarial citations, and calibration alignment.</div>
          <pre id="evalRawJson" class="json-view" style="display:none;"></pre>
        </div>

        <div class="worker-card">
          <div class="section-head" style="margin-bottom:6px;">
            <h2 style="font-size:0.98rem;">Compiled <code>questions_config</code> Policy</h2>
            <span class="pill purple">gemini-decision-1</span>
          </div>
          <div id="policyMetaBox" class="mono">Save human verdict labels below and click <strong>Compile Judging Model (DSPy)</strong> to optimize rubric weights and question prompts.</div>
          <pre id="questionsConfigJson" class="json-view">{{}}</pre>
        </div>
      </div>
    </details>
  </div>

  <script>
    const el = (id) => document.getElementById(id);

    function escapeHtml(value) {{
      const div = document.createElement('div');
      div.textContent = value == null ? '' : String(value);
      return div.innerHTML;
    }}

    function safeUrl(raw) {{
      if (!raw || typeof raw !== 'string') return '';
      const trimmed = raw.trim();
      if (/^https?:\\/\\//i.test(trimmed)) return trimmed;
      return '';
    }}

    function extractYouTubeVideoId(rawUrl) {{
      const clean = safeUrl(rawUrl);
      if (!clean) return '';
      try {{
        const parsed = new URL(clean);
        const host = parsed.hostname.replace(/^www\\./i, '').toLowerCase();
        let candidate = '';
        if (host === 'youtu.be') {{
          candidate = parsed.pathname.split('/').filter(Boolean)[0] || '';
        }} else if (host === 'youtube.com' || host === 'm.youtube.com' || host === 'music.youtube.com') {{
          if (parsed.pathname === '/watch') {{
            candidate = parsed.searchParams.get('v') || '';
          }} else {{
            const parts = parsed.pathname.split('/').filter(Boolean);
            if (parts.length >= 2 && ['embed', 'shorts', 'live', 'v'].includes(parts[0])) {{
              candidate = parts[1];
            }}
          }}
        }}
        return /^[A-Za-z0-9_-]{{6,20}}$/.test(candidate) ? candidate : '';
      }} catch (_err) {{
        return '';
      }}
    }}

    const RUBRIC_DIMENSIONS = [
      {{ key: 'identity_reachability', label: '1. Identity & Reachability', defaultSkill: 'dossier-identity' }},
      {{ key: 'live_vocal_proof', label: '2. Live Vocal Proof', defaultSkill: 'dossier-media' }},
      {{ key: 'early_window_depth', label: '3. Early-Window Depth', defaultSkill: 'dossier-footprint' }},
      {{ key: 'listener_pull_cosigns', label: '4. Listener Pull & Co-Signs', defaultSkill: 'dossier-audience' }},
      {{ key: 'stage_momentum_whitespace', label: '5. Stage Momentum & Whitespace', defaultSkill: 'dossier-track-record' }},
    ];

    const urlParams = new URLSearchParams(window.location.search);
    let initialFocusLead = urlParams.get('lead') || '';
    let initialFocusPacket = urlParams.get('packet') || '';
    const VALID_FILTERS = ['all', 'unlabeled', 'ELEVATE', 'WATCH', 'PASS'];
    const reqFilter = urlParams.get('filter') || 'all';

    let allPackets = [];
    let currentFilter = VALID_FILTERS.includes(reqFilter) ? reqFilter : 'all';
    let currentIndex = 0;
    let selectedVerdict = 'WATCH';
    let activeVideoIdOverride = '';

    function syncScreeningUrl(leadId) {{
      try {{
        const url = new URL(window.location.href);
        if (leadId) url.searchParams.set('lead', leadId);
        else url.searchParams.delete('lead');
        if (currentFilter && currentFilter !== 'all') url.searchParams.set('filter', currentFilter);
        else url.searchParams.delete('filter');
        url.searchParams.delete('packet');
        window.history.replaceState({{}}, '', url.toString());
      }} catch (e) {{}}
    }}

    function showBanner(msg, kind) {{
      const node = el('screeningBanner');
      if (!msg) {{
        node.style.display = 'none';
        return;
      }}
      node.textContent = msg;
      node.className = 'banner ' + (kind || 'info');
      node.style.display = 'block';
    }}

    function normalizeVerdict(raw) {{
      const up = String(raw || '').trim().toUpperCase();
      if (up === 'ELEVATE' || up === 'WATCH' || up === 'PASS') return up;
      return '';
    }}

    function effectivePacketVerdict(pkt) {{
      const hr = pkt && pkt.human_review;
      const hv = hr ? normalizeVerdict(hr.human_verdict || hr.verdict) : '';
      if (hv) return hv;
      const jd = (pkt && pkt.judge_decision) || {{}};
      return normalizeVerdict(jd.verdict);
    }}

    function isLabeled(pkt) {{
      const hr = pkt && pkt.human_review;
      return Boolean(hr && normalizeVerdict(hr.human_verdict || hr.verdict));
    }}

    function getFilteredPackets() {{
      if (currentFilter === 'all') return allPackets;
      if (currentFilter === 'unlabeled') return allPackets.filter((p) => !isLabeled(p));
      return allPackets.filter((p) => effectivePacketVerdict(p) === currentFilter);
    }}

    function updateFilterCounts() {{
      el('countAll').textContent = String(allPackets.length);
      el('countUnlabeled').textContent = String(allPackets.filter((p) => !isLabeled(p)).length);
      el('countElevate').textContent = String(allPackets.filter((p) => effectivePacketVerdict(p) === 'ELEVATE').length);
      el('countWatch').textContent = String(allPackets.filter((p) => effectivePacketVerdict(p) === 'WATCH').length);
      el('countPass').textContent = String(allPackets.filter((p) => effectivePacketVerdict(p) === 'PASS').length);

      document.querySelectorAll('#deckFilterBar .filter-pill').forEach((btn) => {{
        btn.classList.toggle('active', btn.dataset.filter === currentFilter);
      }});
    }}

    function formatNumber(val) {{
      if (val == null || val === '') return '—';
      const num = Number(val);
      if (Number.isNaN(num)) return String(val);
      return num.toLocaleString();
    }}

    function formatConfidence(conf) {{
      if (conf == null || conf === '') return '—';
      if (typeof conf === 'number') {{
        return conf <= 1 ? `${{Math.round(conf * 100)}}%` : `${{Math.round(conf)}}%`;
      }}
      return String(conf);
    }}

    function extractDossierView(pkt) {{
      const ds = (pkt && (pkt.dossier_snapshot || pkt.dossier)) || {{}};
      const idc = ds.identity_and_contact || {{}};
      const smq = ds.source_and_media_queue || {{}};
      const pf = ds.public_footprint || {{}};
      const reach = pf.public_reach || ds.public_reach || {{}};
      const lhc = ds.live_history_and_credits || {{}};

      const stageName = pkt.stage_name || idc.stage_name || ds.stage_name || pkt.lead_id || 'Unnamed Candidate';
      const aliases = Array.isArray(idc.aliases) ? idc.aliases : (Array.isArray(ds.aliases) ? ds.aliases : []);
      const projectType = idc.project_type || ds.project_type || 'solo_vocalist';
      const homeCity = idc.home_city || ds.home_city || '';
      const homeNeighborhood = idc.home_neighborhood || ds.home_neighborhood || '';
      const primaryGenre = smq.primary_genre || ds.primary_genre || '';
      const subgenres = Array.isArray(smq.subgenres) ? smq.subgenres : (Array.isArray(ds.subgenres) ? ds.subgenres : []);
      const footprintRegime = pf.footprint_regime || ds.footprint_regime || 'unknown';
      const contactRouteType = idc.contact_route_type || ds.contact_route_type || 'none';
      const ytSubs = reach.youtube_subscribers != null ? reach.youtube_subscribers : ds.youtube_subscribers;
      const topViews = reach.top_video_views != null ? reach.top_video_views : ds.top_video_views;
      const viewSharePct = pf.top_release_view_share_pct != null ? pf.top_release_view_share_pct : ds.top_release_view_share_pct;
      const highestCap = lhc.highest_venue_cap_observed != null ? lhc.highest_venue_cap_observed : ds.highest_venue_cap_observed;
      const platformUrls = idc.platform_urls || ds.platform_urls || {{}};
      const mediaLinks = Array.isArray(smq.media_links) ? smq.media_links : (Array.isArray(ds.media_links) ? ds.media_links : []);
      const seedSourceUrl = smq.seed_source_url || ds.seed_source_url || pkt.seed_source_url || '';
      const bioText = smq.bio_text || ds.bio_text || '';

      return {{
        stageName,
        aliases,
        projectType,
        homeCity,
        homeNeighborhood,
        primaryGenre,
        subgenres,
        footprintRegime,
        contactRouteType,
        ytSubs,
        topViews,
        viewSharePct,
        highestCap,
        platformUrls,
        mediaLinks,
        seedSourceUrl,
        bioText,
      }};
    }}

    function extractRubricEntry(judgeDecision, dim) {{
      const scores = (judgeDecision && judgeDecision.rubric_scores) || {{}};
      const notesMap = (judgeDecision && judgeDecision.rubric_notes) || {{}};
      let rawEntry = null;
      if (Array.isArray(scores)) {{
        rawEntry = scores.find((item) => item && (item.key === dim.key || item.dimension === dim.key || item.id === dim.key));
      }} else if (scores && typeof scores === 'object') {{
        rawEntry = scores[dim.key];
      }}

      let score = 0;
      let skill = dim.defaultSkill;
      let note = notesMap[dim.key] || '';

      if (typeof rawEntry === 'number') {{
        score = rawEntry;
      }} else if (rawEntry && typeof rawEntry === 'object') {{
        score = Number(rawEntry.score != null ? rawEntry.score : (rawEntry.points != null ? rawEntry.points : 0));
        skill = rawEntry.skill || rawEntry.input_skill || rawEntry.skill_id || dim.defaultSkill;
        note = rawEntry.note || rawEntry.rationale || rawEntry.reason || rawEntry.justification || note;
      }}
      if (Number.isNaN(score)) score = 0;
      const clamped = Math.max(0, Math.min(2, score));
      return {{ score: clamped, skill, note }};
    }}

    function syncSelectedVerdictForCurrentPacket() {{
      const filtered = getFilteredPackets();
      const pkt = filtered[currentIndex];
      if (!pkt) return;
      const hr = pkt.human_review;
      const hv = hr ? normalizeVerdict(hr.human_verdict || hr.verdict) : '';
      const jv = normalizeVerdict(pkt.judge_decision && pkt.judge_decision.verdict);
      selectedVerdict = hv || jv || 'WATCH';
      activeVideoIdOverride = '';
    }}

    function renderStepper(filtered) {{
      const total = filtered.length;
      if (total === 0) {{
        el('deckCounterBadge').textContent = 'Artist 0 of 0';
        el('prevCandidateBtn').disabled = true;
        el('nextCandidateBtn').disabled = true;
        el('candidateJumpPills').innerHTML = '<span class="mono">No candidates in current filter</span>';
        return;
      }}
      if (currentIndex >= total) currentIndex = total - 1;
      if (currentIndex < 0) currentIndex = 0;

      el('deckCounterBadge').textContent = `Artist ${{currentIndex + 1}} of ${{total}}`;
      el('prevCandidateBtn').disabled = currentIndex <= 0;
      el('nextCandidateBtn').disabled = currentIndex >= total - 1;

      el('candidateJumpPills').innerHTML = filtered.map((pkt, idx) => {{
        const d = extractDossierView(pkt);
        const v = effectivePacketVerdict(pkt) || 'UNSET';
        const activeCls = idx === currentIndex ? 'active' : '';
        const reviewedMark = isLabeled(pkt) ? ' ✓' : '';
        return `<button type="button" class="jump-pill ${{activeCls}}" data-jump-idx="${{idx}}">
          <span class="verdict-dot ${{escapeHtml(v)}}"></span>
          <span>${{idx + 1}}. ${{escapeHtml(d.stageName)}}${{reviewedMark}}</span>
        </button>`;
      }}).join('');

      document.querySelectorAll('[data-jump-idx]').forEach((btn) => {{
        btn.onclick = () => {{
          currentIndex = Number(btn.dataset.jumpIdx || 0);
          syncSelectedVerdictForCurrentPacket();
          renderDeck();
        }};
      }});
    }}

    function renderDeck() {{
      updateFilterCounts();
      const filtered = getFilteredPackets();
      renderStepper(filtered);

      const container = el('profileCardContainer');
      if (!filtered.length) {{
        const msg = allPackets.length === 0
          ? 'No Stage 3 screening packets stored yet. Click "Run Neon Screening Fleet" above to run Advocate, Skeptic, and Neon Judge across your Stage 2 Investigator dossiers.'
          : `No candidates match filter "${{currentFilter}}". Switch filter pills above to inspect the deck.`;
        container.innerHTML = `
          <div style="text-align:center; padding:32px 16px;">
            <div style="font-size:1.08rem; font-weight:700; margin-bottom:8px;">Screening Deck Ready</div>
            <div class="mono" style="max-width:620px; margin:0 auto 16px;">${{escapeHtml(msg)}}</div>
          </div>`;
        return;
      }}

      const pkt = filtered[currentIndex];
      const packetId = pkt.packet_id || pkt.id || pkt._doc_id || `pkt_${{currentIndex + 1}}`;
      const leadId = pkt.lead_id || (pkt.dossier_snapshot && pkt.dossier_snapshot.lead_id) || '';
      syncScreeningUrl(leadId);
      const d = extractDossierView(pkt);
      const judge = pkt.judge_decision || {{}};
      const advocate = pkt.advocate_case || pkt.advocate || {{}};
      const skeptic = pkt.skeptic_case || pkt.skeptic || {{}};
      const humanReview = pkt.human_review || null;

      // Determine YouTube video embed from media_links[0].url or seed_source_url
      const queueItems = [];
      d.mediaLinks.forEach((m) => {{
        if (m && m.url) {{
          queueItems.push({{
            url: m.url,
            title: m.title || m.url,
            ytId: extractYouTubeVideoId(m.url),
          }});
        }}
      }});
      if (d.seedSourceUrl && !queueItems.some((q) => q.url === d.seedSourceUrl)) {{
        queueItems.push({{
          url: d.seedSourceUrl,
          title: 'Seed Discovery Source',
          ytId: extractYouTubeVideoId(d.seedSourceUrl),
        }});
      }}

      const firstMediaYt = (d.mediaLinks[0] && extractYouTubeVideoId(d.mediaLinks[0].url)) || '';
      const seedYt = extractYouTubeVideoId(d.seedSourceUrl);
      const anyQueueYt = (queueItems.find((q) => q.ytId) || {{}}).ytId || '';
      const activeYtId = activeVideoIdOverride || firstMediaYt || seedYt || anyQueueYt;

      const embedHtml = activeYtId
        ? `<div class="yt-embed-frame">
             <iframe
               src="https://www.youtube.com/embed/${{encodeURIComponent(activeYtId)}}"
               title="${{escapeHtml(d.stageName)}} performance player"
               referrerpolicy="strict-origin-when-cross-origin"
               allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
               allowfullscreen></iframe>
           </div>`
        : `<div class="yt-empty-frame">
             <div>No embeddable YouTube video URL on primary clip.</div>
             ${{safeUrl(d.seedSourceUrl) ? `<div style="margin-top:8px;"><a href="${{escapeHtml(safeUrl(d.seedSourceUrl))}}" target="_blank" rel="noopener">Open Seed Source Link ↗</a></div>` : ''}}
           </div>`;

      const mediaQueueHtml = queueItems.length
        ? `<div class="media-queue-list">
             ${{queueItems.map((q) => {{
               const href = safeUrl(q.url);
               const isCurrent = Boolean(q.ytId && q.ytId === activeYtId);
               return `<div class="media-queue-item ${{isCurrent ? 'active' : ''}}">
                 ${{q.ytId
                   ? `<button type="button" class="media-play-btn" data-play-yt="${{escapeHtml(q.ytId)}}">▶ ${{escapeHtml(q.title)}}</button>`
                   : `<span style="flex:1;">${{escapeHtml(q.title)}}</span>`}}
                 ${{href ? `<a class="mono" href="${{escapeHtml(href)}}" target="_blank" rel="noopener">Open ↗</a>` : ''}}
               </div>`;
             }}).join('')}}
           </div>`
        : '<div class="mono" style="margin-top:8px;">No media queue links attached.</div>';

      const locationStr = [d.homeNeighborhood, d.homeCity].filter(Boolean).join(', ') || 'Location unverified';
      const genres = [d.primaryGenre].concat(d.subgenres || []).filter(Boolean);
      const genrePillsHtml = genres.map((g) => `<span class="pill">${{escapeHtml(g)}}</span>`).join('');
      const platformLinksHtml = Object.entries(d.platformUrls || {{}})
        .filter(([, url]) => Boolean(safeUrl(url)))
        .map(([platform, url]) => `<a class="pill blue" href="${{escapeHtml(safeUrl(url))}}" target="_blank" rel="noopener">${{escapeHtml(platform)}} ↗</a>`)
        .join('');

      // 5 Input-Skill Rubric Scoreboard
      const rubricRows = RUBRIC_DIMENSIONS.map((dim) => ({{
        ...dim,
        ...extractRubricEntry(judge, dim),
      }}));
      const computedSum = rubricRows.reduce((acc, r) => acc + r.score, 0);
      const totalScore = judge.total_score != null ? Number(judge.total_score) : computedSum;

      const rubricHtml = rubricRows.map((r) => {{
        const pct = Math.round((r.score / 2) * 100);
        const fillCls = `score-${{Math.round(r.score)}}`;
        return `
          <div class="rubric-row" data-rubric-key="${{escapeHtml(r.key)}}">
            <div class="rubric-row-top">
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong>${{escapeHtml(r.label)}}</strong>
                <span class="pill purple">${{escapeHtml(r.skill)}}</span>
              </div>
              <span class="mono" style="font-weight:800; color:var(--text);">${{escapeHtml(r.score)}} / 2</span>
            </div>
            <div class="meter-track"><div class="meter-fill ${{fillCls}}" style="width:${{pct}}%;"></div></div>
            <div class="rubric-note">${{escapeHtml(r.note || 'Objective dossier check recorded.')}}</div>
          </div>`;
      }}).join('');

      // Adversarial Debate: Advocate vs. Skeptic
      const prosList = Array.isArray(advocate.pros) ? advocate.pros : [];
      const prosHtml = prosList.length
        ? prosList.map((item) => {{
            const title = (item && (item.title || item.point || item.claim)) || 'Supporting signal';
            const evidence = (item && (item.evidence || item.detail || item.citation)) || '';
            const skill = (item && (item.skill || item.input_skill || item.tag)) || '';
            return `<li class="debate-item">
              <div style="display:flex; justify-content:space-between; gap:8px; align-items:center; flex-wrap:wrap;">
                <strong>${{escapeHtml(title)}}</strong>
                ${{skill ? `<span class="pill ok">[${{escapeHtml(skill)}}]</span>` : ''}}
              </div>
              ${{evidence ? `<div style="color:var(--muted); margin-top:4px;">${{escapeHtml(evidence)}}</div>` : ''}}
            </li>`;
          }}).join('')
        : '<li class="debate-item mono">No Advocate pros recorded.</li>';

      const consList = Array.isArray(skeptic.cons) ? skeptic.cons : [];
      const consHtml = consList.length
        ? consList.map((item) => {{
            const title = (item && (item.title || item.point || item.risk)) || 'Risk or evidence gap';
            const evidence = (item && (item.evidence || item.detail || item.citation)) || '';
            const skill = (item && (item.skill || item.input_skill || item.tag)) || '';
            return `<li class="debate-item">
              <div style="display:flex; justify-content:space-between; gap:8px; align-items:center; flex-wrap:wrap;">
                <strong>${{escapeHtml(title)}}</strong>
                ${{skill ? `<span class="pill warn">[${{escapeHtml(skill)}}]</span>` : ''}}
              </div>
              ${{evidence ? `<div style="color:var(--muted); margin-top:4px;">${{escapeHtml(evidence)}}</div>` : ''}}
            </li>`;
          }}).join('')
        : '<li class="debate-item mono">No Skeptic cons recorded.</li>';

      const missingFlags = Array.isArray(skeptic.missing_evidence_flags) ? skeptic.missing_evidence_flags : [];
      const missingFlagsHtml = missingFlags.length
        ? missingFlags.map((flag) => {{
            const label = typeof flag === 'string' ? flag : (flag.field || flag.flag || JSON.stringify(flag));
            return `<span class="pill warn">${{escapeHtml(label)}}</span>`;
          }}).join(' ')
        : '<span class="mono">None flagged</span>';

      // Judge Synthesis + Taste Engine + HITL Footer
      const judgeVerdict = normalizeVerdict(judge.verdict) || 'WATCH';
      const isOverride = selectedVerdict !== judgeVerdict;
      const existingReason = (humanReview && (humanReview.reason || humanReview.notes)) || '';
      const savedHumanVerdict = humanReview ? normalizeVerdict(humanReview.human_verdict || humanReview.verdict) : '';
      const tasteScore = pkt.latest_taste_score || null;
      const tasteVerdict = tasteScore ? (normalizeVerdict(tasteScore.taste_verdict) || 'WATCH') : '';
      const tasteProbs = (tasteScore && tasteScore.probabilities) || {{}};
      const pElev = tasteProbs.elevate != null ? Math.round(Number(tasteProbs.elevate) * 100) + '%' : '—';
      const pWatch = tasteProbs.watch != null ? Math.round(Number(tasteProbs.watch) * 100) + '%' : '—';
      const pPass = tasteProbs.pass != null ? Math.round(Number(tasteProbs.pass) * 100) + '%' : '—';
      const pSignable = (tasteScore && tasteScore.live_signable && tasteScore.live_signable.noul != null)
        ? Math.round(Number(tasteScore.live_signable.noul) * 100) + '%'
        : '—';
      const compFit = (tasteScore && tasteScore.composite_fit && tasteScore.composite_fit.score != null)
        ? `${{Number(tasteScore.composite_fit.score).toFixed(2)}} / 4`
        : '—';
      const tasteOutTok = (tasteScore && tasteScore.usage && tasteScore.usage.output_tokens != null)
        ? tasteScore.usage.output_tokens
        : 0;
      const tasteHtml = tasteScore
        ? `<div class="taste-engine-panel">
             <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px;">
               <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
                 <strong style="font-size:0.9rem;">Calibrated Taste Engine (<code>gemini-decision-1</code>)</strong>
                 <span class="verdict-badge ${{escapeHtml(tasteVerdict)}}">${{escapeHtml(tasteVerdict)}}</span>
                 <span class="pill purple">P(elevate): ${{escapeHtml(pElev)}}</span>
                 <span class="pill blue">Confidence: ${{escapeHtml(formatConfidence(tasteScore.confidence))}}</span>
                 <span class="pill ok">${{escapeHtml(String(tasteOutTok))}} output tokens</span>
                 <span class="pill">${{escapeHtml(tasteScore.policy_id || 'policy_v1')}}</span>
               </div>
               <button type="button" id="cardTasteEngineBtn" class="btn taste" data-lead-id="${{escapeHtml(leadId)}}">
                 Re-run Taste Engine (gemini-decision-1 · 0 tok)
               </button>
             </div>
             <div class="prob-grid">
               <div class="prob-cell"><div class="reach-label">P(elevate)</div><div class="reach-val">${{escapeHtml(pElev)}}</div></div>
               <div class="prob-cell"><div class="reach-label">P(watch) · P(pass)</div><div class="reach-val">${{escapeHtml(pWatch)}} · ${{escapeHtml(pPass)}}</div></div>
               <div class="prob-cell"><div class="reach-label">Live Signable (noul)</div><div class="reach-val">${{escapeHtml(pSignable)}}</div></div>
               <div class="prob-cell"><div class="reach-label">Composite Fit</div><div class="reach-val">${{escapeHtml(compFit)}}</div></div>
             </div>
           </div>`
        : `<div class="taste-engine-panel">
             <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px;">
               <div>
                 <strong style="font-size:0.9rem;">Culmination Point · Calibrated Taste Engine (<code>gemini-decision-1</code>)</strong>
                 <div class="mono" style="margin-top:3px;">Evaluate this dossier against the compiled DSPy policy in one pass with calibrated probabilities and 0 output tokens.</div>
               </div>
               <button type="button" id="cardTasteEngineBtn" class="btn taste" data-lead-id="${{escapeHtml(leadId)}}">
                 Run Taste Engine (gemini-decision-1 · 0 tok)
               </button>
             </div>
           </div>`;

      container.innerHTML = `
        <!-- 1. Hero Dossier Header -->
        <div class="hero-grid">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap;">
              <div>
                <h2 class="hero-stage-name">
                  <span>${{escapeHtml(d.stageName)}}</span>
                  <span class="verdict-badge ${{escapeHtml(judgeVerdict)}}">${{escapeHtml(judgeVerdict)}}</span>
                </h2>
                ${{d.aliases.length ? `<div class="hero-aliases">Aliases: ${{escapeHtml(d.aliases.join(', '))}}</div>` : ''}}
              </div>
              <span class="mono">lead_id: ${{escapeHtml(leadId || '—')}}</span>
            </div>

            <div class="hero-badges">
              <span class="pill ok">${{escapeHtml(d.projectType)}}</span>
              <span class="pill">${{escapeHtml(locationStr)}}</span>
              <span class="pill blue">regime: ${{escapeHtml(d.footprintRegime)}}</span>
              <span class="pill ${{d.contactRouteType !== 'none' ? 'ok' : 'warn'}}">contact: ${{escapeHtml(d.contactRouteType)}}</span>
              ${{genrePillsHtml}}
            </div>

            ${{d.bioText ? `<div class="hero-bio">${{escapeHtml(d.bioText)}}</div>` : ''}}

            <div class="reach-grid">
              <div class="reach-cell">
                <div class="reach-label">YouTube Subs</div>
                <div class="reach-val">${{escapeHtml(formatNumber(d.ytSubs))}}</div>
              </div>
              <div class="reach-cell">
                <div class="reach-label">Top Video Views</div>
                <div class="reach-val">${{escapeHtml(formatNumber(d.topViews))}}</div>
              </div>
              <div class="reach-cell">
                <div class="reach-label">Top View Share</div>
                <div class="reach-val">${{d.viewSharePct != null ? escapeHtml(String(d.viewSharePct)) + '%' : '—'}}</div>
              </div>
              <div class="reach-cell">
                <div class="reach-label">Highest Venue Cap</div>
                <div class="reach-val">${{escapeHtml(formatNumber(d.highestCap))}}</div>
              </div>
            </div>

            <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
              ${{platformLinksHtml || '<span class="mono">No external platform URLs recorded.</span>'}}
            </div>
          </div>

          <div>
            ${{embedHtml}}
            ${{mediaQueueHtml}}
          </div>
        </div>

        <!-- 2. 5 Input-Skill Rubric Scoreboard -->
        <section class="rubric-board" aria-label="5 Input-Skill Rubric Scoreboard">
          <div class="section-head" style="margin-bottom:4px;">
            <h3 style="margin:0; font-size:1.04rem;">5 Input-Skill Rubric Scoreboard (0–2 each)</h3>
            <span class="pill purple" style="font-size:0.86rem; font-weight:800;">${{escapeHtml(totalScore)}} / 10 Total</span>
          </div>
          <div class="rubric-rows">${{rubricHtml}}</div>
        </section>

        <!-- 3. Side-by-Side Adversarial Debate Grid -->
        <section class="debate-grid" aria-label="Adversarial Debate">
          <div class="debate-col advocate">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <strong style="color:var(--teal); font-size:0.95rem;">Talent Advocate · Pros</strong>
              <span class="pill ok">simon-screen-advocate</span>
            </div>
            <div class="debate-headline">${{escapeHtml(advocate.headline || 'Case for elevating candidate')}}</div>
            <ul class="debate-list">${{prosHtml}}</ul>
            <div class="standout-hook-box">
              <strong>Standout Hook:</strong> ${{escapeHtml(advocate.standout_hook || 'Distinct live vocal identity in early discovery window.')}}
            </div>
          </div>

          <div class="debate-col skeptic">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <strong style="color:var(--warn); font-size:0.95rem;">Talent Skeptic · Cons &amp; Gaps</strong>
              <span class="pill warn">simon-screen-skeptic</span>
            </div>
            <div class="debate-headline">${{escapeHtml(skeptic.headline || 'Key uncertainties & missing evidence')}}</div>
            <ul class="debate-list">${{consHtml}}</ul>
            <div class="missing-flags-box">
              <div style="font-size:0.74rem; font-weight:700; text-transform:uppercase; color:var(--muted); margin-bottom:6px;">Missing Evidence Flags</div>
              <div style="display:flex; gap:6px; flex-wrap:wrap;">${{missingFlagsHtml}}</div>
            </div>
          </div>
        </section>

        <!-- 4. Neon Judge Synthesis + Human-in-the-Loop Calibration Footer -->
        <footer class="judge-footer">
          <div>
            <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px;">
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span class="pill purple">gemini-4-neon Judge</span>
                <span class="verdict-badge ${{escapeHtml(judgeVerdict)}}">${{escapeHtml(judgeVerdict)}}</span>
                <span class="pill">${{escapeHtml(totalScore)}} / 10</span>
                <span class="pill blue">Confidence: ${{escapeHtml(formatConfidence(judge.confidence))}}</span>
              </div>
              ${{savedHumanVerdict
                ? `<span id="savedReviewBadge" class="pill ok">✓ Saved Human Verdict: ${{escapeHtml(savedHumanVerdict)}}</span>`
                : '<span id="savedReviewBadge" class="pill">Unlabeled · Awaiting human calibration</span>'}}
            </div>
            <div style="font-size:0.92rem; color:var(--text);">${{escapeHtml(judge.rationale || judge.summary || 'Judge synthesis pending.')}}</div>
          </div>

          ${{tasteHtml}}

          <div class="hitl-bar">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <strong style="font-size:0.88rem;">Human-in-the-Loop Calibration (Trains <code>gemini-decision-1</code> Rubric via DSPy)</strong>
              ${{isOverride
                ? `<span class="pill amber">Override vs. Judge (${{escapeHtml(judgeVerdict)}} → ${{escapeHtml(selectedVerdict)}})</span>`
                : '<span class="mono">Matches Judge verdict</span>'}}
            </div>
            <div class="hitl-controls-row">
              <div class="verdict-btn-group" role="group" aria-label="Human Verdict Choice">
                <button type="button" class="verdict-choice-btn ${{selectedVerdict === 'ELEVATE' ? 'selected' : ''}}" data-verdict="ELEVATE">Elevate</button>
                <button type="button" class="verdict-choice-btn ${{selectedVerdict === 'WATCH' ? 'selected' : ''}}" data-verdict="WATCH">Watch</button>
                <button type="button" class="verdict-choice-btn ${{selectedVerdict === 'PASS' ? 'selected' : ''}}" data-verdict="PASS">Pass</button>
              </div>
              <input
                type="text"
                id="humanReasonInput"
                class="reason-input"
                value="${{escapeHtml(existingReason)}}"
                placeholder="Why? (trains judging rubric — especially on overrides)"
              />
              <button type="button" id="saveAndNextBtn" class="btn primary" data-packet-id="${{escapeHtml(packetId)}}" data-lead-id="${{escapeHtml(leadId)}}" data-stage-name="${{escapeHtml(d.stageName)}}">
                Save &amp; Next →
              </button>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; padding-top:8px; border-top:1px solid var(--border); margin-top:4px;">
              <span class="mono" style="font-size:0.78rem;">Advance candidate to next stage:</span>
              <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
                <a class="btn" href="/investigate?lead=${{encodeURIComponent(leadId)}}" style="font-size:0.78rem; padding:5px 10px;">← Inspect Dossier</a>
                <a class="btn" href="/?tab=review&amp;subtab=screened&amp;lead=${{encodeURIComponent(leadId)}}" style="font-size:0.78rem; padding:5px 10px;">Open in Talent Review →</a>
                <a class="btn primary" href="/?tab=pipeline&amp;phase=4_producer&amp;lead=${{encodeURIComponent(leadId)}}&amp;subject=${{encodeURIComponent(d.stageName)}}" style="font-size:0.78rem; padding:5px 10px;">Draft Callback (Phase 4) →</a>
              </div>
            </div>
          </div>
        </footer>
      `;

      // Wire media queue switching
      container.querySelectorAll('[data-play-yt]').forEach((btn) => {{
        btn.onclick = () => {{
          activeVideoIdOverride = btn.dataset.playYt || '';
          renderDeck();
        }};
      }});

      // Wire verdict choice buttons (preserving typed reason)
      container.querySelectorAll('.verdict-choice-btn').forEach((btn) => {{
        btn.onclick = () => {{
          const typedReason = el('humanReasonInput') ? el('humanReasonInput').value : '';
          selectedVerdict = normalizeVerdict(btn.dataset.verdict) || 'WATCH';
          renderDeck();
          if (el('humanReasonInput')) el('humanReasonInput').value = typedReason;
        }};
      }});

      // Wire Save & Next -> POST /api/screening/labels
      const saveBtn = el('saveAndNextBtn');
      if (saveBtn) {{
        saveBtn.onclick = saveCurrentLabelAndNext;
      }}
      const cardTasteBtn = el('cardTasteEngineBtn');
      if (cardTasteBtn) {{
        cardTasteBtn.onclick = () => runTasteEngineForLead(leadId);
      }}
      const reasonInput = el('humanReasonInput');
      if (reasonInput) {{
        reasonInput.onkeydown = (ev) => {{
          if (ev.key === 'Enter') {{
            ev.preventDefault();
            saveCurrentLabelAndNext();
          }}
        }};
      }}
    }}

    async function saveCurrentLabelAndNext() {{
      const filtered = getFilteredPackets();
      const pkt = filtered[currentIndex];
      if (!pkt) return;
      const saveBtn = el('saveAndNextBtn');
      const d = extractDossierView(pkt);
      const packetId = pkt.packet_id || pkt.id || pkt._doc_id || '';
      const leadId = pkt.lead_id || (pkt.dossier_snapshot && pkt.dossier_snapshot.lead_id) || '';
      const reason = el('humanReasonInput') ? el('humanReasonInput').value.trim() : '';

      if (saveBtn) saveBtn.disabled = true;
      try {{
        const res = await fetch('/api/screening/labels', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            packet_id: packetId,
            lead_id: leadId,
            stage_name: d.stageName,
            human_verdict: selectedVerdict,
            reason,
          }}),
        }});
        const data = await res.json().catch(() => ({{}}));
        if (!res.ok) throw new Error(data.error || 'Failed to save human label');

        pkt.human_review = data.label || data.human_review || {{
          packet_id: packetId,
          lead_id: leadId,
          stage_name: d.stageName,
          human_verdict: selectedVerdict,
          reason,
          saved_at: new Date().toISOString(),
        }};
        showBanner(`Saved ${{selectedVerdict}} calibration label for ${{d.stageName}}.`, 'info');

        const updatedFiltered = getFilteredPackets();
        if (currentFilter === 'unlabeled') {{
          if (currentIndex >= updatedFiltered.length) {{
            currentIndex = Math.max(0, updatedFiltered.length - 1);
          }}
        }} else if (currentIndex < updatedFiltered.length - 1) {{
          currentIndex += 1;
        }}
        syncSelectedVerdictForCurrentPacket();
        renderDeck();
        await loadModels();
      }} catch (err) {{
        showBanner(err.message, 'err');
      }} finally {{
        if (el('saveAndNextBtn')) el('saveAndNextBtn').disabled = false;
      }}
    }}

    function renderModelState(payload) {{
      if (!payload || typeof payload !== 'object') return;
      const active = payload.active_model
        || payload.active_policy
        || payload.model
        || payload.latest
        || (Array.isArray(payload.models) && payload.models[0])
        || payload;

      const version = active.policy_id || active.policy_version || active.version || active.model_id || 'v1.0-seed';
      const labelCount = active.human_label_count != null
        ? active.human_label_count
        : (active.training_label_count != null
          ? active.training_label_count
          : (active.label_count != null ? active.label_count : (active.train_count != null ? active.train_count : 0)));
      const rawAcc = active.val_accuracy != null
        ? active.val_accuracy
        : (active.accuracy != null ? active.accuracy : (active.train_accuracy != null ? active.train_accuracy : active.agreement_rate));
      const accStr = rawAcc != null
        ? (Number(rawAcc) <= 1 ? `${{Math.round(Number(rawAcc) * 100)}}% acc` : `${{Math.round(Number(rawAcc))}}% acc`)
        : 'untrained';

      el('activeModelBadge').textContent = `Policy ${{version}} · ${{labelCount}} label(s) · ${{accStr}}`;
      el('policySummaryBadge').textContent = `gemini-decision-1: ${{version}} (${{accStr}})`;

      const qConfig = active.questions_config || payload.questions_config || active.compiled_policy || active;
      el('policyMetaBox').textContent = `Active policy ${{version}} · trained on ${{labelCount}} human calibration label(s) · accuracy: ${{accStr}}`;
      el('questionsConfigJson').textContent = JSON.stringify(qConfig, null, 2);
    }}

    function renderEvalState(payload) {{
      if (!payload || typeof payload !== 'object') return;
      const overall = payload.overall_score != null
        ? payload.overall_score
        : (payload.score != null ? payload.score : payload.pass_rate);
      const scoreText = overall != null
        ? (Number(overall) <= 1 ? `${{Math.round(Number(overall) * 100)}}%` : String(overall))
        : 'completed';
      el('evalSummaryBadge').textContent = `3-Layer Evals: ${{scoreText}}`;

      const layers = payload.layers || payload.layer_scores || {{}};
      const l1 = layers.layer_1 ?? payload.layer_1_score ?? payload.deterministic_score;
      const l2 = layers.layer_2 ?? payload.layer_2_score ?? payload.process_score;
      const l3 = layers.layer_3 ?? payload.layer_3_score ?? payload.judge_alignment_score;

      const parts = [`Overall: ${{scoreText}}`];
      if (l1 != null) parts.push(`L1 Contract: ${{typeof l1 === 'object' ? JSON.stringify(l1) : l1}}`);
      if (l2 != null) parts.push(`L2 Adversarial Process: ${{typeof l2 === 'object' ? JSON.stringify(l2) : l2}}`);
      if (l3 != null) parts.push(`L3 Outcome Calibration: ${{typeof l3 === 'object' ? JSON.stringify(l3) : l3}}`);

      el('evalBreakdownBox').textContent = parts.join(' · ');
      el('evalRawJson').style.display = 'block';
      el('evalRawJson').textContent = JSON.stringify(payload, null, 2);
    }}

    async function loadPackets() {{
      let res = await fetch('/api/screening/packets').catch(() => null);
      if (!res || !res.ok) {{
        res = await fetch('/api/screening').catch(() => null);
      }}
      if (res && res.ok) {{
        const data = await res.json();
        const list = data.packets || data.items || data.results || (Array.isArray(data) ? data : []);
        allPackets = Array.isArray(list) ? list : [];
      }}

      if (initialFocusPacket || initialFocusLead) {{
        const matchIdx = allPackets.findIndex((p) => {{
          if (initialFocusPacket && (p.packet_id === initialFocusPacket || p.id === initialFocusPacket)) return true;
          if (initialFocusLead && p.lead_id === initialFocusLead) return true;
          return false;
        }});
        if (matchIdx >= 0) {{
          currentFilter = 'all';
          currentIndex = matchIdx;
        }}
        initialFocusPacket = '';
        initialFocusLead = '';
      }}
      syncSelectedVerdictForCurrentPacket();
      renderDeck();
    }}

    async function loadModels() {{
      const res = await fetch('/api/screening/models').catch(() => null);
      if (res && res.ok) {{
        const data = await res.json();
        renderModelState(data);
      }} else {{
        el('activeModelBadge').textContent = 'Policy v1.0-seed · 0 labels';
      }}
    }}

    async function loadLatestEvals() {{
      const res = await fetch('/api/screening/evals').catch(() => null);
      if (!res || !res.ok) return;
      const data = await res.json().catch(() => null);
      if (!data) return;
      const latest = data.latest || (Array.isArray(data.runs) && data.runs[0]) || (Array.isArray(data.eval_runs) && data.eval_runs[0]) || (data.overall_score != null || data.score != null ? data : null);
      if (latest) renderEvalState(latest);
    }}

    function stepCandidate(delta) {{
      const filtered = getFilteredPackets();
      if (!filtered.length) return;
      const next = currentIndex + delta;
      if (next < 0 || next >= filtered.length) return;
      currentIndex = next;
      syncSelectedVerdictForCurrentPacket();
      renderDeck();
    }}

    // Filter pill clicks
    document.querySelectorAll('#deckFilterBar .filter-pill').forEach((btn) => {{
      btn.onclick = () => {{
        currentFilter = btn.dataset.filter || 'all';
        currentIndex = 0;
        syncSelectedVerdictForCurrentPacket();
        renderDeck();
      }};
    }});

    // Stepper buttons
    el('prevCandidateBtn').onclick = () => stepCandidate(-1);
    el('nextCandidateBtn').onclick = () => stepCandidate(1);

    // Keyboard navigation ([ / ] and Left / Right arrows when not focused in an input)
    document.addEventListener('keydown', (ev) => {{
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      const tag = (ev.target && ev.target.tagName) ? ev.target.tagName.toUpperCase() : '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (ev.target && ev.target.isContentEditable)) {{
        return;
      }}
      if (ev.key === '[' || ev.key === 'ArrowLeft') {{
        ev.preventDefault();
        stepCandidate(-1);
      }} else if (ev.key === ']' || ev.key === 'ArrowRight') {{
        ev.preventDefault();
        stepCandidate(1);
      }}
    }});

    // Top Control Strip Fleet / DSPy / Eval buttons
    el('runScreeningBtn').onclick = async () => {{
      const isLive = Boolean(el('liveScreeningToggle').checked);
      el('runScreeningBtn').disabled = true;
      showBanner(`Running Stage 3 Neon Screening Fleet (${{isLive ? 'live' : 'simulated/cached'}})…`, 'info');
      try {{
        const res = await fetch('/api/screening/run', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ live: isLive }}),
        }});
        const data = await res.json().catch(() => ({{}}));
        if (!res.ok) throw new Error(data.error || 'Screening run failed');
        if (Array.isArray(data.packets) && data.packets.length) {{
          allPackets = data.packets;
          currentIndex = 0;
          syncSelectedVerdictForCurrentPacket();
          renderDeck();
        }}
        await loadPackets();
        await loadModels();
        showBanner(`Screening fleet completed: ${{allPackets.length}} candidate packet(s) ready for review.`, 'info');
      }} catch (err) {{
        showBanner(err.message, 'err');
      }} finally {{
        el('runScreeningBtn').disabled = false;
      }}
    }};

    el('trainModelBtn').onclick = async () => {{
      el('trainModelBtn').disabled = true;
      showBanner('Compiling gemini-decision-1 judging policy with DSPy from human calibration labels…', 'info');
      try {{
        const res = await fetch('/api/screening/train', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{}}),
        }});
        const data = await res.json().catch(() => ({{}}));
        if (!res.ok) throw new Error(data.error || 'DSPy policy compilation failed');
        renderModelState(data);
        await loadModels();
        el('policyInspectorDrawer').open = true;
        showBanner('Compiled updated gemini-decision-1 judging model from human labels.', 'info');
      }} catch (err) {{
        showBanner(err.message, 'err');
      }} finally {{
        el('trainModelBtn').disabled = false;
      }}
    }};

    async function runTasteEngineForLead(targetLeadId) {{
      const topBtn = el('runTasteEngineBtn');
      const cardBtn = el('cardTasteEngineBtn');
      if (topBtn) topBtn.disabled = true;
      if (cardBtn) cardBtn.disabled = true;
      showBanner('Running calibrated Taste Engine (gemini-decision-1 · 0 output tokens)…', 'info');
      try {{
        const bodyObj = targetLeadId ? {{ lead_id: targetLeadId, live: true }} : {{ live: true }};
        const res = await fetch('/api/screening/taste-score', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(bodyObj),
        }});
        const data = await res.json().catch(() => ({{}}));
        if (!res.ok) throw new Error(data.error || 'Taste Engine evaluation failed');
        await loadPackets();
        await loadModels();
        const ts = data.taste_score || data;
        const pE = ts.probabilities && ts.probabilities.elevate != null
          ? Math.round(Number(ts.probabilities.elevate) * 100) + '%'
          : '—';
        showBanner(
          `Taste Engine (gemini-decision-1 · 0 tok): P(elevate)=${{pE}}, verdict=${{(ts.taste_verdict || '').toUpperCase()}} (${{ts.policy_id || 'policy_v1'}}).`,
          'info'
        );
      }} catch (err) {{
        showBanner(err.message, 'err');
      }} finally {{
        if (el('runTasteEngineBtn')) el('runTasteEngineBtn').disabled = false;
        if (el('cardTasteEngineBtn')) el('cardTasteEngineBtn').disabled = false;
      }}
    }}

    el('runTasteEngineBtn').onclick = () => {{
      const filtered = getFilteredPackets();
      const pkt = filtered[currentIndex];
      const leadId = pkt ? (pkt.lead_id || '') : '';
      runTasteEngineForLead(leadId);
    }};

    el('runEvalsBtn').onclick = async () => {{
      const isLive = Boolean(el('liveScreeningToggle').checked);
      el('runEvalsBtn').disabled = true;
      showBanner('Running 3-layer Stage 3 Screening Rubric Evals…', 'info');
      try {{
        const res = await fetch('/api/screening/evals/run', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ live: isLive }}),
        }});
        const data = await res.json().catch(() => ({{}}));
        if (!res.ok) throw new Error(data.error || 'Rubric eval run failed');
        renderEvalState(data);
        el('policyInspectorDrawer').open = true;
        showBanner('Completed 3-layer Stage 3 Screening Rubric Evals.', 'info');
      }} catch (err) {{
        showBanner(err.message, 'err');
      }} finally {{
        el('runEvalsBtn').disabled = false;
      }}
    }};

    Promise.all([loadPackets(), loadModels(), loadLatestEvals()]);
  </script>
</body>
</html>
"""


SCREENING_HTML = render_screening_page()
