"""Layer 1 Domain-Agnostic Stage 2 Scout Investigator Pipeline (Option A).

Orchestrates 4 testable agents + 1 deterministic Python assembler per DiscoveryLead:
- Phase A (Sequential Anchor): `identity-resolver` (1a Generic -> 1b Domain)
- Phase B (3-Way Concurrent Fan-Out):
    * `footprint-profiler` (2a Generic || 2b Domain -> deterministic Python stats)
    * `signal-forensics` (fetch once -> 1-pass merged generic + domain classifier)
    * `track-record-mapper` (4a Generic || 4b Domain)
- Phase C (Deterministic Join): `dossier-assembler` (merge, abstain, log sources, schema check)

Also provides deterministic Process Evals (`evaluate_dossier_process`, `evaluate_batch_process`)
that grade step-by-step execution rather than only final text.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Protocol

from .investigator_music import (
    EMAIL_RE,
    MusicDomainPack,
    classify_footprint_regime,
    compute_top_release_view_share_pct,
)

REQUIRED_TRACE_STEPS = (
    "1a_identity_generic",
    "1b_identity_domain",
    "2a_footprint_generic",
    "2b_footprint_domain",
    "3_signal_forensics",
    "4a_track_record_generic",
    "4b_track_record_domain",
    "5_dossier_assembler",
)

FORBIDDEN_RANKING_KEYS = frozenset(
    {
        "rank",
        "score",
        "overall_score",
        "fit_score",
        "rating",
        "grade",
        "tier",
        "career_stage_tier",
        "recommendation",
        "verdict",
        "whitespace_opportunity_flags",
    }
)


class DomainInvestigatorPack(Protocol):
    """Layer 2 plug-in interface so any vertical plugs into Layer 1 without rewriting the DAG."""

    domain: str

    def resolve_identity_generic(self, lead: Dict[str, Any]) -> Dict[str, Any]: ...
    def resolve_identity_domain(
        self, lead: Dict[str, Any], generic_identity: Dict[str, Any]
    ) -> Dict[str, Any]: ...
    def profile_footprint_generic(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]: ...
    def profile_footprint_domain(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]: ...
    def run_signal_forensics(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]: ...
    def map_track_record_generic(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]: ...
    def map_track_record_domain(self, identity_bundle: Dict[str, Any]) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Phase A: Agent 1 — identity-resolver (Strict 1a Generic -> 1b Domain)
# ---------------------------------------------------------------------------
def run_identity_resolver(
    lead: Dict[str, Any],
    pack: Optional[DomainInvestigatorPack] = None,
) -> Dict[str, Any]:
    active_pack = pack or MusicDomainPack()
    generic = active_pack.resolve_identity_generic(lead)
    domain = active_pack.resolve_identity_domain(lead, generic)

    return {
        "lead_id": lead["lead_id"],
        "identity_and_contact": {
            "stage_name": generic["stage_name"],
            "aliases": domain["aliases"],
            "pronouns": generic["pronouns"],
            "project_type": domain["project_type"],
            "home_city": generic["home_city"],
            "home_neighborhood": generic["home_neighborhood"],
            "platform_urls": generic["platform_urls"],
            "musicbrainz_mbid": domain["musicbrainz_mbid"],
            "has_public_business_contact": generic["has_public_business_contact"],
            "contact_route_type": generic["contact_route_type"],
        },
        "source_and_media_queue": {
            "source_channel": generic["source_channel"],
            "seed_source_url": generic["seed_source_url"],
            "attribution_status": generic["attribution_status"],
            "bio_text": generic["bio_text"],
            "primary_genre": domain["primary_genre"],
            "subgenres": domain["subgenres"],
            "media_links": [],
        },
        "process_trace": [generic["trace"], domain["trace"]],
        "missing_fields": list(dict.fromkeys(generic["missing_fields"] + domain["missing_fields"])),
        "newly_discovered_sources": list(
            generic["newly_discovered_sources"] + domain["newly_discovered_sources"]
        ),
    }


# ---------------------------------------------------------------------------
# Phase B (Parallel): Agent 2 — footprint-profiler (2a || 2b -> Python math)
# ---------------------------------------------------------------------------
def run_footprint_profiler(
    identity_bundle: Dict[str, Any],
    pack: Optional[DomainInvestigatorPack] = None,
) -> Dict[str, Any]:
    active_pack = pack or MusicDomainPack()
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_generic = pool.submit(active_pack.profile_footprint_generic, identity_bundle)
        fut_domain = pool.submit(active_pack.profile_footprint_domain, identity_bundle)
        generic = fut_generic.result()
        domain = fut_domain.result()

    public_reach = {
        "youtube_subscribers": generic["youtube_subscribers"],
        "top_video_views": generic["top_video_views"],
        "bandcamp_releases_count": domain["bandcamp_releases_count"],
        "bandcamp_supporters_count": domain["bandcamp_supporters_count"],
        "released_tracks_count": domain["released_tracks_count"],
    }
    top_share = compute_top_release_view_share_pct(generic.get("view_counts") or [])
    footprint_regime = classify_footprint_regime(
        identity_bundle["identity_and_contact"]["platform_urls"],
        public_reach,
    )

    missing = list(dict.fromkeys(generic["missing_fields"] + domain["missing_fields"]))
    if top_share is None:
        missing.append("public_footprint.top_release_view_share_pct")

    return {
        "media_links": generic["media_links"],
        "public_footprint": {
            "footprint_regime": footprint_regime,
            "public_reach": public_reach,
            "top_release_view_share_pct": top_share,
        },
        "process_trace": [generic["trace"], domain["trace"]],
        "missing_fields": list(dict.fromkeys(missing)),
        "newly_discovered_sources": list(
            generic["newly_discovered_sources"] + domain["newly_discovered_sources"]
        ),
    }


# ---------------------------------------------------------------------------
# Phase B (Parallel): Agent 3 — signal-forensics (1-pass merged classifier)
# ---------------------------------------------------------------------------
def run_signal_forensics(
    identity_bundle: Dict[str, Any],
    pack: Optional[DomainInvestigatorPack] = None,
) -> Dict[str, Any]:
    active_pack = pack or MusicDomainPack()
    result = active_pack.run_signal_forensics(identity_bundle)
    return {
        "comment_forensics": {
            "comment_intent_counts": result["comment_intent_counts"],
            "notable_commenters": result["notable_commenters"],
        },
        "process_trace": [result["trace"]],
        "missing_fields": list(result["missing_fields"]),
        "newly_discovered_sources": list(result["newly_discovered_sources"]),
    }


# ---------------------------------------------------------------------------
# Phase B (Parallel): Agent 4 — track-record-mapper (4a || 4b)
# ---------------------------------------------------------------------------
def run_track_record_mapper(
    identity_bundle: Dict[str, Any],
    pack: Optional[DomainInvestigatorPack] = None,
) -> Dict[str, Any]:
    active_pack = pack or MusicDomainPack()
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_generic = pool.submit(active_pack.map_track_record_generic, identity_bundle)
        fut_domain = pool.submit(active_pack.map_track_record_domain, identity_bundle)
        generic = fut_generic.result()
        domain = fut_domain.result()

    # Deduplicate collaborator credits across bio (4a) and domain registries (4b)
    merged_credits: List[Dict[str, Any]] = []
    seen = set()
    for credit in generic["collaborator_credits"] + domain["collaborator_credits"]:
        key = (str(credit.get("name", "")).lower(), str(credit.get("role", "")).lower())
        if key not in seen:
            seen.add(key)
            merged_credits.append(credit)

    missing = list(dict.fromkeys(generic["missing_fields"] + domain["missing_fields"]))
    if not merged_credits:
        missing.append("live_history_and_credits.collaborator_credits")

    return {
        "live_history_and_credits": {
            "show_history": domain["show_history"],
            "upcoming_shows": domain["upcoming_shows"],
            "highest_venue_cap_observed": domain["highest_venue_cap_observed"],
            "public_team_mentions": generic["public_team_mentions"],
            "collaborator_credits": merged_credits,
        },
        "process_trace": [generic["trace"], domain["trace"]],
        "missing_fields": list(dict.fromkeys(missing)),
        "newly_discovered_sources": list(
            generic["newly_discovered_sources"] + domain["newly_discovered_sources"]
        ),
    }


# ---------------------------------------------------------------------------
# Phase C: Deterministic Python Join — dossier-assembler
# ---------------------------------------------------------------------------
def assemble_dossier(
    identity_bundle: Dict[str, Any],
    footprint_result: Dict[str, Any],
    forensics_result: Dict[str, Any],
    track_record_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Deterministically merge all 4 agent outputs into a contract-valid InvestigatorDossier."""
    source_and_media = dict(identity_bundle["source_and_media_queue"])
    source_and_media["media_links"] = footprint_result["media_links"]

    merged_trace = (
        list(identity_bundle["process_trace"])
        + list(footprint_result["process_trace"])
        + list(forensics_result["process_trace"])
        + list(track_record_result["process_trace"])
    )
    merged_missing = list(
        dict.fromkeys(
            identity_bundle["missing_fields"]
            + footprint_result["missing_fields"]
            + forensics_result["missing_fields"]
            + track_record_result["missing_fields"]
        )
    )
    # Deduplicate newly discovered sources by URL
    merged_sources: List[Dict[str, Any]] = []
    seen_urls = set()
    for src in (
        identity_bundle["newly_discovered_sources"]
        + footprint_result["newly_discovered_sources"]
        + forensics_result["newly_discovered_sources"]
        + track_record_result["newly_discovered_sources"]
    ):
        url = src.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged_sources.append(src)

    merged_trace.append(
        {
            "step": "5_dossier_assembler",
            "tool": "assemble_dossier",
            "status": "ok",
            "evidence_urls": [],
            "notes": f"Merged 4 agents; {len(merged_missing)} missing field(s), {len(merged_sources)} discovered source(s).",
        }
    )

    return {
        "lead_id": identity_bundle["lead_id"],
        "identity_and_contact": identity_bundle["identity_and_contact"],
        "source_and_media_queue": source_and_media,
        "public_footprint": footprint_result["public_footprint"],
        "comment_forensics": forensics_result["comment_forensics"],
        "live_history_and_credits": track_record_result["live_history_and_credits"],
        "process_trace": merged_trace,
        "newly_discovered_sources": merged_sources,
        "missing_fields": merged_missing,
    }


