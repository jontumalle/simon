from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from simon.db_tools import list_agent_documents, save_agent_document
from simon.discovery_ui import dispatch_discovery_batch, refresh_discovery_batch
from simon.store import SimonStore
from simon.web import dispatch_http_request


class TestDiscoveryUIAndTraces(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = SimonStore(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_discovery_and_traces_html_routes(self) -> None:
        store = self.store
        code, ctype, html = dispatch_http_request(store, "GET", "/discovery")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"Stage 1 Discovery", html)
        self.assertIn(b"DiscoveryHandoff v1.0.0", html)

        code2, ctype2, html2 = dispatch_http_request(store, "GET", "/traces")
        self.assertEqual(code2, 200)
        self.assertIn("text/html", ctype2)
        self.assertIn(b"Live Agent Traces", html2)

    def test_api_sources_merges_seed_and_db_discovered_sources(self) -> None:
        store = self.store
        save_agent_document(
            store,
            "discovered_sources",
            {
                "url": "https://custom-nyc-openmic.example.com/calendar",
                "source_channel": "open_mic_lineup",
                "title_or_node": "Custom Bushwick Open Mic",
                "why_useful": "Weekly vocal open mic lineup.",
                "discovered_by": "stage_1_discovery",
            },
        )
        code, _, body = dispatch_http_request(store, "GET", "/api/sources")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertGreaterEqual(payload["count"], 37)
        urls = {s["url"] for s in payload["sources"]}
        self.assertIn("https://custom-nyc-openmic.example.com/calendar", urls)
        self.assertIn("youtube_live_session", payload["channels"])
        self.assertIn("New York", payload["cities"])

    def test_simulated_discovery_dispatch_and_batches_api(self) -> None:
        store = self.store
        req_body = json.dumps(
            {
                "source_ids": ["yt_sofar_sounds", "nyc_babys_all_right", "bc_brooklyn_soul_rnb"],
                "brief": "Find NYC emerging solo vocalists",
                "agent_count": 3,
                "leads_per_agent": 2,
                "live": False,
            }
        ).encode("utf-8")
        code, _, body = dispatch_http_request(store, "POST", "/api/discovery/dispatch", req_body)
        self.assertEqual(code, 200)
        batch = json.loads(body)
        self.assertEqual(batch["mode"], "simulated")
        self.assertEqual(len(batch["workers"]), 3)
        for worker in batch["workers"]:
            self.assertEqual(worker["status"], "completed")
            self.assertTrue(worker["contract_valid"])
            self.assertEqual(worker["lead_count"], 2)
            self.assertGreaterEqual(len(worker["steps"]), 3)

        # Verify /api/discovery/batches lists the batch
        code_list, _, body_list = dispatch_http_request(store, "GET", "/api/discovery/batches")
        self.assertEqual(code_list, 200)
        batches = json.loads(body_list)["batches"]
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["batch_id"], batch["batch_id"])
        self.assertEqual(batches[0]["total_leads"], 6)

        # Verify /api/discovery/batches/<id> fetches detail
        code_det, _, body_det = dispatch_http_request(
            store, "GET", f"/api/discovery/batches/{batch['batch_id']}"
        )
        self.assertEqual(code_det, 200)
        detail = json.loads(body_det)
        self.assertEqual(detail["batch_id"], batch["batch_id"])

        # Verify handoffs were persisted in simon-db
        handoffs = list_agent_documents(store, "discovery_handoffs", limit=10)
        self.assertEqual(len(handoffs), 3)

    def test_live_dispatch_and_poll_interaction_trace_refresh(self) -> None:
        store = self.store

        def fake_request(method, url, api_key, body=None, timeout=60):
            if method == "POST":
                return 200, {
                    "id": "int_live_01",
                    "status": "in_progress",
                    "environment_id": "env_01",
                }
            # GET /v1beta/interactions/int_live_01 -> completed with steps + DiscoveryHandoff JSON
            handoff_json = {
                "contract_version": "1.0.0",
                "run_id": "run_live_w1",
                "search_brief": "NYC vocalists",
                "requested_count": 1,
                "leads": [
                    {
                        "lead_id": "lead_01",
                        "stage_name": "Clara Reyes",
                        "seed_sources": [
                            {
                                "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                                "source_channel": "youtube_live_session",
                            }
                        ],
                        "attribution_status": "verified",
                        "context_snippet": "Live room vocal session on Sofar NYC.",
                    }
                ],
                "discovered_sources": [],
            }
            return 200, {
                "id": "int_live_01",
                "status": "completed",
                "environment_id": "env_01",
                "steps": [
                    {
                        "type": "tool_call",
                        "content": [{"type": "code_execution", "name": "code_execution"}],
                    },
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": json.dumps(handoff_json)}],
                    },
                ],
            }

        batch = dispatch_discovery_batch(
            store=store,
            source_ids=["yt_sofar_sounds"],
            brief="NYC vocalists",
            leads_per_agent=1,
            agent_count=1,
            live=True,
            api_key="test-key",
            request_fn=fake_request,
        )
        self.assertEqual(batch["mode"], "live")
        self.assertEqual(batch["workers"][0]["status"], "in_progress")
        self.assertEqual(batch["workers"][0]["interaction_id"], "int_live_01")

        refreshed = refresh_discovery_batch(
            store=store,
            batch_id=batch["batch_id"],
            api_key="test-key",
            request_fn=fake_request,
        )
        self.assertIsNotNone(refreshed)
        w0 = refreshed["workers"][0]
        self.assertEqual(w0["status"], "completed")
        self.assertTrue(w0["contract_valid"])
        self.assertEqual(w0["lead_count"], 1)
        self.assertEqual(len(w0["steps"]), 2)
        self.assertEqual(w0["output_json"]["leads"][0]["stage_name"], "Clara Reyes")


if __name__ == "__main__":
    unittest.main()
