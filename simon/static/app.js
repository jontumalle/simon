/* Simon Talent Review Studio, Pipeline Runner & Agent Lab */
(() => {
  'use strict';

  const state = {
    currentRun: null,
    activeTab: 'review',
    activeSubtab: 'screened',
    selectedLeads: new Set(),
    sources: [],
    filteredSources: [],
    selectedSourceIds: new Set(),
    sourcesExpanded: false,
    discoveryBatches: [],
    discoveredLeads: [],
    screeningPackets: [],
    phases: [],
    phaseRuns: [],
    activePhaseId: '1_discovery',
    pipelineMode: 'test',
    phaseStatus: {},
    agents: [],
    activeAgent: null,
    lastLabResult: null,
    labShowRaw: false,
    evals: [],
  };

  const $ = (id) => document.getElementById(id);

  const AGENT_DISPLAY_NAMES = {
    'discovery-scout': 'Discovery Scout',
    'identity-resolver': 'Identity Resolver',
    'footprint-profiler': 'Footprint Profiler',
    'signal-forensics': 'Audience Signal Analyst',
    'track-record-mapper': 'Live History Mapper',
    'dossier-assembler': 'Profile Assembler',
    'screen-advocate': 'Advocate Scout',
    'screen-skeptic': 'Skeptic Scout',
    'screening-judge': 'Screening Judge',
    'showcase-producer': 'Showcase Producer',
    'performance-critic': 'Performance Critic',
    'booking-critic': 'Booking Critic',
  };

  function formatLabel(val) {
    const text = String(val || '').replace(/[_-]+/g, ' ').trim();
    if (!text) return '';
    return text
      .replace(/\b\w/g, (ch) => ch.toUpperCase())
      .replace(/\bYoutube\b/g, 'YouTube')
      .replace(/\bNyc\b/g, 'NYC')
      .replace(/\bDsp\b/g, 'Streaming')
      .replace(/\bRnb\b/g, 'R&B');
  }

  function formatAgentName(raw) {
    const text = String(raw || '').trim();
    if (!text) return 'Scout';
    const m = text.match(/^([^\s(]+)(?:\s*\(([^)]+)\))?$/);
    if (m) {
      const base = m[1].replace(/^(?:staging|prod|dev)-/, '').replace(/^simon-/, '');
      const label = AGENT_DISPLAY_NAMES[base] || formatLabel(base);
      if (m[2]) {
        const workerNum = m[2].match(/(\d+)$/);
        return workerNum ? `${label} #${workerNum[1]}` : `${label} (${formatLabel(m[2])})`;
      }
      return label;
    }
    return formatLabel(text);
  }

  function formatStatus(val) {
    const key = String(val || '').toLowerCase();
    const map = {
      completed: 'Done',
      done: 'Done',
      active: 'Active',
      live: 'Live',
      test: 'Test',
      simulated: 'Sample',
      dry_run: 'Dry Run',
      dispatched: 'Running',
      running: 'Running',
      failed: 'Failed',
      error: 'Error',
      pending: 'Pending',
      pending_human_review: 'Needs Review',
      verified: 'Verified',
      unverified: 'Unverified',
      uncertain: 'Uncertain',
      elevate: 'Elevate',
      watch: 'Watch',
      pass: 'Pass',
      fail: 'Fail',
    };
    return map[key] || formatLabel(val);
  }

  function esc(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  function setBanner(msg, kind = 'info') {
    const el = $('statusBanner');
    if (!msg) {
      el.className = 'banner';
      el.textContent = '';
      return;
    }
    el.className = 'banner ' + kind;
    el.textContent = msg;
  }

  // --- THEME ---
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('simon_theme', theme);
    $('themeToggleBtn').textContent = theme === 'dark' ? '☾ Studio Dark' : '☀ Light';
  }
  applyTheme(localStorage.getItem('simon_theme') || 'light');
  $('themeToggleBtn').addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'light';
    applyTheme(cur === 'dark' ? 'light' : 'dark');
  });

  // --- TOP TABS & EXPLICIT URL/HISTORY STATE MACHINE ---
  const TAB_LABELS = {
    discovery: 'Discovery',
    review: 'Talent Review',
    pipeline: 'Pipeline Stepper',
    lab: 'Agent Lab',
  };
  const VALID_TABS = new Set(Object.keys(TAB_LABELS));

  function syncUrlState(tabName, pushHistory = false) {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', tabName);
      if (tabName === 'pipeline' && state.activePhaseId) {
        url.searchParams.set('phase', state.activePhaseId);
        url.searchParams.delete('subtab');
      } else if (tabName === 'review') {
        url.searchParams.delete('phase');
        if (state.activeSubtab && state.activeSubtab !== 'screened') {
          url.searchParams.set('subtab', state.activeSubtab);
        } else {
          url.searchParams.delete('subtab');
        }
      } else {
        url.searchParams.delete('phase');
        url.searchParams.delete('subtab');
        url.searchParams.delete('lead');
        url.searchParams.delete('subject');
      }
      const nextHref = url.toString();
      if (pushHistory && nextHref !== window.location.href) {
        window.history.pushState({ tab: tabName, phase: state.activePhaseId, subtab: state.activeSubtab }, '', nextHref);
      } else {
        window.history.replaceState({ tab: tabName, phase: state.activePhaseId, subtab: state.activeSubtab }, '', nextHref);
      }
    } catch (e) {
      // Ignore history errors in restricted frames
    }
  }

  function switchTab(tabName, updateUrl = true, pushHistory = false) {
    const safeTab = VALID_TABS.has(tabName) ? tabName : 'review';
    state.activeTab = safeTab;
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.add('hidden'));
    const target = $('tab-' + safeTab);
    if (target) target.classList.remove('hidden');
    document.querySelectorAll('[data-tab]').forEach((btn) => {
      if (btn.classList.contains('nav-tab')) {
        btn.classList.toggle('active', btn.dataset.tab === safeTab);
      }
    });
    if ($('reviewTopbarControls')) {
      $('reviewTopbarControls').classList.toggle('hidden', safeTab !== 'review');
    }
    const label = TAB_LABELS[safeTab] || 'Studio';
    if ($('brandSubLabel')) {
      $('brandSubLabel').textContent = label;
    }
    document.title = `Simon · ${label}`;
    const moreMenu = $('moreMenu');
    if (moreMenu) moreMenu.removeAttribute('open');
    if (updateUrl) syncUrlState(safeTab, pushHistory);
  }
  document.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab, true, true));
  });

  window.addEventListener('popstate', () => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab') || 'review';
    const phase = params.get('phase');
    const subtab = params.get('subtab') || 'screened';
    if (phase && state.phases.some((p) => p.id === phase)) {
      selectPhase(phase);
    }
    if (tab === 'review') {
      selectSubtab(subtab, false);
    }
    switchTab(tab, false, false);
  });

  // --- DRAWERS & POPOVER DISMISSAL ---
  function closeDrawers() {
    ['profileDrawer', 'traceDrawer'].forEach((id) => {
      const el = $(id);
      if (el) el.classList.add('hidden');
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeDrawers();
      const m = $('moreMenu');
      if (m) m.removeAttribute('open');
    }
  });
  document.addEventListener('click', (e) => {
    const m = $('moreMenu');
    if (m && m.hasAttribute('open') && !m.contains(e.target)) {
      m.removeAttribute('open');
    }
  });
  document.querySelectorAll('[data-close-drawer]').forEach((btn) => {
    btn.addEventListener('click', closeDrawers);
  });
  ['profileDrawer', 'traceDrawer'].forEach((id) => {
    const el = $(id);
    if (el) {
      el.addEventListener('click', (e) => {
        if (e.target.id === id) closeDrawers();
      });
    }
  });
  $('openTraceBtn').addEventListener('click', () => {
    const m = $('moreMenu');
    if (m) m.removeAttribute('open');
    $('traceDrawer').classList.remove('hidden');
  });

  // =========================================================
  // TAB 0: DISCOVERY (SOURCE REGISTRY + FLEET + LEADS BRIDGE)
  // =========================================================
  function leadToPhase2Handoff(lead) {
    const seeds = Array.isArray(lead.seed_sources) ? lead.seed_sources : [];
    const firstSeed = (seeds[0] && typeof seeds[0] === 'object') ? seeds[0] : {};
    return {
      lead_id: lead.lead_id || '',
      stage_name: lead.stage_name || lead.title || 'Unknown Artist',
      attribution_status: lead.attribution_status || 'verified',
      seed_source_url: lead.seed_source_url || firstSeed.url || '',
      source_channel: lead.source_channel || firstSeed.source_channel || 'youtube_session',
      context_snippet: lead.context_snippet || '',
      seed_sources: seeds,
    };
  }

  function syncDiscoveryBatchLinks(batchId, summaryMsg = '') {
    if (!batchId) return;
    const q = `?batch=${encodeURIComponent(batchId)}`;
    if ($('tracesNavLink')) $('tracesNavLink').href = `/field-news${q}`;
    if ($('reportsNavLink')) $('reportsNavLink').href = `/reports${q}`;
    if ($('subflowFieldNewsLink')) $('subflowFieldNewsLink').href = `/field-news${q}`;
    if ($('subflowReportsLink')) $('subflowReportsLink').href = `/reports${q}`;
    if ($('discTopFieldNewsLink')) $('discTopFieldNewsLink').href = `/field-news${q}`;
    if ($('discTopReportsLink')) $('discTopReportsLink').href = `/reports${q}`;
    if ($('discFollowFieldNewsBtn')) $('discFollowFieldNewsBtn').href = `/field-news${q}`;
    if ($('discOpenReportsBtn')) $('discOpenReportsBtn').href = `/reports${q}`;
    if (summaryMsg && $('discPostDispatchBar')) {
      $('discPostDispatchMsg').textContent = summaryMsg;
      $('discPostDispatchBar').classList.remove('hidden');
    }
  }

  function renderDiscChannelChips() {
    const el = $('discChannelChips');
    if (!el) return;
    const activeChannel = $('discChannelFilter').value;
    const counts = new Map();
    state.sources.forEach((s) => {
      const ch = s.source_channel || 'other';
      counts.set(ch, (counts.get(ch) || 0) + 1);
    });
    const chips = [
      `<button type="button" class="chip-btn ${activeChannel === '' ? 'active' : ''}" data-channel="">All (${state.sources.length})</button>`,
    ];
    Array.from(counts.keys()).sort().forEach((ch) => {
      chips.push(
        `<button type="button" class="chip-btn ${activeChannel === ch ? 'active' : ''}" data-channel="${esc(ch)}">${esc(formatLabel(ch))} (${counts.get(ch)})</button>`
      );
    });
    el.innerHTML = chips.join('');
    el.querySelectorAll('.chip-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        $('discChannelFilter').value = btn.dataset.channel || '';
        renderDiscSources();
      });
    });
  }

  function renderDiscSelectedTray() {
    const tray = $('discSelectedTray');
    if (!tray) return;
    if (!state.selectedSourceIds.size) {
      tray.classList.add('hidden');
      tray.innerHTML = '';
      return;
    }
    const byId = new Map(state.sources.map((s) => [s.source_id, s]));
    const items = Array.from(state.selectedSourceIds).map((id) => {
      const src = byId.get(id);
      const name = src ? src.name : id;
      return `<button type="button" class="sel-chip" data-remove-id="${esc(id)}" title="Remove source">${esc(name)} ×</button>`;
    });
    tray.innerHTML = `<span class="muted" style="font-weight:700;">Selected:</span>` + items.join('');
    tray.classList.remove('hidden');
    tray.querySelectorAll('.sel-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.selectedSourceIds.delete(btn.dataset.removeId);
        renderDiscSources();
      });
    });
  }

  function resetDiscFilters() {
    $('discSearchInput').value = '';
    $('discChannelFilter').value = '';
    $('discCityFilter').value = '';
    $('discTierFilter').value = '';
    $('discGenreFilter').value = '';
    renderDiscSources();
  }

  function renderDiscSources() {
    const grid = $('discSourceGrid');
    if (!grid) return;
    const q = ($('discSearchInput').value || '').trim().toLowerCase();
    const ch = $('discChannelFilter').value;
    const city = $('discCityFilter').value;
    const tier = $('discTierFilter').value;
    const genre = $('discGenreFilter').value;

    state.filteredSources = state.sources.filter((s) => {
      const loc = s.location || {};
      const sCity = loc.city || 'Global';
      const tags = Array.isArray(s.genre_tags) ? s.genre_tags : [];
      if (ch && s.source_channel !== ch) return false;
      if (city && sCity !== city) return false;
      if (tier && s.career_tier !== tier) return false;
      if (genre && !tags.includes(genre)) return false;
      if (q) {
        const hay = [
          s.name,
          s.why_useful,
          s.notes,
          s.source_channel,
          sCity,
          loc.area,
          tags.join(' '),
        ].filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    renderDiscChannelChips();
    renderDiscSelectedTray();

    $('discSelectedBadge').textContent = `${state.selectedSourceIds.size} selected`;
    $('discShowingBadge').textContent = `${state.filteredSources.length} / ${state.sources.length} shown`;

    if (!state.filteredSources.length) {
      grid.innerHTML = `
        <div style="grid-column:1/-1; padding:32px 16px; text-align:center;" class="muted">
          <div style="font-weight:700; margin-bottom:8px;">No sources match the active filters.</div>
          <button type="button" class="btn" id="discResetFiltersBtn">Reset Filters</button>
        </div>`;
      if ($('discResetFiltersBtn')) $('discResetFiltersBtn').addEventListener('click', resetDiscFilters);
      return;
    }

    grid.innerHTML = state.filteredSources.map((s) => {
      const isSel = state.selectedSourceIds.has(s.source_id);
      const loc = s.location || {};
      const sCity = loc.city || 'Global';
      const locLabel = loc.area ? `${loc.area} · ${sCity}` : sCity;
      const statusCls = s.status === 'active' ? 'ok' : 'warn';
      const tags = (Array.isArray(s.genre_tags) ? s.genre_tags : []).filter((g) => g && g !== 'all').slice(0, 5);
      const tagsHtml = tags.length
        ? `<div class="source-genres">${tags.map((g) => `<span class="genre-tag">${esc(g)}</span>`).join('')}</div>`
        : '';
      const noteHtml = s.notes ? `<div class="source-note">Note: ${esc(s.notes)}</div>` : '';
      const extHtml = s.url
        ? `<a class="source-ext" href="${esc(s.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Open ↗</a>`
        : '';

      return `
        <div class="source-item ${isSel ? 'selected' : ''}" data-source-id="${esc(s.source_id)}">
          <div class="source-title">
            <span style="display:flex; align-items:flex-start; gap:8px;">
              <span class="source-check">${isSel ? '✓' : ''}</span>
              <span>${esc(s.name)}</span>
            </span>
            <span style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
              ${extHtml}
              <span class="pill ${statusCls}">${esc(formatStatus(s.status))}</span>
            </span>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <span class="pill accent">${esc(formatLabel(s.source_channel))}</span>
            <span class="pill">${esc(locLabel)}</span>
            <span class="pill">${esc(formatLabel(s.career_tier))}</span>
          </div>
          <div class="source-why">${esc(s.why_useful)}</div>
          ${noteHtml}
          ${tagsHtml}
        </div>`;
    }).join('');

    grid.querySelectorAll('.source-item').forEach((node) => {
      node.addEventListener('click', () => {
        const id = node.dataset.sourceId;
        if (state.selectedSourceIds.has(id)) state.selectedSourceIds.delete(id);
        else state.selectedSourceIds.add(id);
        if (state.selectedSourceIds.size > 0) {
          $('discAgentCountInput').value = Math.min(state.selectedSourceIds.size, 10);
        }
        renderDiscSources();
      });
    });
  }

  function renderDiscBatches() {
    const list = $('discBatchesList');
    if (!list) return;
    $('discBatchCountBadge').textContent = String(state.discoveryBatches.length);
    if (!state.discoveryBatches.length) {
      list.innerHTML = `<div class="muted" style="font-size:12.5px;">No discovery runs yet. Pick sources above and click <strong>Send Discovery Scouts</strong>.</div>`;
      return;
    }
    list.innerHTML = state.discoveryBatches.slice(0, 6).map((b, idx) => {
      const workers = b.workers || [];
      const leadSum = workers.reduce((acc, w) => acc + Number(w.lead_count || 0), 0);
      const q = `?batch=${encodeURIComponent(b.batch_id)}`;
      const runNum = state.discoveryBatches.length - idx;
      const runDate = b.created_at ? String(b.created_at).slice(0, 10) : '';
      const runTitle = runDate ? `Discovery Run #${runNum} · ${runDate}` : `Discovery Run #${runNum}`;
      return `
        <div class="lead-row">
          <div class="lead-row-top">
            <div>
              <strong style="font-size:12.5px;">${esc(runTitle)}</strong>
              <span class="pill ${b.mode === 'live' ? 'ok' : 'accent'}" style="margin-left:6px;">${esc(formatStatus(b.mode || 'simulated'))}</span>
            </div>
            <span class="muted" style="font-size:11.5px;">${workers.length} scouts · ${leadSum} leads</span>
          </div>
          <div class="muted" style="font-size:12px;">${esc((b.search_brief || '').slice(0, 110))}</div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <a class="btn" style="padding:4px 9px; font-size:11.5px;" href="/field-news${q}">Field News →</a>
            <a class="btn" style="padding:4px 9px; font-size:11.5px;" href="/reports${q}">Reports →</a>
          </div>
        </div>`;
    }).join('');
  }

  function renderDiscLeads() {
    const list = $('discLeadsList');
    const select = $('phaseLeadSelect');
    if ($('discLeadCountBadge')) $('discLeadCountBadge').textContent = String(state.discoveredLeads.length);

    if (select) {
      const opts = [`<option value="">Choose an artist from Discovery (${state.discoveredLeads.length})…</option>`];
      state.discoveredLeads.forEach((lead, idx) => {
        opts.push(`<option value="${idx}">${esc(lead.stage_name || 'Unnamed Artist')} (${esc(formatStatus(lead.attribution_status || 'unverified'))})</option>`);
      });
      select.innerHTML = opts.join('');
    }

    if (!list) return;
    if (!state.discoveredLeads.length) {
      list.innerHTML = `<div class="muted" style="font-size:12.5px;">No discovered artists yet. Run Discovery above to fill this list.</div>`;
      return;
    }

    list.innerHTML = state.discoveredLeads.slice(0, 16).map((lead, idx) => {
      const seeds = Array.isArray(lead.seed_sources) ? lead.seed_sources : [];
      const firstSeed = seeds[0] || {};
      return `
        <div class="lead-row">
          <div class="lead-row-top">
            <div>
              <strong style="font-size:13.5px;">${esc(lead.stage_name || 'Unnamed Artist')}</strong>
              <span class="pill ${lead.attribution_status === 'verified' ? 'ok' : ''}" style="margin-left:6px;">${esc(formatStatus(lead.attribution_status || 'lead'))}</span>
              ${firstSeed.source_channel ? `<span class="pill" style="margin-left:4px;">${esc(formatLabel(firstSeed.source_channel))}</span>` : ''}
            </div>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              <a class="btn" href="/investigate?subject=${encodeURIComponent(lead.stage_name || '')}${lead.lead_id ? '&lead=' + encodeURIComponent(lead.lead_id) : ''}" style="padding:5px 10px; font-size:11.5px;">
                Investigator Desk →
              </a>
              <button type="button" class="btn btn-primary disc-send-pipeline-btn" data-lidx="${idx}" style="padding:5px 10px; font-size:11.5px;">
                Investigate in Pipeline →
              </button>
            </div>
          </div>
          ${lead.context_snippet ? `<div class="muted" style="font-size:12px;">${esc(lead.context_snippet.slice(0, 160))}</div>` : ''}
        </div>`;
    }).join('');

    list.querySelectorAll('.disc-send-pipeline-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const lead = state.discoveredLeads[Number(btn.dataset.lidx)];
        if (!lead) return;
        selectPhase('2a_identity', leadToPhase2Handoff(lead));
        switchTab('pipeline');
      });
    });
  }

  async function refreshDiscoveryData() {
    const [bRes, lRes] = await Promise.all([
      fetch('/api/discovery/batches').catch(() => null),
      fetch('/api/leads').catch(() => null),
    ]);
    if (bRes && bRes.ok) {
      const bData = await bRes.json();
      state.discoveryBatches = bData.batches || [];
      if (state.discoveryBatches.length) {
        syncDiscoveryBatchLinks(state.discoveryBatches[0].batch_id);
      }
      renderDiscBatches();
    }
    if (lRes && lRes.ok) {
      const lData = await lRes.json();
      state.discoveredLeads = lData.leads || [];
      renderDiscLeads();
    }
  }

  if ($('discSearchInput')) {
    $('discSearchInput').addEventListener('input', renderDiscSources);
    ['discChannelFilter', 'discCityFilter', 'discTierFilter', 'discGenreFilter'].forEach((id) => {
      $(id).addEventListener('change', renderDiscSources);
    });
    $('discSelectQuickBtn').addEventListener('click', () => {
      state.selectedSourceIds.clear();
      state.sources
        .filter((s) => s.status === 'active' && s.location && s.location.city === 'New York')
        .slice(0, 3)
        .forEach((s) => state.selectedSourceIds.add(s.source_id));
      $('discAgentCountInput').value = Math.max(1, state.selectedSourceIds.size);
      renderDiscSources();
    });
    $('discSelectFilteredBtn').addEventListener('click', () => {
      state.filteredSources.forEach((s) => state.selectedSourceIds.add(s.source_id));
      if (state.selectedSourceIds.size > 0) {
        $('discAgentCountInput').value = Math.min(state.selectedSourceIds.size, 100);
      }
      renderDiscSources();
    });
    $('discClearSelBtn').addEventListener('click', () => {
      state.selectedSourceIds.clear();
      renderDiscSources();
    });
    $('discToggleExpandBtn').addEventListener('click', () => {
      state.sourcesExpanded = !state.sourcesExpanded;
      $('discSourceGrid').classList.toggle('expanded', state.sourcesExpanded);
      $('discToggleExpandBtn').textContent = state.sourcesExpanded ? 'Collapse List' : 'Expand Full List';
    });
    $('discRefreshDataBtn').addEventListener('click', refreshDiscoveryData);

    const syncDiscUncUi = () => {
      const unc = $('discUnconstrainedToggle') && $('discUnconstrainedToggle').checked;
      if ($('discLeadsPerAgentInput')) {
        $('discLeadsPerAgentInput').disabled = Boolean(unc);
        $('discLeadsPerAgentInput').style.opacity = unc ? '0.45' : '1';
      }
      const banner = $('discFleetScaleBanner');
      if (banner && state.selectedSourceIds.size > 0) {
        const scouts = Math.max(1, Math.min(Number($('discAgentCountInput').value || 1), 100));
        const srcCount = state.selectedSourceIds.size;
        const est = srcCount * 4;
        const topD = Math.min(30, est);
        banner.innerHTML = unc
          ? `<span><strong>Option A Smart Funnel:</strong> <strong>${scouts}</strong> Scouts across <strong>${srcCount}</strong> sources (No Cap) → <strong>~${est}</strong> Investigated (100% kept) → All <strong>~${est}</strong> Scored by <code>gemini-decision-1</code> (0 tok) → <strong>Top ${topD}</strong> Full Pros/Cons Debates</span>`
          : `<span><strong>Fleet Math:</strong> ${scouts} Scouts × ${$('discLeadsPerAgentInput').value} Leads = ${scouts * Number($('discLeadsPerAgentInput').value || 2)} Candidates</span>`;
        banner.classList.remove('hidden');
      }
    };
    if ($('discUnconstrainedToggle')) $('discUnconstrainedToggle').addEventListener('change', syncDiscUncUi);
    $('discAgentCountInput').addEventListener('input', syncDiscUncUi);

    if ($('discPresetIdolBtn')) {
      $('discPresetIdolBtn').addEventListener('click', () => {
        state.selectedSourceIds.clear();
        state.sources.filter((s) => s.status !== 'inactive').forEach((s) => state.selectedSourceIds.add(s.source_id));
        $('discBriefInput').value = 'American Idol Nationwide Search: scour grassroots open mics, public radio live rooms, and indie venue calendars across all US & global music cities for unsigned breakout vocalists with undeniable live single-take command.';
        if ($('discLiveToggle')) $('discLiveToggle').checked = true;
        if ($('discUnconstrainedToggle')) $('discUnconstrainedToggle').checked = true;
        if ($('discResetPrevToggle')) $('discResetPrevToggle').checked = true;
        const isLive = $('discLiveToggle') && $('discLiveToggle').checked;
        $('discAgentCountInput').value = isLive
          ? Math.min(16, Math.max(12, Math.ceil(state.selectedSourceIds.size / 3)))
          : Math.max(1, state.selectedSourceIds.size);
        renderDiscSources();
        syncDiscUncUi();
        setBanner(`Loaded ★ American Idol · Uncapped Nationwide Search (${state.selectedSourceIds.size} sources · No Cap).`, 'info');
      });
    }

    if ($('discPresetNycBtn')) {
      $('discPresetNycBtn').addEventListener('click', () => {
        state.selectedSourceIds.clear();
        const pref = ['yt_sofar_sounds', 'nyc_babys_all_right', 'nyc_rockwood_music_hall', 'bc_brooklyn_soul_rnb', 'nyc_pianos_showroom', 'nyc_petes_candy_store'];
        pref.forEach((id) => {
          if (state.sources.some((s) => s.source_id === id)) state.selectedSourceIds.add(id);
        });
        if (state.selectedSourceIds.size < 6) {
          state.sources.filter((s) => s.status !== 'inactive' && s.location && ['New York', 'Jersey City'].includes(s.location.city)).slice(0, 6)
            .forEach((s) => state.selectedSourceIds.add(s.source_id));
        }
        $('discBriefInput').value = 'NYC Light Mode (Uncapped): search grassroots Brooklyn and Manhattan live rooms, Sofar sessions, and Bandcamp arrivals for every distinct unsigned solo vocalist.';
        if ($('discLiveToggle')) $('discLiveToggle').checked = true;
        if ($('discUnconstrainedToggle')) $('discUnconstrainedToggle').checked = true;
        if ($('discResetPrevToggle')) $('discResetPrevToggle').checked = true;
        $('discAgentCountInput').value = 3;
        renderDiscSources();
        syncDiscUncUi();
        setBanner(`Loaded 🗽 NYC Light Mode (${state.selectedSourceIds.size} NYC sources across 3 live web scouts · No Cap).`, 'info');
      });
    }

    let discStreamTimer = null;
    let discProceedNow = false;
    const stopDiscStream = () => { if (discStreamTimer) { clearInterval(discStreamTimer); discStreamTimer = null; } };
    if ($('discProceedPartialBtn')) {
      $('discProceedPartialBtn').addEventListener('click', () => { discProceedNow = true; });
    }

    const pollDiscBatchOnce = async (batchId, startMs, allowProceed) => {
      const bRes = await fetch(`/api/discovery/batches?batch_id=${encodeURIComponent(batchId)}&refresh=1`).catch(() => null);
      if (!bRes || !bRes.ok) return null;
      const bData = await bRes.json();
      const workers = bData.workers || [];
      const term = new Set(['completed', 'failed', 'cancelled', 'incomplete', 'budget_exceeded', 'error']);
      const done = workers.filter((w) => term.has(String(w.status || ''))).length;
      const totalLeads = workers.reduce((acc, w) => acc + Number(w.lead_count || 0), 0);
      const elapsed = Math.max(1, Math.round((Date.now() - startMs) / 1000));
      if ($('discLiveStreamBar')) $('discLiveStreamBar').classList.remove('hidden');
      if ($('discLiveStreamTitle')) {
        $('discLiveStreamTitle').textContent = `🌐 Live Web Search · ${done}/${workers.length} Scouts Finished · ${totalLeads} Lead(s) Streamed · ${elapsed}s`;
      }
      if ($('discProceedPartialBtn')) {
        $('discProceedPartialBtn').classList.toggle('hidden', !(allowProceed && done < workers.length && totalLeads > 0));
      }
      if ($('discLiveStreamWorkers')) {
        $('discLiveStreamWorkers').innerHTML = workers.map((w, i) => {
          const steps = w.steps || [];
          const last = steps.length ? (steps[steps.length - 1].preview || 'Searching live web…') : 'Opening assigned sources…';
          return `<div class="card" style="padding:10px; font-size:12px;">
            <div style="display:flex; justify-content:space-between; gap:6px;"><strong>Scout ${i + 1}</strong><span class="pill">${esc(w.status)} (${w.lead_count || 0})</span></div>
            <div class="muted" style="margin-top:4px;">${esc(String(last).slice(0, 140))}</div>
          </div>`;
        }).join('');
      }
      await refreshDiscoveryData();
      return { allFinished: workers.length > 0 && done >= workers.length, done, total: workers.length, totalLeads };
    };

    $('discSyncToPipelineBtn').addEventListener('click', () => {
      const payload = {
        brief: $('discBriefInput').value.trim(),
        source_ids: Array.from(state.selectedSourceIds),
        agent_count: Number($('discAgentCountInput').value || 1),
        leads_per_agent: Number($('discLeadsPerAgentInput').value || 2),
      };
      selectPhase('1_discovery', payload);
      switchTab('pipeline');
    });

    if ($('discClearOldRunsBtn')) {
      $('discClearOldRunsBtn').addEventListener('click', async () => {
        stopDiscStream();
        const btn = $('discClearOldRunsBtn');
        btn.disabled = true;
        setBanner('Archiving previous runs for a clean workspace…', 'info');
        try {
          const res = await fetch('/api/demo/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
          });
          const payload = await res.json();
          if (!res.ok) throw new Error(payload.error || 'Workspace reset failed');
          if ($('discPostDispatchBar')) $('discPostDispatchBar').classList.add('hidden');
          if ($('discLiveStreamBar')) $('discLiveStreamBar').classList.add('hidden');
          await Promise.all([refreshDiscoveryData(), refreshScreeningPackets()]);
          setBanner('Workspace cleared — ready for a fresh end-to-end run.', 'info');
        } catch (err) {
          setBanner(err.message, 'error');
        } finally {
          btn.disabled = false;
        }
      });
    }

    $('discDispatchBtn').addEventListener('click', async () => {
      if (!state.selectedSourceIds.size) {
        setBanner('Pick at least one source first.', 'error');
        return;
      }
      stopDiscStream();
      const isLive = $('discLiveToggle').checked;
      const isUnc = $('discUnconstrainedToggle') ? $('discUnconstrainedToggle').checked : false;
      setBanner(isLive ? 'Launching live web search sandboxes…' : 'Sending simulated scouts…', 'info');
      $('discDispatchBtn').disabled = true;
      try {
        const res = await fetch('/api/discovery/dispatch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_ids: Array.from(state.selectedSourceIds),
            brief: $('discBriefInput').value,
            agent_count: Math.max(1, Math.min(Number($('discAgentCountInput').value || 1), 100)),
            leads_per_agent: Math.max(1, Math.min(Number($('discLeadsPerAgentInput').value || 2), 25)),
            unconstrained: isUnc,
            live: isLive,
            reset_previous: $('discResetPrevToggle') ? $('discResetPrevToggle').checked : false,
          }),
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Discovery dispatch failed');
        const msg = `Launched ${payload.agent_count} scout(s) in ${formatStatus(payload.mode)} mode.`;
        setBanner(msg, 'info');
        syncDiscoveryBatchLinks(payload.batch_id, msg);
        await refreshDiscoveryData();
        if (payload.mode === 'live') {
          const startMs = Date.now();
          await pollDiscBatchOnce(payload.batch_id, startMs, false);
          discStreamTimer = setInterval(async () => {
            const st = await pollDiscBatchOnce(payload.batch_id, startMs, false);
            if (st && st.allFinished) stopDiscStream();
          }, 2500);
        }
      } catch (err) {
        setBanner(err.message, 'error');
      } finally {
        $('discDispatchBtn').disabled = false;
      }
    });

    if ($('discCascadeBtn')) {
      $('discCascadeBtn').addEventListener('click', async () => {
        if (!state.selectedSourceIds.size) {
          setBanner('Pick at least one source first.', 'error');
          return;
        }
        stopDiscStream();
        discProceedNow = false;
        const scouts = Math.max(1, Math.min(Number($('discAgentCountInput').value || 1), 100));
        const perScout = Math.max(1, Math.min(Number($('discLeadsPerAgentInput').value || 2), 25));
        const isLive = $('discLiveToggle').checked;
        const isUnc = $('discUnconstrainedToggle') ? $('discUnconstrainedToggle').checked : false;
        $('discCascadeBtn').disabled = true;
        $('discDispatchBtn').disabled = true;
        try {
          setBanner(`Step 1/4: Launching ${scouts} ${isLive ? 'Live Web Search' : 'Simulated'} Scouts…`, 'info');
          const startMs = Date.now();
          const dRes = await fetch('/api/discovery/dispatch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              source_ids: Array.from(state.selectedSourceIds),
              brief: $('discBriefInput').value,
              agent_count: scouts,
              leads_per_agent: perScout,
              unconstrained: isUnc,
              live: isLive,
              reset_previous: $('discResetPrevToggle') ? $('discResetPrevToggle').checked : false,
            }),
          });
          const dData = await dRes.json();
          if (!dRes.ok) throw new Error(dData.error || 'Discovery dispatch failed');
          syncDiscoveryBatchLinks(dData.batch_id, 'Cascade running…');
          if (dData.mode === 'live') {
            for (let attempt = 0; attempt < 240; attempt++) {
              if (discProceedNow) break;
              await new Promise((r) => setTimeout(r, 2500));
              if (discProceedNow) break;
              const st = await pollDiscBatchOnce(dData.batch_id, startMs, true);
              if (!st || st.allFinished) break;
            }
            if ($('discProceedPartialBtn')) $('discProceedPartialBtn').classList.add('hidden');
          }
          setBanner('Step 2/4: Investigating 100% of discovered artists…', 'info');
          const iRes = await fetch('/api/investigate/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
          const iData = await iRes.json();
          if (!iRes.ok) throw new Error(iData.error || 'Investigation failed');

          setBanner(`Step 3/4 & 4/4: Running Option A Smart Funnel across ${iData.count || 0} artists…`, 'info');
          const oaRes = await fetch('/api/screening/option-a', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_neon_debates: 30, live_taste: true, live_debates: false }),
          });
          const oaData = await oaRes.json();
          if (!oaRes.ok) throw new Error(oaData.error || 'Option A funnel failed');
          await Promise.all([refreshDiscoveryData(), refreshScreeningPackets()]);
          if ($('discOpenInvestigateBtn')) {
            $('discOpenInvestigateBtn').href = '/screen';
            $('discOpenInvestigateBtn').textContent = `Review All ${oaData.total_investigated} Discovered Artists (Top ${oaData.debated_top_count} Debated First) →`;
          }
          if ($('discPostDispatchBar')) $('discPostDispatchBar').classList.remove('hidden');
          setBanner(`Option A Smart Funnel complete! ${oaData.total_investigated} artists investigated & Taste-scored → Top ${oaData.debated_top_count} Pros/Cons debates ready on /screen.`, 'info');
        } catch (err) {
          setBanner(err.message, 'error');
        } finally {
          $('discCascadeBtn').disabled = false;
          $('discDispatchBtn').disabled = false;
        }
      });
    }
  }

  // =========================================================
  // TAB 1: TALENT REVIEW
  // =========================================================
  function playMoment(embedUrl, watchUrl, label, clipTitle, note, autoplay, artistMoments = []) {
    const ytPlayer = $('ytPlayer');
    if (embedUrl) {
      const sep = embedUrl.includes('?') ? '&' : '?';
      ytPlayer.src = autoplay ? (embedUrl + sep + 'autoplay=1') : embedUrl;
    }
    $('openOnYoutubeLink').href = watchUrl || 'https://www.youtube.com';
    $('playerTimestampBadge').textContent = '▶ ' + (label || 'Moment');
    $('playerClipTitle').textContent = clipTitle || label || 'Selected Clip';
    $('nowPlayingCaption').textContent =
      note || 'If embedded playback is restricted by the label, click "YouTube ↗" to jump straight to this second.';

    const row = $('playerMomentsRow');
    if (artistMoments.length > 0) {
      row.innerHTML = artistMoments
        .map(
          (m, idx) => `
          <button type="button" class="moment-chip ${m.label === label ? 'active' : ''}" data-midx="${idx}">
            ▶ ${esc(m.timestamp)} · ${esc(formatLabel(m.dimension || 'moment'))}
          </button>`
        )
        .join('');
      row.querySelectorAll('.moment-chip').forEach((chip) => {
        chip.addEventListener('click', () => {
          const m = artistMoments[Number(chip.dataset.midx)];
          playMoment(m.embed_url, m.play_url, m.label, m.clip_title, m.musical_choice, true, artistMoments);
        });
      });
    } else {
      row.innerHTML = `<span class="muted" style="font-size:12px;">Click Full Profile on any artist to see all verified moments.</span>`;
    }
  }

  function getArtistMoments(run, leadId, stageName) {
    const clips = (run.clip_evidence || []).filter((c) => c.lead_id === leadId);
    const moments = [];
    clips.forEach((clip) => {
      (clip.observations || []).forEach((obs) => {
        moments.push({
          timestamp: obs.timestamp,
          dimension: obs.dimension,
          musical_choice: obs.musical_choice,
          embed_url: obs.embed_url,
          play_url: obs.play_url,
          clip_title: clip.title || clip.source_url,
          label: `${stageName} @ ${obs.timestamp}`,
        });
      });
    });
    return moments;
  }

  function updatePromoteBar() {
    const bar = $('promoteBar');
    if (!bar) return;
    if (state.selectedLeads.size > 0) {
      bar.classList.remove('hidden');
      $('selectedCountLabel').textContent = `${state.selectedLeads.size} selected`;
    } else {
      bar.classList.add('hidden');
    }
  }

  function openFullProfile(leadId) {
    const run = state.currentRun;
    if (!run) return;
    const lead = (run.artist_leads || []).find((l) => l.lead_id === leadId);
    if (!lead) return;
    const clips = (run.clip_evidence || []).filter((c) => c.lead_id === leadId);
    const assess = (run.assessments || []).find((a) => a.lead_id === leadId) || {};
    const moments = getArtistMoments(run, leadId, lead.stage_name);

    $('profileDrawerName').textContent = lead.stage_name;
    const questionsHtml = (assess.open_questions || []).map((q) => `<li>${esc(q)}</li>`).join('');
    const clipsHtml = clips
      .map((clip) => {
        const obsHtml = (clip.observations || [])
          .map(
            (obs) => `
          <div class="output-card" style="margin-top:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <button type="button" class="moment-chip profile-play-btn"
                data-embed="${esc(obs.embed_url)}"
                data-watch="${esc(obs.play_url)}"
                data-label="${esc(lead.stage_name + ' @ ' + obs.timestamp)}"
                data-title="${esc(clip.title || clip.source_url)}"
                data-note="${esc(obs.musical_choice)}">
                ▶ @ ${esc(obs.timestamp)} · ${esc(formatLabel(obs.dimension))}
              </button>
              <a href="${esc(obs.play_url)}" target="_blank" rel="noopener noreferrer" style="font-size:11.5px;">YouTube ↗</a>
            </div>
            <div style="margin-top:6px;">${esc(obs.musical_choice)}</div>
          </div>`
          )
          .join('');
        return `
          <div class="card" style="padding:12px;">
            <div style="display:flex; justify-content:space-between; gap:8px; align-items:center;">
              <strong style="font-size:13px;">${esc(clip.title || clip.source_url)}</strong>
              <span class="pill">${esc(formatLabel(clip.recording_context))}</span>
            </div>
            <div class="muted" style="font-size:12px; margin-top:2px;">${esc(clip.recording_context_notes || '')}</div>
            ${obsHtml}
          </div>`;
      })
      .join('');

    $('profileDrawerBody').innerHTML = `
      <div style="display:flex; gap:6px; flex-wrap:wrap;">
        <span class="pill ${lead.attribution_status === 'uncertain' ? 'warn' : 'ok'}">
          ${lead.attribution_status === 'uncertain' ? '⚠ Uncertain Attribution' : '✓ Verified Performer'}
        </span>
        <span class="pill ${assess.single_clip_flag ? 'warn' : 'ok'}">
          ${assess.single_clip_flag ? '⚠ 1 Clip Only' : clips.length + ' Clips'}
        </span>
      </div>
      <div class="output-card">
        <div class="eyebrow" style="margin-bottom:4px;">Assessment</div>
        <div>${esc(assess.fit_rationale || lead.attribution_notes || 'No summary yet.')}</div>
      </div>
      ${questionsHtml ? `<div><div class="eyebrow" style="margin-bottom:4px;">Open Questions</div><ul style="margin:0; padding-left:18px; font-size:12.5px;" class="muted">${questionsHtml}</ul></div>` : ''}
      <div>
        <div class="eyebrow" style="margin-bottom:8px;">Verified Clips &amp; Moments (${clips.length})</div>
        <div style="display:flex; flex-direction:column; gap:10px;">${clipsHtml || '<div class="muted">No clips recorded.</div>'}</div>
      </div>
      <button type="button" class="btn btn-primary" id="drawerInvestigateBtn">Send to Phase 2 Investigation →</button>
    `;

    $('profileDrawerBody').querySelectorAll('.profile-play-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        playMoment(btn.dataset.embed, btn.dataset.watch, btn.dataset.label, btn.dataset.title, btn.dataset.note, true, moments);
        closeDrawers();
      });
    });
    const invBtn = $('drawerInvestigateBtn');
    if (invBtn) {
      invBtn.addEventListener('click', () => {
        promoteLeadToPhase2(lead, clips);
        closeDrawers();
      });
    }
    $('profileDrawer').classList.remove('hidden');
  }

  function promoteLeadToPhase2(lead, clips) {
    const handoff = {
      lead_id: lead.lead_id,
      stage_name: lead.stage_name,
      attribution_status: lead.attribution_status || 'verified',
      seed_source_url: (clips && clips[0] && clips[0].source_url) || '',
      source_channel: 'youtube_session',
    };
    selectPhase('2a_identity', handoff);
    switchTab('pipeline');
  }

  // Subtabs in Tab 1 (Screened & Elevated)
  function selectSubtab(target, updateUrl = true) {
    state.activeSubtab = target || 'screened';
    document.querySelectorAll('[data-subtab]').forEach((b) => b.classList.toggle('active', b.dataset.subtab === state.activeSubtab));
    if ($('screenedLeadsContainer')) {
      $('screenedLeadsContainer').classList.toggle('hidden', state.activeSubtab !== 'screened');
    }
    if (updateUrl && state.activeTab === 'review') {
      syncUrlState('review');
    }
  }

  document.querySelectorAll('[data-subtab]').forEach((btn) => {
    btn.addEventListener('click', () => selectSubtab(btn.dataset.subtab));
  });

  function extractYtIdFromUrl(url) {
    if (!url) return '';
    const m = String(url).match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : '';
  }

  function findScreeningPacket(leadId, stageName) {
    const packets = state.screeningPackets || [];
    if (leadId) {
      const byId = packets.find((p) => p.lead_id === leadId || (p.dossier_snapshot && p.dossier_snapshot.lead_id === leadId));
      if (byId) return byId;
    }
    if (stageName) {
      const low = String(stageName).toLowerCase();
      return packets.find((p) => {
        const ds = p.dossier_snapshot || {};
        const name = p.stage_name || (ds.identity_and_contact && ds.identity_and_contact.stage_name) || '';
        return name.toLowerCase() === low;
      }) || null;
    }
    return null;
  }

  function buildProducerHandoffFromPacket(pkt, fallbackLeadId = '', fallbackStageName = 'Artist') {
    const ds = (pkt && pkt.dossier_snapshot) || {};
    const idObj = ds.identity_and_contact || {};
    const judge = (pkt && pkt.judge_decision) || {};
    const human = (pkt && pkt.human_review) || null;
    const verdict = String((human && (human.human_verdict || human.verdict)) || judge.verdict || 'ELEVATE').toUpperCase();
    const payload = {
      lead_id: (pkt && pkt.lead_id) || ds.lead_id || fallbackLeadId || '',
      stage_name: (pkt && pkt.stage_name) || idObj.stage_name || fallbackStageName || 'Artist',
      screening_verdict: verdict,
      showcase: 'First Listen NYC',
      slot_minutes: 20,
      fee_cap_usd: 500,
    };
    if (pkt && pkt.advocate_case) payload.advocate_case = pkt.advocate_case;
    if (pkt && pkt.skeptic_case) payload.skeptic_case = pkt.skeptic_case;
    if (pkt && pkt.judge_decision) payload.judge_decision = pkt.judge_decision;
    if (human) payload.human_review = human;
    return payload;
  }

  async function refreshScreeningPackets(focusLeadId = '') {
    try {
      const screenRes = await fetch('/api/screening/packets');
      if (screenRes.ok) {
        const scData = await screenRes.json();
        state.screeningPackets = scData.packets || [];
        renderScreenedPackets(focusLeadId);
      }
    } catch (e) {
      // Ignore refresh error
    }
  }

  function renderScreenedPackets(focusLeadId = '') {
    const container = $('screenedLeadsContainer');
    const btn = $('subtabScreenedBtn');
    const packets = state.screeningPackets || [];
    const rank = { ELEVATE: 0, WATCH: 1, PASS: 2 };
    const sorted = packets.slice().sort((a, b) => {
      const va = String((a.human_review && a.human_review.human_verdict) || (a.judge_decision && a.judge_decision.verdict) || 'WATCH').toUpperCase();
      const vb = String((b.human_review && b.human_review.human_verdict) || (b.judge_decision && b.judge_decision.verdict) || 'WATCH').toUpperCase();
      return (rank[va] ?? 9) - (rank[vb] ?? 9);
    });
    const elevatedCount = sorted.filter((p) => {
      const v = String((p.human_review && p.human_review.human_verdict) || (p.judge_decision && p.judge_decision.verdict) || '').toUpperCase();
      return v === 'ELEVATE';
    }).length;
    if (btn) {
      btn.textContent = `Screened & Elevated (${elevatedCount || sorted.length})`;
    }
    if ($('recordCountBadge')) {
      $('recordCountBadge').textContent = `${sorted.length} screened · ${elevatedCount} elevated`;
    }
    if (!container) return;
    if (!sorted.length) {
      container.innerHTML = `
        <div class="card artist-card">
          <div class="muted" style="font-size:13px;">No screened artists yet. Run Screening from <a href="/investigate">Investigate</a> or <a href="/screen">Screening</a> to see elevated artists here.</div>
        </div>`;
      return;
    }
    container.innerHTML = sorted.map((pkt, idx) => {
      const ds = pkt.dossier_snapshot || {};
      const idObj = ds.identity_and_contact || {};
      const stageName = pkt.stage_name || idObj.stage_name || 'Unnamed Artist';
      const leadId = pkt.lead_id || ds.lead_id || '';
      const judge = pkt.judge_decision || {};
      const human = pkt.human_review || null;
      const verdict = String((human && human.human_verdict) || judge.verdict || 'WATCH').toUpperCase();
      const verdictCls = verdict === 'ELEVATE' ? 'ok' : (verdict === 'PASS' ? 'warn' : 'accent');
      const score = judge.total_score != null ? `${Number(judge.total_score).toFixed(1)} / 10` : '—';
      const rationale = (human && human.reason) || judge.rationale || judge.summary || 'Screened candidate.';
      const media = (ds.source_and_media_queue && ds.source_and_media_queue.media_links) || [];
      const firstUrl = (media[0] && (typeof media[0] === 'string' ? media[0] : media[0].url)) || (ds.source_and_media_queue && ds.source_and_media_queue.seed_source_url) || '';
      const ytId = extractYtIdFromUrl(firstUrl);
      const isFocused = Boolean(focusLeadId && leadId === focusLeadId);
      const city = idObj.home_city || '';
      const srcChannel = (ds.source_and_media_queue && ds.source_and_media_queue.source_channel)
        ? formatLabel(ds.source_and_media_queue.source_channel)
        : '';
      const subline = [city, srcChannel].filter(Boolean).join(' · ') || 'Screened Candidate';
      return `
        <article class="card artist-card" data-lead-id="${esc(leadId)}" style="${isFocused ? 'border-color: var(--accent); box-shadow: 0 0 0 2px rgba(217,119,6,0.22);' : ''}">
          <div class="artist-card-top">
            <div>
              <h3 class="artist-name">${esc(stageName)}</h3>
              <div class="badges">
                <span class="pill ${verdictCls}">${esc(formatStatus(verdict))}</span>
                <span class="pill">${esc(score)}</span>
                ${human ? '<span class="pill ok">Human Verified</span>' : '<span class="pill">Judge Verdict</span>'}
              </div>
            </div>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              ${ytId ? `<button type="button" class="btn screened-play-btn" data-yt="${esc(ytId)}" data-url="${esc(firstUrl)}" data-name="${esc(stageName)}">▶ Play Clip</button>` : ''}
              <a class="btn" href="/screen?lead=${encodeURIComponent(leadId)}">Screening Deck ↗</a>
            </div>
          </div>
          <p class="artist-fit">${esc(rationale)}</p>
          <div class="artist-footer">
            <div class="artist-next">${esc(subline)}</div>
            <button type="button" class="btn btn-primary screened-producer-btn" data-sidx="${idx}">Draft Callback (Phase 4) →</button>
          </div>
        </article>`;
    }).join('');

    container.querySelectorAll('.screened-play-btn').forEach((playBtn) => {
      playBtn.addEventListener('click', () => {
        const yt = playBtn.dataset.yt;
        playMoment(
          `https://www.youtube.com/embed/${encodeURIComponent(yt)}`,
          playBtn.dataset.url,
          `${playBtn.dataset.name} · Screened Clip`,
          playBtn.dataset.name,
          'Loaded from Stage 3 Screening.',
          true,
          []
        );
      });
    });

    container.querySelectorAll('.screened-producer-btn').forEach((prodBtn) => {
      prodBtn.addEventListener('click', () => {
        const pkt = sorted[Number(prodBtn.dataset.sidx)];
        if (!pkt) return;
        selectPhase('4_producer', buildProducerHandoffFromPacket(pkt));
        switchTab('pipeline');
      });
    });

    if (focusLeadId) {
      const focusedCard = Array.from(container.querySelectorAll('[data-lead-id]')).find((c) => c.dataset.leadId === focusLeadId);
      if (focusedCard) {
        focusedCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        const playBtn = focusedCard.querySelector('.screened-play-btn');
        if (playBtn) {
          playMoment(
            `https://www.youtube.com/embed/${encodeURIComponent(playBtn.dataset.yt)}`,
            playBtn.dataset.url,
            `${playBtn.dataset.name} · Screened Clip`,
            playBtn.dataset.name,
            'Loaded from Stage 3 Screening.',
            false,
            []
          );
        }
      }
    } else if ($('ytPlayer') && !$('ytPlayer').getAttribute('src')) {
      const firstPlayBtn = container.querySelector('.screened-play-btn');
      if (firstPlayBtn) {
        playMoment(
          `https://www.youtube.com/embed/${encodeURIComponent(firstPlayBtn.dataset.yt)}`,
          firstPlayBtn.dataset.url,
          `${firstPlayBtn.dataset.name} · Screened Clip`,
          firstPlayBtn.dataset.name,
          'Loaded from Stage 3 Screening.',
          false,
          []
        );
      }
    }
  }

  const promoteBtn = $('promoteToPhase2Btn');
  if (promoteBtn) {
    promoteBtn.addEventListener('click', () => {
      if (!state.currentRun || state.selectedLeads.size === 0) return;
      const firstId = Array.from(state.selectedLeads)[0];
      const lead = (state.currentRun.artist_leads || []).find((l) => l.lead_id === firstId);
      const clips = (state.currentRun.clip_evidence || []).filter((c) => c.lead_id === firstId);
      if (lead) promoteLeadToPhase2(lead, clips);
    });
  }

  // =========================================================
  // TAB 2: PIPELINE RUNNER
  // =========================================================
  function renderPipelineStepper() {
    const stepper = $('phaseStepper');
    stepper.innerHTML = state.phases
      .map((p) => {
        const isActive = p.id === state.activePhaseId;
        const st = state.phaseStatus[p.id] || 'idle';
        const dotClass = st === 'done' ? 'ok' : st === 'failed' ? 'warn' : isActive ? 'accent' : '';
        const stLabel = st === 'done' ? 'Completed' : st === 'failed' ? 'Failed' : isActive ? 'Selected' : 'Pending';
        return `
          <button type="button" class="phase-tile ${isActive ? 'active' : ''}" data-phase-id="${esc(p.id)}">
            <div class="phase-tile-top">
              <span>PHASE ${esc(p.code)}</span>
              <span class="dot ${dotClass}"></span>
            </div>
            <div class="phase-tile-name">${esc(p.name)}</div>
            <div class="phase-tile-state">${esc(stLabel)}</div>
          </button>`;
      })
      .join('');

    stepper.querySelectorAll('.phase-tile').forEach((tile) => {
      tile.addEventListener('click', () => selectPhase(tile.dataset.phaseId));
    });

    const cur = state.phases.find((p) => p.id === state.activePhaseId) || state.phases[0];
    if (!cur) return;
    $('phaseTitle').textContent = `Phase ${cur.code} — ${cur.name}`;
    $('phaseDomainBadge').textContent = cur.domain;
    $('phaseDesc').textContent = cur.description;
    $('phaseInputHint').textContent = cur.input_hint;
  }

  function resetPhaseOutputPanel() {
    $('phaseRunMeta').textContent = 'Not run yet';
    $('phaseChecks').innerHTML = '';
    $('phaseOutputCards').innerHTML = '<div class="muted" style="font-size:12.5px;">Run this phase to view scout outputs, checks, and the next handoff.</div>';
    $('phaseRawJson').textContent = '{}';
    const batchLinks = $('phaseBatchLinks');
    if (batchLinks) {
      batchLinks.innerHTML = '';
      batchLinks.classList.add('hidden');
    }
  }

  function selectPhase(phaseId, customInput = null) {
    const validPhase = state.phases.some((p) => p.id === phaseId) ? phaseId : (state.phases[0] ? state.phases[0].id : '1_discovery');
    state.activePhaseId = validPhase;
    renderPipelineStepper();
    const cur = state.phases.find((p) => p.id === validPhase);
    if (cur) {
      $('phaseInputJson').value = JSON.stringify(customInput || cur.default_input, null, 2);
    }
    if ($('phaseSourceBridgeBar')) {
      $('phaseSourceBridgeBar').classList.toggle('hidden', validPhase !== '1_discovery');
    }
    if ($('phaseLeadBridgeBar')) {
      const showLeads = ['2a_identity', '2b_investigators', '2c_dossier', '3_screening', '4_producer'].includes(validPhase);
      $('phaseLeadBridgeBar').classList.toggle('hidden', !showLeads);
    }
    // Explicitly sync output panel to this phase's latest checkpoint or clean empty state
    const latestForPhase = (state.phaseRuns || []).find((r) => r.phase_id === validPhase);
    if (latestForPhase && !customInput) {
      renderPhaseResult(latestForPhase);
    } else {
      resetPhaseOutputPanel();
    }
    if (state.activeTab === 'pipeline') {
      syncUrlState('pipeline');
    }
  }

  if ($('phaseOpenDiscoveryBtn')) {
    $('phaseOpenDiscoveryBtn').addEventListener('click', () => switchTab('discovery'));
  }
  if ($('phaseLeadSelect')) {
    $('phaseLeadSelect').addEventListener('change', () => {
      const rawIdx = $('phaseLeadSelect').value;
      if (rawIdx === '') return;
      const lead = state.discoveredLeads[Number(rawIdx)];
      if (!lead) return;
      let payload;
      if (state.activePhaseId === '4_producer') {
        const pkt = findScreeningPacket(lead.lead_id, lead.stage_name);
        payload = buildProducerHandoffFromPacket(pkt, lead.lead_id, lead.stage_name);
      } else if (state.activePhaseId === '3_screening') {
        payload = { lead_id: lead.lead_id || '', stage_name: lead.stage_name || lead.title || 'Unknown Artist' };
      } else {
        payload = leadToPhase2Handoff(lead);
      }
      $('phaseInputJson').value = JSON.stringify(payload, null, 2);
    });
  }

  function renderPhaseResult(result) {
    const modeLabel = formatStatus(result.mode || 'test');
    const statusLabel = result.passed ? 'Passed' : 'Needs Review';
    const durLabel = result.duration_ms >= 1000 ? `${(result.duration_ms / 1000).toFixed(1)}s` : `${result.duration_ms} ms`;
    $('phaseRunMeta').textContent = `${modeLabel} · ${statusLabel} · ${durLabel}`;
    const batchLinks = $('phaseBatchLinks');
    if (batchLinks) {
      const batchId = result.output && result.output.batch_id;
      const dossierLeadId = result.phase_id === '2c_dossier' && result.output && result.output.lead_id;
      const screenLeadId = result.phase_id === '3_screening' && result.output && result.output.lead_id;
      const producerLeadId = result.phase_id === '4_producer' && result.output && (result.output.lead_id || (result.input && result.input.lead_id));
      if (batchId) {
        const q = `?batch=${encodeURIComponent(batchId)}`;
        batchLinks.innerHTML = `<a class="btn" style="padding:3px 8px; font-size:11px;" href="/field-news${q}">Field News →</a><a class="btn" style="padding:3px 8px; font-size:11px;" href="/reports${q}">Reports →</a><a class="btn btn-primary" style="padding:3px 8px; font-size:11px;" href="/investigate?autorun=1">Investigate →</a>`;
        batchLinks.classList.remove('hidden');
      } else if (screenLeadId) {
        const q = `?lead=${encodeURIComponent(screenLeadId)}`;
        batchLinks.innerHTML = `<a class="btn btn-primary" style="padding:3px 8px; font-size:11px;" href="/screen${q}">Open in Screening Deck →</a><a class="btn" style="padding:3px 8px; font-size:11px;" href="/?tab=review&amp;subtab=screened&amp;lead=${encodeURIComponent(screenLeadId)}">Talent Review →</a>`;
        batchLinks.classList.remove('hidden');
      } else if (producerLeadId) {
        batchLinks.innerHTML = `<a class="btn btn-primary" style="padding:3px 8px; font-size:11px;" href="/?tab=review&amp;subtab=screened&amp;lead=${encodeURIComponent(producerLeadId)}">Open in Talent Review →</a><a class="btn" style="padding:3px 8px; font-size:11px;" href="/screen?lead=${encodeURIComponent(producerLeadId)}">Screening Deck →</a>`;
        batchLinks.classList.remove('hidden');
      } else if (dossierLeadId) {
        const q = `?lead=${encodeURIComponent(dossierLeadId)}`;
        batchLinks.innerHTML = `<button id="phaseSendToScreeningBtn" type="button" class="btn btn-primary" style="padding:3px 8px; font-size:11px;">Run Screening →</button><a class="btn" style="padding:3px 8px; font-size:11px;" href="/investigate${q}">Investigator Desk →</a>`;
        batchLinks.classList.remove('hidden');
        const scrBtn = $('phaseSendToScreeningBtn');
        if (scrBtn) {
          scrBtn.addEventListener('click', async () => {
            scrBtn.disabled = true;
            scrBtn.textContent = 'Running Screening…';
            try {
              const sRes = await fetch('/api/screening/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_id: dossierLeadId, dossier: result.output.profile || null, live: false }),
              });
              if (sRes.ok) {
                window.location.href = `/screen${q}`;
                return;
              }
              setBanner('Screening run failed.', 'error');
            } catch (err) {
              setBanner('Network error running screening: ' + err.message, 'error');
            } finally {
              scrBtn.disabled = false;
              scrBtn.textContent = 'Run Screening →';
            }
          });
        }
      } else {
        batchLinks.innerHTML = '';
        batchLinks.classList.add('hidden');
      }
    }
    $('phaseChecks').innerHTML = (result.checks || [])
      .map(
        (c) => `<span class="pill ${c.passed ? 'ok' : 'warn'}">${c.passed ? '✓' : '✕'} ${esc(c.label || c.name)}</span>`
      )
      .join('');

    const grid = $('phaseOutputCards');
    const cards = result.cards || [];
    grid.className = cards.length >= 3 ? 'output-grid cols-3' : 'output-grid';
    grid.innerHTML = cards
      .map(
        (c) => `
        <div class="output-card">
          <div class="output-card-head">
            <span>${esc(formatAgentName(c.agent))}</span>
            <span class="pill ${c.status === 'failed' ? 'warn' : 'ok'}">${esc(formatStatus(c.status))}</span>
          </div>
          <div>${esc(c.summary)}</div>
        </div>`
      )
      .join('');
    $('phaseRawJson').textContent = JSON.stringify(result.output || {}, null, 2);
  }

  function renderCheckpoints() {
    $('checkpointCountBadge').textContent = `${state.phaseRuns.length} saved`;
    const list = $('checkpointList');
    if (state.phaseRuns.length === 0) {
      list.innerHTML = `<div class="muted" style="font-size:12px;">Run any phase to save a checkpoint here.</div>`;
      return;
    }
    list.innerHTML = state.phaseRuns
      .slice(0, 10)
      .map(
        (r, idx) => `
        <div class="eval-row">
          <div>
            <span class="pill ${r.passed ? 'ok' : 'warn'}">${r.passed ? 'Passed' : 'Review'}</span>
            <strong style="margin-left:6px;">Phase ${esc(r.phase_code)} · ${esc(r.phase_name)}</strong>
            <span class="muted" style="margin-left:6px;">${esc(formatStatus(r.mode))} · ${esc(r.duration_ms)} ms</span>
          </div>
          <button type="button" class="btn load-ckpt-btn" data-cidx="${idx}">Inspect</button>
        </div>`
      )
      .join('');
    list.querySelectorAll('.load-ckpt-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const rec = state.phaseRuns[Number(btn.dataset.cidx)];
        selectPhase(rec.phase_id, rec.input || {});
        renderPhaseResult(rec);
      });
    });
  }

  async function executePhase(phaseId, advanceNext = false) {
    let parsedInput = {};
    try {
      parsedInput = JSON.parse($('phaseInputJson').value || '{}');
    } catch (err) {
      setBanner('Phase input is not valid JSON: ' + err.message, 'error');
      return;
    }

    const wantLive = state.pipelineMode === 'live';
    const keyOverride = $('apiKeyInput') ? $('apiKeyInput').value.trim() : '';
    const phaseObj = state.phases.find((p) => p.id === phaseId);
    const phaseLabel = phaseObj ? `Phase ${phaseObj.code} — ${phaseObj.name}` : formatLabel(phaseId);
    setBanner(`Running ${phaseLabel} (${wantLive ? 'Live' : 'Test'})…`, 'info');
    $('runThisPhaseBtn').disabled = true;
    $('runNextPhaseBtn').disabled = true;
    try {
      const res = await fetch('/api/phases/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phase_id: phaseId,
          payload: parsedInput,
          live: wantLive,
          run_id: state.currentRun ? state.currentRun.run_id : null,
          api_key: keyOverride || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        state.phaseStatus[phaseId] = 'failed';
        renderPipelineStepper();
        setBanner(data.error || 'Phase execution failed.', 'error');
        return;
      }
      setBanner('', 'info');
      state.phaseStatus[phaseId] = data.passed ? 'done' : 'failed';
      state.phaseRuns.unshift(data);
      renderPipelineStepper();
      renderPhaseResult(data);
      renderCheckpoints();

      // If Phase 1 ran, refresh Discovery batches/leads
      if (phaseId === '1_discovery') {
        await refreshDiscoveryData();
        if (data.output && data.output.batch_id) {
          syncDiscoveryBatchLinks(data.output.batch_id);
        }
      } else if (phaseId === '3_screening') {
        await refreshScreeningPackets();
      }

      if (advanceNext) {
        const idx = state.phases.findIndex((p) => p.id === phaseId);
        if (idx >= 0 && idx < state.phases.length - 1) {
          const nextPhase = state.phases[idx + 1];
          selectPhase(nextPhase.id, (data.next_handoff && Object.keys(data.next_handoff).length) ? data.next_handoff : null);
        }
      }
    } catch (err) {
      setBanner('Network error running phase: ' + err.message, 'error');
    } finally {
      $('runThisPhaseBtn').disabled = false;
      $('runNextPhaseBtn').disabled = false;
    }
  }

  document.querySelectorAll('[data-pmode]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.pipelineMode = btn.dataset.pmode;
      document.querySelectorAll('[data-pmode]').forEach((b) => b.classList.toggle('active', b.dataset.pmode === state.pipelineMode));
    });
  });
  $('loadPhaseFixtureBtn').addEventListener('click', () => selectPhase(state.activePhaseId));
  $('runThisPhaseBtn').addEventListener('click', () => executePhase(state.activePhaseId, false));
  $('runNextPhaseBtn').addEventListener('click', () => executePhase(state.activePhaseId, true));

  // =========================================================
  // TAB 3: AGENT LAB
  // =========================================================
  function renderAgentRoster() {
    const el = $('agentRoster');
    el.innerHTML = state.agents
      .map(
        (a) => `
        <button type="button" class="roster-item ${state.activeAgent && state.activeAgent.package === a.package ? 'active' : ''}" data-pkg="${esc(a.package)}">
          <span>${esc(formatAgentName(a.package))}</span>
        </button>`
      )
      .join('');
    el.querySelectorAll('.roster-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const found = state.agents.find((x) => x.package === btn.dataset.pkg);
        if (found) selectAgent(found);
      });
    });
  }

  function selectAgent(agent) {
    const changed = !state.activeAgent || state.activeAgent.package !== agent.package;
    state.activeAgent = agent;
    renderAgentRoster();
    $('labAgentName').textContent = formatAgentName(agent.package);
    $('labAgentDeployedId').textContent = 'Ready for isolated testing';
    $('labAgentModel').textContent = agent.model ? formatLabel(agent.model.replace(/^gemini-4-/, 'Gemini ')) : 'Standard';
    const hintEl = $('labInputHint');
    if (hintEl) {
      hintEl.textContent = agent.input_hint || 'JSON object or list of inputs';
    }
    const defaultPayload = agent.default_input || {
      lead_id: 'lead_luna_jinna',
      stage_name: 'Luna Jinna',
      seed_source_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    };
    $('labInput').value = JSON.stringify(defaultPayload, null, 2);
    if (changed) {
      state.lastLabResult = null;
      $('labLatency').textContent = '—';
      $('labChecksRow').innerHTML = '';
      $('labOutputRaw').textContent = '{}';
      $('labOutputFormatted').innerHTML =
        '<div class="muted">Run an agent to view its output and rule checks.</div>';
    }
    renderEvalHistory();
  }

  const labResetBtn = $('labResetInputBtn');
  if (labResetBtn) {
    labResetBtn.addEventListener('click', () => {
      if (state.activeAgent) selectAgent(state.activeAgent);
    });
  }

  function renderEvalHistory() {
    const list = $('evalHistoryList');
    const filtered = state.activeAgent
      ? state.evals.filter((e) => e.agent_id === state.activeAgent.package || e.agent_id === state.activeAgent.deployed_id)
      : state.evals;
    if (filtered.length === 0) {
      list.innerHTML = `<div class="muted" style="font-size:12px;">No saved review notes for this agent yet.</div>`;
      return;
    }
    list.innerHTML = filtered
      .slice(0, 8)
      .map(
        (ev) => `
        <div class="eval-row">
          <div>
            <span class="pill ${ev.verdict === 'pass' ? 'ok' : 'warn'}">${esc(formatStatus(ev.verdict))}</span>
            <strong style="margin-left:6px;">${esc(formatAgentName(ev.agent_id))}</strong>
            <span class="muted" style="margin-left:6px;">${esc(ev.note || '')}</span>
          </div>
          <span class="muted" style="font-size:11px;">${esc((ev.created_at || '').slice(11, 19))}</span>
        </div>`
      )
      .join('');
  }

  $('toggleLabRawBtn').addEventListener('click', () => {
    state.labShowRaw = !state.labShowRaw;
    $('labOutputFormatted').classList.toggle('hidden', state.labShowRaw);
    $('labOutputRaw').classList.toggle('hidden', !state.labShowRaw);
    $('toggleLabRawBtn').textContent = state.labShowRaw ? 'Formatted' : 'Raw JSON';
  });

  $('labRunBtn').addEventListener('click', async () => {
    if (!state.activeAgent) return;
    let parsed;
    try {
      parsed = JSON.parse($('labInput').value || '{}');
    } catch (err) {
      setBanner('Agent input is not valid JSON: ' + err.message, 'error');
      return;
    }
    const assignments = Array.isArray(parsed) ? parsed : [parsed];
    const dryRun = $('labDryRunToggle').checked;
    const keyOverride = $('apiKeyInput') ? $('apiKeyInput').value.trim() : '';

    $('labRunBtn').disabled = true;
    setBanner(`Running ${formatAgentName(state.activeAgent.package)} (${dryRun ? 'Dry Run' : 'Live'})…`, 'info');
    const t0 = performance.now();
    try {
      const res = await fetch('/api/fleet/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent: state.activeAgent.deployed_id,
          assignments,
          dry_run: dryRun,
          wait: !dryRun,
          api_key: keyOverride || null,
        }),
      });
      const data = await res.json();
      const elapsed = Math.round(performance.now() - t0);
      if (!res.ok) {
        setBanner(data.error || 'Agent run failed.', 'error');
        return;
      }
      setBanner('', 'info');
      state.lastLabResult = data;
      $('labLatency').textContent = `${elapsed} ms`;
      $('labOutputRaw').textContent = JSON.stringify(data, null, 2);

      // Auto-check via /api/evals (dry evaluation without saving human verdict)
      const worker = (data.results || [{}])[0];
      const evalRes = await fetch('/api/evals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: state.activeAgent.package,
          output: worker.output || data,
          save: false,
        }),
      });
      const evalData = evalRes.ok ? await evalRes.json() : { checks: [] };
      $('labChecksRow').innerHTML = (evalData.checks || [])
        .map((c) => `<span class="pill ${c.passed ? 'ok' : 'warn'}">${c.passed ? '✓' : '✕'} ${esc(c.label)}</span>`)
        .join('');

      $('labOutputFormatted').innerHTML = `
        <div class="output-card-head">
          <span>${esc(formatAgentName(state.activeAgent.package))}</span>
          <span class="pill ok">${esc(formatStatus(data.mode || (dryRun ? 'dry_run' : 'live')))}</span>
        </div>
        <div><strong>Scouts Run:</strong> ${esc((data.results || []).length)}</div>
        <div class="muted" style="margin-top:6px;">${esc(typeof worker.output === 'string' ? worker.output.slice(0, 320) : JSON.stringify(worker).slice(0, 320))}</div>
      `;
    } catch (err) {
      setBanner('Network error running agent: ' + err.message, 'error');
    } finally {
      $('labRunBtn').disabled = false;
    }
  });

  document.querySelectorAll('[data-eval-score]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!state.activeAgent) return;
      const verdict = btn.dataset.evalScore;
      const note = $('evalNoteInput').value.trim();
      const res = await fetch('/api/evals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: state.activeAgent.package,
          verdict,
          note,
          output: state.lastLabResult || {},
          save: true,
        }),
      });
      if (res.ok) {
        const saved = await res.json();
        state.evals.unshift(saved);
        $('evalNoteInput').value = '';
        renderEvalHistory();
      }
    });
  });

  // =========================================================
  // INITIALIZE ALL TABS
  // =========================================================
  async function init() {
    const [statusRes, phasesRes, agentsRes, evalsRes, sourcesRes, screenRes] = await Promise.all([
      fetch('/api/status'),
      fetch('/api/phases'),
      fetch('/api/agents'),
      fetch('/api/evals'),
      fetch('/api/sources'),
      fetch('/api/screening/packets').catch(() => null),
    ]);

    const status = await statusRes.json();
    const keyBadge = $('serverKeyBadge');
    if (status.has_api_key) {
      keyBadge.innerHTML = `<span class="dot ok"></span><span>Live Ready</span>`;
    } else {
      keyBadge.innerHTML = `<span class="dot accent"></span><span>Demo Mode</span>`;
    }

    if (sourcesRes && sourcesRes.ok) {
      const sData = await sourcesRes.json();
      state.sources = sData.sources || [];
      if ($('discChannelFilter')) {
        (sData.channels || []).forEach((c) => $('discChannelFilter').add(new Option(formatLabel(c), c)));
        (sData.cities || []).forEach((c) => $('discCityFilter').add(new Option(c, c)));
        (sData.tiers || []).forEach((t) => $('discTierFilter').add(new Option(formatLabel(t), t)));
        const genres = (sData.genres && sData.genres.length)
          ? sData.genres
          : Array.from(new Set(state.sources.flatMap((s) => Array.isArray(s.genre_tags) ? s.genre_tags : []).filter((g) => g && g !== 'all'))).sort();
        genres.forEach((g) => $('discGenreFilter').add(new Option(g, g)));
        ['yt_sofar_sounds', 'nyc_babys_all_right', 'bc_brooklyn_soul_rnb'].forEach((id) => {
          if (state.sources.some((s) => s.source_id === id)) state.selectedSourceIds.add(id);
        });
        $('discAgentCountInput').value = Math.max(1, state.selectedSourceIds.size);
        renderDiscSources();
      }
    }

    await refreshDiscoveryData();

    if (phasesRes.ok) {
      const pData = await phasesRes.json();
      state.phases = pData.phases || [];
      state.phaseRuns = pData.phase_runs || [];
      selectPhase('1_discovery');
      renderCheckpoints();
    }

    if (agentsRes.ok) {
      const aData = await agentsRes.json();
      state.agents = aData.agents || [];
      if (state.agents.length > 0) selectAgent(state.agents[0]);
    }

    if (evalsRes.ok) {
      const eData = await evalsRes.json();
      state.evals = eData.evals || [];
      renderEvalHistory();
    }

    if (screenRes && screenRes.ok) {
      const scData = await screenRes.json();
      state.screeningPackets = scData.packets || [];
      renderScreenedPackets();
    }

    // Apply URL deep links (?tab=discovery|review|pipeline|lab&phase=...&subtab=...&lead=...&subject=...)
    const params = new URLSearchParams(window.location.search);
    const reqTab = params.get('tab');
    const reqPhase = params.get('phase');
    const reqSubtab = params.get('subtab');
    const reqLead = params.get('lead');
    const reqSubject = params.get('subject');
    if (reqTab === 'review' && reqSubtab) {
      switchTab('review', false);
      selectSubtab(reqSubtab, false);
      if (reqSubtab === 'screened' && reqLead) {
        renderScreenedPackets(reqLead);
      }
    } else if (reqLead || reqSubject) {
      const matched = state.discoveredLeads.find(
        (l) => (reqLead && l.lead_id === reqLead) || (reqSubject && (l.stage_name || '').toLowerCase() === reqSubject.toLowerCase())
      );
      const targetPhase = reqPhase || '2a_identity';
      let handoff;
      if (targetPhase === '4_producer') {
        const pkt = findScreeningPacket(reqLead || (matched && matched.lead_id), reqSubject || (matched && matched.stage_name));
        handoff = buildProducerHandoffFromPacket(
          pkt,
          reqLead || (matched && matched.lead_id) || '',
          reqSubject || (matched && matched.stage_name) || 'Artist'
        );
      } else if (targetPhase === '3_screening') {
        handoff = {
          lead_id: reqLead || (matched && matched.lead_id) || '',
          stage_name: reqSubject || (matched && matched.stage_name) || 'Unknown Artist',
        };
      } else {
        handoff = matched
          ? leadToPhase2Handoff(matched)
          : {
              lead_id: reqLead || '',
              stage_name: reqSubject || 'Unknown Artist',
              attribution_status: 'verified',
              source_channel: 'youtube_session',
            };
      }
      selectPhase(targetPhase, handoff);
      switchTab(reqTab || 'pipeline', false);
    } else if (reqPhase) {
      selectPhase(reqPhase);
      switchTab(reqTab || 'pipeline', false);
    } else if (reqTab) {
      switchTab(reqTab, false);
    }
  }

  init();
})();
