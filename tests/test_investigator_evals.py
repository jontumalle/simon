"""Isolated agent tests and Stage 2 Process Evals for Simon's Scout Investigator (Option A).

Tests:
1. TestIdentityResolverEval    — Phase A sequential (1a Generic -> 1b Music Domain), PII scrub
2. TestFootprintProfilerEval   — Phase B Agent 2 (2a || 2b + deterministic Python stats)
3. TestSignalForensicsEval     — Phase B Agent 3 (1-pass merged classifier + abstention)
4. TestTrackRecordMapperEval   — Phase B Agent 4 (4a || 4b, grounded shows/credits, venue cap)
5. TestInvestigatorPipelineAndProcessEvals — Phase B 3-way concurrency, Phase C assembler,
   sparse-artist abstention, and adversarial process-eval detection
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import threading
import time
import unittest

from simon.investigator import (
    evaluate_batch_process,
    evaluate_dossier_process,
    investigate_handoff,
    investigate_lead,
    run_footprint_profiler,
    run_identity_resolver,
    run_signal_forensics,
    run_track_record_mapper,
)
from simon.investigator_music import (
    MusicDomainPack,
    fetch_youtube_comments_api,
    fetch_youtube_video_and_channel_api,
    parse_iso8601_duration,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_HANDOFF_PATH = REPO_ROOT / "examples" / "discovery_handoff_demo.json"
CONTRACT_PATH = REPO_ROOT / "data" / "discovery_investigator_contract.json"


def build_demo_music_pack() -> MusicDomainPack:
    """Deterministic offline MusicDomainPack fixture matching examples/discovery_handoff_demo.json."""
    mira_seed = "https://www.youtube.com/watch?v=3-K26i1go0s"
    mira_clip2 = "https://www.youtube.com/watch?v=BcQnHzrc24Y"
    mira_linktree = "https://linktr.ee/mirasolmusic"
    mira_bandcamp = "https://mirasol.bandcamp.com"
    devon_seed = "https://www.youtube.com/watch?v=RXwE1G7_U9M"

    return MusicDomainPack(
        page_fixtures={
            mira_seed: {
                "bio_text": (
                    "Mira Sol (she/her) — solo vocalist & singer-songwriter based in Bushwick, NYC. "
                    "Neo-soul & indie folk. Mgmt: North Star Artists (mgmt@northstar.example). "
                    "Distributed by DistroKid. Produced by Jonah Reyes. Mixed by Priya Nair."
                ),
                "outbound_urls": [
                    mira_linktree,
                    "https://www.instagram.com/mirasolmusic",
                ],
                "media_urls": [mira_seed, mira_clip2],
                "youtube_subscribers": 4200,
                "verified_artist_match": True,
            },
            mira_linktree: {
                "bio_text": "Listen everywhere",
                "outbound_urls": [
                    "https://open.spotify.com/artist/123456",
                    mira_bandcamp,
                    "https://soundcloud.com/mirasol",
                ],
            },
            devon_seed: {
                "bio_text": "Open mic night in Brooklyn.",
                "outbound_urls": [],
                "media_urls": [devon_seed],
                "youtube_subscribers": None,
                "verified_artist_match": False,
            },
        },
        musicbrainz_fixtures={
            "mira sol": {
                "artists": [
                    {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "name": "Mira Sol",
                        "aliases": [{"name": "M. Sol"}],
                    }
                ]
            }
        },
        oembed_fixtures={
            mira_seed: {
                "title": "Mira Sol - Midnight Train (Live Session)",
                "author_name": "Sofar Sounds",
                "duration_seconds": 215,
                "embeddable": True,
                "view_count": 18000,
            },
            mira_clip2: {
                "title": "Mira Sol - Paper Walls (Acoustic)",
                "author_name": "Mira Sol",
                "duration_seconds": 192,
                "embeddable": True,
                "view_count": 6000,
            },
            devon_seed: {
                "title": "Devon K - Open Mic Clip",
                "author_name": "Brooklyn Open Mic",
                "duration_seconds": 140,
                "embeddable": True,
                "view_count": 320,
            },
        },
        bandcamp_fixtures={
            mira_bandcamp: {
                "bandcamp_releases_count": 3,
                "bandcamp_supporters_count": 84,
                "released_tracks_count": 9,
            }
        },
        comment_fixtures={
            mira_seed: [
                {"text": "Please drop this on Spotify immediately!", "author": "@fan1"},
                {"text": "Come to NYC soon, need a live show!", "author": "@fan2"},
                {
                    "text": "Incredible phrasing on the bridge.",
                    "author": "@jonahreyes_prod",
                    "channel_url": "https://www.youtube.com/@jonahreyes_prod",
                    "is_verified": True,
                    "role_hint": "producer",
                },
                {"text": "Check out my channel for free beats lol", "author": "@spambot"},
                {"text": "Chills every time I hear this vocal tone.", "author": "@fan3"},
            ],
            devon_seed: [],
        },
        show_fixtures={
            "mira sol": {
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
                "collaborator_credits": [
                    {
                        "name": "Jonah Reyes",
                        "role": "producer",
                        "source_url": "https://musicbrainz.org/artist/11111111-2222-3333-4444-555555555555",
                    }
                ],
            }
        },
    )


class TestIdentityResolverEval(unittest.TestCase):
    def test_two_step_generic_then_domain_and_no_pii_leak(self) -> None:
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        pack = build_demo_music_pack()
        bundle = run_identity_resolver(handoff["leads"][0], pack=pack)

        ident = bundle["identity_and_contact"]
        self.assertEqual(ident["stage_name"], "Mira Sol")
        self.assertEqual(ident["pronouns"], "she/her")
        self.assertEqual(ident["home_city"], "New York, NY")
        self.assertEqual(ident["home_neighborhood"], "Bushwick")
        self.assertEqual(ident["project_type"], "solo_vocalist")
        self.assertEqual(ident["musicbrainz_mbid"], "11111111-2222-3333-4444-555555555555")
        self.assertIn("M. Sol", ident["aliases"])
        self.assertTrue(ident["has_public_business_contact"])
        self.assertEqual(ident["contact_route_type"], "mgmt_email")
        # Expanded 1 hop into Linktree for Spotify & Bandcamp
        self.assertEqual(ident["platform_urls"]["spotify"], "https://open.spotify.com/artist/123456")
        self.assertEqual(ident["platform_urls"]["bandcamp"], "https://mirasol.bandcamp.com")
        # Raw PII email scrubbed from bio_text
        self.assertNotIn("mgmt@northstar.example", json.dumps(bundle))
        # Ordered 1a -> 1b trace
        steps = [t["step"] for t in bundle["process_trace"]]
        self.assertEqual(steps, ["1a_identity_generic", "1b_identity_domain"])


class TestFootprintProfilerEval(unittest.TestCase):
    def test_parallel_footprint_and_deterministic_python_math(self) -> None:
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        pack = build_demo_music_pack()
        bundle = run_identity_resolver(handoff["leads"][0], pack=pack)

        res = run_footprint_profiler(bundle, pack=pack)
        self.assertEqual(len(res["media_links"]), 2)
        self.assertTrue(all(m["oembed_live_embeddable"] for m in res["media_links"]))
        fp = res["public_footprint"]
        self.assertEqual(fp["footprint_regime"], "early_dsp_inflection")
        self.assertEqual(fp["public_reach"]["youtube_subscribers"], 4200)
        self.assertEqual(fp["public_reach"]["top_video_views"], 18000)
        self.assertEqual(fp["public_reach"]["bandcamp_supporters_count"], 84)
        # 18000 / (18000 + 6000) * 100 = 75.0
        self.assertEqual(fp["top_release_view_share_pct"], 75.0)
        self.assertEqual(
            {t["step"] for t in res["process_trace"]},
            {"2a_footprint_generic", "2b_footprint_domain"},
        )


class TestSignalForensicsEval(unittest.TestCase):
    def test_single_pass_bucket_math_and_notable_commenter(self) -> None:
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        pack = build_demo_music_pack()
        bundle = run_identity_resolver(handoff["leads"][0], pack=pack)

        res = run_signal_forensics(bundle, pack=pack)
        counts = res["comment_forensics"]["comment_intent_counts"]
        self.assertEqual(counts["sample_size"], 5)
        self.assertEqual(counts["release_requests"], 1)
        self.assertEqual(counts["live_show_requests"], 1)
        self.assertEqual(counts["genuine_praise"], 2)
        self.assertEqual(counts["jokes_or_spam"], 1)
        self.assertEqual(
            counts["release_requests"]
            + counts["live_show_requests"]
            + counts["genuine_praise"]
            + counts["jokes_or_spam"],
            counts["sample_size"],
        )
        notable = res["comment_forensics"]["notable_commenters"]
        self.assertEqual(len(notable), 1)
        self.assertEqual(notable[0]["handle"], "@jonahreyes_prod")

    def test_honest_abstention_when_comments_empty(self) -> None:
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        pack = build_demo_music_pack()
        bundle = run_identity_resolver(handoff["leads"][1], pack=pack)

        res = run_signal_forensics(bundle, pack=pack)
        self.assertEqual(res["comment_forensics"]["comment_intent_counts"]["sample_size"], 0)
        self.assertIn("comment_forensics", res["missing_fields"])


class TestTrackRecordMapperEval(unittest.TestCase):
    def test_shows_venue_cap_team_mentions_and_deduped_credits(self) -> None:
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        pack = build_demo_music_pack()
        bundle = run_identity_resolver(handoff["leads"][0], pack=pack)

        res = run_track_record_mapper(bundle, pack=pack)
        live = res["live_history_and_credits"]
        self.assertEqual(len(live["show_history"]), 2)
        self.assertEqual(len(live["upcoming_shows"]), 1)
        # Baby's All Right (280) > Rockwood Stage 1 (75)
        self.assertEqual(live["highest_venue_cap_observed"], 280)
        self.assertEqual(live["public_team_mentions"]["distributor"], "DistroKid")
        self.assertIsNotNone(live["public_team_mentions"]["management"])
        self.assertIsNone(live["public_team_mentions"]["booking_agent"])
        # Jonah Reyes deduped across bio (4a) and MusicBrainz fixture (4b)
        names = [c["name"] for c in live["collaborator_credits"]]
        self.assertEqual(names.count("Jonah Reyes"), 1)
        self.assertIn("Priya Nair", names)


class TestInvestigatorPipelineAndProcessEvals(unittest.TestCase):
    def test_contract_schema_file_exists_and_loads(self) -> None:
        schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertIn("DiscoveryHandoff", schema["$defs"])
        self.assertIn("InvestigatorDossier", schema["$defs"])
        self.assertIn("InvestigatorBatchOutput", schema["$defs"])

    def test_end_to_end_handoff_passes_all_process_evals(self) -> None:
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        pack = build_demo_music_pack()
        batch = investigate_handoff(handoff, pack=pack)

        self.assertTrue(batch["no_ranking_or_scoring"])
        self.assertEqual(len(batch["dossiers"]), 2)

        eval_report = evaluate_batch_process(batch)
        self.assertTrue(eval_report["passed"], msg=json.dumps(eval_report, indent=2))

        # Verify sparse underground artist stays pre_dsp_underground with honest missing_fields
        devon_dossier = batch["dossiers"][1]
        self.assertEqual(devon_dossier["public_footprint"]["footprint_regime"], "pre_dsp_underground")
        self.assertIsNone(devon_dossier["public_footprint"]["top_release_view_share_pct"])
        self.assertIn("comment_forensics", devon_dossier["missing_fields"])
        self.assertIn("identity_and_contact.musicbrainz_mbid", devon_dossier["missing_fields"])

    def test_phase_b_runs_three_agents_concurrently(self) -> None:
        """Prove Phase B fans out footprint, forensics, and track-record concurrently."""
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        base = build_demo_music_pack()
        active_lock = threading.Lock()
        active_count = 0
        peak_concurrency = 0

        class SlowParallelPack(MusicDomainPack):
            def _track(self, fn, *args):
                nonlocal active_count, peak_concurrency
                with active_lock:
                    active_count += 1
                    peak_concurrency = max(peak_concurrency, active_count)
                try:
                    time.sleep(0.05)
                    return fn(*args)
                finally:
                    with active_lock:
                        active_count -= 1

            def profile_footprint_generic(self, identity_bundle):
                return self._track(super().profile_footprint_generic, identity_bundle)

            def run_signal_forensics(self, identity_bundle):
                return self._track(super().run_signal_forensics, identity_bundle)

            def map_track_record_generic(self, identity_bundle):
                return self._track(super().map_track_record_generic, identity_bundle)

        slow_pack = SlowParallelPack(
            page_fixtures=base.page_fixtures,
            musicbrainz_fixtures=base.musicbrainz_fixtures,
            oembed_fixtures=base.oembed_fixtures,
            bandcamp_fixtures=base.bandcamp_fixtures,
            comment_fixtures=base.comment_fixtures,
            show_fixtures=base.show_fixtures,
        )
        dossier = investigate_lead(handoff["leads"][0], pack=slow_pack)
        self.assertTrue(evaluate_dossier_process(dossier)["passed"])
        self.assertGreaterEqual(peak_concurrency, 3)

    def test_process_eval_catches_ranking_pii_and_trace_violations(self) -> None:
        handoff = json.loads(DEMO_HANDOFF_PATH.read_text(encoding="utf-8"))
        pack = build_demo_music_pack()
        clean = investigate_lead(handoff["leads"][0], pack=pack)

        # 1. Catch forbidden ranking/score key
        bad_rank = copy.deepcopy(clean)
        bad_rank["fit_score"] = 9.4
        res = evaluate_dossier_process(bad_rank)
        self.assertFalse(res["passed"])
        self.assertTrue(any("forbidden_ranking_keys" in f for f in res["failures"]))

        # 2. Catch PII email leak
        bad_pii = copy.deepcopy(clean)
        bad_pii["source_and_media_queue"]["bio_text"] = "Reach me at secret@artist.com"
        res = evaluate_dossier_process(bad_pii)
        self.assertFalse(res["passed"])
        self.assertIn("pii_email_leak_detected", res["failures"])

        # 3. Catch mismatched comment bucket math
        bad_math = copy.deepcopy(clean)
        bad_math["comment_forensics"]["comment_intent_counts"]["sample_size"] = 99
        res = evaluate_dossier_process(bad_math)
        self.assertFalse(res["passed"])
        self.assertTrue(any("comment_bucket_sum_mismatch" in f for f in res["failures"]))

        # 4. Catch missing process_trace step
        bad_trace = copy.deepcopy(clean)
        bad_trace["process_trace"] = [
            t for t in bad_trace["process_trace"] if t["step"] != "3_signal_forensics"
        ]
        res = evaluate_dossier_process(bad_trace)
        self.assertFalse(res["passed"])
        self.assertTrue(any("missing_trace_steps" in f for f in res["failures"]))

        # 5. Catch ungrounded show without source_url
        bad_show = copy.deepcopy(clean)
        bad_show["live_history_and_credits"]["show_history"][0]["source_url"] = None
        res = evaluate_dossier_process(bad_show)
        self.assertFalse(res["passed"])
        self.assertTrue(any("ungrounded_show" in f for f in res["failures"]))


    def test_youtube_data_api_v3_helpers(self) -> None:
        self.assertEqual(parse_iso8601_duration("PT6M10S"), 370)
        self.assertEqual(parse_iso8601_duration("PT1H2M3S"), 3723)
        self.assertIsNone(parse_iso8601_duration("invalid"))

        def fake_json(url: str):
            if "/youtube/v3/videos" in url:
                return {
                    "items": [
                        {
                            "snippet": {
                                "title": "YEBBA - My Mind | Sofar NYC",
                                "channelTitle": "Sofar Sounds",
                                "channelId": "UC_SOFAR",
                                "description": "Live session in NYC.",
                            },
                            "contentDetails": {"duration": "PT6M10S"},
                            "statistics": {"viewCount": "33220000"},
                        }
                    ]
                }
            if "/youtube/v3/channels" in url:
                return {"items": [{"statistics": {"subscriberCount": "1400000"}}]}
            if "/youtube/v3/commentThreads" in url:
                return {
                    "items": [
                        {
                            "snippet": {
                                "topLevelComment": {
                                    "snippet": {
                                        "textDisplay": "Please drop this on Spotify!",
                                        "authorDisplayName": "@fan1",
                                        "authorChannelUrl": "https://www.youtube.com/@fan1",
                                    }
                                }
                            }
                        }
                    ]
                }
            return None

        meta = fetch_youtube_video_and_channel_api("RXwE1G7_U9M", "fake-key", json_fetcher=fake_json)
        self.assertEqual(meta["duration_seconds"], 370)
        self.assertEqual(meta["view_count"], 33220000)
        self.assertEqual(meta["youtube_subscribers"], 1400000)

        comments = fetch_youtube_comments_api("RXwE1G7_U9M", "fake-key", json_fetcher=fake_json)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["text"], "Please drop this on Spotify!")


if __name__ == "__main__":
    unittest.main()
