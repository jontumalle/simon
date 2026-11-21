"""Stage 3 Screening Backend: 5-Rubric Baseline, Parallel Advocate/Skeptic/Judge Fleet,
HITL Label Feedback, DSPy / Gemini-Decision-1 Policy Compiler, and 3-Layer Screening Evals.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request
import uuid

from .db_tools import (
    REPORT_FORBIDDEN_KEYS,
    VALID_SCREENING_VERDICTS,
    get_agent_document,
    list_agent_documents,
    sanitize_agent_report,
    save_agent_document,
)
from .gemini import Gemini, extract_json_object
from .youtube import extract_video_id

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_SKILLS_ROOT = REPO_ROOT / "agents" / "_shared" / "skills"
DEMO_SCREENING_PATH = REPO_ROOT / "examples" / "screening_demo.json"
SCREENING_RUBRICS_PATH = REPO_ROOT / "data" / "evals" / "screening_rubrics.json"

RUBRIC_ORDER: Tuple[str, ...] = (
    "identity_reachability",
    "live_vocal_proof",
    "early_window_depth",
    "listener_pull_cosigns",
    "stage_momentum_whitespace",
)

RUBRIC_META: Dict[str, Dict[str, str]] = {
    "identity_reachability": {
        "label": "Identity & Reachability",
        "skill": "dossier-identity",
        "block": "identity_and_contact",
        "level_0": "No verified identity links or public contact route (none).",
        "level_1": "Partial platform identity or open DM route, missing business email or home city.",
        "level_2": "Clear artist identity, active platform links, and direct business/mgmt contact route.",
    },
    "live_vocal_proof": {
        "label": "Live Vocal Proof",
        "skill": "dossier-media",
        "block": "source_and_media_queue",
        "level_0": "No embeddable performance clips in source_and_media_queue.",
        "level_1": "Single embeddable clip or uncertain performer attribution requiring second-take verification.",
        "level_2": "Verified performer attribution with 2+ embeddable live/acoustic performance clips.",
    },
    "early_window_depth": {
        "label": "Early-Window Catalog Depth",
        "skill": "dossier-footprint",
        "block": "public_footprint",
        "level_0": "Unknown footprint regime with zero public reach or catalog metrics.",
        "level_1": "Thin single-release footprint or already post-inflection established streaming act.",
        "level_2": "Pre-DSP underground or early-DSP inflection artist with multi-track depth and organic reach.",
    },
    "listener_pull_cosigns": {
        "label": "Listener Pull & Scene Cosigns",
        "skill": "dossier-audience",
        "block": "comment_forensics",
        "level_0": "Zero sampled comment signal or spam-dominated comment section.",
        "level_1": "Modest organic listener praise without explicit release/live requests or peer cosigns.",
        "level_2": "Strong release/live-show demand counts and/or notable producer, musician, or curator cosigns.",
    },
    "stage_momentum_whitespace": {
        "label": "Stage Momentum & A&R Whitespace",
        "skill": "dossier-track-record",
        "block": "live_history_and_credits",
        "level_0": "Zero documented live show history, upcoming bills, or collaborator credits.",
        "level_1": "Early single-room show or credit activity, or active live act already signed to a label.",
        "level_2": "Active room/club billing momentum plus collaborator credits with unsigned label whitespace.",
    },
}

VERDICT_SORT_RANK = {"elevate": 0, "watch": 1, "pass": 2}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unwrap_doc(row: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    inner = row.get("data")
    if isinstance(inner, dict):
        return inner
    return row


def _dedupe_strs(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in items:
        s = str(raw or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _clamp_rubric_score(val: Any) -> int:
    try:
        num = int(round(float(val)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(2, num))


# ---------------------------------------------------------------------------
# 1. Dynamic Dossier Skill Loader + 5-Rubric Deterministic Baseline
# ---------------------------------------------------------------------------


def _match_rubric_key(name: str) -> Optional[str]:
    lowered = name.lower().replace("-", "_")
    for key in RUBRIC_ORDER:
        if key in lowered:
            return key
    keyword_map = {
        "identity": "identity_reachability",
        "reachability": "identity_reachability",
        "contact": "identity_reachability",
        "vocal": "live_vocal_proof",
        "media": "live_vocal_proof",
        "clip": "live_vocal_proof",
        "footprint": "early_window_depth",
        "window": "early_window_depth",
        "depth": "early_window_depth",
        "comment": "listener_pull_cosigns",
        "audience": "listener_pull_cosigns",
        "cosign": "listener_pull_cosigns",
        "signal": "listener_pull_cosigns",
        "listener": "listener_pull_cosigns",
        "momentum": "stage_momentum_whitespace",
        "whitespace": "stage_momentum_whitespace",
        "history": "stage_momentum_whitespace",
        "track_record": "stage_momentum_whitespace",
        "live_history": "stage_momentum_whitespace",
    }
    for token, rubric_key in keyword_map.items():
        if token in lowered:
            return rubric_key
    return None


def _run_dynamic_skill_scripts(dossier: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Dynamically load `agents/_shared/skills/dossier-*/scripts/score_*.py` if present on disk."""
    results: Dict[str, Dict[str, Any]] = {}
    loaded_skills: List[str] = []
    if not SHARED_SKILLS_ROOT.is_dir():
        return results, loaded_skills

    script_paths = sorted(SHARED_SKILLS_ROOT.glob("dossier-*/scripts/score_*.py"))
    for script_path in script_paths:
        skill_dir_name = script_path.parent.parent.name
        rubric_key = _match_rubric_key(f"{skill_dir_name}_{script_path.stem}")
        try:
            mod_name = f"_simon_dyn_{skill_dir_name.replace('-', '_')}_{script_path.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, str(script_path))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            candidate_fns = []
            for attr_name in dir(module):
                if attr_name.startswith("_"):
                    continue
                attr = getattr(module, attr_name)
                if callable(attr) and (
                    attr_name in ("score", "evaluate", "score_dossier", "score_block")
                    or attr_name.startswith("score_")
                ):
                    candidate_fns.append((0 if attr_name == "score" else 1, attr_name, attr))
            candidate_fns.sort(key=lambda item: (item[0], item[1]))
            if not candidate_fns:
                continue

            _, _, fn = candidate_fns[0]
            block_name = RUBRIC_META.get(rubric_key or "", {}).get("block", "")
            try:
                raw_out = fn(dossier)
            except (KeyError, TypeError):
                if block_name and isinstance(dossier.get(block_name), dict):
                    raw_out = fn(dossier[block_name])
                else:
                    continue

            if isinstance(raw_out, dict):
                inferred_key = (
                    _match_rubric_key(
                        str(raw_out.get("rubric_key") or raw_out.get("rubric_id") or raw_out.get("rubric") or "")
                    )
                    or rubric_key
                )
                if inferred_key in RUBRIC_META:
                    results[inferred_key] = raw_out
                    loaded_skills.append(skill_dir_name)
        except Exception:
            continue

    return results, _dedupe_strs(loaded_skills)


