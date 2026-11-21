import json
import unittest

from simon.models import ClipEvidence, ScoutRun, TimestampedObservation
from simon.scout import run_demo_scout, run_live_scout
from simon.store import SimonStore
from simon.web import dispatch_http_request
from simon.youtube import (
    YouTubeConnector,
    build_play_first_url,
    canonical_watch_url,
    extract_video_id,
    infer_performer_and_attribution,
    timestamp_to_seconds,
)


class FakeYouTubeConnector(YouTubeConnector):
    def verify_oembed(self, url: str):
        vid = extract_video_id(url)
        catalog = {
            "3-K26i1go0s": {
                "video_id": "3-K26i1go0s",
                "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                "title": "Olivia Dean - Wish I Didn't Miss You (Angie Stone) | Mahogany Session",
                "channel": "Mahogany",
            },
            "BcQnHzrc24Y": {
                "video_id": "BcQnHzrc24Y",
                "url": "https://www.youtube.com/watch?v=BcQnHzrc24Y",
                "title": "Olivia Dean - Love Me Not in the Live Lounge",
                "channel": "BBCRadio1VEVO",
            },
            "RXwE1G7_U9M": {
                "video_id": "RXwE1G7_U9M",
                "url": "https://www.youtube.com/watch?v=RXwE1G7_U9M",
                "title": "YEBBA - My Mind | Sofar NYC",
                "channel": "Sofar Sounds",
            },
            "XIIYcEz1u28": {
                "video_id": "XIIYcEz1u28",
                "url": "https://www.youtube.com/watch?v=XIIYcEz1u28",
                "title": "Acantha Lang at Sofar Sounds NYC",
                "channel": "Hiddentravel",
            },
        }
        return catalog.get(vid)

    def search_public_videos(self, query: str, max_results: int = 6):
        if "Olivia Dean" in query:
            return [
                {
                    "video_id": "BcQnHzrc24Y",
                    "url": "https://www.youtube.com/watch?v=BcQnHzrc24Y",
                    "title": "Olivia Dean - Love Me Not in the Live Lounge",
                    "channel": "BBCRadio1VEVO",
                    "duration": "3:18",
                    "query_used": query,
                }
            ]
        if "YEBBA" in query:
            return []
        return [
            {
                "video_id": "3-K26i1go0s",
                "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                "title": "Olivia Dean - Wish I Didn't Miss You (Angie Stone) | Mahogany Session",
                "channel": "Mahogany",
                "duration": "3:50",
                "query_used": query,
            },
            {
                "video_id": "RXwE1G7_U9M",
                "url": "https://www.youtube.com/watch?v=RXwE1G7_U9M",
                "title": "YEBBA - My Mind | Sofar NYC",
                "channel": "Sofar Sounds",
                "duration": "6:10",
                "query_used": query,
            },
            {
                "video_id": "XIIYcEz1u28",
                "url": "https://www.youtube.com/watch?v=XIIYcEz1u28",
                "title": "Acantha Lang at Sofar Sounds NYC",
                "channel": "Hiddentravel",
                "duration": "2:38",
                "query_used": query,
            },
        ]