def investigate_lead(
    lead: Dict[str, Any],
    pack: Optional[DomainInvestigatorPack] = None,
) -> Dict[str, Any]:
    """Run Phase A -> Phase B (3 concurrent agents) -> Phase C for one DiscoveryLead."""
    active_pack = pack or MusicDomainPack()

    # Phase A: Sequential anchor
    identity_bundle = run_identity_resolver(lead, pack=active_pack)

    # Phase B: 3-way concurrent fan-out
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_footprint = pool.submit(run_footprint_profiler, identity_bundle, active_pack)
        fut_forensics = pool.submit(run_signal_forensics, identity_bundle, active_pack)
        fut_track_record = pool.submit(run_track_record_mapper, identity_bundle, active_pack)
        footprint_res = fut_footprint.result()
        forensics_res = fut_forensics.result()
        track_record_res = fut_track_record.result()

    # Phase C: Deterministic Python join
    return assemble_dossier(identity_bundle, footprint_res, forensics_res, track_record_res)


def investigate_handoff(
    handoff: Dict[str, Any],
    pack: Optional[DomainInvestigatorPack] = None,
    max_concurrent_leads: int = 4,
) -> Dict[str, Any]:
    """Investigate an entire Stage 1 DiscoveryHandoff concurrently across leads."""
    active_pack = pack or MusicDomainPack()
    leads = list(handoff.get("leads") or [])
    if not leads:
        dossiers: List[Dict[str, Any]] = []
    else:
        with ThreadPoolExecutor(max_workers=min(max_concurrent_leads, len(leads))) as pool:
            dossiers = list(pool.map(lambda lead: investigate_lead(lead, pack=active_pack), leads))

    # Roll up unique discovered sources across Stage 1 + Stage 2
    discovered_sources: List[Dict[str, Any]] = []
    seen = set()
    for src in list(handoff.get("discovered_sources") or []):
        if src.get("url") and src["url"] not in seen:
            seen.add(src["url"])
            discovered_sources.append(src)
    for dossier in dossiers:
        for src in dossier.get("newly_discovered_sources") or []:
            if src.get("url") and src["url"] not in seen:
                seen.add(src["url"])
                discovered_sources.append(src)

    return {
        "contract_version": "1.0.0",
        "run_id": handoff["run_id"],
        "investigated_at": datetime.now(timezone.utc).isoformat(),
        "no_ranking_or_scoring": True,
        "dossiers": dossiers,
        "discovered_sources": discovered_sources,
    }