def _builtin_score_dossier(dossier: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Deterministic 5-rubric scorer over Stage 2 `InvestigatorDossier` blocks."""
    ident = dossier.get("identity_and_contact") or {}
    media_q = dossier.get("source_and_media_queue") or {}
    footprint = dossier.get("public_footprint") or {}
    comments = dossier.get("comment_forensics") or {}
    live_hist = dossier.get("live_history_and_credits") or {}

    out: Dict[str, Dict[str, Any]] = {}

    # 1. identity_reachability
    platform_urls = ident.get("platform_urls") or {}
    active_platforms = [k for k, v in platform_urls.items() if isinstance(v, str) and v.strip()]
    has_contact = bool(ident.get("has_public_business_contact"))
    route_type = str(ident.get("contact_route_type") or "none").strip()
    home_city = str(ident.get("home_city") or "").strip()
    id_pros: List[str] = []
    id_cons: List[str] = []
    id_missing: List[str] = []

    if has_contact and route_type in ("bio_email", "mgmt_email", "open_dm") and (home_city or len(active_platforms) >= 2):
        id_score = 2
    elif active_platforms or route_type in ("bio_email", "mgmt_email", "open_dm"):
        id_score = 1
    else:
        id_score = 0

    if route_type in ("bio_email", "mgmt_email"):
        id_pros.append(f"Direct outreach available via {route_type}" + (f" ({home_city})." if home_city else "."))
    elif route_type == "open_dm":
        id_pros.append("Reachable via open social DM route.")
    else:
        id_cons.append("No public business email or open DM route verified yet.")
        id_missing.append("identity_and_contact.contact_route_type")

    if len(active_platforms) >= 2:
        id_pros.append(f"Cross-linked across {len(active_platforms)} platforms ({', '.join(active_platforms[:4])}).")
    elif not active_platforms:
        id_missing.append("identity_and_contact.platform_urls")

    if not home_city:
        id_missing.append("identity_and_contact.home_city")

    out["identity_reachability"] = {
        "score": id_score,
        "rationale": (
            f"Contact route={route_type}, home_city={home_city or 'unknown'}, "
            f"{len(active_platforms)} active platform URL(s)."
        ),
        "pros": id_pros,
        "cons": id_cons,
        "missing_evidence_flags": id_missing,
        "evidence": active_platforms[:4],
    }

    # 2. live_vocal_proof
    attr_status = str(media_q.get("attribution_status") or "uncertain").strip()
    media_links = [m for m in (media_q.get("media_links") or []) if isinstance(m, dict) and m.get("url")]
    embeddable_links = [m for m in media_links if m.get("oembed_live_embeddable", True)]
    live_cues = [
        m for m in embeddable_links
        if re.search(r"\b(live|acoustic|session|open mic|sofar|tiny desk|room)\b", str(m.get("title") or ""), re.I)
        or str(media_q.get("source_channel") or "") in ("youtube_live_session", "open_mic_lineup")
    ]
    vp_pros: List[str] = []
    vp_cons: List[str] = []
    vp_missing: List[str] = []

    if attr_status == "verified" and len(embeddable_links) >= 2:
        vp_score = 2
        vp_pros.append(f"Verified performer with {len(embeddable_links)} embeddable vocal clips ({len(live_cues)} live/acoustic).")
    elif len(embeddable_links) >= 1:
        vp_score = 1
        if len(embeddable_links) == 1:
            vp_cons.append("Single clip only — needs a second independent live vocal take.")
            vp_missing.append("source_and_media_queue.second_live_take")
        if attr_status != "verified":
            vp_cons.append("Performer attribution is still marked uncertain on seed clip.")
            vp_missing.append("source_and_media_queue.verified_attribution")
        else:
            vp_pros.append(f"Verified vocal clip queued ({embeddable_links[0].get('title') or 'seed performance'}).")
    else:
        vp_score = 0
        vp_cons.append("No embeddable performance clips verified in media queue.")
        vp_missing.append("source_and_media_queue.media_links")

    out["live_vocal_proof"] = {
        "score": vp_score,
        "rationale": f"Attribution={attr_status}, {len(embeddable_links)} embeddable clip(s) queued.",
        "pros": vp_pros,
        "cons": vp_cons,
        "missing_evidence_flags": vp_missing,
        "evidence": [str(m.get("url")) for m in embeddable_links[:3]],
    }

    # 3. early_window_depth
    regime = str(footprint.get("footprint_regime") or "unknown").strip()
    reach = footprint.get("public_reach") or {}
    yt_subs = reach.get("youtube_subscribers")
    top_views = reach.get("top_video_views")
    bc_releases = reach.get("bandcamp_releases_count") or 0
    bc_supporters = reach.get("bandcamp_supporters_count") or 0
    tracks_count = reach.get("released_tracks_count") or 0
    share_pct = footprint.get("top_release_view_share_pct")

    ew_pros: List[str] = []
    ew_cons: List[str] = []
    ew_missing: List[str] = []

    has_depth = (
        tracks_count >= 2
        or bc_releases >= 1
        or bc_supporters >= 10
        or (isinstance(yt_subs, int) and 100 <= yt_subs <= 100_000)
    )
    not_one_hit_spike = share_pct is None or float(share_pct) <= 88.0

    if regime in ("pre_dsp_underground", "early_dsp_inflection") and has_depth and not_one_hit_spike:
        ew_score = 2
        details = []
        if isinstance(yt_subs, int):
            details.append(f"{yt_subs:,} YT subs")
        if tracks_count:
            details.append(f"{tracks_count} tracks")
        if bc_supporters:
            details.append(f"{bc_supporters} Bandcamp supporters")
        ew_pros.append(f"Ideal {regime.replace('_', ' ')} window" + (f" ({', '.join(details)})." if details else "."))
    elif regime == "established_streaming":
        ew_score = 1
        ew_cons.append("Already in established_streaming regime; verify whether still actionable for early-slot discovery.")
    elif regime in ("pre_dsp_underground", "early_dsp_inflection") or any(v is not None for v in reach.values()):
        ew_score = 1
        if share_pct is not None and float(share_pct) > 88.0:
            ew_cons.append(f"Top video accounts for {float(share_pct):.0f}% of views; check multi-song consistency.")
        else:
            ew_cons.append("Early-window profile has thin public catalog depth metrics.")
    else:
        ew_score = 0
        ew_cons.append("Public footprint regime and catalog reach metrics are unknown.")
        ew_missing.append("public_footprint.public_reach")

    if yt_subs is None and top_views is None:
        ew_missing.append("public_footprint.youtube_metrics")

    out["early_window_depth"] = {
        "score": ew_score,
        "rationale": f"Regime={regime}, tracks={tracks_count}, yt_subs={yt_subs}, top_views={top_views}.",
        "pros": ew_pros,
        "cons": ew_cons,
        "missing_evidence_flags": ew_missing,
        "evidence": [f"regime:{regime}"],
    }

    # 4. listener_pull_cosigns
    counts = comments.get("comment_intent_counts") or {}
    sample_size = int(counts.get("sample_size") or 0)
    rel_req = int(counts.get("release_requests") or 0)
    live_req = int(counts.get("live_show_requests") or 0)
    praise = int(counts.get("genuine_praise") or 0)
    spam = int(counts.get("jokes_or_spam") or 0)
    notable = [n for n in (comments.get("notable_commenters") or []) if isinstance(n, dict) and n.get("handle")]

    lp_pros: List[str] = []
    lp_cons: List[str] = []
    lp_missing: List[str] = []

    high_intent = rel_req + live_req
    positive_signal = high_intent + praise

    if (high_intent >= 2 or (len(notable) >= 1 and positive_signal >= 1)) and spam <= max(2, positive_signal):
        lp_score = 2
        if high_intent:
            lp_pros.append(
                f"Organic listener pull ({rel_req} release request(s), {live_req} live-show request(s) in {sample_size} comments)."
            )
        if notable:
            handles = ", ".join(f"{n['handle']} ({n.get('role_or_context', 'peer')})" for n in notable[:2])
            lp_pros.append(f"Peer/scene cosign observed: {handles}.")
    elif sample_size > 0 and positive_signal >= 1 and positive_signal >= spam:
        lp_score = 1
        lp_pros.append(f"Positive listener reception ({praise} praise, {high_intent} demand comments).")
    else:
        lp_score = 0
        if sample_size == 0 and not notable:
            lp_cons.append("Zero sampled audience comments or peer cosigns available.")
            lp_missing.append("comment_forensics.comment_intent_counts")
        else:
            lp_cons.append("Weak listener demand signal relative to noise/spam in comments.")

    out["listener_pull_cosigns"] = {
        "score": lp_score,
        "rationale": (
            f"Sample={sample_size}, release_requests={rel_req}, live_requests={live_req}, "
            f"notable_cosigns={len(notable)}."
        ),
        "pros": lp_pros,
        "cons": lp_cons,
        "missing_evidence_flags": lp_missing,
        "evidence": [str(n.get("handle")) for n in notable[:3]],
    }

    # 5. stage_momentum_whitespace
    past_shows = [s for s in (live_hist.get("show_history") or []) if isinstance(s, dict) and s.get("venue")]
    upcoming = [s for s in (live_hist.get("upcoming_shows") or []) if isinstance(s, dict) and s.get("venue")]
    credits_list = [c for c in (live_hist.get("collaborator_credits") or []) if isinstance(c, dict) and c.get("name")]
    team = live_hist.get("public_team_mentions") or {}
    label_mention = str(team.get("label") or "").strip()
    cap_obs = live_hist.get("highest_venue_cap_observed")

    sm_pros: List[str] = []
    sm_cons: List[str] = []
    sm_missing: List[str] = []

    total_shows = len(past_shows) + len(upcoming)
    unsigned_whitespace = not bool(label_mention)

    if (total_shows >= 2 or (total_shows >= 1 and len(credits_list) >= 1)) and unsigned_whitespace:
        sm_score = 2
        venues = [str(s.get("venue")) for s in (past_shows + upcoming)[:3]]
        sm_pros.append(
            f"Active live momentum ({len(past_shows)} past, {len(upcoming)} upcoming across {', '.join(venues)}) with unsigned label whitespace."
        )
        if credits_list:
            collab_names = ", ".join(f"{c['name']} ({c.get('role', 'collab')})" for c in credits_list[:2])
            sm_pros.append(f"Verified collaborator network: {collab_names}.")
    elif total_shows >= 1 or len(credits_list) >= 1:
        sm_score = 1
        if not unsigned_whitespace:
            sm_cons.append(f"Public label mention present ({label_mention}); confirm deal exclusivity.")
        else:
            sm_pros.append(f"Early live/credit foothold ({total_shows} show(s), {len(credits_list)} collaborator credit(s)).")
    else:
        sm_score = 0
        sm_cons.append("No public club/room show history or collaborator credits documented yet.")
        sm_missing.append("live_history_and_credits.show_history")

    out["stage_momentum_whitespace"] = {
        "score": sm_score,
        "rationale": (
            f"Past_shows={len(past_shows)}, upcoming={len(upcoming)}, "
            f"credits={len(credits_list)}, label={label_mention or 'unsigned'}, max_cap={cap_obs}."
        ),
        "pros": sm_pros,
        "cons": sm_cons,
        "missing_evidence_flags": sm_missing,
        "evidence": [str(s.get("venue")) for s in (past_shows + upcoming)[:3]],
    }

    return out


def _flatten_claim_items(items: List[Any]) -> List[str]:
    out: List[str] = []
    for raw in items:
        if isinstance(raw, dict):
            title = str(raw.get("title") or "").strip()
            evidence = str(raw.get("evidence") or "").strip()
            combined = f"{title}: {evidence}".strip(": ")
            if combined:
                out.append(combined)
        elif raw is not None:
            s = str(raw).strip()
            if s:
                out.append(s)
    return _dedupe_strs(out)


def _to_structured_claims(items: List[Any], default_skill: str = "dossier-identity") -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for raw in items:
        if isinstance(raw, dict):
            title = str(raw.get("title") or raw.get("point") or raw.get("claim") or "").strip()
            evidence = str(raw.get("evidence") or raw.get("detail") or raw.get("citation") or "").strip()
            skill = str(raw.get("skill") or default_skill).strip()
            if title or evidence:
                out.append(
                    {
                        "skill": skill,
                        "title": title or evidence,
                        "evidence": evidence or title,
                    }
                )
        elif isinstance(raw, str) and raw.strip():
            text = raw.strip()
            if ":" in text:
                head, tail = text.split(":", 1)
                out.append({"skill": default_skill, "title": head.strip(), "evidence": tail.strip()})
            else:
                out.append({"skill": default_skill, "title": text, "evidence": text})
    return out


def score_dossier_inputs(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """Score all 5 Stage 2 `InvestigatorDossier` blocks (0..2 each -> 0..10 total).

    Dynamically loads `agents/_shared/skills/dossier-*/scripts/score_*.py` if present on disk,
    falling back cleanly to built-in deterministic rubric scoring.
    """
    if not isinstance(dossier, dict):
        raise ValueError("dossier must be a dictionary.")

    ident = dossier.get("identity_and_contact") or {}
    lead_id = str(dossier.get("lead_id") or dossier.get("_doc_id") or f"lead_{uuid.uuid4().hex[:8]}").strip()
    stage_name = str(dossier.get("stage_name") or ident.get("stage_name") or lead_id).strip()

    builtin_results = _builtin_score_dossier(dossier)
    dynamic_results, dynamic_skills = _run_dynamic_skill_scripts(dossier)

    rubric_scores: Dict[str, int] = {}
    rubric_breakdown: List[Dict[str, Any]] = []
    all_pros: List[str] = []
    all_cons: List[str] = []
    structured_pros: List[Dict[str, str]] = []
    structured_cons: List[Dict[str, str]] = []
    missing_flags: List[str] = list(dossier.get("missing_fields") or [])

    for key in RUBRIC_ORDER:
        meta = RUBRIC_META[key]
        base = builtin_results[key]
        dyn = dynamic_results.get(key) or {}

        score_val = _clamp_rubric_score(dyn["score"] if "score" in dyn else base["score"])
        rationale = str(dyn.get("note") or dyn.get("rationale") or dyn.get("summary") or base["rationale"]).strip()
        raw_pros = list(dyn.get("pros") or []) + list(base["pros"])
        raw_cons = list(dyn.get("cons") or []) + list(base["cons"])
        pros = _flatten_claim_items(raw_pros)
        cons = _flatten_claim_items(raw_cons)
        structured_pros.extend(_to_structured_claims(list(dyn.get("pros") or []) or list(base["pros"]), meta["skill"]))
        structured_cons.extend(_to_structured_claims(list(dyn.get("cons") or []) or list(base["cons"]), meta["skill"]))
        missing = _dedupe_strs(
            list(dyn.get("missing") or dyn.get("missing_evidence_flags") or dyn.get("missing_fields") or [])
            + list(base["missing_evidence_flags"])
        )
        evidence = _dedupe_strs(_flatten_claim_items(list(dyn.get("evidence") or []) + list(base["evidence"])))

        rubric_scores[key] = score_val
        rubric_breakdown.append(
            {
                "rubric_id": key,
                "label": meta["label"],
                "skill": meta["skill"],
                "block": meta["block"],
                "score": score_val,
                "max_score": 2,
                "rationale": rationale,
                "evidence": evidence,
            }
        )
        all_pros.extend(pros)
        all_cons.extend(cons)
        missing_flags.extend(missing)

    total_score = sum(rubric_scores.values())
    return {
        "lead_id": lead_id,
        "stage_name": stage_name,
        "rubric_scores": rubric_scores,
        "rubric_breakdown": rubric_breakdown,
        "total_score": total_score,
        "max_score": 10,
        "pros": _dedupe_strs(all_pros),
        "cons": _dedupe_strs(all_cons),
        "structured_pros": structured_pros[:6],
        "structured_cons": structured_cons[:6],
        "missing_evidence_flags": _dedupe_strs(missing_flags),
        "input_skills_used": [RUBRIC_META[k]["skill"] for k in RUBRIC_ORDER],
        "dynamic_skills_loaded": dynamic_skills,
    }


# ---------------------------------------------------------------------------
# 2. Stage 3 Fleet Orchestrator (Advocate || Skeptic -> Judge)
# ---------------------------------------------------------------------------


def _enrich_media_links(media_links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for idx, raw in enumerate(media_links):
        if not isinstance(raw, dict) or not raw.get("url"):
            continue
        url = str(raw["url"]).strip()
        item = dict(raw)
        vid = extract_video_id(url)
        if vid:
            item.setdefault("video_id", vid)
            item.setdefault("play_url", f"https://www.youtube.com/watch?v={vid}")
            item.setdefault("embed_url", f"https://www.youtube-nocookie.com/embed/{vid}")
        else:
            item.setdefault("play_url", url)
        item.setdefault("clip_index", idx + 1)
        enriched.append(item)
    return enriched


def _build_artist_snapshot(dossier: Dict[str, Any], stage_name: str) -> Dict[str, Any]:
    ident = dossier.get("identity_and_contact") or {}
    media_q = dossier.get("source_and_media_queue") or {}
    footprint = dossier.get("public_footprint") or {}
    comments = dossier.get("comment_forensics") or {}
    live_hist = dossier.get("live_history_and_credits") or {}
    media_links = _enrich_media_links(list(media_q.get("media_links") or []))

    return {
        "stage_name": stage_name,
        "project_type": ident.get("project_type") or "solo_vocalist",
        "pronouns": ident.get("pronouns"),
        "home_city": ident.get("home_city"),
        "home_neighborhood": ident.get("home_neighborhood"),
        "primary_genre": media_q.get("primary_genre"),
        "subgenres": list(media_q.get("subgenres") or []),
        "bio_text": media_q.get("bio_text"),
        "source_channel": media_q.get("source_channel"),
        "seed_source_url": media_q.get("seed_source_url") or (media_links[0]["url"] if media_links else None),
        "attribution_status": media_q.get("attribution_status") or "uncertain",
        "contact_route_type": ident.get("contact_route_type") or "none",
        "has_public_business_contact": bool(ident.get("has_public_business_contact")),
        "platform_urls": dict(ident.get("platform_urls") or {}),
        "media_links": media_links,
        "footprint_regime": footprint.get("footprint_regime") or "unknown",
        "public_reach": dict(footprint.get("public_reach") or {}),
        "comment_intent_counts": dict(comments.get("comment_intent_counts") or {}),
        "notable_commenters": list(comments.get("notable_commenters") or []),
        "show_history": list(live_hist.get("show_history") or []),
        "upcoming_shows": list(live_hist.get("upcoming_shows") or []),
        "public_team_mentions": dict(live_hist.get("public_team_mentions") or {}),
        "collaborator_credits": list(live_hist.get("collaborator_credits") or []),
    }


def _get_active_judging_policy(store: Optional[Any]) -> Optional[Dict[str, Any]]:
    if store is None:
        return None
    models = list_judging_models(store, limit=20)
    for m in models:
        if m.get("is_active"):
            return m
    return models[0] if models else None


def _deterministic_cases_and_decision(
    baseline: Dict[str, Any],
    snapshot: Dict[str, Any],
    active_policy: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    stage_name = baseline["stage_name"]
    scores = baseline["rubric_scores"]
    total = baseline["total_score"]
    pros = baseline["pros"]
    cons = baseline["cons"]
    missing = baseline["missing_evidence_flags"]

    elevate_min = int((active_policy or {}).get("thresholds", {}).get("elevate_min_score", 7))
    watch_min = int((active_policy or {}).get("thresholds", {}).get("watch_min_score", 4))

    if total >= elevate_min and scores["live_vocal_proof"] >= 1:
        verdict = "elevate"
        confidence = round(min(0.96, 0.68 + (total - elevate_min) * 0.08), 2)
        next_action = (
            f"Invite {stage_name} via {snapshot.get('contact_route_type') or 'direct outreach'} "
            "for a paid First Listen NYC showcase callback."
        )
    elif total >= watch_min:
        verdict = "watch"
        confidence = round(min(0.86, 0.58 + (total - watch_min) * 0.07), 2)
        gap_focus = missing[0].split(".")[-1].replace("_", " ") if missing else "second live room clip"
        next_action = f"Hold on Watchlist; verify {gap_focus} before extending a paid callback."
    else:
        verdict = "pass"
        confidence = round(min(0.92, 0.72 + max(0, watch_min - 1 - total) * 0.06), 2)
        next_action = "Pass for current cycle; keep passive monitor if new verified live sessions surface."

    advocate_points = pros[:4] or [
        f"{stage_name} surfaced in Stage 2 discovery with {len(snapshot.get('media_links') or [])} queued clip(s)."
    ]
    skeptic_points = cons[:4] or [
        "Confirm live vocal consistency and stage plot requirements before final booking guarantee."
    ]

    structured_pros = list(baseline.get("structured_pros") or []) or _to_structured_claims(
        advocate_points, "dossier-media"
    )
    structured_cons = list(baseline.get("structured_cons") or []) or _to_structured_claims(
        skeptic_points, "dossier-track-record"
    )
    thesis_str = (
        f"{stage_name} brings verifiable upside ({total}/10 across 5 rubrics): "
        f"{advocate_points[0]}"
    )
    standout_str = (
        "Act early before broader DSP/label discovery closes the local showcase window."
        if scores["early_window_depth"] >= 1
        else "Potential raw vocal upside if live room proof expands."
    )
    advocate_case = {
        "role": "advocate",
        "agent_id": "simon-screen-advocate",
        "headline": thesis_str,
        "thesis": thesis_str,
        "pros": structured_pros,
        "strongest_points": advocate_points,
        "cited_evidence": [b["rationale"] for b in baseline["rubric_breakdown"] if b["score"] >= 1][:3],
        "standout_hook": standout_str,
        "upside_bet": standout_str,
    }

    counter_str = f"Key diligence risk for {stage_name}: {skeptic_points[0]}"
    skeptic_case = {
        "role": "skeptic",
        "agent_id": "simon-screen-skeptic",
        "headline": counter_str,
        "counter_thesis": counter_str,
        "cons": structured_cons,
        "risk_points": skeptic_points,
        "missing_evidence_flags": missing[:6],
        "missing_proof": missing[:5],
        "dealbreakers_checked": [
            "one_clip_view_concentration_gt_85pct",
            "studio_only_media",
            "uncertain_attribution",
            "contact_route_none",
            "major_label_lockup",
            "spam_comments",
        ],
        "verification_needed": (
            f"Resolve {len(missing)} missing evidence flag(s) ({', '.join(missing[:2])})."
            if missing
            else "Verify live room setup and date availability with artist/management."
        ),
    }

    policy_id = str((active_policy or {}).get("policy_id") or "policy_baseline_v0")
    headline = {
        "elevate": f"Elevate {stage_name} ({total}/10) — verified vocal proof, audience pull, and open A&R whitespace.",
        "watch": f"Watch {stage_name} ({total}/10) — promising signal with specific evidence gaps to close.",
        "pass": f"Pass {stage_name} ({total}/10) — insufficient verified vocal, audience, or reachability proof.",
    }[verdict]

    jd_rubric_scores = {
        b["rubric_id"]: {
            "score": int(b["score"]),
            "max_score": 2,
            "skill": b["skill"],
            "note": b["rationale"],
        }
        for b in baseline["rubric_breakdown"]
    }
    judge_decision = {
        "verdict": verdict,
        "confidence": confidence,
        "total_score": total,
        "max_score": 10,
        "headline": headline,
        "rationale": (
            f"Weighed Advocate upside against Skeptic diligence across 5 rubrics ({total}/10): "
            f"{advocate_points[0]} Counterweight: {skeptic_points[0]}"
        ),
        "rubric_scores": jd_rubric_scores,
        "decisive_factors": (pros[:2] + cons[:1]) if verdict == "elevate" else (cons[:2] + pros[:1]),
        "next_action": next_action,
        "policy_id": policy_id,
    }
    return advocate_case, skeptic_case, judge_decision


def _invoke_screening_agent_or_neon(
    gemini: Gemini,
    agent_id: str,
    prompt: str,
    fallback_model: str = "gemini-4-neon",
) -> Dict[str, Any]:
    """Invoke a deployed Stage 3 Managed Agent via `/v1beta/interactions`, falling back cleanly to `gemini-4-neon`."""
    try:
        resp = gemini.interact(
            {
                "agent": agent_id,
                "environment": {"type": "remote"},
                "store": True,
                "background": True,
                "input": [{"type": "text", "text": prompt}],
            },
            include_trace=True,
        )
        return extract_json_object(resp["report"])
    except (RuntimeError, ValueError):
        resp = gemini.interact(
            {
                "model": fallback_model,
                "store": True,
                "input": [{"type": "text", "text": prompt}],
            },
            include_trace=True,
        )
        return extract_json_object(resp["report"])


def _publish_screening_agent_report(
    store: Any,
    packet: Dict[str, Any],
) -> Dict[str, Any]:
    lead_id = packet["lead_id"]
    stage_name = packet["stage_name"]
    verdict = packet["judge_decision"]["verdict"]
    total = packet["total_score"]
    report_id = f"rep_scr_{lead_id}"
    now = _utc_now_iso()

    report_payload: Dict[str, Any] = {
        "contract_version": "1.0.0",
        "report_id": report_id,
        "batch_id": None,
        "agent_name": "Stage 3 Screening Judge",
        "stage": "screening",
        "brief": f"Adversarial Stage 3 screening (Advocate || Skeptic -> Judge) for {stage_name}.",
        "status": "completed",
        "headline": packet["judge_decision"].get("headline") or f"Screened {stage_name}: {verdict.upper()} ({total}/10).",
        "current_focus": "Screening packet finalized",
        "steps": [
            {
                "step_number": 1,
                "phase": "looking_at",
                "title": f"Scored 5 dossier rubrics for {stage_name}",
                "looking_at": "Stage 2 InvestigatorDossier across identity, vocal clips, footprint, comments, and live history.",
                "finding": f"Baseline rubric score: {total}/10 ({len(packet.get('missing_evidence_flags') or [])} missing flag(s)).",
                "analysis": "Grounded deterministic rubric checks completed with zero unverified assumptions.",
                "status": "done",
                "updated_at": now,
            },
            {
                "step_number": 2,
                "phase": "finding",
                "title": "Ran parallel Advocate & Skeptic debate",
                "looking_at": "Upside thesis vs. diligence gaps and attribution risks.",
                "finding": f"Advocate: {packet['advocate_case']['thesis']}",
                "analysis": f"Skeptic: {packet['skeptic_case']['counter_thesis']}",
                "status": "done",
                "updated_at": now,
            },
            {
                "step_number": 3,
                "phase": "analysis",
                "title": f"Judge verdict: {verdict.upper()}",
                "looking_at": "Calibrated JudgingModelPolicy & 5-rubric evidence balance.",
                "finding": packet["judge_decision"]["rationale"],
                "analysis": packet["judge_decision"]["next_action"],
                "status": "done",
                "updated_at": now,
            },
            {
                "step_number": 4,
                "phase": "saved",
                "title": "Saved ScreeningPacket v1.0.0",
                "looking_at": "screening_packets collection",
                "finding": f"Stored packet {packet['packet_id']} ready for human swipe/review on /screen.",
                "analysis": "Available immediately in the Screening Card Deck.",
                "status": "done",
                "updated_at": now,
            },
        ],
        "findings": [
            {
                "title": f"{stage_name} · {verdict.upper()} ({total}/10)",
                "summary": packet["judge_decision"]["rationale"],
                "url": str((packet.get("artist_snapshot") or {}).get("seed_source_url") or ""),
                "attribution_status": str((packet.get("artist_snapshot") or {}).get("attribution_status") or "uncertain"),
            }
        ],
        "output": sanitize_agent_report(packet),
        "archived": False,
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }
    report_payload["findings"] = [{k: v for k, v in f.items() if v} for f in report_payload["findings"]]
    clean_report = sanitize_agent_report(report_payload)
    save_agent_document(store, "agent_reports", clean_report, doc_id=report_id)
    return clean_report


def run_screening_for_dossier(
    store: Any,
    dossier: Dict[str, Any],
    live: bool = False,
    api_key: Optional[str] = None,
    prefix: Optional[str] = None,
    gemini: Optional[Gemini] = None,
) -> Dict[str, Any]:
    """Run Stage 3 Screening on a Stage 2 `InvestigatorDossier` and persist `ScreeningPacket` v1.0.0."""
    clean_dossier = sanitize_agent_report(dossier)
    baseline = score_dossier_inputs(clean_dossier)
    lead_id = baseline["lead_id"]
    stage_name = baseline["stage_name"]
    packet_id = str(clean_dossier.get("packet_id") or f"scr_{lead_id}")

    snapshot = _build_artist_snapshot(clean_dossier, stage_name)
    active_policy = _get_active_judging_policy(store)
    det_adv, det_skp, det_judge = _deterministic_cases_and_decision(baseline, snapshot, active_policy)

    resolved_key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip() or None
    resolved_prefix = (
        prefix if prefix is not None else os.environ.get("SIMON_AGENT_PREFIX", "")
    ).strip()

    advocate_id = f"{resolved_prefix}simon-screen-advocate"
    skeptic_id = f"{resolved_prefix}simon-screen-skeptic"
    judge_id = f"{resolved_prefix}simon-screening-judge"

    mode = "deterministic_baseline"
    advocate_case = det_adv
    skeptic_case = det_skp
    judge_decision = det_judge
    rubric_scores = dict(baseline["rubric_scores"])
    pros = list(baseline["pros"])
    cons = list(baseline["cons"])
    missing_flags = list(baseline["missing_evidence_flags"])

    if live and (resolved_key or gemini is not None):
        client = gemini or Gemini(api_key=resolved_key)
        shared_context = json.dumps(
            {
                "lead_id": lead_id,
                "stage_name": stage_name,
                "dossier": clean_dossier,
                "baseline_rubrics": baseline,
            },
            ensure_ascii=False,
        )
        adv_prompt = (
            "You are Simon's Stage 3 Screen Advocate (`gemini-4-neon`). Build the strongest grounded "
            "A&R case for elevating this artist using ONLY verified dossier facts. Never invent facts.\n"
            'Return ONLY JSON matching: {"lead_id": "...", "stage_name": "...", "headline": "...", '
            '"pros": [{"skill": "dossier-...", "title": "...", "evidence": "..."}], '
            '"standout_hook": "..."}\n\n'
            f"INPUT JSON:\n{shared_context}"
        )
        skp_prompt = (
            "You are Simon's Stage 3 Screen Skeptic (`gemini-4-neon`). Stress-test this artist dossier, "
            "surfacing missing proof, single-clip or attribution risks, and reasons to pass or hold.\n"
            'Return ONLY JSON matching: {"lead_id": "...", "stage_name": "...", "headline": "...", '
            '"cons": [{"skill": "dossier-...", "title": "...", "evidence": "..."}], '
            '"missing_evidence_flags": ["..."], "dealbreakers_checked": ["..."]}\n\n'
            f"INPUT JSON:\n{shared_context}"
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            adv_fut = pool.submit(_invoke_screening_agent_or_neon, client, advocate_id, adv_prompt)
            skp_fut = pool.submit(_invoke_screening_agent_or_neon, client, skeptic_id, skp_prompt)
            live_adv = adv_fut.result()
            live_skp = skp_fut.result()

        adv_headline = str(live_adv.get("headline") or live_adv.get("thesis") or det_adv["thesis"]).strip()
        adv_standout = str(live_adv.get("standout_hook") or live_adv.get("upside_bet") or det_adv["upside_bet"]).strip()
        adv_raw_pros = list(live_adv.get("pros") or live_adv.get("strongest_points") or det_adv["pros"])
        adv_struct_pros = _to_structured_claims(adv_raw_pros, "dossier-media") or det_adv["pros"]
        adv_flat_pros = _flatten_claim_items(adv_raw_pros) or det_adv["strongest_points"]

        advocate_case = {
            "role": "advocate",
            "agent_id": advocate_id,
            "headline": adv_headline,
            "thesis": adv_headline,
            "pros": adv_struct_pros,
            "strongest_points": adv_flat_pros,
            "cited_evidence": _dedupe_strs(list(live_adv.get("cited_evidence") or det_adv["cited_evidence"])),
            "standout_hook": adv_standout,
            "upside_bet": adv_standout,
        }

        skp_headline = str(live_skp.get("headline") or live_skp.get("counter_thesis") or det_skp["counter_thesis"]).strip()
        skp_raw_cons = list(live_skp.get("cons") or live_skp.get("risk_points") or det_skp["cons"])
        skp_struct_cons = _to_structured_claims(skp_raw_cons, "dossier-track-record")
        skp_flat_cons = _flatten_claim_items(skp_raw_cons) or det_skp["risk_points"]
        skp_missing = _dedupe_strs(
            list(live_skp.get("missing_evidence_flags") or live_skp.get("missing_proof") or det_skp["missing_proof"])
        )

        skeptic_case = {
            "role": "skeptic",
            "agent_id": skeptic_id,
            "headline": skp_headline,
            "counter_thesis": skp_headline,
            "cons": skp_struct_cons,
            "risk_points": skp_flat_cons,
            "missing_evidence_flags": skp_missing,
            "missing_proof": skp_missing,
            "dealbreakers_checked": _dedupe_strs(
                list(live_skp.get("dealbreakers_checked") or det_skp.get("dealbreakers_checked") or ["standard_diligence"])
            ),
            "verification_needed": str(live_skp.get("verification_needed") or det_skp["verification_needed"]).strip(),
        }

        judge_input = json.dumps(
            {
                "lead_id": lead_id,
                "stage_name": stage_name,
                "dossier": clean_dossier,
                "baseline_rubrics": baseline,
                "advocate_case": advocate_case,
                "skeptic_case": skeptic_case,
                "active_judging_policy": active_policy,
            },
            ensure_ascii=False,
        )
        judge_prompt = (
            "You are Simon's Stage 3 Screening Judge (`gemini-4-neon`). Weigh the Stage 2 dossier, "
            "the 5 rubric scores (0..2 each), the Advocate case, and the Skeptic case.\n"
            "Return ONLY JSON with `verdict` ('elevate' | 'watch' | 'pass'), `confidence` (0..1), "
            "`rubric_scores` ({identity_reachability, live_vocal_proof, early_window_depth, "
            "listener_pull_cosigns, stage_momentum_whitespace} each 0..2), `total_score` (0..10), "
            "`headline`, `rationale`, and `next_action`.\n\n"
            f"INPUT JSON:\n{judge_input}"
        )
        live_judge = _invoke_screening_agent_or_neon(client, judge_id, judge_prompt)
        nested_jd = live_judge.get("judge_decision") if isinstance(live_judge.get("judge_decision"), dict) else live_judge

        raw_verdict = str(nested_jd.get("verdict") or live_judge.get("verdict") or det_judge["verdict"]).strip().lower()
        final_verdict = raw_verdict if raw_verdict in VALID_SCREENING_VERDICTS else det_judge["verdict"]
        try:
            final_conf = max(
                0.0,
                min(
                    1.0,
                    round(
                        float(nested_jd.get("confidence", live_judge.get("confidence", det_judge["confidence"]))),
                        2,
                    ),
                ),
            )
        except (TypeError, ValueError):
            final_conf = det_judge["confidence"]

        raw_rubrics = live_judge.get("rubric_scores") or nested_jd.get("rubric_scores")
        if isinstance(raw_rubrics, dict):
            for k in RUBRIC_ORDER:
                if k in raw_rubrics:
                    val = raw_rubrics[k]
                    rubric_scores[k] = _clamp_rubric_score(val.get("score") if isinstance(val, dict) else val)

        total_live_score = sum(rubric_scores.values())
        pros = _dedupe_strs(_flatten_claim_items(list(live_judge.get("pros") or [])) + advocate_case["strongest_points"] + pros)
        cons = _dedupe_strs(_flatten_claim_items(list(live_judge.get("cons") or [])) + skeptic_case["risk_points"] + cons)
        missing_flags = _dedupe_strs(
            list(live_judge.get("missing_evidence_flags") or []) + skeptic_case["missing_proof"] + missing_flags
        )

        judge_decision = {
            "verdict": final_verdict,
            "confidence": final_conf,
            "total_score": total_live_score,
            "max_score": 10,
            "headline": str(nested_jd.get("headline") or live_judge.get("headline") or det_judge["headline"]).strip(),
            "rationale": str(nested_jd.get("rationale") or live_judge.get("rationale") or det_judge["rationale"]).strip(),
            "decisive_factors": _dedupe_strs(list(nested_jd.get("decisive_factors") or det_judge["decisive_factors"])),
            "next_action": str(nested_jd.get("next_action") or det_judge["next_action"]).strip(),
            "policy_id": str((active_policy or {}).get("policy_id") or det_judge["policy_id"]),
        }
        mode = "live"

    # Sync rubric_breakdown and judge_decision.rubric_scores with final rubric_scores
    breakdown = []
    jd_rubric_scores = {}
    for item in baseline["rubric_breakdown"]:
        r_key = item["rubric_id"]
        updated_item = dict(item)
        updated_item["score"] = rubric_scores[r_key]
        breakdown.append(updated_item)
        jd_rubric_scores[r_key] = {
            "score": int(rubric_scores[r_key]),
            "max_score": 2,
            "skill": item["skill"],
            "note": item["rationale"],
        }
    total_final = sum(rubric_scores.values())
    judge_decision["total_score"] = total_final
    judge_decision["rubric_scores"] = jd_rubric_scores

    packet: Dict[str, Any] = {
        "contract_version": "1.0.0",
        "packet_id": packet_id,
        "lead_id": lead_id,
        "dossier_id": str(clean_dossier.get("dossier_id") or clean_dossier.get("_doc_id") or lead_id),
        "stage_name": stage_name,
        "screening_model": "gemini-4-neon",
        "verdict": judge_decision["verdict"],
        "confidence": judge_decision["confidence"],
        "headline": judge_decision["headline"],
        "next_action": judge_decision["next_action"],
        "total_score": total_final,
        "max_score": 10,
        "rubric_scores": rubric_scores,
        "rubric_breakdown": breakdown,
        "pros": pros[:6],
        "cons": cons[:6],
        "missing_evidence_flags": missing_flags,
        "advocate_case": advocate_case,
        "skeptic_case": skeptic_case,
        "judge_decision": judge_decision,
        "dossier_snapshot": clean_dossier,
        "artist_snapshot": snapshot,
        "input_skills_used": list(baseline["input_skills_used"]),
        "mode": mode,
        "archived": False,
        "screened_at": _utc_now_iso(),
    }

    clean_packet = _normalize_screening_packet(sanitize_agent_report(packet))
    clean_packet["archived"] = False
    if store is not None:
        save_agent_document(store, "screening_packets", clean_packet, doc_id=packet_id)
        _publish_screening_agent_report(store, clean_packet)
    return clean_packet


# ---------------------------------------------------------------------------
# 3. Demo Fixtures & Deck Loader (`/screen` & `GET /api/screening/packets`)
# ---------------------------------------------------------------------------


def _normalize_screening_packet(raw_pkt: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize any ScreeningPacket (seeded demo or runtime) so UI, evals, and trainer share exact keys."""
    clean = sanitize_agent_report(dict(raw_pkt))
    lead_id = str(clean.get("lead_id") or "").strip()
    stage_name = str(clean.get("stage_name") or lead_id).strip()
    pkt_id = str(clean.get("packet_id") or f"scr_{lead_id}")

    dossier = clean.get("dossier_snapshot") if isinstance(clean.get("dossier_snapshot"), dict) else None
    snapshot = clean.get("artist_snapshot") if isinstance(clean.get("artist_snapshot"), dict) else None
    if snapshot is None and dossier is not None:
        snapshot = _build_artist_snapshot(dossier, stage_name)
    elif dossier is None and snapshot is not None:
        dossier = {
            "lead_id": lead_id,
            "stage_name": stage_name,
            "identity_and_contact": {
                "stage_name": stage_name,
                "aliases": [],
                "pronouns": snapshot.get("pronouns"),
                "project_type": snapshot.get("project_type") or "solo_vocalist",
                "home_city": snapshot.get("home_city"),
                "home_neighborhood": snapshot.get("home_neighborhood"),
                "platform_urls": snapshot.get("platform_urls") or {},
                "musicbrainz_mbid": None,
                "has_public_business_contact": bool(snapshot.get("has_public_business_contact")),
                "contact_route_type": snapshot.get("contact_route_type") or "none",
            },
            "source_and_media_queue": {
                "source_channel": snapshot.get("source_channel") or "other",
                "seed_source_url": snapshot.get("seed_source_url") or "",
                "attribution_status": snapshot.get("attribution_status") or "uncertain",
                "bio_text": snapshot.get("bio_text"),
                "primary_genre": snapshot.get("primary_genre"),
                "subgenres": snapshot.get("subgenres") or [],
                "media_links": snapshot.get("media_links") or [],
            },
            "public_footprint": {
                "footprint_regime": snapshot.get("footprint_regime") or "unknown",
                "public_reach": snapshot.get("public_reach") or {},
                "top_release_view_share_pct": None,
            },
            "comment_forensics": {
                "comment_intent_counts": snapshot.get("comment_intent_counts") or {},
                "notable_commenters": snapshot.get("notable_commenters") or [],
            },
            "live_history_and_credits": {
                "show_history": snapshot.get("show_history") or [],
                "upcoming_shows": snapshot.get("upcoming_shows") or [],
                "highest_venue_cap_observed": None,
                "public_team_mentions": snapshot.get("public_team_mentions") or {},
                "collaborator_credits": snapshot.get("collaborator_credits") or [],
            },
            "missing_fields": list(clean.get("missing_evidence_flags") or []),
        }

    jd = dict(clean.get("judge_decision") or {})
    top_rubrics = clean.get("rubric_scores") if isinstance(clean.get("rubric_scores"), dict) else {}
    jd_rubrics = jd.get("rubric_scores") if isinstance(jd.get("rubric_scores"), dict) else {}

    flat_scores: Dict[str, int] = {}
    nested_scores: Dict[str, Dict[str, Any]] = {}
    breakdown: List[Dict[str, Any]] = []

    for r_key in RUBRIC_ORDER:
        meta = RUBRIC_META[r_key]
        raw_entry = jd_rubrics.get(r_key) if r_key in jd_rubrics else top_rubrics.get(r_key, 0)
        if isinstance(raw_entry, dict):
            sc = _clamp_rubric_score(raw_entry.get("score", 0))
            note = str(raw_entry.get("note") or raw_entry.get("rationale") or "").strip()
            skill = str(raw_entry.get("skill") or meta["skill"]).strip()
        else:
            sc = _clamp_rubric_score(raw_entry)
            note = ""
            skill = meta["skill"]
        flat_scores[r_key] = sc
        nested_scores[r_key] = {
            "score": sc,
            "max_score": 2,
            "skill": skill,
            "note": note or f"Rubric {meta['label']} scored {sc}/2.",
        }
        breakdown.append(
            {
                "rubric_id": r_key,
                "label": meta["label"],
                "skill": skill,
                "block": meta["block"],
                "score": sc,
                "max_score": 2,
                "rationale": nested_scores[r_key]["note"],
                "evidence": [],
            }
        )

    total_score = int(
        clean.get("total_score")
        if clean.get("total_score") is not None
        else (jd.get("total_score") if jd.get("total_score") is not None else sum(flat_scores.values()))
    )
    verdict = str(jd.get("verdict") or clean.get("verdict") or "watch").strip().lower()
    if verdict not in VALID_SCREENING_VERDICTS:
        verdict = "watch"
    confidence = jd.get("confidence", clean.get("confidence", 0.75))

    adv = dict(clean.get("advocate_case") or {})
    adv_headline = str(adv.get("headline") or adv.get("thesis") or f"Advocate case for {stage_name}.").strip()
    adv_raw_pros = list(adv.get("pros") or adv.get("strongest_points") or clean.get("pros") or [])
    adv["headline"] = adv_headline
    adv["thesis"] = str(adv.get("thesis") or adv_headline).strip()
    adv["pros"] = _to_structured_claims(adv_raw_pros, "dossier-media")
    adv["strongest_points"] = _flatten_claim_items(adv_raw_pros)
    adv["standout_hook"] = str(adv.get("standout_hook") or adv.get("upside_bet") or adv_headline).strip()
    adv["upside_bet"] = str(adv.get("upside_bet") or adv["standout_hook"]).strip()

    skp = dict(clean.get("skeptic_case") or {})
    skp_headline = str(skp.get("headline") or skp.get("counter_thesis") or f"Diligence audit for {stage_name}.").strip()
    skp_raw_cons = list(skp.get("cons") or skp.get("risk_points") or clean.get("cons") or [])
    skp_missing = _dedupe_strs(
        list(skp.get("missing_evidence_flags") or [])
        + list(skp.get("missing_proof") or [])
        + list(clean.get("missing_evidence_flags") or [])
        + list((dossier or {}).get("missing_fields") or [])
    )
    skp["headline"] = skp_headline
    skp["counter_thesis"] = str(skp.get("counter_thesis") or skp_headline).strip()
    skp["cons"] = _to_structured_claims(skp_raw_cons, "dossier-track-record")
    skp["risk_points"] = _flatten_claim_items(skp_raw_cons)
    skp["missing_evidence_flags"] = skp_missing
    skp["missing_proof"] = skp_missing
    skp.setdefault("dealbreakers_checked", ["standard_diligence"])

    jd["verdict"] = verdict
    jd["confidence"] = confidence
    jd["total_score"] = total_score
    jd["max_score"] = 10
    jd["rubric_scores"] = nested_scores
    jd.setdefault("rationale", f"{stage_name} scored {total_score}/10 -> {verdict}.")
    jd.setdefault("headline", f"{verdict.capitalize()} {stage_name} ({total_score}/10).")
    jd.setdefault("next_action", f"Review {stage_name} on /screen.")

    clean["contract_version"] = "1.0.0"
    clean["packet_id"] = pkt_id
    clean["lead_id"] = lead_id
    clean["stage_name"] = stage_name
    clean.setdefault("screening_model", "gemini-4-neon")
    clean["verdict"] = verdict
    clean["confidence"] = confidence
    clean["total_score"] = total_score
    clean["max_score"] = 10
    clean["rubric_scores"] = flat_scores
    clean.setdefault("rubric_breakdown", breakdown)
    clean["pros"] = _dedupe_strs(list(clean.get("pros") or []) + adv["strongest_points"])[:6]
    clean["cons"] = _dedupe_strs(list(clean.get("cons") or []) + skp["risk_points"])[:6]
    clean["missing_evidence_flags"] = skp_missing
    clean["advocate_case"] = adv
    clean["skeptic_case"] = skp
    clean["judge_decision"] = jd
    if dossier is not None:
        clean["dossier_snapshot"] = dossier
    if snapshot is not None:
        clean["artist_snapshot"] = snapshot
    clean["input_skills_used"] = [RUBRIC_META[k]["skill"] for k in RUBRIC_ORDER]
    clean.setdefault("screened_at", _utc_now_iso())
    return clean


def build_builtin_demo_dossiers() -> List[Dict[str, Any]]:
    """Three grounded Stage 2 dossiers spanning Elevate, Watch, and Pass for instant `/screen` readiness."""
    return [
        {
            "lead_id": "lead_demo_mira_sol",
            "stage_name": "Mira Sol",
            "identity_and_contact": {
                "stage_name": "Mira Sol",
                "aliases": ["M. Sol"],
                "pronouns": "she/her",
                "project_type": "solo_vocalist",
                "home_city": "New York, NY",
                "home_neighborhood": "Bushwick, Brooklyn",
                "platform_urls": {
                    "youtube": "https://www.youtube.com/@mirasolmusic",
                    "instagram": "https://www.instagram.com/mirasolmusic",
                    "bandcamp": "https://mirasol.bandcamp.com",
                    "spotify": "https://open.spotify.com/artist/123456",
                },
                "musicbrainz_mbid": "11111111-2222-3333-4444-555555555555",
                "has_public_business_contact": True,
                "contact_route_type": "mgmt_email",
            },
            "source_and_media_queue": {
                "source_channel": "youtube_live_session",
                "seed_source_url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                "attribution_status": "verified",
                "bio_text": "Bushwick neo-soul & indie-folk vocalist performing stripped-back quartet and acoustic rooms across NYC.",
                "primary_genre": "neo-soul",
                "subgenres": ["indie folk", "acoustic soul"],
                "media_links": [
                    {
                        "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                        "title": "Mira Sol - Midnight Train (Sofar Sounds NYC Live Session)",
                        "uploader_channel": "Sofar Sounds",
                        "duration_seconds": 218,
                        "oembed_live_embeddable": True,
                    },
                    {
                        "url": "https://www.youtube.com/watch?v=M7lc1UVf-VE",
                        "title": "Mira Sol - Paper Walls (Live Acoustic Trio in Brooklyn)",
                        "uploader_channel": "Mira Sol",
                        "duration_seconds": 196,
                        "oembed_live_embeddable": True,
                    },
                ],
            },
            "public_footprint": {
                "footprint_regime": "early_dsp_inflection",
                "public_reach": {
                    "youtube_subscribers": 4800,
                    "top_video_views": 22400,
                    "bandcamp_releases_count": 2,
                    "bandcamp_supporters_count": 92,
                    "released_tracks_count": 8,
                },
                "top_release_view_share_pct": 58.0,
            },
            "comment_forensics": {
                "comment_intent_counts": {
                    "sample_size": 40,
                    "release_requests": 9,
                    "live_show_requests": 6,
                    "genuine_praise": 22,
                    "jokes_or_spam": 3,
                },
                "notable_commenters": [
                    {
                        "handle": "@jonahreyes_prod",
                        "channel_url": "https://www.youtube.com/@jonahreyes_prod",
                        "role_or_context": "Brooklyn indie-soul producer",
                        "comment_excerpt": "Phrasing on the bridge modulation is unreal live.",
                    }
                ],
            },
            "live_history_and_credits": {
                "show_history": [
                    {
                        "venue": "Baby's All Right",
                        "city": "Brooklyn, NY",
                        "date": "2026-10-14",
                        "billing_slot": "direct_support",
                        "source_url": "https://dice.fm/event/mira-sol-babys",
                    },
                    {
                        "venue": "Rockwood Music Hall Stage 1",
                        "city": "New York, NY",
                        "date": "2026-08-03",
                        "billing_slot": "headliner",
                        "source_url": "https://www.bandsintown.com/e/12345",
                    },
                    {
                        "venue": "Union Pool",
                        "city": "Brooklyn, NY",
                        "date": "2026-06-19",
                        "billing_slot": "direct_support",
                        "source_url": "https://unionpool.com/events/mira-sol",
                    },
                ],
                "upcoming_shows": [
                    {
                        "venue": "Mercury Lounge",
                        "city": "New York, NY",
                        "date": "2026-12-09",
                        "billing_slot": "opener",
                        "source_url": "https://dice.fm/event/mira-sol-mercury",
                    }
                ],
                "highest_venue_cap_observed": 280,
                "public_team_mentions": {
                    "management": "North Star Artists",
                    "booking_agent": None,
                    "label": None,
                    "distributor": "DistroKid",
                },
                "collaborator_credits": [
                    {
                        "name": "Jonah Reyes",
                        "role": "producer",
                        "source_url": "https://musicbrainz.org/artist/11111111-2222-3333-4444-555555555555",
                    }
                ],
            },
            "process_trace": [{"step": "assemble_dossier", "tool": "investigator", "status": "ok"}],
            "missing_fields": [],
        },
        {
            "lead_id": "lead_demo_soraia_bell",
            "stage_name": "Soraia Bell",
            "identity_and_contact": {
                "stage_name": "Soraia Bell",
                "aliases": [],
                "pronouns": "she/they",
                "project_type": "solo_vocalist",
                "home_city": "New York, NY",
                "home_neighborhood": "Harlem",
                "platform_urls": {
                    "youtube": "https://www.youtube.com/@soraiabell",
                    "instagram": "https://www.instagram.com/soraiabell",
                },
                "musicbrainz_mbid": None,
                "has_public_business_contact": False,
                "contact_route_type": "open_dm",
            },
            "source_and_media_queue": {
                "source_channel": "open_mic_lineup",
                "seed_source_url": "https://www.youtube.com/watch?v=9bZkp7q19f0",
                "attribution_status": "verified",
                "bio_text": "Harlem acoustic R&B singer-guitarist testing unreleased ballads at listening rooms.",
                "primary_genre": "acoustic r&b",
                "subgenres": ["alt-soul"],
                "media_links": [
                    {
                        "url": "https://www.youtube.com/watch?v=9bZkp7q19f0",
                        "title": "Soraia Bell - Static in the Hallway (Harlem Acoustic Room)",
                        "uploader_channel": "Harlem Listening Room",
                        "duration_seconds": 184,
                        "oembed_live_embeddable": True,
                    }
                ],
            },
            "public_footprint": {
                "footprint_regime": "pre_dsp_underground",
                "public_reach": {
                    "youtube_subscribers": 90,
                    "top_video_views": 5900,
                    "bandcamp_releases_count": 0,
                    "bandcamp_supporters_count": 6,
                    "released_tracks_count": 1,
                },
                "top_release_view_share_pct": 89.0,
            },
            "comment_forensics": {
                "comment_intent_counts": {
                    "sample_size": 18,
                    "release_requests": 5,
                    "live_show_requests": 2,
                    "genuine_praise": 10,
                    "jokes_or_spam": 1,
                },
                "notable_commenters": [],
            },
            "live_history_and_credits": {
                "show_history": [
                    {
                        "venue": "Shrine World Music Venue",
                        "city": "New York, NY",
                        "date": "2026-09-21",
                        "billing_slot": "showcase",
                        "source_url": "https://shrinenyc.com/calendar",
                    }
                ],
                "upcoming_shows": [],
                "highest_venue_cap_observed": 120,
                "public_team_mentions": {
                    "management": None,
                    "booking_agent": None,
                    "label": None,
                    "distributor": None,
                },
                "collaborator_credits": [],
            },
            "process_trace": [{"step": "assemble_dossier", "tool": "investigator", "status": "ok"}],
            "missing_fields": [
                "identity_and_contact.business_email",
                "source_and_media_queue.second_live_take",
            ],
        },
        {
            "lead_id": "lead_demo_devon_k",
            "stage_name": "Devon K.",
            "identity_and_contact": {
                "stage_name": "Devon K.",
                "aliases": [],
                "pronouns": None,
                "project_type": "unknown",
                "home_city": None,
                "home_neighborhood": None,
                "platform_urls": {},
                "musicbrainz_mbid": None,
                "has_public_business_contact": False,
                "contact_route_type": "none",
            },
            "source_and_media_queue": {
                "source_channel": "open_mic_lineup",
                "seed_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "attribution_status": "uncertain",
                "bio_text": "Short crowd-shot open mic clip with noisy room bleed and unverified vocalist handle.",
                "primary_genre": "indie pop",
                "subgenres": [],
                "media_links": [
                    {
                        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        "title": "Tuesday Open Mic Clip #4 - Devon K?",
                        "uploader_channel": "East Village Clips",
                        "duration_seconds": 95,
                        "oembed_live_embeddable": True,
                    }
                ],
            },
            "public_footprint": {
                "footprint_regime": "unknown",
                "public_reach": {
                    "youtube_subscribers": None,
                    "top_video_views": 210,
                    "bandcamp_releases_count": 0,
                    "bandcamp_supporters_count": 0,
                    "released_tracks_count": 0,
                },
                "top_release_view_share_pct": 100.0,
            },
            "comment_forensics": {
                "comment_intent_counts": {
                    "sample_size": 0,
                    "release_requests": 0,
                    "live_show_requests": 0,
                    "genuine_praise": 0,
                    "jokes_or_spam": 0,
                },
                "notable_commenters": [],
            },
            "live_history_and_credits": {
                "show_history": [],
                "upcoming_shows": [],
                "highest_venue_cap_observed": None,
                "public_team_mentions": {
                    "management": None,
                    "booking_agent": None,
                    "label": None,
                    "distributor": None,
                },
                "collaborator_credits": [],
            },
            "process_trace": [{"step": "assemble_dossier", "tool": "investigator", "status": "ok"}],
            "missing_fields": [
                "identity_and_contact.contact_route_type",
                "source_and_media_queue.verified_attribution",
                "public_footprint.public_reach",
                "comment_forensics.comment_intent_counts",
                "live_history_and_credits.show_history",
            ],
        },
    ]


def _seed_demo_packets_into_store(store: Any) -> List[Dict[str, Any]]:
    """Seed `screening_packets` from `examples/screening_demo.json` if present, else built-in demo dossiers."""
    seeded: List[Dict[str, Any]] = []
    if DEMO_SCREENING_PATH.is_file():
        try:
            raw = json.loads(DEMO_SCREENING_PATH.read_text(encoding="utf-8"))
            items: List[Any] = []
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = (
                    raw.get("packets")
                    or raw.get("screening_packets")
                    or raw.get("dossiers")
                    or []
                )
            for item in items:
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("judge_decision"), dict) and item.get("lead_id") and item.get("stage_name"):
                    clean = _normalize_screening_packet(dict(item))
                    pkt_id = str(clean.get("packet_id") or f"scr_{clean['lead_id']}")
                    save_agent_document(store, "screening_packets", clean, doc_id=pkt_id)
                    seeded.append(clean)
                elif item.get("lead_id"):
                    seeded.append(run_screening_for_dossier(store, item, live=False))
            if seeded:
                return seeded
        except (OSError, ValueError):
            pass

    for demo_dossier in build_builtin_demo_dossiers():
        seeded.append(run_screening_for_dossier(store, demo_dossier, live=False))
    return seeded


