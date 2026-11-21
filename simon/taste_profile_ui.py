"""Stage 3 Taste Profile & Judging Methodology Inspector UI (/taste-profile).

Presents Simon's active judging criteria, 5 shared dossier input-skill rubrics, learned human
overrides, DSPy few-shot calibration anchors, and 4-step methodology around three human-first pillars:
  1. "Where We Are" — Live calibration stage, Firestore counters, policy version selector, & DSPy compiler
  2. "What We Care About" — "What You Taught Us" overrides, Elevate/Watch/Pass bars, gates, & 5 dossier rubrics
  3. "Our Methodology" — Fact-vs-taste 4-step pipeline, DSPy Calibration Demos, & Live Human Review Log
"""

from __future__ import annotations

from typing import Any

from .db_tools import sanitize_agent_report
from .discovery_ui import _SHARED_CSS, render_page_topbar
from .screening import (
    RUBRIC_META,
    RUBRIC_ORDER,
    compile_judging_model,
    list_judging_models,
    list_screening_deck,
    list_screening_labels,
    load_screening_rubrics,
)


def _compute_calibration_stage(human_reviews_count: int, overrides_count: int) -> dict[str, str]:
    """Classify current producer taste calibration maturity for Pillar 1 ('Where We Are')."""
    if human_reviews_count <= 0:
        return {
            "stage": "Bootstrapping",
            "tone": "amber",
            "detail": (
                "Starting with the 5-part A&R scorecard and starter examples. "
                "Review artists on the Screening Deck to teach Simon your taste."
            ),
        }
    if human_reviews_count < 3 and overrides_count < 2:
        return {
            "stage": "Learning Your Taste",
            "tone": "purple",
            "detail": (
                f"Learning from {human_reviews_count} producer review(s) and "
                f"{overrides_count} override(s) at 2x weight."
            ),
        }
    return {
        "stage": "Calibrated",
        "tone": "ok",
        "detail": (
            f"Tuned across {human_reviews_count} producer review(s), with "
            f"{overrides_count} override(s) active in your Instant Taste Engine."
        ),
    }


