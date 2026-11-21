from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlparse

from simon.deploy import compile_agent_package

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "_shared"
    / "skills"
    / "youtube"
    / "scripts"
    / "youtube_api.py"
)


def _load_youtube_module():
    spec = importlib.util.spec_from_file_location("simon_shared_youtube_api", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


yt_mod = _load_youtube_module()


class TestSharedYouTubeSkill(unittest.TestCase):
    def test_extract_video_id_formats(self) -> None:
        self.assertEqual(yt_mod.extract_video_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(
            yt_mod.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(yt_mod.extract_video_id("https://youtu.be/dQw4w9WgXcQ?si=abc"), "dQw4w9WgXcQ")
        self.assertEqual(yt_mod.extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(yt_mod.extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        with self.assertRaises(ValueError):
            yt_mod.extract_video_id("https://example.com/not-youtube")

    def test_extract_channel_ref_formats(self) -> None:
        self.assertEqual(
            yt_mod.extract_channel_ref("UCuAXFkgsw1L7xaCfnd5JJOw"),
            ("id", "UCuAXFkgsw1L7xaCfnd5JJOw"),
        )
        self.assertEqual(yt_mod.extract_channel_ref("@SofarSounds"), ("forHandle", "@SofarSounds"))
        self.assertEqual(
            yt_mod.extract_channel_ref("https://www.youtube.com/@SofarSounds/videos"),
            ("forHandle", "@SofarSounds"),
        )
        self.assertEqual(
            yt_mod.extract_channel_ref("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"),
            ("id", "UCuAXFkgsw1L7xaCfnd5JJOw"),
        )

    def test_parse_iso8601_duration(self) -> None:
        self.assertEqual(yt_mod.parse_iso8601_duration("PT4M12S"), 252)
        self.assertEqual(yt_mod.parse_iso8601_duration("PT1H2M3S"), 3723)
        self.assertEqual(yt_mod.parse_iso8601_duration("PT45S"), 45)
        self.assertIsNone(yt_mod.parse_iso8601_duration(None))

    def test_header_auth_never_puts_key_in_query_string(self) -> None:
        seen = []

        def fake_get(url, headers, timeout):
            seen.append((url, headers))
            return 200, {
                "items": [
                    {
                        "id": "dQw4w9WgXcQ",
                        "snippet": {
                            "title": "Live Session",
                            "channelId": "UCuAXFkgsw1L7xaCfnd5JJOw",
                            "channelTitle": "Sofar Sounds",
                            "publishedAt": "2026-10-01T00:00:00Z",
                            "description": "Recorded live in NYC",
                            "tags": ["live", "acoustic"],
                        },
                        "contentDetails": {"duration": "PT3M30S"},
                        "statistics": {"viewCount": "1200", "likeCount": "95", "commentCount": "12"},
                    }
                ]
            }

        client = yt_mod.YouTubeAPI(api_key="test-secret-key", request_fn=fake_get)
        vids = client.videos(["https://youtu.be/dQw4w9WgXcQ"])
        self.assertEqual(len(vids), 1)
        self.assertEqual(vids[0]["duration_seconds"], 210)
        self.assertEqual(vids[0]["view_count"], 1200)

        req_url, req_headers = seen[0]
        self.assertEqual(req_headers.get("X-Goog-Api-Key"), "test-secret-key")
        self.assertNotIn("key", parse_qs(urlparse(req_url).query))

    def test_channel_videos_uses_uploads_playlist_and_enriches(self) -> None:
        endpoints = []

        def fake_get(url, headers, timeout):
            path = urlparse(url).path.rsplit("/", 1)[-1]
            endpoints.append(path)
            if path == "channels":
                return 200, {
                    "items": [
                        {
                            "id": "UCuAXFkgsw1L7xaCfnd5JJOw",
                            "snippet": {
                                "title": "Sofar Sounds",
                                "customUrl": "@SofarSounds",
                                "description": "Live sessions",
                                "country": "US",
                            },
                            "statistics": {"subscriberCount": "100000", "viewCount": "5000000", "videoCount": "500"},
                            "contentDetails": {"relatedPlaylists": {"uploads": "UUuAXFkgsw1L7xaCfnd5JJOw"}},
                        }
                    ]
                }
            if path == "playlistItems":
                return 200, {
                    "items": [
                        {
                            "snippet": {"title": "Song A", "channelId": "UCuAXFkgsw1L7xaCfnd5JJOw"},
                            "contentDetails": {"videoId": "abcDEF12345", "videoPublishedAt": "2026-11-01T00:00:00Z"},
                        }
                    ]
                }
            if path == "videos":
                return 200, {
                    "items": [
                        {
                            "id": "abcDEF12345",
                            "snippet": {"title": "Song A", "channelId": "UCuAXFkgsw1L7xaCfnd5JJOw"},
                            "contentDetails": {"duration": "PT4M00S"},
                            "statistics": {"viewCount": "4321", "likeCount": "300", "commentCount": "25"},
                        }
                    ]
                }
            raise AssertionError(f"Unexpected endpoint {path}")

        client = yt_mod.YouTubeAPI(api_key="k", request_fn=fake_get)
        res = client.channel_videos("@SofarSounds", max_results=5)
        self.assertEqual(endpoints, ["channels", "playlistItems", "videos"])
        self.assertEqual(res["channel"]["subscriber_count"], 100000)
        self.assertEqual(res["videos"][0]["view_count"], 4321)
        self.assertEqual(res["videos"][0]["duration_seconds"], 240)

    def test_comments_handles_comments_disabled_gracefully(self) -> None:
        def fake_get(url, headers, timeout):
            return 403, {
                "error": {
                    "message": "The video identified by the videoId parameter has disabled comments.",
                    "errors": [{"reason": "commentsDisabled"}],
                }
            }

        client = yt_mod.YouTubeAPI(api_key="k", request_fn=fake_get)
        res = client.comments("dQw4w9WgXcQ")
        self.assertTrue(res["comments_disabled"])
        self.assertEqual(res["comments"], [])

    def test_stage_agents_bundle_shared_youtube_skill_and_credential(self) -> None:
        agents_root = Path(__file__).resolve().parents[1] / "agents"
        for name in (
            "discovery-scout",
            "identity-resolver",
            "footprint-profiler",
            "signal-forensics",
            "track-record-mapper",
        ):
            compiled = compile_agent_package(agents_root / name, prefix="staging-")
            env = compiled["payload"]["base_environment"]["env"]
            self.assertEqual(env.get("YOUTUBE_API_KEY"), {"credential": "youtube-api-key"}, name)
            targets = {s["target"] for s in compiled["payload"]["base_environment"]["sources"]}
            self.assertIn(".agents/skills/youtube/SKILL.md", targets, name)
            self.assertIn(".agents/skills/youtube/scripts/youtube_api.py", targets, name)


if __name__ == "__main__":
    unittest.main()