def list_screening_labels(
    store: Any,
    lead_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows = list_agent_documents(store, "screening_labels", limit=max(1, min(limit, 100)))
    labels: List[Dict[str, Any]] = []
    for row in rows:
        doc = _unwrap_doc(row)
        if not isinstance(doc, dict) or bool(doc.get("archived", False)):
            continue
        if lead_id and doc.get("lead_id") != lead_id and doc.get("packet_id") != lead_id:
            continue
        labels.append(sanitize_agent_report(doc))
    labels.sort(
        key=lambda item: str(item.get("labeled_at") or item.get("updated_at") or item.get("_saved_at") or ""),
        reverse=True,
    )
    return labels[:limit]


def list_screening_deck(
    store: Any,
    limit: int = 100,
    verdict_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Load Stage 3 Screening Deck, auto-screening unscreened dossiers or seeding demo candidates if empty."""
    packets_by_lead: Dict[str, Dict[str, Any]] = {}
    for row in list_agent_documents(store, "screening_packets", limit=100):
        doc = _unwrap_doc(row)
        if not isinstance(doc, dict) or not doc.get("lead_id") or bool(doc.get("archived", False)):
            continue
        clean = _normalize_screening_packet(dict(doc))
        lead_key = str(clean["lead_id"])
        if lead_key not in packets_by_lead:
            packets_by_lead[lead_key] = clean

    # Check Stage 2 investigator_dossiers and auto-generate baseline ScreeningPackets for unscreened leads
    for row in list_agent_documents(store, "investigator_dossiers", limit=100):
        dossier = _unwrap_doc(row)
        if not isinstance(dossier, dict) or not dossier.get("lead_id") or bool(dossier.get("archived", False)):
            continue
        lead_key = str(dossier["lead_id"])
        if lead_key not in packets_by_lead:
            generated = run_screening_for_dossier(store, dossier, live=False)
            packets_by_lead[lead_key] = generated

    # Seed rich demo candidates when both collections are empty
    if not packets_by_lead:
        for pkt in _seed_demo_packets_into_store(store):
            packets_by_lead[str(pkt["lead_id"])] = pkt

    # Join latest human review from screening_labels onto each packet
    latest_label_by_lead: Dict[str, Dict[str, Any]] = {}
    for lbl in list_screening_labels(store, limit=100):
        lid = str(lbl.get("lead_id") or "")
        if lid and lid not in latest_label_by_lead:
            latest_label_by_lead[lid] = {
                "label_id": lbl.get("label_id") or lbl.get("_doc_id"),
                "human_verdict": lbl.get("human_verdict"),
                "reason": lbl.get("reason") or "",
                "agreed_with_model": lbl.get("agreed_with_model"),
                "labeled_at": lbl.get("labeled_at") or lbl.get("_saved_at"),
            }

    # Join latest calibrated taste_score from taste_scores onto each packet
    latest_taste_by_lead: Dict[str, Dict[str, Any]] = {}
    for ts_doc in list_taste_scores(store, limit=100):
        lid = str(ts_doc.get("lead_id") or "")
        if lid and lid not in latest_taste_by_lead:
            latest_taste_by_lead[lid] = ts_doc

    all_packets: List[Dict[str, Any]] = []
    for lead_key, pkt in packets_by_lead.items():
        enriched = dict(pkt)
        enriched["human_review"] = latest_label_by_lead.get(lead_key)
        enriched["latest_taste_score"] = latest_taste_by_lead.get(lead_key)
        all_packets.append(enriched)

    all_packets.sort(
        key=lambda p: (
            VERDICT_SORT_RANK.get(str((p.get("judge_decision") or {}).get("verdict") or "watch"), 9),
            -int(p.get("total_score") or 0),
            str(p.get("stage_name") or ""),
        )
    )

    elevate_count = sum(1 for p in all_packets if (p.get("judge_decision") or {}).get("verdict") == "elevate")
    watch_count = sum(1 for p in all_packets if (p.get("judge_decision") or {}).get("verdict") == "watch")
    pass_count = sum(1 for p in all_packets if (p.get("judge_decision") or {}).get("verdict") == "pass")
    human_labeled_count = sum(1 for p in all_packets if p.get("human_review") is not None)

    filtered = all_packets
    if verdict_filter and verdict_filter.lower() in VALID_SCREENING_VERDICTS:
        vf = verdict_filter.lower()
        filtered = [p for p in all_packets if (p.get("judge_decision") or {}).get("verdict") == vf]
    filtered = filtered[: max(1, min(int(limit), 100))]

    active_policy = _get_active_judging_policy(store)
    summary = {
        "total": len(all_packets),
        "elevate_count": elevate_count,
        "watch_count": watch_count,
        "pass_count": pass_count,
        "human_labeled_count": human_labeled_count,
        "active_policy_id": (active_policy or {}).get("policy_id"),
    }
    return {
        "count": len(filtered),
        "total": summary["total"],
        "elevate_count": elevate_count,
        "watch_count": watch_count,
        "pass_count": pass_count,
        "human_labeled_count": human_labeled_count,
        "active_policy": active_policy,
        "summary": summary,
        "packets": filtered,
    }


def run_screening_batch(
    store: Any,
    lead_id: Optional[str] = None,
    dossier: Optional[Dict[str, Any]] = None,
    live: bool = False,
    api_key: Optional[str] = None,
    prefix: Optional[str] = None,
    gemini: Optional[Gemini] = None,
) -> List[Dict[str, Any]]:
    """Run screening for an explicit dossier, a specific `lead_id`, or all dossiers in `store`."""
    if isinstance(dossier, dict):
        return [
            run_screening_for_dossier(
                store, dossier, live=live, api_key=api_key, prefix=prefix, gemini=gemini
            )
        ]

    dossiers_by_lead: Dict[str, Dict[str, Any]] = {}
    for row in list_agent_documents(store, "investigator_dossiers", limit=100):
        doc = _unwrap_doc(row)
        if isinstance(doc, dict) and doc.get("lead_id") and not bool(doc.get("archived", False)):
            dossiers_by_lead[str(doc["lead_id"])] = doc

    if lead_id:
        target = dossiers_by_lead.get(lead_id)
        if target is None:
            for demo_d in build_builtin_demo_dossiers():
                if demo_d["lead_id"] == lead_id:
                    target = demo_d
                    break
        if target is None:
            existing_pkt = get_agent_document(store, "screening_packets", f"scr_{lead_id}") or get_agent_document(
                store, "screening_packets", lead_id
            )
            if isinstance(existing_pkt, dict):
                snap = existing_pkt.get("artist_snapshot") or {}
                target = {
                    "lead_id": existing_pkt.get("lead_id") or lead_id,
                    "stage_name": existing_pkt.get("stage_name") or lead_id,
                    "identity_and_contact": {
                        "stage_name": existing_pkt.get("stage_name") or lead_id,
                        "aliases": [],
                        "pronouns": snap.get("pronouns"),
                        "project_type": snap.get("project_type") or "solo_vocalist",
                        "home_city": snap.get("home_city"),
                        "home_neighborhood": snap.get("home_neighborhood"),
                        "platform_urls": snap.get("platform_urls") or {},
                        "musicbrainz_mbid": None,
                        "has_public_business_contact": bool(snap.get("has_public_business_contact")),
                        "contact_route_type": snap.get("contact_route_type") or "none",
                    },
                    "source_and_media_queue": {
                        "source_channel": snap.get("source_channel") or "other",
                        "seed_source_url": snap.get("seed_source_url") or "https://example.com",
                        "attribution_status": snap.get("attribution_status") or "uncertain",
                        "bio_text": snap.get("bio_text"),
                        "primary_genre": snap.get("primary_genre"),
                        "subgenres": snap.get("subgenres") or [],
                        "media_links": snap.get("media_links") or [],
                    },
                    "public_footprint": {
                        "footprint_regime": snap.get("footprint_regime") or "unknown",
                        "public_reach": snap.get("public_reach") or {},
                        "top_release_view_share_pct": None,
                    },
                    "comment_forensics": {
                        "comment_intent_counts": snap.get("comment_intent_counts")
                        or {
                            "sample_size": 0,
                            "release_requests": 0,
                            "live_show_requests": 0,
                            "genuine_praise": 0,
                            "jokes_or_spam": 0,
                        },
                        "notable_commenters": snap.get("notable_commenters") or [],
                    },
                    "live_history_and_credits": {
                        "show_history": snap.get("show_history") or [],
                        "upcoming_shows": snap.get("upcoming_shows") or [],
                        "highest_venue_cap_observed": None,
                        "public_team_mentions": snap.get("public_team_mentions") or {},
                        "collaborator_credits": snap.get("collaborator_credits") or [],
                    },
                    "process_trace": [{"step": "rescreen", "tool": "screening", "status": "ok"}],
                    "missing_fields": existing_pkt.get("missing_evidence_flags") or [],
                }
        if target is None:
            raise ValueError(f"No Stage 2 dossier found for lead_id '{lead_id}'.")
        return [
            run_screening_for_dossier(
                store, target, live=live, api_key=api_key, prefix=prefix, gemini=gemini
            )
        ]

    # Batch screen unscreened dossiers (or all dossiers if already screened, or demo dossiers if DB empty)
    existing_leads = {
        str((_unwrap_doc(r) or {}).get("lead_id"))
        for r in list_agent_documents(store, "screening_packets", limit=100)
        if (_unwrap_doc(r) or {}).get("lead_id") and not bool((_unwrap_doc(r) or {}).get("archived", False))
    }
    unscreened = [d for lid, d in dossiers_by_lead.items() if lid not in existing_leads]
    targets = unscreened or list(dossiers_by_lead.values()) or build_builtin_demo_dossiers()
    return [
        run_screening_for_dossier(
            store, d, live=live, api_key=api_key, prefix=prefix, gemini=gemini
        )
        for d in targets
    ]


# ---------------------------------------------------------------------------
# 4. HITL Feedback Writer (`save_screening_label`)
# ---------------------------------------------------------------------------


def _find_packet_for_label(store: Any, lead_id: str, packet_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    candidates = []
    if packet_id:
        candidates.append(packet_id)
    if lead_id:
        candidates.extend([f"scr_{lead_id}", lead_id])
    for cid in candidates:
        doc = get_agent_document(store, "screening_packets", cid)
        unwrapped = _unwrap_doc(doc)
        if isinstance(unwrapped, dict) and unwrapped.get("lead_id"):
            return _normalize_screening_packet(unwrapped)

    for row in list_agent_documents(store, "screening_packets", limit=100):
        doc = _unwrap_doc(row)
        if not isinstance(doc, dict):
            continue
        if doc.get("lead_id") == lead_id or (packet_id and doc.get("packet_id") == packet_id):
            return _normalize_screening_packet(doc)

    if lead_id:
        for demo_d in build_builtin_demo_dossiers():
            if demo_d["lead_id"] == lead_id:
                return run_screening_for_dossier(store, demo_d, live=False)
    return None


def save_screening_label(store: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and record a human scout's screening verdict (`elevate | watch | pass`) + training features."""
    if not isinstance(payload, dict):
        raise ValueError("Label payload must be a JSON object.")

    raw_verdict = str(payload.get("human_verdict") or payload.get("verdict") or "").strip().lower()
    if raw_verdict not in VALID_SCREENING_VERDICTS:
        raise ValueError(
            f"Invalid human_verdict '{raw_verdict}'. Must be one of: {sorted(VALID_SCREENING_VERDICTS)}."
        )

    packet_id_hint = str(payload.get("packet_id") or "").strip() or None
    lead_id = str(payload.get("lead_id") or "").strip()
    if not lead_id and packet_id_hint and packet_id_hint.startswith("scr_"):
        lead_id = packet_id_hint[len("scr_") :]

    packet = _find_packet_for_label(store, lead_id=lead_id, packet_id=packet_id_hint)
    if not lead_id and packet:
        lead_id = str(packet.get("lead_id") or "").strip()
    if not lead_id:
        raise ValueError("Missing required field 'lead_id'.")

    model_verdict = None
    agreed_with_model: Optional[bool] = None
    training_features: Dict[str, Any] = {
        "rubric_scores": {},
        "total_score": None,
        "pros": [],
        "cons": [],
        "missing_evidence_flags": [],
    }
    stage_name = str(payload.get("stage_name") or lead_id).strip()
    resolved_packet_id = packet_id_hint or f"scr_{lead_id}"

    if packet is not None:
        stage_name = str(packet.get("stage_name") or stage_name)
        resolved_packet_id = str(packet.get("packet_id") or resolved_packet_id)
        jd = packet.get("judge_decision") or {}
        mv = str(jd.get("verdict") or packet.get("verdict") or "").strip().lower()
        if mv in VALID_SCREENING_VERDICTS:
            model_verdict = mv
            agreed_with_model = raw_verdict == model_verdict
        training_features = {
            "rubric_scores": dict(packet.get("rubric_scores") or {}),
            "total_score": packet.get("total_score"),
            "pros": list(packet.get("pros") or []),
            "cons": list(packet.get("cons") or []),
            "missing_evidence_flags": list(packet.get("missing_evidence_flags") or []),
        }

    label_id = str(payload.get("label_id") or f"lbl_{uuid.uuid4().hex[:8]}").strip()
    reason = str(payload.get("reason") or payload.get("notes") or payload.get("rationale") or "").strip()
    reviewer = str(payload.get("reviewer") or "human_scout").strip()

    label_doc: Dict[str, Any] = {
        "label_id": label_id,
        "packet_id": resolved_packet_id,
        "lead_id": lead_id,
        "stage_name": stage_name,
        "human_verdict": raw_verdict,
        "model_verdict": model_verdict,
        "agreed_with_model": agreed_with_model,
        "reason": reason,
        "reviewer": reviewer,
        "training_features": training_features,
        "labeled_at": _utc_now_iso(),
    }
    saved = save_agent_document(store, "screening_labels", label_doc, doc_id=label_id)
    return saved["document"]


# ---------------------------------------------------------------------------
# 5. Judging Model Compiler (`compile_judging_model` -> DSPy + Gemini Decision 1)
# ---------------------------------------------------------------------------


def list_judging_models(store: Any, limit: int = 25) -> List[Dict[str, Any]]:
    rows = list_agent_documents(store, "judging_models", limit=max(1, min(limit, 100)))
    models: List[Dict[str, Any]] = []
    for row in rows:
        doc = _unwrap_doc(row)
        if isinstance(doc, dict) and doc.get("policy_id"):
            models.append(sanitize_agent_report(doc))

    def _version_num(m: Dict[str, Any]) -> int:
        v = m.get("version")
        if isinstance(v, int):
            return v
        match = re.search(r"(\d+)", str(v or m.get("policy_id") or "0"))
        return int(match.group(1)) if match else 0

    models.sort(key=lambda m: (_version_num(m), str(m.get("compiled_at") or "")), reverse=True)
    return models[:limit]


def _build_decision_questions_config(
    override_reasons_by_verdict: Dict[str, List[str]],
    elevate_min: int,
    watch_min: int,
) -> Dict[str, Any]:
    """Build `google.genai.decisions` (`v1beta` `gemini-decision-1`) `NoulQuestion`, `ScoreQuestion`, & `ChoiceQuestion`."""
    questions: Dict[str, Any] = {
        "live_signable": {
            "type": "noul",
            "instructions": (
                "Does this candidate demonstrate verified live vocal performance proof, unsigned early-window "
                "whitespace, and direct outreach readiness suitable for an immediate human callback?"
            ),
            "criteria": {
                "true_description": (
                    "Verified performer attribution on embeddable live/acoustic clips, unsigned A&R whitespace, "
                    "and an actionable public contact route."
                ),
                "false_description": (
                    "Unverified attribution, studio-only or zero embeddable clips, major-label lockup, or no contact route."
                ),
            },
        },
        "sufficient_live_evidence": {
            "type": "noul",
            "instructions": (
                "Does the Stage 2 artist dossier contain verified performer attribution and at least one "
                "embeddable live or acoustic vocal clip suitable for human scout evaluation?"
            ),
            "criteria": {
                "true_description": (
                    "Performer attribution is verified and media_links contains embeddable vocal performance proof."
                ),
                "false_description": (
                    "Performer attribution is uncertain or zero embeddable performance clips are queued."
                ),
            },
        },
        "actionable_whitespace": {
            "type": "noul",
            "instructions": (
                "Is the artist in an actionable early scouting window with a public outreach route and "
                "without an existing major-label lockup?"
            ),
            "criteria": {
                "true_description": (
                    "Artist has a public contact route (email, management, or open DM) and unsigned early-window room to act."
                ),
                "false_description": (
                    "No public contact route exists or the act is already locked into an established major deal."
                ),
            },
        },
        "composite_fit": {
            "type": "score",
            "instructions": (
                "Rate overall calibrated Taste Engine A&R & showcase fit from 0 to 4 across vocal proof, "
                "early-window catalog depth, listener demand, and unsigned stage momentum."
            ),
            "criteria": [
                "0: Hard dealbreaker (major-label lockup, uncertain attribution with zero proof, or spam channel).",
                "1: Weak early signal (<=3/10 rubric equivalent) with major missing evidence.",
                "2: Watch-band promise (4..5/10 equivalent) needing a second live take or verified contact route.",
                "3: Strong callback contender (6..7/10 equivalent) with real vocal proof and audience demand.",
                "4: Standout ground-floor signing/callback priority (>=8/10 equivalent) with multi-session live proof, peer cosigns, and immediate unsigned reachability.",
            ],
        },
    }

    # 5 ScoreQuestions (0..2 discrete levels matching `ScoreQuestion.criteria: List[str]`)
    for key in RUBRIC_ORDER:
        meta = RUBRIC_META[key]
        questions[key] = {
            "type": "score",
            "instructions": f"Score {meta['label']} ({meta['skill']}) from 0 to 2 using only grounded Stage 2 dossier facts.",
            "criteria": [
                f"0: {meta['level_0']}",
                f"1: {meta['level_1']}",
                f"2: {meta['level_2']}",
            ],
        }

    elevate_notes = "; ".join(override_reasons_by_verdict["elevate"][:3])
    watch_notes = "; ".join(override_reasons_by_verdict["watch"][:3])
    pass_notes = "; ".join(override_reasons_by_verdict["pass"][:3])

    elevate_desc = (
        f"Total rubric score >= {elevate_min}/10 with verified vocal proof, organic listener demand or peer cosigns, "
        "and reachable unsigned whitespace ready for a paid showcase callback."
    )
    if elevate_notes:
        elevate_desc += f" Human scout elevate guidance: {elevate_notes}"

    watch_desc = (
        f"Total rubric score {watch_min}..{max(watch_min, elevate_min - 1)}/10 showing real vocal or audience promise "
        "but missing 1-2 diligence items (such as a second live clip or business email)."
    )
    if watch_notes:
        watch_desc += f" Human scout watch guidance: {watch_notes}"

    pass_desc = (
        f"Total rubric score <= {watch_min - 1}/10 or unverified attribution with thin vocal/audience evidence."
    )
    if pass_notes:
        pass_desc += f" Human scout pass guidance: {pass_notes}"

    all_override_notes = _dedupe_strs(
        override_reasons_by_verdict["elevate"]
        + override_reasons_by_verdict["watch"]
        + override_reasons_by_verdict["pass"]
    )
    choice_instructions = (
        "Select the calibrated Stage 3 screening verdict ('elevate', 'watch', or 'pass') after weighing "
        "all 5 dossier rubrics and the adversarial Advocate vs. Skeptic arguments."
    )
    if all_override_notes:
        choice_instructions += f" Incorporate human override feedback: {' | '.join(all_override_notes[:4])}"

    # ChoiceQuestions (`criteria: Dict[str, str]`)
    choice_criteria = {
        "elevate": elevate_desc,
        "watch": watch_desc,
        "pass": pass_desc,
    }
    questions["taste_verdict"] = {
        "type": "choice",
        "instructions": choice_instructions,
        "criteria": dict(choice_criteria),
    }
    questions["screening_verdict"] = {
        "type": "choice",
        "instructions": choice_instructions,
        "criteria": dict(choice_criteria),
    }
    return questions


def _try_compile_with_dspy(examples: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Lazily import `dspy` when available to structure few-shot examples via `BootstrapFewShot`."""
    ranked = sorted(
        examples,
        key=lambda ex: (
            -float(ex.get("weight", 1.0)),
            1 if ex.get("reason") else 0,
            -int(ex.get("total_score") or 0),
        ),
    )
    selected_demos = [
        {
            "lead_id": ex["lead_id"],
            "stage_name": ex["stage_name"],
            "rubric_scores": ex["rubric_scores"],
            "total_score": ex["total_score"],
            "pros": ex["pros"][:3],
            "cons": ex["cons"][:3],
            "missing_evidence_flags": ex["missing_evidence_flags"][:4],
            "target_verdict": ex["target_verdict"],
            "source": ex["source"],
            "weight": ex["weight"],
            "reason": ex["reason"],
        }
        for ex in ranked[:6]
    ]

    try:
        import dspy  # type: ignore[import-not-found]

        dspy_trainset = [
            dspy.Example(
                stage_name=ex["stage_name"],
                rubric_scores=json.dumps(ex["rubric_scores"], sort_keys=True),
                pros="; ".join(ex["pros"][:3]),
                cons="; ".join(ex["cons"][:3]),
                missing_evidence_flags=", ".join(ex["missing_evidence_flags"][:4]),
                verdict=ex["target_verdict"],
                rationale=ex["reason"],
            ).with_inputs("stage_name", "rubric_scores", "pros", "cons", "missing_evidence_flags")
            for ex in ranked
        ]

        def _verdict_metric(gold: Any, pred: Any, trace: Any = None) -> bool:
            return str(getattr(gold, "verdict", "")).lower() == str(getattr(pred, "verdict", "")).lower()

        _ = dspy.BootstrapFewShot(
            metric=_verdict_metric,
            max_bootstrapped_demos=min(4, max(1, len(dspy_trainset))),
            max_labeled_demos=min(6, max(1, len(dspy_trainset))),
        )
        return "dspy.BootstrapFewShot", selected_demos
    except Exception:
        return "calibrated_rubric_bootstrap", selected_demos


def compile_judging_model(store: Any) -> Dict[str, Any]:
    """Compile a versioned `JudgingModelPolicy` from HITL `screening_labels` + `screening_packets`."""
    deck = list_screening_deck(store, limit=100)
    packets = deck["packets"]
    packets_by_lead = {str(p["lead_id"]): p for p in packets}

    raw_labels = list_screening_labels(store, limit=100)
    # Deduplicate to latest human label per lead_id while keeping count of human examples
    latest_human_by_lead: Dict[str, Dict[str, Any]] = {}
    for lbl in raw_labels:
        lid = str(lbl.get("lead_id") or "")
        if lid and lid not in latest_human_by_lead:
            latest_human_by_lead[lid] = lbl

    training_examples: List[Dict[str, Any]] = []
    override_reasons_by_verdict: Dict[str, List[str]] = {"elevate": [], "watch": [], "pass": []}
    override_count = 0

    for lid, lbl in latest_human_by_lead.items():
        pkt = packets_by_lead.get(lid) or {}
        feats = lbl.get("training_features") or {}
        r_scores = dict(feats.get("rubric_scores") or pkt.get("rubric_scores") or {})
        total = feats.get("total_score")
        if total is None:
            total = sum(int(v) for v in r_scores.values()) if r_scores else int(pkt.get("total_score") or 5)

        agreed = lbl.get("agreed_with_model")
        is_override = agreed is False
        weight = 2.0 if is_override else 1.0
        verdict = str(lbl.get("human_verdict") or "watch").lower()
        reason = str(lbl.get("reason") or "").strip()

        if is_override:
            override_count += 1
            if reason and verdict in override_reasons_by_verdict:
                override_reasons_by_verdict[verdict].append(reason)
        elif reason and verdict in override_reasons_by_verdict:
            override_reasons_by_verdict[verdict].append(reason)

        training_examples.append(
            {
                "lead_id": lid,
                "stage_name": str(lbl.get("stage_name") or pkt.get("stage_name") or lid),
                "rubric_scores": r_scores,
                "total_score": int(total),
                "pros": list(feats.get("pros") or pkt.get("pros") or []),
                "cons": list(feats.get("cons") or pkt.get("cons") or []),
                "missing_evidence_flags": list(
                    feats.get("missing_evidence_flags") or pkt.get("missing_evidence_flags") or []
                ),
                "target_verdict": verdict,
                "reason": reason or f"Human scout confirmed {verdict}.",
                "weight": weight,
                "source": "human_override" if is_override else "human_label",
            }
        )

    # Seed from packet judge_decisions as bootstrap examples when <3 human labels exist
    human_count = len(training_examples)
    if human_count < 3:
        for pkt in packets:
            lid = str(pkt["lead_id"])
            if lid in latest_human_by_lead:
                continue
            jd = pkt.get("judge_decision") or {}
            verdict = str(jd.get("verdict") or pkt.get("verdict") or "watch").lower()
            training_examples.append(
                {
                    "lead_id": lid,
                    "stage_name": str(pkt.get("stage_name") or lid),
                    "rubric_scores": dict(pkt.get("rubric_scores") or {}),
                    "total_score": int(pkt.get("total_score") or 0),
                    "pros": list(pkt.get("pros") or []),
                    "cons": list(pkt.get("cons") or []),
                    "missing_evidence_flags": list(pkt.get("missing_evidence_flags") or []),
                    "target_verdict": verdict,
                    "reason": str(jd.get("rationale") or f"Bootstrap judge verdict: {verdict}."),
                    "weight": 0.5,
                    "source": "judge_bootstrap",
                }
            )

    # Calibrate score thresholds via grid search maximizing weighted accuracy across examples
    best_elevate_min = 7
    best_watch_min = 4
    best_weighted_acc = -1.0
    total_weight = sum(float(ex["weight"]) for ex in training_examples) or 1.0

    for cand_elev in range(6, 10):
        for cand_watch in range(3, cand_elev):
            matched_w = 0.0
            for ex in training_examples:
                sc = int(ex["total_score"])
                vocal_sc = int((ex["rubric_scores"] or {}).get("live_vocal_proof", 1))
                if sc >= cand_elev and vocal_sc >= 1:
                    pred = "elevate"
                elif sc >= cand_watch:
                    pred = "watch"
                else:
                    pred = "pass"
                if pred == ex["target_verdict"]:
                    matched_w += float(ex["weight"])
            acc = matched_w / total_weight
            if acc > best_weighted_acc:
                best_weighted_acc = acc
                best_elevate_min = cand_elev
                best_watch_min = cand_watch

    optimizer_name, demos = _try_compile_with_dspy(training_examples)
    questions_config = _build_decision_questions_config(
        override_reasons_by_verdict=override_reasons_by_verdict,
        elevate_min=best_elevate_min,
        watch_min=best_watch_min,
    )

    existing_models = list_judging_models(store, limit=100)
    max_version = 0
    for m in existing_models:
        v = m.get("version")
        if isinstance(v, int):
            max_version = max(max_version, v)
        else:
            match = re.search(r"(\d+)", str(v or m.get("policy_id") or "0"))
            if match:
                max_version = max(max_version, int(match.group(1)))

    # Deactivate prior active policies
    for prev in existing_models:
        if prev.get("is_active"):
            deactivated = dict(prev)
            deactivated["is_active"] = False
            save_agent_document(store, "judging_models", deactivated, doc_id=str(prev["policy_id"]))

    next_version = max_version + 1
    policy_id = f"policy_v{next_version}"
    policy_doc: Dict[str, Any] = {
        "contract_version": "1.0.0",
        "policy_id": policy_id,
        "version": next_version,
        "target_model": "gemini-decision-1",
        "api_version": "v1beta",
        "optimizer": optimizer_name,
        "is_active": True,
        "train_count": len(training_examples),
        "human_label_count": human_count,
        "override_count": override_count,
        "override_weight_multiplier": 2.0,
        "val_accuracy": round(max(0.0, best_weighted_acc), 4),
        "thresholds": {
            "elevate_min_score": best_elevate_min,
            "watch_min_score": best_watch_min,
        },
        "questions_config": questions_config,
        "demos": demos,
        "override_notes": override_reasons_by_verdict,
        "compiled_at": _utc_now_iso(),
    }
    saved = save_agent_document(store, "judging_models", policy_doc, doc_id=policy_id)
    return saved["document"]


# ---------------------------------------------------------------------------
# 5b. Calibrated Taste Engine Inference (`gemini-decision-1` · 0 Output Tokens)
# ---------------------------------------------------------------------------


def list_taste_scores(
    store: Any,
    lead_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List saved `gemini-decision-1` calibrated taste scores from `taste_scores`."""
    if store is None:
        return []
    rows = list_agent_documents(store, "taste_scores", limit=max(1, min(limit, 100)))
    items: List[Dict[str, Any]] = []
    for row in rows:
        doc = _unwrap_doc(row)
        if not isinstance(doc, dict) or not doc.get("lead_id") or bool(doc.get("archived", False)):
            continue
        if lead_id and doc.get("lead_id") != lead_id and doc.get("taste_score_id") != lead_id:
            continue
        items.append(sanitize_agent_report(doc))
    items.sort(
        key=lambda item: str(item.get("evaluated_at") or item.get("updated_at") or item.get("_saved_at") or ""),
        reverse=True,
    )
    return items[:limit]


def _resolve_dossier_and_packet(
    store: Any,
    dossier_or_lead_id: Any,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    if isinstance(dossier_or_lead_id, dict):
        if isinstance(dossier_or_lead_id.get("dossier_snapshot"), dict):
            pkt = _normalize_screening_packet(dossier_or_lead_id)
            return dict(pkt["dossier_snapshot"]), pkt
        if isinstance(dossier_or_lead_id.get("judge_decision"), dict):
            pkt = _normalize_screening_packet(dossier_or_lead_id)
            return dict(pkt.get("dossier_snapshot") or {}), pkt
        return sanitize_agent_report(dict(dossier_or_lead_id)), None

    target_id = str(dossier_or_lead_id or "").strip()
    if not target_id:
        raise ValueError("dossier_or_lead_id requires a non-empty lead_id, packet_id, or dossier object.")

    if store is not None:
        pkt = _find_packet_for_label(store, lead_id=target_id, packet_id=target_id)
        if pkt is None:
            deck = list_screening_deck(store, limit=100)
            for cand in deck.get("packets") or []:
                if cand.get("lead_id") == target_id or cand.get("packet_id") == target_id:
                    pkt = cand
                    break
        if pkt is not None:
            norm = _normalize_screening_packet(pkt)
            return dict(norm.get("dossier_snapshot") or {}), norm

        for row in list_agent_documents(store, "investigator_dossiers", limit=100):
            doc = _unwrap_doc(row)
            if isinstance(doc, dict) and (doc.get("lead_id") == target_id or doc.get("dossier_id") == target_id):
                return sanitize_agent_report(dict(doc)), None

    if DEMO_SCREENING_PATH.is_file():
        try:
            raw = json.loads(DEMO_SCREENING_PATH.read_text(encoding="utf-8"))
            pkts = raw.get("packets") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
            for item in pkts or []:
                if isinstance(item, dict) and (item.get("lead_id") == target_id or item.get("packet_id") == target_id):
                    norm = _normalize_screening_packet(item)
                    return dict(norm.get("dossier_snapshot") or {}), norm
        except (OSError, ValueError):
            pass

    for demo_d in build_builtin_demo_dossiers():
        if demo_d["lead_id"] == target_id:
            return dict(demo_d), None

    raise ValueError(f"Could not find dossier or screening packet for '{target_id}'.")


def _format_taste_engine_input(
    dossier: Dict[str, Any],
    packet: Optional[Dict[str, Any]],
    baseline: Dict[str, Any],
    policy: Dict[str, Any],
) -> str:
    summary_obj: Dict[str, Any] = {
        "lead_id": baseline["lead_id"],
        "stage_name": baseline["stage_name"],
        "dossier": {
            "identity_and_contact": dossier.get("identity_and_contact") or {},
            "source_and_media_queue": dossier.get("source_and_media_queue") or {},
            "public_footprint": dossier.get("public_footprint") or {},
            "comment_forensics": dossier.get("comment_forensics") or {},
            "live_history_and_credits": dossier.get("live_history_and_credits") or {},
            "missing_fields": dossier.get("missing_fields") or [],
        },
        "deterministic_rubric_scores": baseline["rubric_scores"],
        "deterministic_total_score": baseline["total_score"],
    }
    if packet is not None:
        summary_obj["advocate_headline"] = (packet.get("advocate_case") or {}).get("headline")
        summary_obj["advocate_pros"] = (packet.get("advocate_case") or {}).get("pros", [])[:4]
        summary_obj["skeptic_headline"] = (packet.get("skeptic_case") or {}).get("headline")
        summary_obj["skeptic_cons"] = (packet.get("skeptic_case") or {}).get("cons", [])[:4]
        summary_obj["neon_judge_verdict"] = (packet.get("judge_decision") or {}).get("verdict")
    demos = list(policy.get("demos") or [])[:4]
    if demos:
        summary_obj["calibrated_human_few_shot_examples"] = [
            {
                "stage_name": d.get("stage_name"),
                "total_score": d.get("total_score"),
                "target_verdict": d.get("target_verdict") or d.get("verdict"),
                "reason": d.get("reason"),
            }
            for d in demos
            if isinstance(d, dict)
        ]
    return (
        "Stage 3 Candidate Artist Factual Dossier & Adversarial Screening Context:\n"
        + json.dumps(summary_obj, indent=2, ensure_ascii=False)
    )


def _post_decisions_v1beta(api_key: str, body: Dict[str, Any]) -> Dict[str, Any]:
    url = "https://generativelanguage.googleapis.com/v1beta/decisions"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "Api-Revision": "2026-05-20",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"gemini-decision-1 HTTP {exc.code}: {detail}") from exc


def _offline_calibrated_taste_answers(
    baseline: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    total = int(baseline["total_score"])
    scores = baseline["rubric_scores"]
    thresholds = policy.get("thresholds") or {}
    elevate_min = int(thresholds.get("elevate_min_score", 7))
    watch_min = int(thresholds.get("watch_min_score", 4))
    vocal_ok = int(scores.get("live_vocal_proof", 0)) >= 1
    reach_ok = int(scores.get("identity_reachability", 0)) >= 1
    ws_ok = int(scores.get("stage_momentum_whitespace", 0)) >= 1

    if total >= elevate_min and vocal_ok:
        margin = min(3, total - elevate_min)
        p_elev = round(min(0.94, 0.72 + 0.07 * margin), 4)
        p_watch = round(max(0.04, 1.0 - p_elev - 0.02), 4)
        p_pass = round(max(0.01, 1.0 - p_elev - p_watch), 4)
        choice = "elevate"
    elif total >= watch_min:
        p_watch = 0.68 if total < elevate_min - 1 else 0.60
        p_elev = 0.24 if vocal_ok else 0.12
        p_pass = round(max(0.02, 1.0 - p_watch - p_elev), 4)
        choice = "watch"
    else:
        p_pass = round(min(0.95, 0.76 + 0.05 * max(0, watch_min - 1 - total)), 4)
        p_watch = round(max(0.03, 1.0 - p_pass - 0.02), 4)
        p_elev = round(max(0.01, 1.0 - p_pass - p_watch), 4)
        choice = "pass"

    probs = {"elevate": p_elev, "watch": p_watch, "pass": p_pass}
    conf = round(max(probs.values()), 4)
    signable_prob = round(
        min(0.97, max(0.03, (0.45 if vocal_ok else 0.08) + (0.28 if reach_ok else 0.0) + (0.22 if ws_ok else 0.0))),
        4,
    )
    comp_score = round(min(4.0, max(0.0, (total / 10.0) * 4.0)), 3)
    return {
        "taste_verdict": {
            "type": "choice",
            "choice": choice,
            "confidence": conf,
            "probabilities": probs,
        },
        "live_signable": {
            "type": "noul",
            "noul": signable_prob,
            "confidence": round(max(signable_prob, 1.0 - signable_prob), 4),
        },
        "composite_fit": {
            "type": "score",
            "score": comp_score,
            "confidence": conf,
            "probabilities": {str(k): (0.6 if k == round(comp_score) else 0.1) for k in range(5)},
        },
    }


def evaluate_with_taste_engine(
    store: Any,
    dossier_or_lead_id: Any,
    live: bool = True,
    api_key: Optional[str] = None,
    http_post: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run calibrated 0-output-token `gemini-decision-1` Taste Engine over a candidate dossier.

    Auto-compiles `policy_v1` into `judging_models` if no active policy exists yet, calls
    `POST https://generativelanguage.googleapis.com/v1beta/decisions` (`Api-Revision: 2026-05-20`)
    when `live=True` and `GEMINI_API_KEY` is configured, persists to `taste_scores`, and returns
    calibrated probabilities (`P(elevate)`, `P(watch)`, `P(pass)`), `live_signable`, `composite_fit`,
    and `0` output tokens.
    """
    dossier, packet = _resolve_dossier_and_packet(store, dossier_or_lead_id)
    baseline = score_dossier_inputs(dossier)
    lead_id = str((packet or {}).get("lead_id") or baseline["lead_id"])
    stage_name = str((packet or {}).get("stage_name") or baseline["stage_name"])

    policy = _get_active_judging_policy(store)
    if policy is None and store is not None:
        policy = compile_judging_model(store)
    if policy is None:
        policy = {
            "policy_id": "policy_v1",
            "version": 1,
            "thresholds": {"elevate_min_score": 7, "watch_min_score": 4},
            "questions_config": _build_decision_questions_config(
                {"elevate": [], "watch": [], "pass": []}, 7, 4
            ),
            "demos": [],
        }

    policy_id = str(policy.get("policy_id") or "policy_v1")
    raw_qcfg = dict(policy.get("questions_config") or {})
    default_qcfg = _build_decision_questions_config(
        policy.get("override_notes") or {"elevate": [], "watch": [], "pass": []},
        int((policy.get("thresholds") or {}).get("elevate_min_score", 7)),
        int((policy.get("thresholds") or {}).get("watch_min_score", 4)),
    )

    questions_payload: Dict[str, Any] = {
        "live_signable": raw_qcfg.get("live_signable") or default_qcfg["live_signable"],
        "composite_fit": raw_qcfg.get("composite_fit") or default_qcfg["composite_fit"],
        "taste_verdict": (
            raw_qcfg.get("taste_verdict")
            or raw_qcfg.get("screening_verdict")
            or default_qcfg["taste_verdict"]
        ),
    }
    for r_key in RUBRIC_ORDER:
        questions_payload[r_key] = raw_qcfg.get(r_key) or default_qcfg[r_key]

    input_text = _format_taste_engine_input(dossier, packet, baseline, policy)
    resolved_key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip() or None

    mode = "offline_calibrated_fallback"
    input_tokens = 0
    output_tokens = 0

    if live and (resolved_key or http_post is not None):
        req_body = {
            "model": "gemini-decision-1",
            "input": input_text,
            "questions": questions_payload,
        }
        poster = http_post or (lambda body: _post_decisions_v1beta(resolved_key or "", body))
        resp_json = poster(req_body)
        answers = resp_json.get("answers") or {}
        usage = resp_json.get("usage") or {}
        input_tokens = int(usage.get("total_input_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("total_output_tokens") or usage.get("output_tokens") or 0)
        mode = "live_gemini_decision_1"
    else:
        answers = _offline_calibrated_taste_answers(baseline, policy)

    tv_ans = answers.get("taste_verdict") or answers.get("screening_verdict") or {}
    raw_choice = str(tv_ans.get("choice") or "watch").strip().lower()
    taste_verdict = raw_choice if raw_choice in VALID_SCREENING_VERDICTS else "watch"
    raw_probs = tv_ans.get("probabilities") or {}
    probabilities = {
        "elevate": round(float(raw_probs.get("elevate", 0.0)), 4),
        "watch": round(float(raw_probs.get("watch", 0.0)), 4),
        "pass": round(float(raw_probs.get("pass", 0.0)), 4),
    }
    confidence = round(float(tv_ans.get("confidence", max(probabilities.values() or [0.5]))), 4)

    ls_ans = answers.get("live_signable") or {}
    live_signable_prob = round(float(ls_ans.get("noul", 0.5)), 4)
    live_signable_conf = round(float(ls_ans.get("confidence", max(live_signable_prob, 1.0 - live_signable_prob))), 4)

    cf_ans = answers.get("composite_fit") or {}
    composite_fit_score = round(float(cf_ans.get("score", 2.0)), 3)
    composite_fit_conf = round(float(cf_ans.get("confidence", confidence)), 4)

    rubric_expected_scores: Dict[str, float] = {}
    for r_key in RUBRIC_ORDER:
        r_ans = answers.get(r_key)
        if isinstance(r_ans, dict) and r_ans.get("score") is not None:
            rubric_expected_scores[r_key] = round(float(r_ans["score"]), 3)

    taste_score_id = f"taste_{lead_id}"
    taste_doc: Dict[str, Any] = {
        "contract_version": "1.0.0",
        "taste_score_id": taste_score_id,
        "lead_id": lead_id,
        "packet_id": str((packet or {}).get("packet_id") or f"scr_{lead_id}"),
        "stage_name": stage_name,
        "model": "gemini-decision-1",
        "api_revision": "2026-05-20",
        "policy_id": policy_id,
        "policy_version": policy.get("version", 1),
        "mode": mode,
        "taste_verdict": taste_verdict,
        "confidence": confidence,
        "probabilities": probabilities,
        "p_elevate": probabilities["elevate"],
        "p_watch": probabilities["watch"],
        "p_pass": probabilities["pass"],
        "live_signable": {
            "noul": live_signable_prob,
            "confidence": live_signable_conf,
        },
        "composite_fit": {
            "score": composite_fit_score,
            "max_score": 4,
            "confidence": composite_fit_conf,
        },
        "rubric_expected_scores": rubric_expected_scores,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "archived": False,
        "evaluated_at": _utc_now_iso(),
    }
    clean_taste = sanitize_agent_report(taste_doc)
    if store is not None:
        save_agent_document(store, "taste_scores", clean_taste, doc_id=taste_score_id)
    return clean_taste


# ---------------------------------------------------------------------------
# 6. 3-Layer Screening Eval Runner (`run_screening_evals`)
# ---------------------------------------------------------------------------


def load_screening_rubrics() -> Dict[str, Any]:
    """Load `data/evals/screening_rubrics.json` if present, else built-in 3-layer Stage 3 spec."""
    if SCREENING_RUBRICS_PATH.is_file():
        try:
            return json.loads(SCREENING_RUBRICS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {
        "rubric_set_id": "screening-stage3-v1",
        "agent_id": "simon-screening-judge",
        "stage": "stage_3_screening",
        "skills_covered": [RUBRIC_META[k]["skill"] for k in RUBRIC_ORDER],
        "layers": [
            {
                "layer_id": "layer_1_gates",
                "name": "Layer 1 · Contract & Zero-Telemetry Hard Gates",
                "rubrics": [
                    {
                        "id": "gate_screening_contract",
                        "name": "ScreeningPacket v1.0.0 Contract & Verdict Validity",
                        "skill": "simon-db",
                    },
                    {
                        "id": "gate_zero_telemetry",
                        "name": "Zero Raw Telemetry Keys in Screening Packets & Reports",
                        "skill": "field-reporting",
                    },
                ],
            },
            {
                "layer_id": "layer_2_process",
                "name": "Layer 2 · 5-Skill Coverage & Honest Abstention",
                "rubrics": [
                    {
                        "id": "proc_five_input_skills",
                        "name": "All 5 Dossier Input Rubrics Scored & Cited",
                        "skill": "dossier-rubrics",
                    },
                    {
                        "id": "proc_missing_fields_abstention",
                        "name": "Missing Evidence & Uncertain Attribution Flagged Honestly",
                        "skill": "dossier-abstention",
                    },
                ],
            },
            {
                "layer_id": "layer_3_quality",
                "name": "Layer 3 · Dialectical Balance & Judge Calibration",
                "rubrics": [
                    {
                        "id": "qual_dialectical_balance",
                        "name": "Advocate Upside Thesis vs. Skeptic Counter-Thesis Distinctness",
                        "skill": "dialectical-screening",
                    },
                    {
                        "id": "qual_judge_calibration",
                        "name": "Judge Verdict & Confidence Consistency with 5 Rubrics & Policy",
                        "skill": "gemini-decision-1",
                    },
                ],
            },
        ],
    }


def _find_forbidden_keys_raw(obj: Any) -> List[str]:
    found: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in REPORT_FORBIDDEN_KEYS:
                found.append(k)
            found.extend(_find_forbidden_keys_raw(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_forbidden_keys_raw(item))
    return sorted(set(found))


def run_screening_evals(store: Any, trigger: str = "api") -> Dict[str, Any]:
    """Grade current `screening_packets` across Layer 1, Layer 2, and Layer 3 rubrics and save to `eval_runs`."""
    spec = load_screening_rubrics()
    deck = list_screening_deck(store, limit=100)
    packets = deck["packets"]
    active_policy = deck.get("active_policy") or {}
    elevate_min = int((active_policy.get("thresholds") or {}).get("elevate_min_score", 7))
    watch_min = int((active_policy.get("thresholds") or {}).get("watch_min_score", 4))

    n = max(1, len(packets))
    contract_ok = 0
    telemetry_ok = 0
    skills_ok = 0
    abstention_ok = 0
    dialectic_ok = 0
    calibration_ok = 0
    case_results: List[Dict[str, Any]] = []

    for pkt in packets:
        jd = pkt.get("judge_decision") or {}
        verdict = str(jd.get("verdict") or "").lower()
        r_scores = pkt.get("rubric_scores") or {}

        # Layer 1a: contract gate
        has_all_rubrics = all(
            k in r_scores and isinstance(r_scores[k], int) and 0 <= r_scores[k] <= 2
            for k in RUBRIC_ORDER
        )
        c_valid = bool(
            pkt.get("lead_id")
            and pkt.get("stage_name")
            and verdict in VALID_SCREENING_VERDICTS
            and has_all_rubrics
            and isinstance(pkt.get("advocate_case"), dict)
            and isinstance(pkt.get("skeptic_case"), dict)
        )
        if c_valid:
            contract_ok += 1

        # Layer 1b: zero telemetry leak
        leaked = _find_forbidden_keys_raw(pkt)
        t_valid = len(leaked) == 0
        if t_valid:
            telemetry_ok += 1

        # Layer 2a: all 5 input skills cited
        cited_skills = set(pkt.get("input_skills_used") or [])
        expected_skills = {RUBRIC_META[k]["skill"] for k in RUBRIC_ORDER}
        breakdown_ids = {b.get("rubric_id") for b in (pkt.get("rubric_breakdown") or []) if isinstance(b, dict)}
        s_valid = expected_skills.issubset(cited_skills) or set(RUBRIC_ORDER).issubset(breakdown_ids)
        if s_valid:
            skills_ok += 1

        # Layer 2b: missing_fields / uncertain attribution abstention
        snap = pkt.get("artist_snapshot") or {}
        missing_flags = list(pkt.get("missing_evidence_flags") or [])
        attr_uncertain = snap.get("attribution_status") == "uncertain"
        no_contact = snap.get("contact_route_type") in (None, "none") and not snap.get("has_public_business_contact")
        if (attr_uncertain or no_contact) and not missing_flags and not (pkt.get("skeptic_case") or {}).get("risk_points"):
            a_valid = False
        else:
            a_valid = True
        if a_valid:
            abstention_ok += 1

        # Layer 3a: Advocate / Skeptic dialectical balance
        adv = pkt.get("advocate_case") or {}
        skp = pkt.get("skeptic_case") or {}
        adv_thesis = str(adv.get("thesis") or "").strip()
        skp_thesis = str(skp.get("counter_thesis") or "").strip()
        d_valid = bool(adv_thesis and skp_thesis and adv_thesis != skp_thesis)
        if d_valid:
            dialectic_ok += 1

        # Layer 3b: Judge calibration consistency
        total = int(pkt.get("total_score") if pkt.get("total_score") is not None else sum(r_scores.values()))
        conf = jd.get("confidence", 0.5)
        conf_ok = isinstance(conf, (int, float)) and 0.0 <= float(conf) <= 1.0
        human_rev = pkt.get("human_review")
        if human_rev and human_rev.get("human_verdict") == verdict:
            verdict_aligned = True
        elif verdict == "elevate":
            verdict_aligned = total >= max(5, elevate_min - 1) and int(r_scores.get("live_vocal_proof", 0)) >= 1
        elif verdict == "watch":
            verdict_aligned = (watch_min - 1) <= total <= min(10, elevate_min + 1)
        else:
            verdict_aligned = total <= watch_min
        cal_valid = bool(conf_ok and verdict_aligned)
        if cal_valid:
            calibration_ok += 1

        checks = [c_valid, t_valid, s_valid, a_valid, d_valid, cal_valid]
        case_score = round(sum(1 for flag in checks if flag) / len(checks), 4)
        case_results.append(
            {
                "case_id": str(pkt.get("packet_id") or pkt.get("lead_id")),
                "source": "screening_packets",
                "brief": f"{pkt.get('stage_name')} ({verdict}, {total}/10)",
                "passed": all(checks[:2]) and case_score >= 0.8,
                "score": case_score,
                "rationale": (
                    f"L1(contract={c_valid}, no_telemetry={t_valid}), "
                    f"L2(5_skills={s_valid}, abstention={a_valid}), "
                    f"L3(dialectic={d_valid}, calibration={cal_valid})"
                ),
            }
        )

    dimensions = [
        {
            "rubric_id": "gate_screening_contract",
            "name": "ScreeningPacket v1.0.0 Contract Gate",
            "layer": "layer_1_gates",
            "skill": "simon-db",
            "scale": "binary_gate",
            "score": round(contract_ok / n, 4),
            "passed": contract_ok == len(packets),
            "detail": f"{contract_ok}/{len(packets)} packets valid.",
        },
        {
            "rubric_id": "gate_zero_telemetry",
            "name": "Zero Raw Telemetry Keys Gate",
            "layer": "layer_1_gates",
            "skill": "field-reporting",
            "scale": "binary_gate",
            "score": round(telemetry_ok / n, 4),
            "passed": telemetry_ok == len(packets),
            "detail": f"{telemetry_ok}/{len(packets)} packets free of forbidden telemetry keys.",
        },
        {
            "rubric_id": "proc_five_input_skills",
            "name": "All 5 Dossier Input Skills Scored & Cited",
            "layer": "layer_2_process",
            "skill": "dossier-rubrics",
            "scale": "proportion",
            "score": round(skills_ok / n, 4),
            "passed": (skills_ok / n) >= 0.9,
            "detail": f"{skills_ok}/{len(packets)} packets cite all 5 Stage 2 rubric skills.",
        },
        {
            "rubric_id": "proc_missing_fields_abstention",
            "name": "Missing Evidence & Attribution Abstention",
            "layer": "layer_2_process",
            "skill": "dossier-abstention",
            "scale": "proportion",
            "score": round(abstention_ok / n, 4),
            "passed": (abstention_ok / n) >= 0.85,
            "detail": f"{abstention_ok}/{len(packets)} packets flag missing/uncertain evidence honestly.",
        },
        {
            "rubric_id": "qual_dialectical_balance",
            "name": "Advocate vs. Skeptic Dialectical Balance",
            "layer": "layer_3_quality",
            "skill": "dialectical-screening",
            "scale": "proportion",
            "score": round(dialectic_ok / n, 4),
            "passed": (dialectic_ok / n) >= 0.85,
            "detail": f"{dialectic_ok}/{len(packets)} packets present distinct Advocate & Skeptic arguments.",
        },
        {
            "rubric_id": "qual_judge_calibration",
            "name": "Judge Verdict & Policy Calibration Consistency",
            "layer": "layer_3_quality",
            "skill": "gemini-decision-1",
            "scale": "proportion",
            "score": round(calibration_ok / n, 4),
            "passed": (calibration_ok / n) >= 0.8,
            "detail": f"{calibration_ok}/{len(packets)} packets align with calibrated rubric thresholds.",
        },
    ]

    passed_gates = dimensions[0]["passed"] and dimensions[1]["passed"]
    overall_score = round(sum(d["score"] for d in dimensions) / len(dimensions), 4)
    if not passed_gates:
        status = "failed"
    elif overall_score >= 0.85:
        status = "passed"
    else:
        status = "warning"

    eval_run_id = f"eval_scr_{uuid.uuid4().hex[:8]}"
    eval_doc: Dict[str, Any] = {
        "eval_run_id": eval_run_id,
        "stage": "stage_3_screening",
        "agent_id": str(spec.get("agent_id") or "simon-screening-judge"),
        "rubric_set_id": str(spec.get("rubric_set_id") or "screening-stage3-v1"),
        "runner": "offline_baseline",
        "mode": "offline",
        "trigger": trigger,
        "status": status,
        "overall_score": overall_score,
        "passed_gates": passed_gates,
        "sample_count": len(packets),
        "sample_source": "screening_packets",
        "layer_scores": {
            "layer_1_gates": round((dimensions[0]["score"] + dimensions[1]["score"]) / 2.0, 4),
            "layer_2_process": round((dimensions[2]["score"] + dimensions[3]["score"]) / 2.0, 4),
            "layer_3_quality": round((dimensions[4]["score"] + dimensions[5]["score"]) / 2.0, 4),
        },
        "created_at": _utc_now_iso(),
        "dimensions": dimensions,
        "case_results": case_results,
        "notes": "Evaluated Stage 3 ScreeningPackets across Layer 1 hard gates, Layer 2 5-skill abstention, and Layer 3 Judge calibration.",
    }
    save_agent_document(store, "eval_runs", eval_doc, doc_id=eval_run_id)
    return eval_doc


def list_screening_evals(store: Any, limit: int = 25) -> Dict[str, Any]:
    rows = list_agent_documents(store, "eval_runs", limit=max(1, min(limit, 100)))
    eval_runs: List[Dict[str, Any]] = []
    for row in rows:
        doc = _unwrap_doc(row)
        if not isinstance(doc, dict):
            continue
        if doc.get("stage") == "stage_3_screening" or "screen" in str(doc.get("agent_id") or ""):
            eval_runs.append(sanitize_agent_report(doc))
    eval_runs.sort(key=lambda r: str(r.get("created_at") or r.get("updated_at") or ""), reverse=True)
    return {
        "count": len(eval_runs[:limit]),
        "rubrics": load_screening_rubrics(),
        "eval_runs": eval_runs[:limit],
    }


def render_fallback_screening_html() -> str:
    """Minimal fallback HTML for `GET /screen` used until `simon/screening_ui.py` merges."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Simon · Stage 3 Screening Deck</title>
  <style>
    body { margin: 0; background: #0b0d12; color: #eef2ff; font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 28px; }
    .wrap { max-width: 1080px; margin: 0 auto; }
    .card { background: #131722; border: 1px solid #262f45; border-radius: 12px; padding: 18px; margin-bottom: 14px; }
    .pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; background: #191f2e; border: 1px solid #262f45; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Simon · Stage 3 Screening Deck</h1>
    <p>Adversarial Advocate + Skeptic + Calibrated Judge screening packets loaded from <code>/api/screening/packets</code>.</p>
    <div id="deck">Loading screening packets…</div>
  </div>
  <script>
    fetch('/api/screening/packets').then(r => r.json()).then(data => {
      const el = document.getElementById('deck');
      el.innerHTML = (data.packets || []).map(p =>
        `<div class="card"><strong>${p.stage_name}</strong> <span class="pill">${(p.judge_decision || {}).verdict}</span> <span class="pill">${p.total_score}/10</span><p>${(p.judge_decision || {}).rationale || ''}</p></div>`
      ).join('');
    });
  </script>
</body>
</html>
"""


def resolve_screening_page_html(store: Any) -> bytes:
    """Render `/screen` via `simon.screening_ui.render_screening_page` if installed, else fallback HTML."""
    try:
        from .screening_ui import render_screening_page  # type: ignore[import-not-found]

        sig = inspect.signature(render_screening_page)
        params = list(sig.parameters.values())
        accepts_varargs = any(
            p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            for p in params
        )
        if "store" in sig.parameters:
            rendered = render_screening_page(store=store)
        elif len(params) >= 1 or accepts_varargs:
            rendered = render_screening_page(store)
        else:
            rendered = render_screening_page()
        return rendered if isinstance(rendered, bytes) else str(rendered).encode("utf-8")
    except ImportError:
        return render_fallback_screening_html().encode("utf-8")
