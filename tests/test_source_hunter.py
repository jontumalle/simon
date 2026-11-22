from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from simon.db_tools import VALID_SOURCE_CHANNELS, list_agent_documents
from simon.deploy import compile_agent_package
from simon.source_hunter import (
    CURATED_EXPANSION_POOL,
    hunt_new_sources,
    sync_daily_source_hunter_trigger,
)
from simon.store import SimonStore


class TestSourceHunter(unittest.TestCase):
    def test_compile_agent_and_curated_pool_coverage(self) -> None:
        agent_dir = Path(__file__).resolve().parents[1] / "agents" / "source-hunter"
        compiled = compile_agent_package(agent_dir, prefix="staging-")
        self.assertEqual(compiled["deployed_id"], "staging-simon-source-hunter")
        targets = {s["target"] for s in compiled["payload"]["base_environment"]["sources"]}
        self.assertIn(".agents/skills/source-validation/scripts/verify_sources.py", targets)
        self.assertIn(".agents/skills/simon-db/scripts/simon_db.py", targets)

        self.assertGreaterEqual(len(CURATED_EXPANSION_POOL), 24)
        channels = {s["source_channel"] for s in CURATED_EXPANSION_POOL}
        for req_ch in (
            "open_mic_lineup",
            "youtube_live_session",
            "diy_venue_calendar",
            "bandcamp_local_arrival",
            "event_listing",
            "bgv_or_session_credit_graph",
        ):
            self.assertIn(req_ch, channels)
            self.assertIn(req_ch, VALID_SOURCE_CHANNELS)

    def test_hunt_deduplicates_saves_report_and_syncs_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SimonStore(Path(tmp) / "simon.db")
            first = hunt_new_sources(store, focus="Detroit", count=2, live=False)
            self.assertTrue(first["ok"])
            self.assertEqual(first["added_count"], 2)
            self.assertEqual(first["schedule"]["cron"], "0 9 * * *")
            first_urls = {s["url"] for s in first["added_sources"]}

            second = hunt_new_sources(store, focus="Detroit", count=3, live=False)
            second_urls = {s["url"] for s in second["added_sources"]}
            self.assertTrue(first_urls.isdisjoint(second_urls))

            saved_sources = list_agent_documents(store, "discovered_sources", limit=10)
            self.assertEqual(len(saved_sources), 5)
            reports = list_agent_documents(store, "agent_reports", limit=10)
            self.assertEqual(len(reports), 2)
            self.assertEqual(reports[0]["agent_name"], "Source Hunter")
            self.assertEqual(reports[0]["stage"], "discovery")

        calls = []

        def fake_req(method, url, api_key, body=None, timeout=45):
            calls.append((method, url, body))
            if method == "GET":
                return 200, {"triggers": []}
            return 201, {"name": "triggers/trig_123", **(body or {})}

        trig = sync_daily_source_hunter_trigger(
            api_key="test-key", prefix="staging-", request_fn=fake_req
        )
        self.assertTrue(trig["ok"])
        self.assertEqual(trig["action"], "created")
        self.assertEqual([c[0] for c in calls], ["GET", "POST"])
        self.assertEqual(calls[1][2]["interaction"]["agent"], "staging-simon-source-hunter")


if __name__ == "__main__":
    unittest.main()