def _build_input_criteria_catalog(active_policy: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return structured 5-dossier-input criteria combining RUBRIC_META and active questions_config."""
    q_cfg = (active_policy or {}).get("questions_config") or {}
    items: list[dict[str, Any]] = []
    for idx, key in enumerate(RUBRIC_ORDER, start=1):
        meta = RUBRIC_META[key]
        q_entry = q_cfg.get(key) if isinstance(q_cfg.get(key), dict) else {}
        raw_criteria = q_entry.get("criteria") if isinstance(q_entry.get("criteria"), list) else []

        def _tier_text(level_idx: int, fallback: str, criteria: list[Any] = raw_criteria) -> str:
            if level_idx < len(criteria) and isinstance(criteria[level_idx], str):
                cleaned = criteria[level_idx].strip()
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
                    or f"Score {meta['label']} from 0 to 2 using only verified artist dossier facts."
                ),
                "tiers": {
                    "0": _tier_text(0, meta["level_0"]),
                    "1": _tier_text(1, meta["level_1"]),
                    "2": _tier_text(2, meta["level_2"]),
                },
            }
        )
    return items


def build_taste_profile_payload(store: Any) -> dict[str, Any]:
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
  .wrap.wrap-taste { max-width: 1320px; }

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

    const ACRONYM_MAP = {
      ar: 'A&R',
      nyc: 'NYC',
      dm: 'DM',
      dsp: 'DSP',
      ep: 'EP',
      lp: 'LP',
      pct: '%',
    };

    const BLOCK_LABELS = {
      identity_and_contact: 'Identity & Contact',
      source_and_media_queue: 'Media Queue',
      public_footprint: 'Public Footprint',
      comment_forensics: 'Listener Comments',
      live_history_and_credits: 'Live History & Credits',
    };

    const SKILL_LABELS = {
      'dossier-identity': 'Identity',
      'dossier-media': 'Live Media',
      'dossier-footprint': 'Catalog Reach',
      'dossier-audience': 'Audience Pull',
      'dossier-track-record': 'Live Track Record',
    };

    const RUBRIC_LABELS = {
      identity_reachability: 'Identity & Reachability',
      live_vocal_proof: 'Live Vocal Proof',
      early_window_depth: 'Early-Window Catalog Depth',
      listener_pull_cosigns: 'Listener Pull & Scene Cosigns',
      stage_momentum_whitespace: 'Stage Momentum & A&R Whitespace',
    };

    const SOURCE_LABELS = {
      human_override: 'Producer Override',
      human_label: 'Producer Review',
      judge_bootstrap: 'Starter Anchor',
    };

    function titleCaseToken(token) {
      const lower = String(token || '').toLowerCase();
      if (!lower) return '';
      if (ACRONYM_MAP[lower]) return ACRONYM_MAP[lower];
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    }

    function humanizeIdentifier(raw) {
      const text = String(raw || '').trim();
      if (!text) return '';
      return text
        .replace(/[_-]+/g, ' ')
        .split(/\\s+/)
        .map(titleCaseToken)
        .join(' ');
    }

    function formatPolicyLabel(policyId) {
      const raw = String(policyId || 'policy_v1').trim();
      const match = raw.match(/^policy_v(\\d+)$/i);
      if (match) return 'Taste Profile v' + match[1];
      return humanizeIdentifier(raw) || 'Taste Profile v1';
    }

    function formatSourceLabel(source) {
      const key = String(source || 'judge_bootstrap').trim().toLowerCase();
      return SOURCE_LABELS[key] || humanizeIdentifier(key);
    }

    function formatWeight(weight) {
      const num = weight != null ? Number(weight) : 1;
      if (!Number.isFinite(num)) return '1x weight';
      const clean = Number.isInteger(num) ? String(num) : num.toFixed(1).replace(/\\.0$/, '');
      return clean + 'x weight';
    }

    function formatReviewer(handle) {
      const raw = String(handle || '').trim();
      if (!raw || raw.toLowerCase() === 'human_scout') return 'Producer';
      if (!raw.includes('_') && !raw.includes('-')) return raw;
      return humanizeIdentifier(raw);
    }

    function formatBlockLabel(blockKey) {
      const key = String(blockKey || '').trim();
      return BLOCK_LABELS[key] || humanizeIdentifier(key);
    }

    function formatSkillLabel(skillKey) {
      const key = String(skillKey || '').trim();
      return SKILL_LABELS[key] || humanizeIdentifier(key);
    }

    function humanizeText(raw) {
      let text = String(raw || '').trim();
      if (!text) return '';
      // Protect URLs so query parameters are never altered.
      const urls = [];
      text = text.replace(/https?:\\/\\/[^\\s)]+/g, (url) => {
        urls.push(url);
        return '__URL_TOKEN_' + (urls.length - 1) + '__';
      });

      text = text
        .replace(/\\s*\\(dossier-[a-z-]+\\)/gi, '')
        .replace(/grounded Stage 2 dossier facts/gi, 'verified artist dossier facts')
        .replace(/Stage 2 artist dossier/gi, 'artist dossier')
        .replace(/Stage 2 dossier/gi, 'artist dossier')
        .replace(/Stage 3 screening verdict/gi, 'screening verdict')
        .replace(/has_public_business_contact\\s*=\\s*false/gi, 'no public business contact')
        .replace(/has_public_business_contact\\s*=\\s*true/gi, 'public business contact available')
        .replace(/contact_route_type\\s*=\\s*['"]open_dm['"]/gi, 'contact route: open DM')
        .replace(/contact_route_type\\s*=\\s*['"]none['"]/gi, 'contact route: none')
        .replace(/contact_route_type\\s*=\\s*['"]([^'"]+)['"]/gi, (_, v) => 'contact route: ' + humanizeIdentifier(v))
        .replace(/public_team_mentions\\.label\\s*=\\s*['"]([^'"]+)['"]/gi, 'label: $1')
        .replace(/attribution_status\\s*=\\s*['"]([^'"]+)['"]/gi, 'attribution: $1')
        .replace(/label\\s*=\\s*null\\s*,\\s*management\\s*=\\s*null/gi, 'no label or management')
        .replace(/top_release_view_share_pct\\s*=\\s*([0-9.]+%?)/gi, 'top release view share: $1')
        .replace(/\\bopen_dm\\b/gi, 'open DM')
        .replace(/\\bbio_email\\b/gi, 'bio email')
        .replace(/\\bmissing_fields\\b/gi, 'Open Questions');

      Object.keys(BLOCK_LABELS).forEach((key) => {
        text = text.replace(new RegExp('\\\\b' + key + '\\\\b', 'g'), BLOCK_LABELS[key]);
      });
      Object.keys(RUBRIC_LABELS).forEach((key) => {
        text = text.replace(new RegExp('\\\\b' + key + '\\\\b', 'g'), RUBRIC_LABELS[key]);
      });

      // Convert remaining snake_case=value metric pairs into readable phrases.
      text = text.replace(/\\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\\s*=\\s*['"]?([^'",;\\s)]+)['"]?/g, (_, key, val) => {
        const cleanKey = key.replace(/_pct$/i, '').replace(/_/g, ' ');
        const cleanVal = val.includes('_') ? humanizeIdentifier(val) : val;
        return cleanKey + ': ' + cleanVal;
      });

      urls.forEach((url, idx) => {
        text = text.replace('__URL_TOKEN_' + idx + '__', url);
      });
      return text;
    }

    const FALLBACK_RUBRICS = [
      {
        index: 1,
        key: 'identity_reachability',
        label: 'Identity & Reachability',
        skill: 'dossier-identity',
        block: 'identity_and_contact',
        instructions: 'Score Identity & Reachability from 0 to 2 using only verified artist dossier facts.',
        tiers: {
          '0': 'No verified identity links or public contact route.',
          '1': 'Partial platform identity or open DM route, missing business email or home city.',
          '2': 'Clear artist identity, active platform links, and direct business or management contact.'
        }
      },
      {
        index: 2,
        key: 'live_vocal_proof',
        label: 'Live Vocal Proof',
        skill: 'dossier-media',
        block: 'source_and_media_queue',
        instructions: 'Score Live Vocal Proof from 0 to 2 using only verified artist dossier facts.',
        tiers: {
          '0': 'No playable performance clips in the Media Queue.',
          '1': 'Single playable clip or uncertain performer attribution that needs a second take.',
          '2': 'Verified performer attribution with 2+ playable live or acoustic performance clips.'
        }
      },
      {
        index: 3,
        key: 'early_window_depth',
        label: 'Early-Window Catalog Depth',
        skill: 'dossier-footprint',
        block: 'public_footprint',
        instructions: 'Score Early-Window Catalog Depth from 0 to 2 using only verified artist dossier facts.',
        tiers: {
          '0': 'Unknown footprint with zero public reach or catalog metrics.',
          '1': 'Thin single-release catalog or an already established streaming act.',
          '2': 'Early underground or breakout artist with multi-track depth and organic reach.'
        }
      },
      {
        index: 4,
        key: 'listener_pull_cosigns',
        label: 'Listener Pull & Scene Cosigns',
        skill: 'dossier-audience',
        block: 'comment_forensics',
        instructions: 'Score Listener Pull & Scene Cosigns from 0 to 2 using only verified artist dossier facts.',
        tiers: {
          '0': 'Zero sampled comment signal or spam-heavy comment section.',
          '1': 'Modest listener praise without explicit release requests, show requests, or peer cosigns.',
          '2': 'Strong release or live-show demand and notable producer, musician, or curator cosigns.'
        }
      },
      {
        index: 5,
        key: 'stage_momentum_whitespace',
        label: 'Stage Momentum & A&R Whitespace',
        skill: 'dossier-track-record',
        block: 'live_history_and_credits',
        instructions: 'Score Stage Momentum & A&R Whitespace from 0 to 2 using only verified artist dossier facts.',
        tiers: {
          '0': 'Zero documented live show history, upcoming bills, or collaborator credits.',
          '1': 'Early single-room show or credit activity, or active live act already signed to a label.',
          '2': 'Active club billing momentum plus collaborator credits with unsigned label whitespace.'
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
      const match = text.match(/^(.*?)\\s*Human scout\\s+\\w+\\s+guidance:\\s*(.+)$/i);
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
        sel.innerHTML = '<option value="">Taste Profile v1 (Starter)</option>';
        return;
      }
      sel.innerHTML = models.map((m) => {
        const pid = String(m.policy_id || 'policy_v1');
        const displayName = formatPolicyLabel(pid);
        const isAct = Boolean(m.is_active || (activePolicy && activePolicy.policy_id === pid));
        const ovCount = Number(m.override_count || 0);
        const hCount = Number(m.human_label_count || 0);
        const tag = isAct ? ' · Active' : ' · Past version';
        const label = `${displayName}${tag} (${hCount} review${hCount === 1 ? '' : 's'}, ${ovCount} override${ovCount === 1 ? '' : 's'})`;
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
      const activeLabel = formatPolicyLabel(activeId);
      const viewingLabel = formatPolicyLabel(viewingId);
      const isHistorical = Boolean(policy && activePolicy && policy.policy_id !== activePolicy.policy_id);

      const policyBadge = el('activePolicyPill');
      if (policyBadge) {
        policyBadge.textContent = isHistorical
          ? `Viewing ${viewingLabel} (Active: ${activeLabel})`
          : `Active: ${activeLabel}`;
      }

      const notice = el('historicalPolicyNotice');
      if (notice) {
        if (isHistorical) {
          notice.style.display = 'flex';
          notice.innerHTML = `
            <span>Viewing past version <strong>${escapeHtml(viewingLabel)}</strong>. Your active profile is <strong>${escapeHtml(activeLabel)}</strong>.</span>
            <button type="button" class="btn" id="jumpActivePolicyBtn" style="padding:4px 10px; font-size:0.78rem;">Switch to ${escapeHtml(activeLabel)}</button>
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
      const policyCount = Number(summary.policy_count || 1);
      const compiledAt = (policy && policy.compiled_at)
        ? String(policy.compiled_at).replace('T', ' ').replace('Z', ' UTC')
        : 'Live';

      el('whereKpiGrid').innerHTML = `
        <div class="kpi-tile">
          <span class="kpi-label">Selected Profile</span>
          <span class="kpi-value" style="font-size:1.05rem;">${escapeHtml(viewingLabel)}</span>
          <span class="kpi-meta">${isHistorical ? 'Past version' : 'Active profile'} · ${escapeHtml(compiledAt)}</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Calibration Stage</span>
          <span class="kpi-value">${escapeHtml(stageName)}</span>
          <span class="kpi-meta">${escapeHtml(String(policyCount))} saved ${policyCount === 1 ? 'version' : 'versions'}</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Artists Screened</span>
          <span class="kpi-value">${escapeHtml(String(summary.candidates_screened || 0))}</span>
          <span class="kpi-meta">${escapeHtml(String(summary.elevate_count || 0))} Elevate · ${escapeHtml(String(summary.watch_count || 0))} Watch · ${escapeHtml(String(summary.pass_count || 0))} Pass</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Producer Reviews</span>
          <span class="kpi-value">${escapeHtml(String(summary.human_reviews_count || 0))}</span>
          <span class="kpi-meta">${escapeHtml(String((policy && policy.human_label_count) || 0))} included in ${escapeHtml(viewingLabel)}</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Producer Overrides (2x)</span>
          <span class="kpi-value">${escapeHtml(String(summary.overrides_count || 0))}</span>
          <span class="kpi-meta">${escapeHtml(String((policy && policy.override_count) || 0))} active in ${escapeHtml(viewingLabel)}</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Match Rate</span>
          <span class="kpi-value">${escapeHtml(valAcc)}</span>
          <span class="kpi-meta">Elevate &ge; ${escapeHtml(String(elevMin))}/10 · Watch ${escapeHtml(String(watchMin))}–${escapeHtml(String(Math.max(watchMin, elevMin - 1)))}/10</span>
        </div>
        <div class="kpi-tile">
          <span class="kpi-label">Taste Engine</span>
          <span class="kpi-value" style="font-size:0.98rem;">Instant Taste Engine</span>
          <span class="kpi-meta">Updated from your producer reviews</span>
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
            <span>No producer override notes yet. Vote <strong>Elevate</strong>, <strong>Watch</strong>, or <strong>Pass</strong> with a <em>"Why"</em> note on the Screening Deck. Then click <strong>Re-Compile Taste Profile</strong> to apply your instincts at 2x weight.</span>
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
                  ${item.isOverride ? '<span class="pill purple">Producer Override (2x)</span>' : '<span class="pill ok">Confirmed Rule</span>'}
                  ${item.inPolicy ? '<span class="pill blue">Active in Profile</span>' : '<span class="pill amber">Pending Update</span>'}
                </div>
              </div>
              <div style="font-weight:700; color:var(--text);">"${escapeHtml(humanizeText(item.note))}"</div>
              ${item.artist ? `<div class="mono">From review: ${escapeHtml(item.artist)}</div>` : ''}
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
      const baseInst = humanizeText(parsedInst.baseInst)
        || 'Pick Elevate, Watch, or Pass after weighing all 5 scorecard areas and the Advocate vs. Skeptic debate.';
      el('choiceInstructionsBox').innerHTML = `
        <div style="font-size:0.86rem; color:var(--muted); margin-bottom:12px;">
          <strong>How Simon calls a verdict:</strong>
          ${escapeHtml(baseInst)}
          ${parsedInst.overrideFeedback ? `<div style="margin-top:6px;"><span class="pill purple">Active Producer Rule</span> <strong style="color:var(--text);">${escapeHtml(humanizeText(parsedInst.overrideFeedback))}</strong></div>` : ''}
        </div>
      `;

      const cardsMeta = [
        {
          key: 'elevate',
          upper: 'ELEVATE',
          band: `${elevMin}–10 / 10`,
          action: 'Immediate paid-slot or A&R callback',
          fallback: `Score ${elevMin}–10 with verified vocal proof, organic listener demand or peer cosigns, and reachable unsigned whitespace.`
        },
        {
          key: 'watch',
          upper: 'WATCH',
          band: `${watchMin}–${Math.max(watchMin, elevMin - 1)} / 10`,
          action: 'Track and request 1–2 missing details',
          fallback: `Score ${watchMin}–${Math.max(watchMin, elevMin - 1)} showing vocal or audience promise with 1–2 open questions.`
        },
        {
          key: 'pass',
          upper: 'PASS',
          band: `0–${Math.max(0, watchMin - 1)} / 10`,
          action: 'Hold or pass for this cycle',
          fallback: `Score 0–${Math.max(0, watchMin - 1)} or unverified attribution with thin vocal or audience evidence.`
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
            <div style="font-size:0.86rem; color:var(--text); line-height:1.5;">${escapeHtml(humanizeText(parts.baseText))}</div>
            ${parts.humanGuidance
              ? `<div class="human-guidance-callout">
                   <div class="human-guidance-label">Producer Override (2x Weight)</div>
                   <div>${escapeHtml(humanizeText(parts.humanGuidance))}</div>
                 </div>`
              : `<div class="mono" style="margin-top:auto;">No custom ${escapeHtml(meta.upper)} note added yet.</div>`
            }
          </div>
        `;
      }).join('');

      // Binary pass/fail gates
      const gateSpecs = [
        { key: 'sufficient_live_evidence', title: 'Gate 1 · Verified Live Vocal Proof', badge: 'Pass / Fail' },
        { key: 'actionable_whitespace', title: 'Gate 2 · Unsigned Early-Window Whitespace', badge: 'Pass / Fail' },
        { key: 'live_signable', title: 'Composite Gate · Callback Readiness', badge: 'Readiness Check' }
      ];
      const renderedGates = gateSpecs
        .filter((g) => qCfg[g.key] && typeof qCfg[g.key] === 'object')
        .map((g) => {
          const q = qCfg[g.key];
          const crit = q.criteria || {};
          return `
            <div class="noul-card">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong style="font-size:0.88rem;">${escapeHtml(g.title)}</strong>
                <span class="pill blue">${escapeHtml(g.badge)}</span>
              </div>
              <div style="font-size:0.82rem; color:var(--muted);">${escapeHtml(humanizeText(q.instructions || ''))}</div>
              <div class="noul-tf-grid">
                <div class="noul-tf-box true-box">
                  <div style="font-weight:800; font-size:0.72rem; color:var(--teal); text-transform:uppercase; margin-bottom:2px;">Passes When</div>
                  <div>${escapeHtml(humanizeText(crit.true_description || ''))}</div>
                </div>
                <div class="noul-tf-box false-box">
                  <div style="font-weight:800; font-size:0.72rem; color:var(--warn); text-transform:uppercase; margin-bottom:2px;">Fails When</div>
                  <div>${escapeHtml(humanizeText(crit.false_description || ''))}</div>
                </div>
              </div>
            </div>
          `;
        }).join('');
      el('noulGatesContainer').innerHTML = renderedGates || '<div class="mono">No hard gates configured.</div>';

      // Composite Fit 0..4 ladder
      const compFit = qCfg.composite_fit || {};
      const compCriteria = Array.isArray(compFit.criteria) ? compFit.criteria : [];
      el('compositeFitInstructions').textContent = humanizeText(compFit.instructions)
        || 'Rate overall A&R and showcase fit from 0 to 4.';
      el('compositeFitLadder').innerHTML = compCriteria.map((line, idx) => {
        const text = humanizeText(stripTierPrefix(line, idx));
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
        const instructions = humanizeText(qEntry.instructions || item.instructions || '');
        const rawArr = Array.isArray(qEntry.criteria) ? qEntry.criteria : [];
        const t0 = humanizeText(rawArr[0] ? stripTierPrefix(rawArr[0], 0) : (item.tiers && item.tiers['0']) || '');
        const t1 = humanizeText(rawArr[1] ? stripTierPrefix(rawArr[1], 1) : (item.tiers && item.tiers['1']) || '');
        const t2 = humanizeText(rawArr[2] ? stripTierPrefix(rawArr[2], 2) : (item.tiers && item.tiers['2']) || '');
        const num = item.index || (idx + 1);

        return `
          <div class="criteria-card" data-rubric-key="${escapeHtml(item.key)}">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px; flex-wrap:wrap;">
              <div>
                <div style="font-weight:800; font-size:0.98rem; color:var(--text);">${escapeHtml(String(num))}. ${escapeHtml(item.label)}</div>
                <div class="mono" style="margin-top:2px;">Dossier Section: ${escapeHtml(formatBlockLabel(item.block))}</div>
              </div>
              <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                <span class="pill blue">${escapeHtml(formatSkillLabel(item.skill))}</span>
                <span class="pill purple">0–2 pts</span>
              </div>
            </div>
            <div style="font-size:0.83rem; color:var(--muted);">${escapeHtml(instructions)}</div>
            <div class="criteria-tiers">
              <div class="tier-cell pt-0">
                <span class="tier-badge">0 pt · Weak or Missing</span>
                <span>${escapeHtml(t0)}</span>
              </div>
              <div class="tier-cell pt-1">
                <span class="tier-badge">1 pt · Partial or Mixed</span>
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
        demoBadge.textContent = `${demos.length} example${demos.length === 1 ? '' : 's'}`;
      }

      if (!demos.length) {
        el('calibrationDemosList').innerHTML = '<div class="mono">No calibration examples saved for this version yet.</div>';
      } else {
        el('calibrationDemosList').innerHTML = demos.map((d) => {
          const verdict = String(d.target_verdict || d.verdict || 'watch').toUpperCase();
          const src = String(d.source || 'judge_bootstrap');
          const isOverride = src === 'human_override';
          const srcPillCls = isOverride ? 'purple' : (src === 'human_label' ? 'ok' : 'amber');
          const srcLabel = formatSourceLabel(src);
          const weightLabel = formatWeight(d.weight);
          const pros = Array.isArray(d.pros) ? d.pros.slice(0, 2).map(humanizeText) : [];
          const cons = Array.isArray(d.cons) ? d.cons.slice(0, 2).map(humanizeText) : [];

          return `
            <div class="anchor-card ${isOverride ? 'is-override' : ''}">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong style="font-size:0.94rem;">${escapeHtml(d.stage_name || d.lead_id || 'Artist')}</strong>
                <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                  <span class="verdict-pill ${escapeHtml(verdict)}" style="padding:2px 9px; font-size:0.72rem;">${escapeHtml(verdict)}</span>
                  <span class="pill" style="font-family:var(--mono);">${escapeHtml(String(d.total_score != null ? d.total_score : '—'))}/10</span>
                  <span class="pill ${srcPillCls}">${escapeHtml(srcLabel)} · ${escapeHtml(weightLabel)}</span>
                </div>
              </div>
              ${d.reason ? `<div style="color:var(--text);"><strong>Rationale:</strong> ${escapeHtml(humanizeText(d.reason))}</div>` : ''}
              ${pros.length ? `<div class="mono" style="color:var(--teal);">+ Strengths: ${escapeHtml(pros.join(' · '))}</div>` : ''}
              ${cons.length ? `<div class="mono" style="color:var(--warn);">&minus; Watchouts: ${escapeHtml(cons.join(' · '))}</div>` : ''}
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
            <div style="color:var(--muted);">No producer reviews logged yet.</div>
            <div><a class="btn" href="/screen">Open Screening Deck to Vote →</a></div>
          </div>
        `;
      } else {
        el('humanReviewLogList').innerHTML = safeLabels.map((lbl) => {
          const hVerdict = String(lbl.human_verdict || 'watch').toUpperCase();
          const mVerdict = lbl.model_verdict ? String(lbl.model_verdict).toUpperCase() : 'UNSET';
          const isOverride = lbl.agreed_with_model === false;
          const agreedBadge = isOverride
            ? '<span class="pill purple">Producer Override (2x)</span>'
            : '<span class="pill ok">Agreed</span>';
          const stamp = lbl.labeled_at ? String(lbl.labeled_at).replace('T', ' ').replace('Z', ' UTC') : '';

          return `
            <div class="review-log-card ${isOverride ? 'is-override' : ''}">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong style="font-size:0.94rem;">${escapeHtml(lbl.stage_name || lbl.lead_id || 'Artist')}</strong>
                <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                  <span class="mono">Simon: <strong>${escapeHtml(mVerdict)}</strong> &rarr; You:</span>
                  <span class="verdict-pill ${escapeHtml(hVerdict)}" style="padding:2px 9px; font-size:0.72rem;">${escapeHtml(hVerdict)}</span>
                  ${agreedBadge}
                </div>
              </div>
              <div style="color:var(--text);">
                ${lbl.reason ? `<strong>Why:</strong> "${escapeHtml(humanizeText(lbl.reason))}"` : '<span class="mono">No note added.</span>'}
              </div>
              <div class="mono" style="display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;">
                <span>Reviewer: ${escapeHtml(formatReviewer(lbl.reviewer))}</span>
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
      showBanner('Updating your Taste Profile from your latest producer reviews…', 'info');
      try {
        const res = await fetch('/api/screening/train', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Could not update Taste Profile');
        const newPolicy = data.policy || data;
        selectedPolicyId = newPolicy.policy_id || null;
        await loadTasteProfile(true);
        const newLabel = formatPolicyLabel(newPolicy.policy_id || '');
        const revCount = Number(newPolicy.human_label_count || 0);
        const ovCount = Number(newPolicy.override_count || 0);
        showBanner(
          `Updated ${newLabel} (${revCount} producer review${revCount === 1 ? '' : 's'}, ${ovCount} override${ovCount === 1 ? '' : 's'}).`,
          'info'
        );
      } catch (err) {
        showBanner(err.message || 'Could not update Taste Profile.', 'err');
      } finally {
        btn.disabled = false;
      }
    };

    loadTasteProfile(false);
  </script>
"""


def render_taste_profile_page() -> str:
    """Render the `/taste-profile` ('8. Taste Profile') HTML page."""
    topbar = render_page_topbar("/taste-profile", "Taste Profile")
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · 8. Taste Profile</title>
  <style>"""
        + _SHARED_CSS
        + _TASTE_PROFILE_CSS
        + """</style>
</head>
<body>
  """
        + topbar
        + """
  <div class="wrap wrap-taste">
    <div class="page-hero">
      <h1>8. Taste Profile <span class="pill purple">Stage 4</span></h1>
      <p>See how Simon matches your A&amp;R taste across 5 scorecard criteria, producer overrides, and calibration examples.</p>
    </div>

    <div id="tasteBanner" class="banner"></div>

    <!-- PILLAR 1: WHERE WE ARE -->
    <section class="pillar-section pillar-hero" id="pillarWhereWeAre" aria-label="Where We Are">
      <div class="pillar-top">
        <div>
          <div class="pillar-kicker">Pillar 1 · Live Calibration Snapshot</div>
          <h2 class="pillar-title">
            1. Where We Are
            <span id="calibrationStageBadge" class="pill amber">Stage: Loading…</span>
            <span id="activePolicyPill" class="pill purple">Active: Taste Profile v1</span>
          </h2>
          <p class="pillar-sub" id="whereStageDetail">Loading your Screening Deck, producer reviews, and active Taste Profile…</p>
        </div>

        <div class="toolbar-actions">
          <label for="policyVersionSelect" class="mono" style="font-weight:700;">Profile Version:</label>
          <select id="policyVersionSelect" aria-label="Select Taste Profile version">
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
          <div class="pillar-kicker">Pillar 2 · Active Criteria, Verdict Bar &amp; Producer Rules</div>
          <h2 class="pillar-title">
            2. What We Care About
            <span class="pill purple">5 Criteria &times; 0–2 pts = 10 pts</span>
            <span class="pill ok">Instant Taste Engine</span>
          </h2>
          <p class="pillar-sub">Simon scores every artist with clear, inspectable rules. It blends baseline A&amp;R checks with overrides from your Screening Deck votes.</p>
        </div>
      </div>

      <!-- Highlighted "What You Taught Us" Box -->
      <div class="taught-box" id="whatYouTaughtUsBox">
        <div class="taught-head">
          <h3>
            What You Taught Us
            <span id="taughtCountBadge" class="pill purple">0 producer rules</span>
          </h3>
          <span class="mono">Your overrides count <strong>2x</strong> when updating your Taste Profile</span>
        </div>
        <div id="whatYouTaughtUsContent" class="mono">Loading your producer notes…</div>
      </div>

      <!-- Elevate / Watch / Pass Choice Cards -->
      <div class="section-head" style="margin-bottom:8px;">
        <h2>Verdict Bar (Elevate &middot; Watch &middot; Pass) &amp; Producer Rules</h2>
        <span class="pill purple">3-Tier Call</span>
      </div>
      <div id="choiceInstructionsBox"></div>
      <div id="verdictCardsGrid" class="verdict-cards-grid"></div>

      <!-- Global Hard Gates + 0-4 Showcase Fit Scale -->
      <div class="gates-grid">
        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">Global Hard Gates (Pass / Fail)</h2>
            <span class="pill blue">Must-Pass Checks</span>
          </div>
          <div id="noulGatesContainer" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>

        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">Overall Showcase Fit (0–4)</h2>
            <span class="pill purple">0–4 Fit Scale</span>
          </div>
          <div id="compositeFitInstructions" class="mono" style="margin-bottom:4px;"></div>
          <div id="compositeFitLadder" class="ladder-list"></div>
        </div>
      </div>

      <!-- The 5 Artist Scorecard Criteria (0-2 pts each = 10 pts total) -->
      <div class="section-head" style="margin-top:6px;">
        <h2>The 5 Artist Scorecard Criteria (0–2 pts each = 10 pts)</h2>
        <span class="pill blue">5 Core Areas</span>
      </div>
      <div id="dossierCriteriaGrid" class="dossier-criteria-grid"></div>
    </section>

    <!-- PILLAR 3: OUR METHODOLOGY -->
    <section class="pillar-section" id="pillarOurMethodology" aria-label="Our Methodology">
      <div class="pillar-top">
        <div>
          <div class="pillar-kicker">Pillar 3 · Fact-vs-Taste Process &amp; Audit Trail</div>
          <h2 class="pillar-title">
            3. Our Methodology: How Simon Separates Facts from Taste
            <span class="pill ok">Fact-Checked Process</span>
          </h2>
          <p class="pillar-sub">Research scouts never rank artists or guess. Taste enters only during screening, where balanced debate meets your producer votes.</p>
        </div>
        <div class="toolbar-actions">
          <a href="/evals" class="btn">Inspect Quality Evals →</a>
          <a href="/screen" class="btn">Vote on Screening Deck →</a>
        </div>
      </div>

      <div class="methodology-steps-grid">
        <div class="method-step-card">
          <span class="method-step-num">Step 1 · Artist Research</span>
          <h3>Fact-Only Dossier</h3>
          <p>Our research scout gathers 5 factual sections: identity, media queue, catalog reach, comments, and live history. It never ranks artists and marks unverified details as <strong>Open Questions</strong>.</p>
          <span class="pill" style="margin-top:auto; align-self:flex-start;">Fact-Only Dossier</span>
        </div>

        <div class="method-step-card">
          <span class="method-step-num">Step 2 · Balanced Debate</span>
          <h3>Advocate &amp; Skeptic Debate</h3>
          <p>The Advocate builds the upside case, highlighting strengths and the <strong>Standout Hook</strong>. The Skeptic flags risks and dealbreakers. The Judge then scores the artist from 0 to 10.</p>
          <span class="pill amber" style="margin-top:auto; align-self:flex-start;">Screening Packet</span>
        </div>

        <div class="method-step-card">
          <span class="method-step-num">Step 3 · Producer Review</span>
          <h3>Producer Override (2x Weight)</h3>
          <p>On <a href="/screen">7. Screening Deck</a>, you watch live clips and vote <strong>Elevate</strong>, <strong>Watch</strong>, or <strong>Pass</strong> with a <em>"Why"</em> note. Your overrides carry <strong>2x weight</strong>.</p>
          <span class="pill purple" style="margin-top:auto; align-self:flex-start;">Producer Override (2x Weight)</span>
        </div>

        <div class="method-step-card">
          <span class="method-step-num">Step 4 · Instant Taste Engine</span>
          <h3>Live Taste Profile</h3>
          <p>Simon updates your score cutoffs, producer rules, and <strong>Calibration Examples</strong> into one Taste Profile. Every new artist is scored instantly against your taste.</p>
          <span class="pill ok" style="margin-top:auto; align-self:flex-start;">Instant Taste Engine</span>
        </div>
      </div>

      <!-- Calibration Examples & Producer Review Log -->
      <div class="calibration-split-grid">
        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">Calibration Examples</h2>
            <span id="demosCountBadge" class="pill purple">0 examples</span>
          </div>
          <div class="mono" style="margin-bottom:4px;">Reference artists guiding this Taste Profile. Your overrides carry 2x weight.</div>
          <div id="calibrationDemosList" class="anchor-list"></div>
        </div>

        <div class="gate-panel">
          <div class="section-head" style="margin-bottom:4px;">
            <h2 style="font-size:0.98rem;">Producer Review Log</h2>
            <span id="labelsCountBadge" class="pill ok">0 reviews</span>
          </div>
          <div class="mono" style="margin-bottom:4px;">Every producer vote comparing Simon's call, your final call, and your <em>"Why"</em> note.</div>
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
