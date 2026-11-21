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
        self.assertIn(b"1. Discovery Dashboard", html)
        self.assertIn(b"2. Field News", html)
        self.assertIn(b"3. Scouting Reports", html)

        code2, ctype2, html2 = dispatch_http_request(store, "GET", "/field-news")
        self.assertEqual(code2, 200)
        self.assertIn("text/html", ctype2)
        self.assertIn(b"2. Field News", html2)
        self.assertNotIn(b"interaction_id", html2)

        # /traces remains a compatible alias to Field News
        code_alias, _, html_alias = dispatch_http_request(store, "GET", "/traces")
        self.assertEqual(code_alias, 200)
        self.assertIn(b"2. Field News", html_alias)

        code3, ctype3, html3 = dispatch_http_request(store, "GET", "/reports")
        self.assertEqual(code3, 200)
        self.assertIn("text/html", ctype3)
        self.assertIn(b"3. Scouting Reports", html3)
        self.assertNotIn(b"interaction_id", html3)

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

        # Verify human-first Field News & Scouting Reports API stored output without telemetry
        code_fn, _, body_fn = dispatch_http_request(
            store, "GET", f"/api/field-news?batch_id={batch['batch_id']}"
        )
        self.assertEqual(code_fn, 200)
        fn_payload = json.loads(body_fn)
        self.assertEqual(fn_payload["count"], 1)
        rep = fn_payload["reports"][0]
        self.assertEqual(rep["status"], "completed")
        self.assertNotIn("interaction_id", rep)
        self.assertNotIn("environment_id", rep)
        self.assertNotIn("metadata", rep)
        self.assertEqual(rep["findings"][0]["title"], "Clara Reyes")
        self.assertEqual(rep["output"]["leads"][0]["stage_name"], "Clara Reyes")
        for st in rep["steps"]:
            self.assertNotIn("interaction_id", st)
            self.assertNotIn("metadata", st)
            self.assertIn(st["phase"], {"looking_at", "finding", "analysis", "saved"})

        # Verify /api/reports/<report_id> returns the same sanitized report
        code_rep, _, body_rep = dispatch_http_request(
            store, "GET", f"/api/reports/{rep['report_id']}"
        )
        self.assertEqual(code_rep, 200)
        rep_detail = json.loads(body_rep)
        self.assertEqual(rep_detail["report_id"], rep["report_id"])
        self.assertNotIn("interaction_id", rep_detail)

    def test_agent_reports_rejects_interaction_id_and_metadata(self) -> None:
        store = self.store
        with self.assertRaises(ValueError) as ctx:
            save_agent_document(
                store,
                "agent_reports",
                {
                    "report_id": "rep_bad_01",
                    "agent_name": "Discovery Scout 01",
                    "stage": "discovery",
                    "status": "in_motion",
                    "interaction_id": "int_should_fail",
                    "metadata": {"raw": True},
                    "steps": [],
                    "findings": [],
                },
            )
        self.assertIn("interaction_id", str(ctx.exception))
        self.assertIn("metadata", str(ctx.exception))

    def test_discovery_scout_bundles_field_reporting_and_source_discovery_skills(self) -> None:
        from simon.deploy import compile_agent_package

        pkg = compile_agent_package(Path("agents/discovery-scout"))
        sources = pkg["payload"]["base_environment"]["sources"]
        targets = {s.get("target") for s in sources}
        self.assertIn(".agents/skills/field-reporting/SKILL.md", targets)
        self.assertIn(".agents/skills/field-reporting/scripts/field_report.py", targets)
        self.assertIn(".agents/skills/source-discovery/SKILL.md", targets)


if __name__ == "__main__":
    unittest.main()