# ---------------------------------------------------------------------------
# Deterministic Process Eval Grader
# ---------------------------------------------------------------------------
def _find_forbidden_keys(obj: Any, path: str = "") -> List[str]:
    hits: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{path}.{k}" if path else str(k)
            if str(k).lower() in FORBIDDEN_RANKING_KEYS:
                hits.append(full)
            hits.extend(_find_forbidden_keys(v, full))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            hits.extend(_find_forbidden_keys(item, f"{path}[{idx}]"))
    return hits


def evaluate_dossier_process(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """Grade one InvestigatorDossier on process execution, grounding, abstention, and contract."""
    failures: List[str] = []

    # 1. Required top-level keys match discovery_investigator_contract.json
    required_top = {
        "lead_id",
        "identity_and_contact",
        "source_and_media_queue",
        "public_footprint",
        "comment_forensics",
        "live_history_and_credits",
        "process_trace",
    }
    missing_top = sorted(required_top - set(dossier.keys()))
    if missing_top:
        failures.append(f"contract_missing_top_keys:{missing_top}")

    # 2. Step completeness & ordering in process_trace
    trace = dossier.get("process_trace") or []
    steps_seen = [t.get("step") for t in trace if isinstance(t, dict)]
    missing_steps = [s for s in REQUIRED_TRACE_STEPS if s not in steps_seen]
    if missing_steps:
        failures.append(f"missing_trace_steps:{missing_steps}")
    if "1a_identity_generic" in steps_seen and "1b_identity_domain" in steps_seen:
        if steps_seen.index("1a_identity_generic") > steps_seen.index("1b_identity_domain"):
            failures.append("identity_steps_out_of_order")
    if "5_dossier_assembler" in steps_seen and steps_seen[-1] != "5_dossier_assembler":
        failures.append("assembler_must_be_final_step")

    # 3. Zero ranking / scoring keys anywhere
    forbidden_hits = _find_forbidden_keys(dossier)
    if forbidden_hits:
        failures.append(f"forbidden_ranking_keys:{forbidden_hits}")

    # 4. Zero raw PII email leakage
    serialized = json.dumps(dossier)
    if EMAIL_RE.search(serialized):
        failures.append("pii_email_leak_detected")

    # 5. Comment bucket math consistency
    counts = (dossier.get("comment_forensics") or {}).get("comment_intent_counts") or {}
    if counts:
        sample_size = counts.get("sample_size", 0)
        bucket_sum = (
            counts.get("release_requests", 0)
            + counts.get("live_show_requests", 0)
            + counts.get("genuine_praise", 0)
            + counts.get("jokes_or_spam", 0)
        )
        if bucket_sum != sample_size:
            failures.append(f"comment_bucket_sum_mismatch:{bucket_sum}!={sample_size}")
        if sample_size == 0 and "comment_forensics" not in (dossier.get("missing_fields") or []):
            failures.append("unrecorded_missing_field:comment_forensics")

    # 6. Evidence grounding for shows & credits
    live_section = dossier.get("live_history_and_credits") or {}
    for show in (live_section.get("show_history") or []) + (live_section.get("upcoming_shows") or []):
        src = show.get("source_url")
        if not isinstance(src, str) or not src.startswith(("http://", "https://")):
            failures.append(f"ungrounded_show:{show.get('venue')}")
    for credit in live_section.get("collaborator_credits") or []:
        src = credit.get("source_url")
        if not isinstance(src, str) or not src.startswith(("http://", "https://")):
            failures.append(f"ungrounded_credit:{credit.get('name')}")

    # 7. Honest abstention checks
    missing_fields = set(dossier.get("missing_fields") or [])
    ident = dossier.get("identity_and_contact") or {}
    if ident.get("musicbrainz_mbid") is None and "identity_and_contact.musicbrainz_mbid" not in missing_fields:
        failures.append("unrecorded_missing_field:identity_and_contact.musicbrainz_mbid")

    return {
        "passed": len(failures) == 0,
        "lead_id": dossier.get("lead_id"),
        "checks_run": 7,
        "failures": failures,
    }


def evaluate_batch_process(batch_output: Dict[str, Any]) -> Dict[str, Any]:
    """Grade an entire InvestigatorBatchOutput against Stage 2 process & contract invariants."""
    batch_failures: List[str] = []
    if batch_output.get("no_ranking_or_scoring") is not True:
        batch_failures.append("no_ranking_or_scoring_must_be_true")
    if batch_output.get("contract_version") != "1.0.0":
        batch_failures.append("invalid_contract_version")

    dossier_results = [
        evaluate_dossier_process(d) for d in (batch_output.get("dossiers") or [])
    ]
    all_passed = (len(batch_failures) == 0) and all(r["passed"] for r in dossier_results)
    return {
        "passed": all_passed,
        "batch_failures": batch_failures,
        "dossier_results": dossier_results,
    }
