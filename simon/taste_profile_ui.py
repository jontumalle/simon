"""Stage 3 Taste Profile & Judging Methodology Inspector UI (/taste-profile).

Presents Simon's active judging criteria, 5 shared dossier input-skill rubrics, learned human
overrides, DSPy few-shot calibration anchors, and 4-step methodology around three human-first pillars:
  1. "Where We Are" — Live calibration stage, Firestore counters, policy version selector, & DSPy compiler
  2. "What We Care About" — "What You Taught Us" overrides, Elevate/Watch/Pass bars, gates, & 5 dossier rubrics
  3. "Our Methodology" — Fact-vs-taste 4-step pipeline, DSPy Calibration Demos, & Live Human Review Log
"""

from __future__ import annotations

from typing import Any, Dict, List

from .db_tools import sanitize_agent_report
from .discovery_ui import _SHARED_CSS, render_top_nav
from .screening import (
    RUBRIC_META,
    RUBRIC_ORDER,
    compile_judging_model,
    list_judging_models,
    list_screening_deck,
    list_screening_labels,
    load_screening_rubrics,
)


def _compute_calibration_stage(human_reviews_count: int, overrides_count: int) -> Dict[str, str]:
    """Classify current producer taste calibration maturity for Pillar 1 ('Where We Are')."""
    if human_reviews_count <= 0:
        return {
            "stage": "Bootstrapping",
            "tone": "amber",
            "detail": (
                "Baseline 5-skill rubric + Neon Judge anchors active. Review candidates on Screening Deck "
                "to teach Simon your personal taste."
            ),
        }
    if human_reviews_count < 3 and overrides_count < 2:
        return {
            "stage": "Learning Your Taste",
            "tone": "purple",
            "detail": (
                f"Incorporating {human_reviews_count} human review(s) and {overrides_count} override(s) "
                "at 2.0x training weight."
            ),
        }
    return {
        "stage": "Calibrated",
        "tone": "ok",
        "detail": (
            f"Calibrated across {human_reviews_count} producer review(s) ({overrides_count} override(s) "
            "baked into 0-output-token gemini-decision-1 policy)."
        ),
    }


