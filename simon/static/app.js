/* Simon Talent Review Studio, Pipeline Runner & Agent Lab */
(() => {
  'use strict';

  const state = {
    currentRun: null,
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

  function formatLabel(val) {
    return String(val || '').replace(/_/g, ' ');
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

  // --- TOP TABS & URL STATE SYNC ---
  const TAB_LABELS = {
    discovery: 'Discovery',
    review: 'Talent Review',
    pipeline: 'Pipeline Stepper',
    lab: 'Agent Lab',
  };

  function syncUrlState(tabName) {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', tabName);
      if (tabName === 'pipeline' && state.activePhaseId) {
        url.searchParams.set('phase', state.activePhaseId);
      } else {
        url.searchParams.delete('phase');
      }
      window.history.replaceState({}, '', url.toString());
    } catch (e) {
      // Ignore history errors in restricted frames
    }
  }

  function switchTab(tabName, updateUrl = true) {
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.add('hidden'));
    const target = $('tab-' + tabName);
    if (target) target.classList.remove('hidden');
    document.querySelectorAll('[data-tab]').forEach((btn) => {
      if (btn.classList.contains('nav-tab')) {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
      }
    });
    if ($('reviewTopbarControls')) {
      $('reviewTopbarControls').classList.toggle('hidden', tabName !== 'review');
    }
    if ($('brandSubLabel')) {
      $('brandSubLabel').textContent = TAB_LABELS[tabName] || 'Studio';
    }
    const moreMenu = $('moreMenu');
    if (moreMenu) moreMenu.removeAttribute('open');
    if (updateUrl) syncUrlState(tabName);
  }
  document.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // --- DRAWERS ---
  function closeDrawers() {
    ['profileDrawer', 'briefDrawer', 'traceDrawer'].forEach((id) => $(id).classList.add('hidden'));
  }
  document.querySelectorAll('[data-close-drawer]').forEach((btn) => {
    btn.addEventListener('click', closeDrawers);
  });
  ['profileDrawer', 'briefDrawer', 'traceDrawer'].forEach((id) => {
    $(id).addEventListener('click', (e) => {
      if (e.target.id === id) closeDrawers();
    });
  });
  $('openBriefBtn').addEventListener('click', () => $('briefDrawer').classList.remove('hidden'));
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
              <span class="pill ${statusCls}">${esc(s.status)}</span>
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
      list.innerHTML = `<div class="muted" style="font-size:12.5px;">No discovery batches dispatched yet. Select sources above and click <strong>Send Discovery Agents</strong>.</div>`;
      return;
    }
    list.innerHTML = state.discoveryBatches.slice(0, 6).map((b) => {
      const workers = b.workers || [];
      const leadSum = workers.reduce((acc, w) => acc + Number(w.lead_count || 0), 0);
      const q = `?batch=${encodeURIComponent(b.batch_id)}`;
      return `
        <div class="lead-row">
          <div class="lead-row-top">
            <div>
              <strong class="mono" style="font-size:12px;">${esc(b.batch_id)}</strong>
              <span class="pill ${b.mode === 'live' ? 'ok' : 'accent'}" style="margin-left:6px;">${esc(b.mode || 'simulated')}</span>
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
      const opts = [`<option value="">Choose a lead from Discovery (${state.discoveredLeads.length})…</option>`];
      state.discoveredLeads.forEach((lead, idx) => {
        opts.push(`<option value="${idx}">${esc(lead.stage_name || lead.lead_id)} (${esc(lead.attribution_status || 'unverified')})</option>`);
      });
      select.innerHTML = opts.join('');
    }

    if (!list) return;
    if (!state.discoveredLeads.length) {
      list.innerHTML = `<div class="muted" style="font-size:12.5px;">No discovered leads stored yet. Run a Discovery batch or Phase 1 to populate this queue.</div>`;
      return;
    }

    list.innerHTML = state.discoveredLeads.slice(0, 16).map((lead, idx) => {
      const seeds = Array.isArray(lead.seed_sources) ? lead.seed_sources : [];
      const firstSeed = seeds[0] || {};
      return `
        <div class="lead-row">
          <div class="lead-row-top">
            <div>
              <strong style="font-size:13.5px;">${esc(lead.stage_name || lead.lead_id)}</strong>
              <span class="pill ${lead.attribution_status === 'verified' ? 'ok' : ''}" style="margin-left:6px;">${esc(lead.attribution_status || 'lead')}</span>
              ${firstSeed.source_channel ? `<span class="pill" style="margin-left:4px;">${esc(formatLabel(firstSeed.source_channel))}</span>` : ''}
            </div>
            <button type="button" class="btn btn-primary disc-send-pipeline-btn" data-lidx="${idx}" style="padding:5px 10px; font-size:11.5px;">
              Investigate in Pipeline →
            </button>
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
        $('discAgentCountInput').value = Math.min(state.selectedSourceIds.size, 10);
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

    $('discDispatchBtn').addEventListener('click', async () => {
      if (!state.selectedSourceIds.size) {
        setBanner('Select at least one source from the Discovery Source Registry first.', 'error');
        return;
      }
      setBanner('Dispatching discovery agents…', 'info');
      $('discDispatchBtn').disabled = true;
      try {
        const res = await fetch('/api/discovery/dispatch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_ids: Array.from(state.selectedSourceIds),
            brief: $('discBriefInput').value,
            agent_count: Number($('discAgentCountInput').value || 1),
            leads_per_agent: Number($('discLeadsPerAgentInput').value || 2),
            live: $('discLiveToggle').checked,
          }),
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Discovery dispatch failed');
        const msg = `Dispatched ${payload.agent_count} scout(s) in ${payload.mode} mode (${payload.batch_id}).`;
        setBanner(msg, 'info');
        syncDiscoveryBatchLinks(payload.batch_id, msg);
        await refreshDiscoveryData();
      } catch (err) {
        setBanner(err.message, 'error');
      } finally {
        $('discDispatchBtn').disabled = false;
      }
    });
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
            ▶ ${esc(m.timestamp)} · ${esc(m.dimension || 'moment')}
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
                ▶ @ ${esc(obs.timestamp)} · ${esc(obs.dimension)}
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
              <span class="pill">${esc(clip.recording_context)}</span>
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
    state.activePhaseId = '2a_identity';
    renderPipelineStepper();
    $('phaseInputJson').value = JSON.stringify(handoff, null, 2);
    switchTab('pipeline');
  }

  function renderRun(run) {
    state.currentRun = run;
    state.selectedLeads.clear();
    updatePromoteBar();

    const briefPrompt = (run.brief && run.brief.prompt) || '';
    $('briefInput').value = briefPrompt;
    $('activeBriefHeading').textContent = briefPrompt ? `“${briefPrompt}”` : 'Active Scouting Run';

    const modeBadge = $('runModeBadge');
    modeBadge.textContent = run.mode === 'live' ? 'LIVE MANAGED AGENTS' : 'VERIFIED YOUTUBE DEMO';
    modeBadge.className = 'pill ' + (run.mode === 'live' ? 'ok' : 'accent');

    const leads = run.artist_leads || [];
    const clips = run.clip_evidence || [];
    const shortlist = run.shortlist || [];
    $('recordCountBadge').textContent = `${leads.length} artists · ${clips.length} clips`;
    $('subtabShortlistBtn').textContent = `Shortlist (${shortlist.length})`;
    $('subtabAllBtn').textContent = `All Artists (${leads.length})`;

    // Cue #1 shortlist artist without autoplay on initial load
    if (shortlist.length > 0) {
      const first = shortlist[0];
      const lead = leads.find((l) => l.stage_name === first.stage_name) || {};
      const moments = lead.lead_id ? getArtistMoments(run, lead.lead_id, first.stage_name) : [];
      playMoment(
        first.play_first_embed_url,
        first.play_first_url,
        `${first.stage_name} @ ${first.play_first_timestamp}`,
        first.play_first_clip_title,
        first.why_it_fits,
        false,
        moments
      );
    }

    // Render Shortlist Cards
    const shortlistEl = $('shortlistContainer');
    shortlistEl.innerHTML = shortlist
      .map((item) => {
        const lead = leads.find((l) => l.stage_name === item.stage_name) || { lead_id: item.lead_id || '' };
        const badges = [];
        badges.push(`<span class="pill ${item.recording_context === 'live' ? 'ok' : ''}">${esc(item.recording_context)}</span>`);
        badges.push(
          item.single_clip_flag
            ? `<span class="pill warn">⚠ 1 Clip Only</span>`
            : `<span class="pill ok">Multi-Clip</span>`
        );
        if (item.uncertain_attribution_flag) {
          badges.push(`<span class="pill warn">⚠ Uncertain Attribution</span>`);
        }
        return `
          <article class="card artist-card">
            <div class="artist-card-top">
              <div>
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                  <span class="pill accent">#${esc(item.rank)}</span>
                  <h3 class="artist-name">${esc(item.stage_name)}</h3>
                </div>
                <div class="badges">${badges.join('')}</div>
              </div>
              <button type="button" class="btn open-profile-btn" data-lead-id="${esc(lead.lead_id)}">Full Profile →</button>
            </div>
            <p class="artist-fit">${esc(item.why_it_fits)}</p>
            <div class="artist-footer">
              <button type="button" class="btn btn-primary play-first-btn"
                data-lead-id="${esc(lead.lead_id)}"
                data-name="${esc(item.stage_name)}"
                data-embed="${esc(item.play_first_embed_url)}"
                data-watch="${esc(item.play_first_url)}"
                data-label="${esc(item.stage_name + ' @ ' + item.play_first_timestamp)}"
                data-title="${esc(item.play_first_clip_title)}"
                data-note="${esc(item.why_it_fits)}">
                ▶ Play First @ ${esc(item.play_first_timestamp)}
              </button>
              <div class="artist-next"><strong>Next:</strong> ${esc(item.what_to_hear_next)}</div>
            </div>
          </article>`;
      })
      .join('');

    // Render All Leads list
    const assessByLead = {};
    (run.assessments || []).forEach((a) => { assessByLead[a.lead_id] = a; });
    const clipsByLead = {};
    clips.forEach((c) => { (clipsByLead[c.lead_id] = clipsByLead[c.lead_id] || []).push(c); });

    const allEl = $('allLeadsContainer');
    allEl.innerHTML = leads
      .map((lead) => {
        const assess = assessByLead[lead.lead_id] || {};
        const leadClips = clipsByLead[lead.lead_id] || [];
        const shortlisted = shortlist.find((s) => s.stage_name === lead.stage_name);
        return `
          <article class="card artist-card">
            <div class="artist-card-top">
              <div>
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                  <span class="pill ${shortlisted ? 'accent' : ''}">${shortlisted ? '#' + shortlisted.rank : 'Artist'}</span>
                  <h3 class="artist-name">${esc(lead.stage_name)}</h3>
                </div>
                <div class="badges">
                  <span class="pill ${lead.attribution_status === 'uncertain' ? 'warn' : 'ok'}">${lead.attribution_status === 'uncertain' ? '⚠ Uncertain Credit' : 'Verified'}</span>
                  <span class="pill">${leadClips.length} Clips</span>
                </div>
              </div>
              <button type="button" class="btn open-profile-btn" data-lead-id="${esc(lead.lead_id)}">Full Profile →</button>
            </div>
            <p class="artist-fit">${esc(assess.fit_rationale || lead.attribution_notes || '')}</p>
          </article>`;
      })
      .join('');

    // Wire events on both lists
    document.querySelectorAll('.play-first-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const moments = btn.dataset.leadId ? getArtistMoments(run, btn.dataset.leadId, btn.dataset.name) : [];
        playMoment(btn.dataset.embed, btn.dataset.watch, btn.dataset.label, btn.dataset.title, btn.dataset.note, true, moments);
      });
    });
    document.querySelectorAll('.open-profile-btn').forEach((btn) => {
      btn.addEventListener('click', () => openFullProfile(btn.dataset.leadId));
    });
    document.querySelectorAll('.lead-check').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = cb.dataset.leadId;
        if (!id) return;
        if (cb.checked) state.selectedLeads.add(id);
        else state.selectedLeads.delete(id);
        updatePromoteBar();
      });
    });

    // Trace Drawer
    $('traceContainer').innerHTML = (run.trace || [])
      .map(
        (step) => `
        <div class="output-card">
          <div class="output-card-head">
            <span>${esc(step.stage.replace(/_/g, ' ').toUpperCase())}</span>
            <span>${esc(step.duration_ms)} ms</span>
          </div>
          <div class="mono muted" style="font-size:11px;">${esc(step.actor)}</div>
          <div style="margin-top:6px;">${esc(step.summary)}</div>
          <div class="mono muted" style="font-size:11px; margin-top:4px;">interaction_id: ${esc(step.interaction_id || 'n/a')}</div>
        </div>`
      )
      .join('');
  }

  // Subtabs in Tab 1 (Shortlist, All Artists, Screened & Elevated)
  function selectSubtab(target) {
    document.querySelectorAll('[data-subtab]').forEach((b) => b.classList.toggle('active', b.dataset.subtab === target));
    $('shortlistContainer').classList.toggle('hidden', target !== 'shortlist');
    $('allLeadsContainer').classList.toggle('hidden', target !== 'all');
    if ($('screenedLeadsContainer')) {
      $('screenedLeadsContainer').classList.toggle('hidden', target !== 'screened');
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

  function renderScreenedPackets() {
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
    if (!container) return;
    if (!sorted.length) {
      container.innerHTML = `
        <div class="card artist-card">
          <div class="muted" style="font-size:13px;">No Screening Deck packets yet. Run Screening from <a href="/investigate">Investigate</a> or <a href="/screen">Screening</a> to surface elevated artists here.</div>
        </div>`;
      return;
    }
    container.innerHTML = sorted.map((pkt, idx) => {
      const ds = pkt.dossier_snapshot || {};
      const idObj = ds.identity_and_contact || {};
      const stageName = pkt.stage_name || idObj.stage_name || pkt.lead_id || 'Unnamed Artist';
      const leadId = pkt.lead_id || ds.lead_id || '';
      const judge = pkt.judge_decision || {};
      const human = pkt.human_review || null;
      const verdict = String((human && human.human_verdict) || judge.verdict || 'WATCH').toUpperCase();
      const verdictCls = verdict === 'ELEVATE' ? 'ok' : (verdict === 'PASS' ? 'warn' : 'accent');
      const score = judge.total_score != null ? `${Number(judge.total_score).toFixed(1)} / 10` : '—';
      const rationale = (human && human.reason) || judge.rationale || judge.summary || 'Screened candidate packet.';
      const media = (ds.source_and_media_queue && ds.source_and_media_queue.media_links) || [];
      const firstUrl = (media[0] && media[0].url) || (ds.source_and_media_queue && ds.source_and_media_queue.seed_source_url) || '';
      const ytId = extractYtIdFromUrl(firstUrl);
      return `
        <article class="card artist-card">
          <div class="artist-card-top">
            <div>
              <h3 class="artist-name">${esc(stageName)}</h3>
              <div class="badges">
                <span class="pill ${verdictCls}">${esc(verdict)}</span>
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
            <div class="artist-next mono">lead_id: ${esc(leadId || '—')}</div>
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
          'Loaded from Stage 3 Screening Deck packet.',
          true,
          []
        );
      });
    });

    container.querySelectorAll('.screened-producer-btn').forEach((prodBtn) => {
      prodBtn.addEventListener('click', () => {
        const pkt = sorted[Number(prodBtn.dataset.sidx)];
        if (!pkt) return;
        const ds = pkt.dossier_snapshot || {};
        const stageName = pkt.stage_name || (ds.identity_and_contact && ds.identity_and_contact.stage_name) || pkt.lead_id || 'Artist';
        selectPhase('4_producer', {
          lead_id: pkt.lead_id || ds.lead_id || '',
          stage_name: stageName,
          showcase: 'First Listen NYC',
          slot_minutes: 20,
          fee_cap_usd: 500,
        });
        switchTab('pipeline');
      });
    });
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

  function selectPhase(phaseId, customInput = null) {
    state.activePhaseId = phaseId;
    renderPipelineStepper();
    const cur = state.phases.find((p) => p.id === phaseId);
    if (cur) {
      $('phaseInputJson').value = JSON.stringify(customInput || cur.default_input, null, 2);
    }
    if ($('phaseSourceBridgeBar')) {
      $('phaseSourceBridgeBar').classList.toggle('hidden', phaseId !== '1_discovery');
    }
    if ($('phaseLeadBridgeBar')) {
      const showLeads = ['2a_identity', '2b_investigators', '2c_dossier'].includes(phaseId);
      $('phaseLeadBridgeBar').classList.toggle('hidden', !showLeads);
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
      $('phaseInputJson').value = JSON.stringify(leadToPhase2Handoff(lead), null, 2);
    });
  }

  function renderPhaseResult(result) {
    $('phaseRunMeta').textContent = `${result.mode.toUpperCase()} · ${result.duration_ms} ms · ${result.phase_run_id}`;
    const batchLinks = $('phaseBatchLinks');
    if (batchLinks) {
      const batchId = result.output && result.output.batch_id;
      const dossierLeadId = result.phase_id === '2c_dossier' && result.output && result.output.lead_id;
      if (batchId) {
        const q = `?batch=${encodeURIComponent(batchId)}`;
        batchLinks.innerHTML = `<a class="btn" style="padding:3px 8px; font-size:11px;" href="/field-news${q}">Field News →</a><a class="btn" style="padding:3px 8px; font-size:11px;" href="/reports${q}">Reports →</a>`;
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
            <span>${esc(c.agent)}</span>
            <span class="pill ${c.status === 'failed' ? 'warn' : 'ok'}">${esc(c.status)}</span>
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
      list.innerHTML = `<div class="muted" style="font-size:12px;">Run any phase to save a replayable checkpoint here.</div>`;
      return;
    }
    list.innerHTML = state.phaseRuns
      .slice(0, 10)
      .map(
        (r, idx) => `
        <div class="eval-row">
          <div>
            <span class="pill ${r.passed ? 'ok' : 'warn'}">${r.passed ? 'PASS' : 'CHECK'}</span>
            <strong style="margin-left:6px;">Phase ${esc(r.phase_code)} · ${esc(r.phase_name)}</strong>
            <span class="mono muted" style="margin-left:6px;">[${esc(r.mode)}] ${esc(r.duration_ms)}ms</span>
          </div>
          <button type="button" class="btn load-ckpt-btn" data-cidx="${idx}">Inspect</button>
        </div>`
      )
      .join('');
    list.querySelectorAll('.load-ckpt-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const rec = state.phaseRuns[Number(btn.dataset.cidx)];
        state.activePhaseId = rec.phase_id;
        renderPipelineStepper();
        $('phaseInputJson').value = JSON.stringify(rec.input || {}, null, 2);
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
    const keyOverride = $('apiKeyInput').value.trim();
    setBanner(`Running Phase ${phaseId} (${wantLive ? 'LIVE' : 'TEST'})…`, 'info');
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

      // If Phase 1 ran, refresh Discovery batches/leads & Talent Review runs
      if (phaseId === '1_discovery') {
        await refreshDiscoveryData();
        if (data.output && data.output.batch_id) {
          syncDiscoveryBatchLinks(data.output.batch_id);
        }
        if (data.run_id) {
          await refreshHistory();
          const runRes = await fetch('/api/runs?id=' + encodeURIComponent(data.run_id));
          if (runRes.ok) renderRun(await runRes.json());
        }
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
          <span>${esc(a.package)}</span>
          <span class="mono" style="font-size:10px; opacity:0.7;">${esc((a.model || '').replace('gemini-4-', ''))}</span>
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
    $('labAgentName').textContent = agent.package;
    $('labAgentDeployedId').textContent = agent.deployed_id;
    $('labAgentModel').textContent = agent.model || 'default';
    const hintEl = $('labInputHint');
    if (hintEl) {
      hintEl.textContent = agent.input_hint || 'JSON object or array for batch fan-out';
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
        '<div class="muted">Run an agent to inspect its response and contract checks.</div>';
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
      list.innerHTML = `<div class="muted" style="font-size:12px;">No saved evals for this agent yet.</div>`;
      return;
    }
    list.innerHTML = filtered
      .slice(0, 8)
      .map(
        (ev) => `
        <div class="eval-row">
          <div>
            <span class="pill ${ev.verdict === 'pass' ? 'ok' : 'warn'}">${esc((ev.verdict || '').toUpperCase())}</span>
            <strong style="margin-left:6px;">${esc(ev.agent_id)}</strong>
            <span class="muted" style="margin-left:6px;">${esc(ev.note || '')}</span>
          </div>
          <span class="mono muted" style="font-size:11px;">${esc((ev.created_at || '').slice(11, 19))}</span>
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
    const keyOverride = $('apiKeyInput').value.trim();

    $('labRunBtn').disabled = true;
    setBanner(`Running ${state.activeAgent.deployed_id} (${dryRun ? 'Dry Run' : 'Live'})…`, 'info');
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
          <span>${esc(state.activeAgent.deployed_id)}</span>
          <span class="pill ok">${esc(data.mode || (dryRun ? 'dry_run' : 'live'))}</span>
        </div>
        <div><strong>Workers:</strong> ${esc((data.results || []).length)} · <strong>Fleet ID:</strong> <span class="mono">${esc(data.fleet_run_id || 'n/a')}</span></div>
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
  // BRIEF, DEMO & HISTORY HANDLERS
  // =========================================================
  async function refreshHistory() {
    const res = await fetch('/api/runs');
    if (!res.ok) return;
    const data = await res.json();
    const opts = [`<option value="">Saved runs (${data.runs.length})…</option>`];
    data.runs.forEach((r) => {
      opts.push(`<option value="${esc(r.run_id)}">[${esc(r.mode)}] ${esc(r.brief_prompt.slice(0, 46))}…</option>`);
    });
    $('historySelect').innerHTML = opts.join('');
  }

  $('historySelect').addEventListener('change', async () => {
    const id = $('historySelect').value;
    if (!id) return;
    const res = await fetch('/api/runs?id=' + encodeURIComponent(id));
    if (res.ok) renderRun(await res.json());
  });

  document.querySelectorAll('.preset-btn').forEach((btn) => {
    btn.addEventListener('click', () => { $('briefInput').value = btn.dataset.brief; });
  });

  async function triggerScout(wantLive) {
    const keyOverride = $('apiKeyInput').value.trim();
    closeDrawers();
    setBanner(
      wantLive
        ? 'Running Discovery Scout → Gemini 4 Hydrogen clip evaluation → Synthesis Scout… (20–50s)'
        : 'Loading verified public YouTube performances & shortlist…',
      'info'
    );
    $('scoutBtn').disabled = true;
    try {
      const res = await fetch('/api/scout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brief: $('briefInput').value,
          live: wantLive,
          api_key: keyOverride || null,
        }),
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
      setBanner('Network error talking to Simon server: ' + err.message, 'error');
    } finally {
      $('scoutBtn').disabled = false;
    }
  }

  $('demoBtn').addEventListener('click', () => triggerScout(false));
  $('scoutBtn').addEventListener('click', () => triggerScout($('liveToggle').checked));

  // =========================================================
  // INITIALIZE ALL 4 TABS
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
    $('briefInput').value = status.default_brief || '';
    const keyBadge = $('serverKeyBadge');
    if (status.has_api_key) {
      keyBadge.innerHTML = `<span class="dot ok"></span><span>Live Ready</span>`;
      $('liveToggle').checked = true;
    } else {
      keyBadge.innerHTML = `<span class="dot accent"></span><span>Demo Mode</span>`;
      $('liveToggle').checked = false;
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
      selectSubtab(reqSubtab);
    } else if (reqLead || reqSubject) {
      const matched = state.discoveredLeads.find(
        (l) => (reqLead && l.lead_id === reqLead) || (reqSubject && (l.stage_name || '').toLowerCase() === reqSubject.toLowerCase())
      );
      const targetPhase = reqPhase || '2a_identity';
      const handoff = targetPhase === '4_producer'
        ? {
            lead_id: reqLead || (matched && matched.lead_id) || '',
            stage_name: reqSubject || (matched && matched.stage_name) || 'Artist',
            showcase: 'First Listen NYC',
            slot_minutes: 20,
            fee_cap_usd: 500,
          }
        : (matched
          ? leadToPhase2Handoff(matched)
          : {
              lead_id: reqLead || '',
              stage_name: reqSubject || 'Unknown Artist',
              attribution_status: 'verified',
              source_channel: 'youtube_session',
            });
      selectPhase(targetPhase, handoff);
      switchTab(reqTab || 'pipeline', false);
    } else if (reqPhase) {
      selectPhase(reqPhase);
      switchTab(reqTab || 'pipeline', false);
    } else if (reqTab) {
      switchTab(reqTab, false);
    }

    // Load newest saved run or seed demo
    const runsRes = await fetch('/api/runs');
    if (runsRes.ok) {
      const runsData = await runsRes.json();
      if (runsData.runs && runsData.runs.length > 0) {
        const latestId = runsData.runs[0].run_id;
        const latestRes = await fetch('/api/runs?id=' + encodeURIComponent(latestId));
        if (latestRes.ok) {
          renderRun(await latestRes.json());
          await refreshHistory();
          $('historySelect').value = latestId;
          return;
        }
      }
    }
    await triggerScout(false);
  }

  init();
})();