class FakeGemini:
    discovery_agent = "antigravity-preview-09-2026"
    synthesis_agent = "antigravity-preview-09-2026"
    audio_model = "gemini-4-hydrogen"

    def discover_youtube_leads(self, taste_brief, target_artist=None):
        return {
            "interaction_id": "live-disc-001",
            "duration_ms": 420,
            "steps": [{"index": 1, "type": "model_output", "preview": "Searched sessions"}],
            "data": {
                "search_queries": ["Mahogany Session soul cover live"],
                "candidate_videos": [],
                "discovery_summary": "Targeted stripped-back live sessions.",
            },
        }

    def evaluate_youtube_clip(self, taste_brief, stage_name, video_url, title="", channel=""):
        return {
            "interaction_id": f"live-eval-{extract_video_id(video_url)}",
            "duration_ms": 310,
            "evaluated_model": "gemini-4-hydrogen",
            "data": {
                "recording_context": "live",
                "recording_context_notes": "Single-room acoustic live capture.",
                "observations": [
                    {
                        "timestamp": "1:12",
                        "dimension": "phrasing",
                        "musical_choice": f"{stage_name} delays vowel resolution behind the acoustic groove.",
                    },
                    {
                        "timestamp": "2:05",
                        "dimension": "dynamics",
                        "musical_choice": "Drops to soft head voice before chest-voice release.",
                    },
                ],
            },
        }

    def synthesize_shortlist(self, taste_brief, leads, clip_evidence):
        return {
            "interaction_id": "live-synth-001",
            "duration_ms": 510,
            "steps": [{"index": 1, "type": "model_output", "preview": "Synthesized top 3"}],
            "data": {
                "synthesis_summary": "Compared live phrasing across 3 discovered performers.",
                "assessments": [
                    {
                        "lead_id": lead["lead_id"],
                        "shortlisted": True,
                        "fit_rationale": f"Strong phrasing fit for {lead['stage_name']}.",
                        "open_questions": [],
                    }
                    for lead in leads
                ],
                "shortlist": [
                    {
                        "rank": idx,
                        "lead_id": lead["lead_id"],
                        "play_first_clip_id": f"clip_{idx:02d}",
                        "why_it_fits": f"{lead['stage_name']} reshapes the melody at 1:12.",
                        "what_to_hear_next": "Check original-song phrasing next.",
                        "listen_next_url": None,
                    }
                    for idx, lead in enumerate(leads[:3], start=1)
                ],
            },
        }