def _build_input_criteria_catalog(active_policy: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    """Return structured 5-dossier-input criteria combining RUBRIC_META and active questions_config."""
    q_cfg = (active_policy or {}).get("questions_config") or {}
    items: List[Dict[str, Any]] = []
    for idx, key in enumerate(RUBRIC_ORDER, start=1):
        meta = RUBRIC_META[key]
        q_entry = q_cfg.get(key) if isinstance(q_cfg.get(key), dict) else {}
        raw_criteria = q_entry.get("criteria") if isinstance(q_entry.get("criteria"), list) else []

        def _tier_text(level_idx: int, fallback: str) -> str:
            if level_idx < len(raw_criteria) and isinstance(raw_criteria[level_idx], str):
                cleaned = raw_criteria[level_idx].strip()
                prefix = f"{level_idx}:"
                if cleaned.startswith(prefix):
                    return cleaned[len(prefix) :].strip()
                return cleaned
            return fallback

        items.append(
            {
                "index": idx,
                "key": key,
                "label": meta["label"],
                "skill": meta["skill"],
                "block": meta["block"],
                "max_points": 2,
                "instructions": str(
                    q_entry.get("instructions")
                    or f"Score {meta['label']} ({meta['skill']}) from 0 to 2 using only grounded Stage 2 dossier facts."
                ),
                "tiers": {
                    "0": _tier_text(0, meta["level_0"]),
                    "1": _tier_text(1, meta["level_1"]),
                    "2": _tier_text(2, meta["level_2"]),
                },
            }
        )
    return items


def build_taste_profile_payload(store: Any) -> Dict[str, Any]:
    """Assemble combined `GET /api/taste-profile` payload, auto-compiling `policy_v1` if empty."""
    deck = list_screening_deck(store, limit=100)
    models = list_judging_models(store, limit=50)
    if not models:
        compile_judging_model(store)
        models = list_judging_models(store, limit=50)

    active_policy = next((m for m in models if m.get("is_active")), models[0] if models else None)
    labels = list_screening_labels(store, limit=100)
    rubric_spec = load_screening_rubrics()

    overrides_count = sum(1 for lbl in labels if lbl.get("agreed_with_model") is False)
    agreed_count = sum(1 for lbl in labels if lbl.get("agreed_with_model") is True)
    human_reviews_count = max(len(labels), int((active_policy or {}).get("human_label_count") or 0))
    effective_overrides = max(overrides_count, int((active_policy or {}).get("override_count") or 0))
    stage_info = _compute_calibration_stage(human_reviews_count, effective_overrides)

    summary = {
        "candidates_screened": int(deck.get("total") or 0),
        "elevate_count": int(deck.get("elevate_count") or 0),
        "watch_count": int(deck.get("watch_count") or 0),
        "pass_count": int(deck.get("pass_count") or 0),
        "human_reviews_count": len(labels),
        "unique_candidates_reviewed": int(deck.get("human_labeled_count") or 0),
        "overrides_count": overrides_count,
        "agreed_count": agreed_count,
        "active_policy_id": (active_policy or {}).get("policy_id"),
        "policy_count": len(models),
        "calibration_stage": stage_info["stage"],
        "calibration_stage_tone": stage_info["tone"],
        "calibration_stage_detail": stage_info["detail"],
    }

    payload = {
        "ok": True,
        "active_policy": active_policy,
        "models": models,
        "labels": labels,
        "rubric_spec": rubric_spec,
        "input_criteria": _build_input_criteria_catalog(active_policy),
        "summary": summary,
    }
    return sanitize_agent_report(payload)


_TASTE_PROFILE_CSS = """
  .wrap.wrap-taste { max-width: 1360px; }

  .pillar-section {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 22px 24px;
    margin-bottom: 22px;
    box-shadow: var(--shadow);
  }
  .pillar-section.pillar-hero {
    border-color: var(--purple);
  }
  .pillar-kicker {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 0.71rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--purple); margin-bottom: 4px;
  }
  .pillar-top {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start;
    gap: 14px; margin-bottom: 16px;
  }
  .pillar-title {
    margin: 0; font-size: 1.25rem; font-weight: 800; letter-spacing: -0.015em;
    display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  }
  .pillar-sub {
    margin: 4px 0 0; color: var(--muted); font-size: 0.88rem; max-width: 820px;
  }
  .toolbar-actions {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  }
  .btn.compile-btn {
    background: linear-gradient(135deg, #0f766e, #7e22ce);
    color: #ffffff;
    border: none;
    font-weight: 800;
    padding: 9px 15px;
  }
  .btn.compile-btn:hover { filter: brightness(1.08); text-decoration: none; }

  .snapshot-notice {
    display: none; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;
    padding: 9px 13px; border-radius: 10px; margin-bottom: 14px;
    background: var(--amber-bg); border: 1px solid var(--accent); color: var(--accent);
    font-size: 0.83rem; font-weight: 600;
  }

  .where-kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
    gap: 10px;
  }
  .kpi-tile {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 14px;
    display: flex; flex-direction: column; gap: 4px;
  }
  .kpi-label {
    font-size: 0.7rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
  }
  .kpi-value {
    font-size: 1.28rem; font-weight: 800; font-family: var(--mono); color: var(--text); line-height: 1.2;
  }
  .kpi-meta {
    font-size: 0.77rem; color: var(--muted);
  }

  .taught-box {
    background: var(--purple-bg);
    border: 1px solid var(--purple);
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 18px;
  }
  .taught-head {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px;
    margin-bottom: 10px;
  }
  .taught-head h3 {
    margin: 0; font-size: 1rem; font-weight: 800; color: var(--text);
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }
  .taught-chips {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 10px;
  }
  .taught-item {
    background: var(--panel);
    border: 1px solid var(--border);
    border-left: 4px solid var(--purple);
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 0.85rem;
    display: flex; flex-direction: column; gap: 5px;
  }
  .taught-item.ELEVATE { border-left-color: var(--teal); }
  .taught-item.WATCH { border-left-color: var(--accent); }
  .taught-item.PASS { border-left-color: var(--warn); }

  .verdict-cards-grid {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 18px;
  }
  @media (max-width: 960px) { .verdict-cards-grid { grid-template-columns: 1fr; } }

  .verdict-criteria-card {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px 18px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .verdict-criteria-card.ELEVATE { border-top: 4px solid var(--teal); }
  .verdict-criteria-card.WATCH { border-top: 4px solid var(--accent); }
  .verdict-criteria-card.PASS { border-top: 4px solid var(--warn); }

  .verdict-pill {
    display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 999px;
    font-size: 0.79rem; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase;
  }
  .verdict-pill.ELEVATE { background: var(--teal-bg); color: var(--teal); border: 1px solid var(--teal); }
  .verdict-pill.WATCH { background: var(--amber-bg); color: var(--accent); border: 1px solid var(--accent); }
  .verdict-pill.PASS { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn); }

  .human-guidance-callout {
    margin-top: auto;
    background: var(--purple-bg);
    border: 1px solid var(--purple);
    border-radius: 10px;
    padding: 9px 11px;
    font-size: 0.82rem;
    color: var(--text);
  }
  .human-guidance-label {
    font-size: 0.69rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--purple); margin-bottom: 3px;
  }

  .gates-grid {
    display: grid; grid-template-columns: 1.25fr 1fr; gap: 14px; margin-bottom: 20px;
  }
  @media (max-width: 980px) { .gates-grid { grid-template-columns: 1fr; } }

  .gate-panel {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 14px; padding: 15px 17px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .noul-card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px;
    display: flex; flex-direction: column; gap: 7px;
  }
  .noul-tf-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
  }
  @media (max-width: 640px) { .noul-tf-grid { grid-template-columns: 1fr; } }
  .noul-tf-box {
    border-radius: 8px; padding: 8px 10px; font-size: 0.8rem; border: 1px solid var(--border);
    background: var(--input-bg);
  }
  .noul-tf-box.true-box { border-left: 3px solid var(--teal); }
  .noul-tf-box.false-box { border-left: 3px solid var(--warn); }

  .ladder-list { display: flex; flex-direction: column; gap: 7px; }
  .ladder-step {
    background: var(--panel); border: 1px solid var(--border); border-radius: 9px;
    padding: 8px 11px; font-size: 0.82rem; display: flex; gap: 9px; align-items: flex-start;
  }
  .ladder-score {
    font-family: var(--mono); font-weight: 800; font-size: 0.78rem; padding: 2px 7px;
    border-radius: 6px; background: var(--purple-bg); color: var(--purple); flex-shrink: 0;
  }

  .dossier-criteria-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 14px;
  }
  @media (max-width: 520px) { .dossier-criteria-grid { grid-template-columns: 1fr; } }

  .criteria-card {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px 18px;
    display: flex; flex-direction: column; gap: 11px;
  }
  .criteria-tiers {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: auto;
  }
  @media (max-width: 640px) { .criteria-tiers { grid-template-columns: 1fr; } }
  .tier-cell {
    background: var(--panel); border: 1px solid var(--border); border-radius: 9px;
    padding: 9px 10px; font-size: 0.79rem; display: flex; flex-direction: column; gap: 4px;
  }
  .tier-cell.pt-0 { border-top: 3px solid var(--warn); }
  .tier-cell.pt-1 { border-top: 3px solid var(--accent); }
  .tier-cell.pt-2 { border-top: 3px solid var(--teal); }
  .tier-badge {
    font-family: var(--mono); font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
  }
  .tier-cell.pt-0 .tier-badge { color: var(--warn); }
  .tier-cell.pt-1 .tier-badge { color: var(--accent); }
  .tier-cell.pt-2 .tier-badge { color: var(--teal); }

  .methodology-steps-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;
  }
  @media (max-width: 1080px) { .methodology-steps-grid { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 640px) { .methodology-steps-grid { grid-template-columns: 1fr; } }

  .method-step-card {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 15px 16px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .method-step-num {
    font-family: var(--mono); font-size: 0.73rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--purple);
  }
  .method-step-card h3 {
    margin: 0; font-size: 0.96rem; font-weight: 800; color: var(--text);
  }
  .method-step-card p {
    margin: 0; font-size: 0.83rem; color: var(--muted); line-height: 1.48;
  }

  .calibration-split-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  }
  @media (max-width: 980px) { .calibration-split-grid { grid-template-columns: 1fr; } }

  .anchor-list, .review-log-list {
    display: flex; flex-direction: column; gap: 10px; max-height: 520px; overflow-y: auto; padding-right: 4px;
  }
  .anchor-card, .review-log-card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 11px;
    padding: 12px 14px; display: flex; flex-direction: column; gap: 7px; font-size: 0.84rem;
  }
  .anchor-card.is-override, .review-log-card.is-override {
    border-color: var(--purple);
  }
"""


_TASTE_PROFILE_SCRIPT = """
  <script>
    const el = (id) => document.getElementById(id);

    function escapeHtml(value) {
      const div = document.createElement('div');
      div.textContent = value == null ? '' : String(value);
      return div.innerHTML;
    }

    const FALLBACK_RUBRICS = [
      {
        index: 1,
        key: 'identity_reachability',
        label: 'Identity & Reachability',
        skill: 'dossier-identity',
        block: 'identity_and_contact',
        instructions: 'Score Identity & Reachability (dossier-identity) from 0 to 2 using only grounded Stage 2 dossier facts.',
        tiers: {
          '0': 'No verified identity links or public contact route (none).',
          '1': 'Partial platform identity or open DM route, missing business email or home city.',
          '2': 'Clear artist identity, active platform links, and direct business/mgmt contact route.'
        }
      },
      {
        index: 2,
        key: 'live_vocal_proof',
        label: 'Live Vocal Proof',
        skill: 'dossier-media',
        block: 'source_and_media_queue',
        instructions: 'Score Live Vocal Proof (dossier-media) from 0 to 2 using only grounded Stage 2 dossier facts.',
        tiers: {
          '0': 'No embeddable performance clips in source_and_media_queue.',
          '1': 'Single embeddable clip or uncertain performer attribution requiring second-take verification.',
          '2': 'Verified performer attribution with 2+ embeddable live/acoustic performance clips.'
        }
      },
      {
        index: 3,
        key: 'early_window_depth',
        label: 'Early-Window Catalog Depth',
        skill: 'dossier-footprint',
        block: 'public_footprint',
        instructions: 'Score Early-Window Catalog Depth (dossier-footprint) from 0 to 2 using only grounded Stage 2 dossier facts.',
        tiers: {
          '0': 'Unknown footprint regime with zero public reach or catalog metrics.',
          '1': 'Thin single-release footprint or already post-inflection established streaming act.',
          '2': 'Pre-DSP underground or early-DSP inflection artist with multi-track depth and organic reach.'
        }
      },
      {
        index: 4,
        key: 'listener_pull_cosigns',
        label: 'Listener Pull & Scene Cosigns',
        skill: 'dossier-audience',
        block: 'comment_forensics',
        instructions: 'Score Listener Pull & Scene Cosigns (dossier-audience) from 0 to 2 using only grounded Stage 2 dossier facts.',
        tiers: {
          '0': 'Zero sampled comment signal or spam-dominated comment section.',
          '1': 'Modest organic listener praise without explicit release/live requests or peer cosigns.',
          '2': 'Strong release/live-show demand counts and/or notable producer, musician, or curator cosigns.'
        }
      },
      {
        index: 5,
        key: 'stage_momentum_whitespace',
        label: 'Stage Momentum & A&R Whitespace',
        skill: 'dossier-track-record',
        block: 'live_history_and_credits',
        instructions: 'Score Stage Momentum & A&R Whitespace (dossier-track-record) from 0 to 2 using only grounded Stage 2 dossier facts.',
        tiers: {
          '0': 'Zero documented live show history, upcoming bills, or collaborator credits.',
          '1': 'Early single-room show or credit activity, or active live act already signed to a label.',
          '2': 'Active room/club billing momentum plus collaborator credits with unsigned label whitespace.'
        }
      }
    ];

    let tastePayload = null;
    let selectedPolicyId = null;

    function showBanner(msg, kind) {
      const b = el('tasteBanner');
      if (!b) return;
      if (!msg) {
        b.style.display = 'none';
        b.textContent = '';
        return;
      }
      b.textContent = msg;
      b.className = 'banner ' + (kind || 'info');
      b.style.display = 'block';
    }

    function getSelectedPolicy() {
      if (!tastePayload) return null;
      const models = Array.isArray(tastePayload.models) ? tastePayload.models : [];
      if (selectedPolicyId) {
        const found = models.find((m) => m && m.policy_id === selectedPolicyId);
        if (found) return found;
      }
      return tastePayload.active_policy || models[0] || null;
    }

    function splitHumanGuidance(rawDesc) {
      const text = String(rawDesc || '').trim();
      const match = text.match(/^(.*?)\\s*(Human scout\\s+\\w+\\s+guidance:\\s*.+)$/i);
      if (!match) {
        return { baseText: text, humanGuidance: '' };
      }
      return {
        baseText: match[1].trim(),
        humanGuidance: match[2].trim(),
      };
    }

    function splitChoiceInstructions(rawInst) {
      const text = String(rawInst || '').trim();
      const marker = 'Incorporate human override feedback:';
      const idx = text.indexOf(marker);
      if (idx === -1) {
        return { baseInst: text, overrideFeedback: '' };
      }
      return {
        baseInst: text.slice(0, idx).trim(),
        overrideFeedback: text.slice(idx + marker.length).trim(),
      };
    }

    function stripTierPrefix(raw, tierNum) {
      const text = String(raw || '').trim();
      const prefix = String(tierNum) + ':';
      return text.startsWith(prefix) ? text.slice(prefix.length).trim() : text;
    }

    function renderVersionDropdown(models, activePolicy, currentPolicy) {
      const sel = el('policyVersionSelect');
      if (!sel) return;
      if (!models.length) {
        sel.innerHTML = '<option value="">policy_v1 (baseline)</option>';
        return;
      }
      sel.innerHTML = models.map((m) => {
        const pid = String(m.policy_id || 'policy_v1');
        const isAct = Boolean(m.is_active || (activePolicy && activePolicy.policy_id === pid));
        const ovCount = Number(m.override_count || 0);
        const hCount = Number(m.human_label_count || 0);
        const tag = isAct ? ' · ACTIVE' : ' · snapshot';
        const label = `${pid}${tag} (${hCount} human, ${ovCount} override${ovCount === 1 ? '' : 's'})`;
        const selectedAttr = currentPolicy && currentPolicy.policy_id === pid ? ' selected' : '';
        return `<option value="${escapeHtml(pid)}"${selectedAttr}>${escapeHtml(label)}</option>`;
      }).join('');
    }

    function renderWhereWeAre(policy, summary, activePolicy) {
      const stageName = summary.calibration_stage || 'Bootstrapping';
      const stageTone = summary.calibration_stage_tone || 'amber';
      const stageBadge = el('calibrationStageBadge');
      if (stageBadge) {
        stageBadge.className = 'pill ' + stageTone;
        stageBadge.textContent = 'Stage: ' + stageName;
      }

      const activeId = (activePolicy && activePolicy.policy_id) || summary.active_policy_id || 'policy_v1';
      const viewingId = (policy && policy.policy_id) || activeId;
      const isHistorical = Boolean(policy && activePolicy && policy.policy_id !== activePolicy.policy_id);

      const policyBadge = el('activePolicyPill');
      if (policyBadge) {
        policyBadge.textContent = isHistorical
          ? `Inspecting ${viewingId} (Active: ${activeId})`
          : `Active Policy: ${activeId}`;
      }

      const notice = el('historicalPolicyNotice');
      if (notice) {
        if (isHistorical) {
          notice.style.display = 'flex';
          notice.innerHTML = `
            <span>Inspecting historical snapshot <strong>${escapeHtml(viewingId)}</strong>. Active live policy is <strong>${escapeHtml(activeId)}</strong>.</span>
            <button type="button" class="btn" id="jumpActivePolicyBtn" style="padding:4px 10px; font-size:0.78rem;">Return to Active (${escapeHtml(activeId)})</button>
          `;
          const jumpBtn = el('jumpActivePolicyBtn');
          if (jumpBtn) {
            jumpBtn.onclick = () => {
              selectedPolicyId = activeId;
              renderAll();
            };
          }
        } else {
          notice.style.display = 'none';
          notice.innerHTML = '';
        }
      }

      const stageSub = el('whereStageDetail');
      if (stageSub) {
        stageSub.textContent = summary.calibration_stage_detail || '';
      }

      const valAcc = policy && policy.val_accuracy != null
        ? Math.round(Number(policy.val_accuracy) * 100) + '%'
        : '100%';
      const thresholds = (policy && policy.thresholds) || {};
      const elevMin = thresholds.elevate_min_score != null ? thresholds.elevate_min_score : 7;
      const watchMin = thresholds.watch_min_score != null ? thresholds.watch_min_score : 4;
      const optimizer = (policy && policy.optimizer) || 'dspy.BootstrapFewShot';
      const targetModel = (policy && policy.target_model) || 'gemini-decision-1';
      const compiledAt = (policy && policy.compiled_at)
        ? String(policy.compiled_at).replace('T', ' ').replace('Z', ' UTC')
        : 'Live';

      el('whereKpiGrid').innerHTML = `
        <div class="kpi-tile">
          <span class="kpi-label">Selected Policy</span>
          <span class="kpi-value">${escapeHtml(viewingId)}</span>
          <span class="kpi-meta">${isHistorical ? 'Historical version' : 'Active live policy'} · ${escapeHtml(compiledAt)}</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Calibration Stage</span>
          <span class="kpi-value">${escapeHtml(stageName)}</span>
          <span class="kpi-meta">${escapeHtml(String(summary.policy_count || 1))} compiled version(s) in Firestore</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Candidates Screened</span>
          <span class="kpi-value">${escapeHtml(String(summary.candidates_screened || 0))}</span>
          <span class="kpi-meta">${escapeHtml(String(summary.elevate_count || 0))} Elevate · ${escapeHtml(String(summary.watch_count || 0))} Watch · ${escapeHtml(String(summary.pass_count || 0))} Pass</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Human Reviews Logged</span>
          <span class="kpi-value">${escapeHtml(String(summary.human_reviews_count || 0))}</span>
          <span class="kpi-meta">${escapeHtml(String((policy && policy.human_label_count) || 0))} compiled into ${escapeHtml(viewingId)}</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Overrides Learned (2x)</span>
          <span class="kpi-value">${escapeHtml(String(summary.overrides_count || 0))}</span>
          <span class="kpi-meta">${escapeHtml(String((policy && policy.override_count) || 0))} baked into ${escapeHtml(viewingId)} prompts</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Validation Accuracy</span>
          <span class="kpi-value">${escapeHtml(valAcc)}</span>
          <span class="kpi-meta">Elevate &ge; ${escapeHtml(String(elevMin))}/10 · Watch ${escapeHtml(String(watchMin))}–${escapeHtml(String(Math.max(watchMin, elevMin - 1)))}/10</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Target Engine &amp; Optimizer</span>
          <span class="kpi-value" style="font-size:0.98rem;">${escapeHtml(targetModel)}</span>
          <span class="kpi-meta">0 output tokens · ${escapeHtml(optimizer)}</span>
        </div>
      `;
    }

    function renderWhatYouTaughtUs(policy, labels) {
      const overrideNotes = (policy && policy.override_notes) || {};
      const learnedItems = [];
      const seen = new Set();

      ['elevate', 'watch', 'pass'].forEach((verdictKey) => {
        const arr = Array.isArray(overrideNotes[verdictKey]) ? overrideNotes[verdictKey] : [];
        arr.forEach((note) => {
          const clean = String(note || '').trim();
          const sig = verdictKey + '::' + clean.toLowerCase();
          if (clean && !seen.has(sig)) {
            seen.add(sig);
            learnedItems.push({
              verdict: verdictKey.toUpperCase(),
              note: clean,
              artist: '',
              inPolicy: true,
              isOverride: true,
            });
          }
        });
      });

      (Array.isArray(labels) ? labels : []).forEach((lbl) => {
        const reason = String(lbl.reason || '').trim();
        const v = String(lbl.human_verdict || '').toLowerCase();
        if (!reason || !v) return;
        const sig = v + '::' + reason.toLowerCase();
        if (seen.has(sig)) {
          const match = learnedItems.find((it) => it.verdict.toLowerCase() === v && it.note.toLowerCase() === reason.toLowerCase());
          if (match && !match.artist && lbl.stage_name) {
            match.artist = String(lbl.stage_name);
            match.isOverride = lbl.agreed_with_model === false;
          }
          return;
        }
        seen.add(sig);
        learnedItems.push({
          verdict: v.toUpperCase(),
          note: reason,
          artist: String(lbl.stage_name || lbl.lead_id || ''),
          inPolicy: false,
          isOverride: lbl.agreed_with_model === false,
        });
      });

      const container = el('whatYouTaughtUsContent');
      const countPill = el('taughtCountBadge');
      if (countPill) {
        countPill.textContent = `${learnedItems.length} producer rule${learnedItems.length === 1 ? '' : 's'}`;
      }

      if (!learnedItems.length) {
        container.innerHTML = `
          <div style="font-size:0.86rem; color:var(--muted); display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px;">
            <span>No explicit producer override notes recorded yet. Vote <strong>Elevate / Watch / Pass</strong> with a <em>"Why"</em> note on the Screening Deck (e.g., stage look, vocal tone, room energy) and click <strong>Re-Compile Taste Profile</strong> to bake your instincts into <code>gemini-decision-1</code> at 2.0x weight.</span>
            <a class="btn" href="/screen">Review Artists on Screening Deck →</a>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div class="taught-chips">
          ${learnedItems.map((item) => `
            <div class="taught-item ${escapeHtml(item.verdict)}">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; flex-wrap:wrap;">
                <span class="verdict-pill ${escapeHtml(item.verdict)}" style="padding:2px 9px; font-size:0.71rem;">${escapeHtml(item.verdict)}</span>
                <div style="display:flex; gap:5px; flex-wrap:wrap;">
                  ${item.isOverride ? '<span class="pill purple">2.0x Override</span>' : '<span class="pill ok">Confirmed Rule</span>'}
                  ${item.inPolicy ? '<span class="pill blue">Compiled in Policy</span>' : '<span class="pill amber">Pending Re-Compile</span>'}
                </div>
              </div>
              <div style="font-weight:700; color:var(--text);">"${escapeHtml(item.note)}"</div>
              ${item.artist ? `<div class="mono">Taught while reviewing: ${escapeHtml(item.artist)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      `;
    }

    function renderVerdictAndGates(policy) {
      const qCfg = (policy && policy.questions_config) || {};
      const tv = qCfg.taste_verdict || qCfg.screening_verdict || {};
      const criteria = tv.criteria || {};
      const thresholds = (policy && policy.thresholds) || {};
      const elevMin = thresholds.elevate_min_score != null ? thresholds.elevate_min_score : 7;
      const watchMin = thresholds.watch_min_score != null ? thresholds.watch_min_score : 4;

      const parsedInst = splitChoiceInstructions(tv.instructions || '');
      el('choiceInstructionsBox').innerHTML = `
        <div style="font-size:0.86rem; color:var(--muted); margin-bottom:12px;">
          <strong>Choice Prompt (<code>taste_verdict</code> / <code>screening_verdict</code>):</strong>
          ${escapeHtml(parsedInst.baseInst || 'Select the calibrated Stage 3 screening verdict after weighing all 5 dossier rubrics and Advocate vs. Skeptic arguments.')}
          ${parsedInst.overrideFeedback ? `<div style="margin-top:6px;"><span class="pill purple">Active Override Directive</span> <strong style="color:var(--text);">${escapeHtml(parsedInst.overrideFeedback)}</strong></div>` : ''}
        </div>
      `;

      const cardsMeta = [
        {
          key: 'elevate',
          upper: 'ELEVATE',
          band: `Score >= ${elevMin}/10`,
          action: 'Immediate paid-slot / A&R callback',
          fallback: `Total rubric score >= ${elevMin}/10 with verified vocal proof, organic listener demand or peer cosigns, and reachable unsigned whitespace.`
        },
        {
          key: 'watch',
          upper: 'WATCH',
          band: `Score ${watchMin}..${Math.max(watchMin, elevMin - 1)}/10`,
          action: 'Track & request 1–2 missing diligence items',
          fallback: `Total rubric score ${watchMin}..${Math.max(watchMin, elevMin - 1)}/10 showing vocal or audience promise but missing 1-2 diligence items.`
        },
        {
          key: 'pass',
          upper: 'PASS',
          band: `Score <= ${watchMin - 1}/10`,
          action: 'Hold / pass for current cycle',
          fallback: `Total rubric score <= ${watchMin - 1}/10 or unverified attribution with thin vocal/audience evidence.`
        }
      ];

      el('verdictCardsGrid').innerHTML = cardsMeta.map((meta) => {
        const rawText = criteria[meta.key] || meta.fallback;
        const parts = splitHumanGuidance(rawText);
        return `
          <div class="verdict-criteria-card ${meta.upper}">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <span class="verdict-pill ${meta.upper}">${meta.upper}</span>
              <span class="pill" style="font-family:var(--mono);">${escapeHtml(meta.band)}</span>
            </div>
            <div class="mono" style="color:var(--text); font-weight:600;">${escapeHtml(meta.action)}</div>
            <div style="font-size:0.86rem; color:var(--text); line-height:1.5;">${escapeHtml(parts.baseText)}</div>
            ${parts.humanGuidance
              ? `<div class="human-guidance-callout">
                   <div class="human-guidance-label">Learned Producer Guidance (2.0x Weight)</div>
                   <div>${escapeHtml(parts.humanGuidance)}</div>
                 </div>`
              : `<div class="mono" style="margin-top:auto;">No custom ${escapeHtml(meta.key)} override appended in this version.</div>`
            }
          </div>
        `;
      }).join('');

      // Binary noul gates
      const gateSpecs = [
        { key: 'sufficient_live_evidence', title: 'Gate 1 · Sufficient Live Vocal Evidence', badge: 'noul · True/False' },
        { key: 'actionable_whitespace', title: 'Gate 2 · Actionable Early-Window Whitespace', badge: 'noul · True/False' },
        { key: 'live_signable', title: 'Composite Gate · Live Callback Signability', badge: 'noul · P(True)' }
      ];
      const renderedGates = gateSpecs
        .filter((g) => qCfg[g.key] && typeof qCfg[g.key] === 'object')
        .map((g) => {
          const q = qCfg[g.key];
          const crit = q.criteria || {};
          return `
            <div class="noul-card">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong style="font-size:0.88rem;">${escapeHtml(g.title)} <code class="mono">(${escapeHtml(g.key)})</code></strong>
                <span class="pill blue">${escapeHtml(g.badge)}</span>
              </div>
              <div style="font-size:0.82rem; color:var(--muted);">${escapeHtml(q.instructions || '')}</div>
              <div class="noul-tf-grid">
                <div class="noul-tf-box true-box">
                  <div style="font-weight:800; font-size:0.72rem; color:var(--teal); text-transform:uppercase; margin-bottom:2px;">TRUE Criteria</div>
                  <div>${escapeHtml(crit.true_description || '')}</div>
                </div>
                <div class="noul-tf-box false-box">
                  <div style="font-weight:800; font-size:0.72rem; color:var(--warn); text-transform:uppercase; margin-bottom:2px;">FALSE Criteria</div>
                  <div>${escapeHtml(crit.false_description || '')}</div>
                </div>
              </div>
            </div>
          `;
        }).join('');
      el('noulGatesContainer').innerHTML = renderedGates || '<div class="mono">No binary noul gates configured.</div>';

      // Composite Fit 0..4 ladder
      const compFit = qCfg.composite_fit || {};
      const compCriteria = Array.isArray(compFit.criteria) ? compFit.criteria : [];
      el('compositeFitInstructions').textContent = compFit.instructions || 'Rate overall calibrated Taste Engine A&R & showcase fit from 0 to 4.';
      el('compositeFitLadder').innerHTML = compCriteria.map((line, idx) => {
        const text = stripTierPrefix(line, idx);
        return `
          <div class="ladder-step">
            <span class="ladder-score">${idx} / 4</span>
            <span>${escapeHtml(text)}</span>
          </div>
        `;
      }).join('');
    }

    function renderFiveDossierCriteria(policy) {
      const qCfg = (policy && policy.questions_config) || {};
      const baseCatalog = (tastePayload && Array.isArray(tastePayload.input_criteria) && tastePayload.input_criteria.length === 5)
        ? tastePayload.input_criteria
        : FALLBACK_RUBRICS;

      el('dossierCriteriaGrid').innerHTML = baseCatalog.map((item, idx) => {
        const qEntry = qCfg[item.key] || {};
        const instructions = qEntry.instructions || item.instructions || '';
        const rawArr = Array.isArray(qEntry.criteria) ? qEntry.criteria : [];
        const t0 = rawArr[0] ? stripTierPrefix(rawArr[0], 0) : (item.tiers && item.tiers['0']) || '';
        const t1 = rawArr[1] ? stripTierPrefix(rawArr[1], 1) : (item.tiers && item.tiers['1']) || '';
        const t2 = rawArr[2] ? stripTierPrefix(rawArr[2], 2) : (item.tiers && item.tiers['2']) || '';
        const num = item.index || (idx + 1);

        return `
          <div class="criteria-card" data-rubric-key="${escapeHtml(item.key)}">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px; flex-wrap:wrap;">
              <div>
                <div style="font-weight:800; font-size:0.98rem; color:var(--text);">${escapeHtml(String(num))}. ${escapeHtml(item.label)}</div>
                <div class="mono" style="margin-top:2px;">Stage 2 Block: <code>${escapeHtml(item.block)}</code></div>
              </div>
              <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                <span class="pill blue">${escapeHtml(item.skill)}</span>
                <span class="pill purple">0–2 pts</span>
              </div>
            </div>
            <div style="font-size:0.83rem; color:var(--muted);">${escapeHtml(instructions)}</div>
            <div class="criteria-tiers">
              <div class="tier-cell pt-0">
                <span class="tier-badge">0 pt · Weak / Missing</span>
                <span>${escapeHtml(t0)}</span>
              </div>
              <div class="tier-cell pt-1">
                <span class="tier-badge">1 pt · Partial / Mixed</span>
                <span>${escapeHtml(t1)}</span>
              </div>
              <div class="tier-cell pt-2">
                <span class="tier-badge">2 pt · Strong Signal</span>
                <span>${escapeHtml(t2)}</span>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    function renderAnchorsAndReviewLog(policy, labels) {
      const demos = Array.isArray(policy && policy.demos) ? policy.demos : [];
      const demoBadge = el('demosCountBadge');
      if (demoBadge) {
        demoBadge.textContent = `${demos.length} anchor${demos.length === 1 ? '' : 's'}`;
      }

      if (!demos.length) {
        el('calibrationDemosList').innerHTML = '<div class="mono">No few-shot calibration anchors stored on this policy yet.</div>';
      } else {
        el('calibrationDemosList').innerHTML = demos.map((d) => {
          const verdict = String(d.target_verdict || d.verdict || 'watch').toUpperCase();
          const src = String(d.source || 'judge_bootstrap');
          const isOverride = src === 'human_override';
          const srcPillCls = isOverride ? 'purple' : (src === 'human_label' ? 'ok' : 'amber');
          const weight = d.weight != null ? `${Number(d.weight).toFixed(1)}x wt` : '1.0x wt';
          const pros = Array.isArray(d.pros) ? d.pros.slice(0, 2) : [];
          const cons = Array.isArray(d.cons) ? d.cons.slice(0, 2) : [];

          return `
            <div class="anchor-card ${isOverride ? 'is-override' : ''}">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong style="font-size:0.94rem;">${escapeHtml(d.stage_name || d.lead_id || 'Candidate')}</strong>
                <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                  <span class="verdict-pill ${escapeHtml(verdict)}" style="padding:2px 9px; font-size:0.72rem;">${escapeHtml(verdict)}</span>
                  <span class="pill" style="font-family:var(--mono);">${escapeHtml(String(d.total_score != null ? d.total_score : '—'))}/10</span>
                  <span class="pill ${srcPillCls}">${escapeHtml(src)} · ${escapeHtml(weight)}</span>
                </div>
              </div>
              ${d.reason ? `<div style="color:var(--text);"><strong>Calibration Rationale:</strong> ${escapeHtml(d.reason)}</div>` : ''}
              ${pros.length ? `<div class="mono" style="color:var(--teal);">+ Pros: ${escapeHtml(pros.join(' · '))}</div>` : ''}
              ${cons.length ? `<div class="mono" style="color:var(--warn);">&minus; Cons: ${escapeHtml(cons.join(' · '))}</div>` : ''}
            </div>
          `;
        }).join('');
      }

      const safeLabels = Array.isArray(labels) ? labels : [];
      const logBadge = el('labelsCountBadge');
      if (logBadge) {
        logBadge.textContent = `${safeLabels.length} review${safeLabels.length === 1 ? '' : 's'}`;
      }

      if (!safeLabels.length) {
        el('humanReviewLogList').innerHTML = `
          <div class="anchor-card">
            <div style="color:var(--muted);">No human reviews saved in <code>screening_labels</code> yet.</div>
            <div><a class="btn" href="/screen">Open Screening Deck to Vote →</a></div>
          </div>
        `;
      } else {
        el('humanReviewLogList').innerHTML = safeLabels.map((lbl) => {
          const hVerdict = String(lbl.human_verdict || 'watch').toUpperCase();
          const mVerdict = lbl.model_verdict ? String(lbl.model_verdict).toUpperCase() : 'UNSET';
          const isOverride = lbl.agreed_with_model === false;
          const agreedBadge = isOverride
            ? '<span class="pill purple">Override (2.0x)</span>'
            : '<span class="pill ok">Agreed (1.0x)</span>';
          const stamp = lbl.labeled_at ? String(lbl.labeled_at).replace('T', ' ').replace('Z', ' UTC') : '';

          return `
            <div class="review-log-card ${isOverride ? 'is-override' : ''}">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong style="font-size:0.94rem;">${escapeHtml(lbl.stage_name || lbl.lead_id || 'Candidate')}</strong>
                <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                  <span class="mono">Model: <strong>${escapeHtml(mVerdict)}</strong> &rarr; Human:</span>
                  <span class="verdict-pill ${escapeHtml(hVerdict)}" style="padding:2px 9px; font-size:0.72rem;">${escapeHtml(hVerdict)}</span>
                  ${agreedBadge}
                </div>
              </div>
              <div style="color:var(--text);">
                ${lbl.reason ? `<strong>Why:</strong> "${escapeHtml(lbl.reason)}"` : '<span class="mono">No written note attached.</span>'}
              </div>
              <div class="mono" style="display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;">
                <span>Reviewer: ${escapeHtml(lbl.reviewer || 'human_scout')}</span>
                <span>${escapeHtml(stamp)}</span>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    function renderAll() {
      if (!tastePayload) return;
      const models = Array.isArray(tastePayload.models) ? tastePayload.models : [];
      const activePolicy = tastePayload.active_policy || models[0] || null;
      const policy = getSelectedPolicy();
      const summary = tastePayload.summary || {};
      const labels = Array.isArray(tastePayload.labels) ? tastePayload.labels : [];

      renderVersionDropdown(models, activePolicy, policy);
      renderWhereWeAre(policy, summary, activePolicy);
      renderWhatYouTaughtUs(policy, labels);
      renderVerdictAndGates(policy);
      renderFiveDossierCriteria(policy);
      renderAnchorsAndReviewLog(policy, labels);
    }

    async function loadTasteProfile(preserveSelection) {
      try {
        const res = await fetch('/api/taste-profile');
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Failed to load Taste Profile');
        tastePayload = data;
        if (!preserveSelection || !selectedPolicyId) {
          selectedPolicyId = (data.active_policy && data.active_policy.policy_id)
            || (Array.isArray(data.models) && data.models[0] && data.models[0].policy_id)
            || null;
        }
        renderAll();
      } catch (err) {
        showBanner(err.message || 'Unable to load Taste Profile.', 'err');
      }
    }

    el('policyVersionSelect').onchange = (ev) => {
      selectedPolicyId = ev.target.value || null;
      renderAll();
    };

    el('recompileTasteBtn').onclick = async () => {
      const btn = el('recompileTasteBtn');
      btn.disabled = true;
      showBanner('Re-compiling DSPy + gemini-decision-1 Taste Profile from human reviews…', 'info');
      try {
        const res = await fetch('/api/screening/train', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Policy compilation failed');
        const newPolicy = data.policy || data;
        selectedPolicyId = newPolicy.policy_id || null;
        await loadTasteProfile(true);
        showBanner(
          `Compiled active Taste Profile ${newPolicy.policy_id || ''} (${newPolicy.human_label_count || 0} human reviews, ${newPolicy.override_count || 0} overrides).`,
          'info'
        );
      } catch (err) {
        showBanner(err.message || 'Failed to compile Taste Profile.', 'err');
      } finally {
        btn.disabled = false;
      }
    };

    loadTasteProfile(false);
  </script>
"""


def render_taste_profile_page() -> str:
    """Render the `/taste-profile` ('8. Taste Profile') HTML page."""
    top_nav = render_top_nav("/taste-profile")
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · 8. Taste Profile &amp; Judging Methodology</title>
  <style>"""
        + _SHARED_CSS
        + _TASTE_PROFILE_CSS
        + """</style>
</head>
<body>
  <div class="wrap wrap-taste">
    <header>
      <div class="brand">
        <h1>Simon <span class="pill purple">8. Taste Profile</span></h1>
        <p>Inspect <strong>where we are</strong> in calibration, <strong>what we care about</strong> across 5 factual dossier skills &amp; human overrides, and <strong>our methodology</strong> separating objective scouting facts from subjective A&amp;R taste.</p>
      </div>
      """
        + top_nav
        + """
    </header>

    <div id="tasteBanner" class="banner"></div>

    <!-- PILLAR 1: WHERE WE ARE -->
    <section class="pillar-section pillar-hero" id="pillarWhereWeAre" aria-label="Where We Are">
      <div class="pillar-top">
        <div>
          <div class="pillar-kicker">Pillar 1 · Live Calibration &amp; Pipeline Snapshot</div>
          <h2 class="pillar-title">
            1. Where We Are
            <span id="calibrationStageBadge" class="pill amber">Stage: Loading…</span>
            <span id="activePolicyPill" class="pill purple">Active Policy: policy_v1</span>
          </h2>
          <p class="pillar-sub" id="whereStageDetail">Loading live Firestore screening deck, human calibration reviews, and compiled <code>gemini-decision-1</code> policy…</p>
        </div>

        <div class="toolbar-actions">
          <label for="policyVersionSelect" class="mono" style="font-weight:700;">Policy Version:</label>
          <select id="policyVersionSelect" aria-label="Select compiled Taste Profile policy version">
            <option value="">Loading versions…</option>
          </select>
          <button id="recompileTasteBtn" class="btn compile-btn" type="button">Re-Compile Taste Profile</button>
          <a href="/screen" class="btn">← Back to Screening Deck</a>
        </div>
      </div>

      <div id="historicalPolicyNotice" class="snapshot-notice"></div>

      <div id="whereKpiGrid" class="where-kpi-grid">
        <div class="kpi-tile"><span class="kpi-label">Loading</span><span class="kpi-value">…</span></div>
      </div>
    </section>

    <!-- PILLAR 2: WHAT WE CARE ABOUT -->
    <section class="pillar-section" id="pillarWhatWeCareAbout" aria-label="What We Care About">
      <div class="pillar-top">
        <div>
          <div class="pillar-kicker">Pillar 2 · Active Criteria, Verdict Bar &amp; Learned Preferences</div>
          <h2 class="pillar-title">
            2. What We Care About
            <span class="pill purple">5 Dossier Skills &times; 0–2 pts = 10 pts</span>
            <span class="pill ok">gemini-decision-1 · 0 output tokens</span>
          </h2>
          <p class="pillar-sub">Every candidate is evaluated against explicit, inspectable criteria — combining baseline A&amp;R evidence rules with producer overrides learned from your votes on <code>/screen</code>.</p>
        </div>
      </div>

      <!-- Highlighted "What You Taught Us" Box -->
      <div class="taught-box" id="whatYouTaughtUsBox">
        <div class="taught-head">
          <h3>
            What You Taught Us (Learned Human Overrides)
            <span id="taughtCountBadge" class="pill purple">0 producer rules</span>
          </h3>
          <span class="mono">Human disagreements carry <strong>2.0x weight</strong> in DSPy policy compilation</span>
        </div>
        <div id="whatYouTaughtUsContent" class="mono">Loading learned producer feedback…</div>
      </div>

      <!-- Elevate / Watch / Pass Choice Cards -->
      <div class="section-head" style="margin-bottom:8px;">
        <h2>Verdict Bar (<code>Elevate</code> &middot; <code>Watch</code> &middot; <code>Pass</code>) &amp; Human-Taught Rules</h2>
        <span class="pill purple">ChoiceQuestion · questions_config.taste_verdict</span>
      </div>
      <div id="choiceInstructionsBox"></div>
      <div id="verdictCardsGrid" class="verdict-cards-grid"></div>

      <!-- Global gemini-decision-1 Noul Gates + 0-4 Composite Fit Ladder -->
      <div class="gates-grid">
        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">Global Hard Gates (<code>NoulQuestion</code> · True vs. False)</h2>
            <span class="pill blue">Zero-Token Binary Checks</span>
          </div>
          <div id="noulGatesContainer" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>

        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">Calibrated Composite Fit Ladder (<code>0–4</code>)</h2>
            <span class="pill purple">ScoreQuestion · composite_fit</span>
          </div>
          <div id="compositeFitInstructions" class="mono" style="margin-bottom:4px;"></div>
          <div id="compositeFitLadder" class="ladder-list"></div>
        </div>
      </div>

      <!-- The 5 Dossier Input Criteria (0-2 pts each = 10 pts total) -->
      <div class="section-head" style="margin-top:6px;">
        <h2>The 5 Stage 2 Dossier Input Criteria (<code>0–2</code> pts each = <code>10</code> pts total)</h2>
        <span class="pill blue">1:1 Shared Dossier Skills</span>
      </div>
      <div id="dossierCriteriaGrid" class="dossier-criteria-grid"></div>
    </section>

    <!-- PILLAR 3: OUR METHODOLOGY -->
    <section class="pillar-section" id="pillarOurMethodology" aria-label="Our Methodology">
      <div class="pillar-top">
        <div>
          <div class="pillar-kicker">Pillar 3 · Fact-vs-Taste Architecture &amp; Audit Trail</div>
          <h2 class="pillar-title">
            3. Our Methodology: How Simon Separates Facts from Taste
            <span class="pill ok">3-Layer Rubric Verified</span>
          </h2>
          <p class="pillar-sub">Scouting agents never rank or editorialize during research. Subjective taste enters only in Stage 3, where adversarial arguments meet explicit human producer calibration.</p>
        </div>
        <div class="toolbar-actions">
          <a href="/evals" class="btn">Inspect 3-Layer Evals →</a>
          <a href="/screen" class="btn">Vote on Screening Deck →</a>
        </div>
      </div>

      <div class="methodology-steps-grid">
        <div class="method-step-card">
          <span class="method-step-num">Step 1 · Stage 2 Intake</span>
          <h3>Fact-Only Dossiers</h3>
          <p><code>simon-scout-investigator</code> gathers 5 objective blocks (identity, media queue, footprint, comments, live history) with <strong>zero ranking</strong>. Unverified items go into <code>missing_fields</code> — abstaining honestly rather than inventing flaws.</p>
          <span class="pill" style="margin-top:auto; align-self:flex-start;">InvestigatorDossier v1.0.0</span>
        </div>

        <div class="method-step-card">
          <span class="method-step-num">Step 2 · Adversarial Neon Debate</span>
          <h3>Advocate vs. Skeptic &rarr; Judge</h3>
          <p><code>simon-screen-advocate</code> steelmans upside (<code>pros[]</code> + <code>standout_hook</code>) while <code>simon-screen-skeptic</code> audits concentration &amp; dealbreakers (<code>cons[]</code>). <code>simon-screening-judge</code> (<code>gemini-4-neon</code>) synthesizes a <code>0–10</code> rubric call.</p>
          <span class="pill amber" style="margin-top:auto; align-self:flex-start;">ScreeningPacket v1.0.0</span>
        </div>

        <div class="method-step-card">
          <span class="method-step-num">Step 3 · Human-in-the-Loop</span>
          <h3>Producer Overrides (2.0x Weight)</h3>
          <p>On <a href="/screen">7. Screening Deck</a>, producers review one candidate at a time, watch live clips, and log <strong>Elevate / Watch / Pass</strong> + a <em>"Why"</em> note. Overrides carry <strong>2.0x weight</strong> to capture human instincts.</p>
          <span class="pill purple" style="margin-top:auto; align-self:flex-start;">screening_labels · 2.0x Override</span>
        </div>

        <div class="method-step-card">
          <span class="method-step-num">Step 4 · Instant Taste Engine</span>
          <h3>Compiled <code>gemini-decision-1</code></h3>
          <p><code>dspy.BootstrapFewShot</code> compiles calibrated thresholds, override rules, and few-shot anchors into <code>questions_config</code>, powering <strong>0-output-token</strong> calibrated <code>P(elevate)</code> scoring via <code>v1beta/decisions</code>.</p>
          <span class="pill ok" style="margin-top:auto; align-self:flex-start;">gemini-decision-1 · 0 tok</span>
        </div>
      </div>

      <!-- Calibration Anchors & Live Human Review Log -->
      <div class="calibration-split-grid">
        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">DSPy Bootstrapped Calibration Anchors (<code>demos[]</code>)</h2>
            <span id="demosCountBadge" class="pill purple">0 anchors</span>
          </div>
          <div class="mono" style="margin-bottom:4px;">Few-shot examples selected by <code>dspy.BootstrapFewShot</code> for the selected policy version (<code>human_override</code> prioritized at 2.0x).</div>
          <div id="calibrationDemosList" class="anchor-list"></div>
        </div>

        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">Live Human Producer Review Log (<code>screening_labels</code>)</h2>
            <span id="labelsCountBadge" class="pill ok">0 reviews</span>
          </div>
          <div class="mono" style="margin-bottom:4px;">Audit log of every producer decision comparing model verdict vs. human call and recorded <em>"Why"</em> rationale.</div>
          <div id="humanReviewLogList" class="review-log-list"></div>
        </div>
      </div>
    </section>
  </div>
"""
        + _TASTE_PROFILE_SCRIPT
        + """
</body>
</html>
"""
    )


TASTE_PROFILE_HTML = render_taste_profile_page()