class MvpScoutTests(unittest.TestCase):
    def test_youtube_url_and_timestamp_helpers(self):
        self.assertEqual(extract_video_id("https://youtu.be/3-K26i1go0s?t=72"), "3-K26i1go0s")
        self.assertEqual(
            canonical_watch_url("https://youtu.be/3-K26i1go0s"),
            "https://www.youtube.com/watch?v=3-K26i1go0s",
        )
        self.assertEqual(timestamp_to_seconds("1:12"), 72)
        self.assertEqual(
            build_play_first_url("https://www.youtube.com/watch?v=3-K26i1go0s", "1:12"),
            "https://www.youtube.com/watch?v=3-K26i1go0s&t=72s",
        )

    def test_performer_grouping_and_uncertain_attribution_flags(self):
        artist, status, _ = infer_performer_and_attribution(
            "Olivia Dean - Wish I Didn't Miss You (Angie Stone) | Mahogany Session",
            "Mahogany",
        )
        self.assertEqual(artist, "Olivia Dean")
        self.assertEqual(status, "verified")

        artist2, status2, _ = infer_performer_and_attribution(
            "Acantha Lang at Sofar Sounds NYC",
            "Hiddentravel",
        )
        self.assertEqual(artist2, "Acantha Lang")
        self.assertEqual(status2, "uncertain")

        artist3, status3, _ = infer_performer_and_attribution(
            "Amber Run - I Found ft. London Contemporary Voices | Mahogany Session",
            "Mahogany",
        )
        self.assertEqual(artist3, "Amber Run")
        self.assertEqual(status3, "uncertain")

    def test_clip_evidence_preserves_original_link_and_bounds_observations(self):
        url = "https://www.youtube.com/watch?v=Bb07cO7lX_0"
        obs = TimestampedObservation.create("clip_01", url, "0:42", "phrasing", "Rubato 6/8 phrasing")
        clip = ClipEvidence(
            clip_id="clip_01",
            lead_id="lead_01",
            stage_name="Allen Stone",
            source_url=url,
            video_id="Bb07cO7lX_0",
            title="Allen Stone - Is This Love",
            channel="Mahogany",
            recording_context="live",
            recording_context_notes="Live room",
            observations=[obs],
        )
        self.assertEqual(clip.observations[0].source_url, url)
        self.assertEqual(clip.observations[0].play_url, "https://www.youtube.com/watch?v=Bb07cO7lX_0&t=42s")

    def test_demo_scout_persists_records_and_enforces_mvp_requirements(self):
        store = SimonStore(":memory:")
        run: ScoutRun = run_demo_scout(
            brief_prompt="Find singers who reinterpret familiar songs through phrasing or arrangement.",
            store=store,
        )
        self.assertLessEqual(len(run.shortlist), 3)
        self.assertEqual(len(run.shortlist), 3)
        # Requirement 5: single-clip flag on YEBBA (lead_03), multi-clip false on lead_01 & lead_02
        by_lead = {item.lead_id: item for item in run.shortlist}
        self.assertFalse(by_lead["lead_01"].single_clip_flag)
        self.assertFalse(by_lead["lead_02"].single_clip_flag)
        self.assertTrue(by_lead["lead_03"].single_clip_flag)
        self.assertIn("&t=72s", by_lead["lead_01"].play_first_url)

        # Requirement 4: every stored observation retains original link
        saved = store.get_run(run.run_id)
        self.assertIsNotNone(saved)
        stored_obs = store.get_observations_for_run(run.run_id)
        self.assertGreaterEqual(len(stored_obs), 6)
        for obs_row in stored_obs:
            self.assertTrue(obs_row["source_url"].startswith("https://www.youtube.com/watch?v="))
            self.assertTrue(obs_row["play_url"].startswith(obs_row["source_url"]))

    def test_live_scout_pipeline_and_second_take_loop_with_fakes(self):
        store = SimonStore(":memory:")
        run = run_live_scout(
            brief_prompt="Stripped-back soul with distinctive phrasing",
            store=store,
            gemini=FakeGemini(),
            youtube=FakeYouTubeConnector(),
            max_leads=3,
            max_second_takes=2,
        )
        self.assertEqual(run.mode, "live")
        self.assertEqual(len(run.shortlist), 3)
        stages = [step.stage for step in run.trace]
        self.assertEqual(
            stages,
            ["discovery", "evaluation", "second_take_discovery", "synthesis"],
        )
        # Olivia Dean got a 2nd take via second_take_discovery -> single_clip_flag False
        olivia = next(item for item in run.shortlist if item.stage_name == "Olivia Dean")
        self.assertFalse(olivia.single_clip_flag)
        # YEBBA had no 2nd take -> single_clip_flag True
        yebba = next(item for item in run.shortlist if item.stage_name == "YEBBA")
        self.assertTrue(yebba.single_clip_flag)
        # Acantha Lang came from third-party channel Hiddentravel -> uncertain_attribution_flag True
        acantha = next(item for item in run.shortlist if item.stage_name == "Acantha Lang")
        self.assertTrue(acantha.uncertain_attribution_flag)

    def test_web_api_endpoints_end_to_end(self):
        store = SimonStore(":memory:")
        code, ctype, html_bytes = dispatch_http_request(store, "GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"Taste-Brief Vocal Scout MVP", html_bytes)

        code, _, status_bytes = dispatch_http_request(store, "GET", "/api/status")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(status_bytes)["ok"])

        code, _, run_bytes = dispatch_http_request(
            store,
            "POST",
            "/api/scout",
            json.dumps({"brief": "Acoustic soul phrasing", "live": False}).encode("utf-8"),
        )
        self.assertEqual(code, 200)
        run_payload = json.loads(run_bytes)
        self.assertEqual(len(run_payload["shortlist"]), 3)
        self.assertEqual(run_payload["brief"]["prompt"], "Acoustic soul phrasing")

        code, _, runs_bytes = dispatch_http_request(store, "GET", "/api/runs")
        self.assertEqual(code, 200)
        runs = json.loads(runs_bytes)["runs"]
        self.assertEqual(len(runs), 1)


if __name__ == "__main__":
    unittest.main()
