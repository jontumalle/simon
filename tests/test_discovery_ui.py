from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from simon.db_tools import list_agent_documents, save_agent_document
from simon.discovery_ui import (
    dispatch_discovery_batch,
    load_source_registry,
    refresh_discovery_batch,
)
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

    def test_two_section_nav_across_all_five_pages(self) -> None:
        store = self.store
        expected_pages = [
            ("/discovery", b"1. Discovery Dashboard"),
            ("/field-news", b"2. Field News"),
            ("/reports", b"3. Scouting Reports"),
            ("/investigate", b"4. Investigator Desk"),
            ("/", b"5. Vocal Studio"),
        ]
        for route, heading in expected_pages:
            code, ctype, html = dispatch_http_request(store, "GET", route)
            self.assertEqual(code, 200, f"Route {route} failed")
            self.assertIn("text/html", ctype)
            self.assertIn(heading, html)
            # Both top-level section groups present
            self.assertIn(b"nav-sections", html)
            self.assertIn(b">Discovery<", html)
            self.assertIn(b">Investigation<", html)
            # All 5 page links present
            for href in (
                b'href="/discovery"',
                b'href="/field-news"',
                b'href="/reports"',
                b'href="/investigate"',
                b'href="/"',
            ):
                self.assertIn(href, html, f"Missing {href!r} on {route}")

        # Scouting Reports has jump button to /investigate
        _, _, reports_html = dispatch_http_request(store, "GET", "/reports")
        self.assertIn(b"/investigate?subject=", reports_html)

        # Investigator Desk never leaks raw interaction_id
        _, _, inv_html = dispatch_http_request(store, "GET", "/investigate")
        self.assertNotIn(b"interaction_id", inv_html)
        self.assertIn(b"/api/field-news?stage=investigator", inv_html)
        self.assertIn(b"/api/dossiers", inv_html)
        self.assertIn(b"/api/leads", inv_html)

    def test_api_dossiers_leads_and_investigator_field_news(self) -> None:
        store = self.store
        # Save a verified lead directly and a handoff containing the same + a second lead
        save_agent_document(
            store,
            "leads",
            {
                "lead_id": "lead_maya_01",
                "stage_name": "Maya Vance",
                "attribution_status": "verified",
                "context_snippet": "Live soul vocal set at Baby's All Right.",
                "seed_sources": [
                    {
                        "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                        "source_channel": "youtube_live_session",
                    }
                ],
                "interaction_id": "int_should_be_stripped",
            },
        )
        save_agent_document(
            store,
            "discovery_handoffs",
            {
                "contract_version": "1.0.0",
                "run_id": "run_disc_01",
                "search_brief": "NYC solo vocalists",
                "requested_count": 2,
                "leads": [
                    {
                        "lead_id": "lead_maya_01",
                        "stage_name": "Maya Vance",
                        "seed_sources": [
                            {
                                "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                                "source_channel": "youtube_live_session",
                            }
                        ],
                    },
                    {
                        "lead_id": "lead_clara_02",
                        "stage_name": "Clara Reyes",
                        "attribution_status": "verified",
                        "seed_sources": [
                            {
                                "url": "https://babysallright.com/events/clara",
                                "source_channel": "diy_venue_calendar",
                            }
                        ],
                    },
                ],
            },
        )

        # Save an investigator dossier containing raw telemetry keys to confirm sanitization
        save_agent_document(
            store,
            "investigator_dossiers",
            {
                "dossier_id": "dos_maya_01",
                "lead_id": "lead_maya_01",
                "stage_name": "Maya Vance",
                "interaction_id": "int_secret_99",
                "environment_id": "env_secret_99",
                "metadata": {"raw": True},
                "identity_and_contact": {
                    "stage_name": "Maya Vance",
                    "project_type": "solo_vocalist",
                    "home_city": "New York",
                    "home_neighborhood": "Brooklyn",
                    "contact_route_type": "bio_email",
                    "has_public_business_contact": True,
                    "platform_urls": {"youtube": "https://youtube.com/@mayavance"},
                },
                "public_footprint": {
                    "footprint_regime": "early_dsp_inflection",
                    "public_reach": {"youtube_subscribers": 1420, "top_video_views": 18500},
                    "trace_id": "trace_nested_strip",
                },
            },
        )

        # Save one discovery report and one investigator report
        save_agent_document(
            store,
            "agent_reports",
            {
                "report_id": "rep_disc_1",
                "agent_name": "Discovery Scout 01",
                "stage": "discovery",
                "status": "completed",
                "headline": "Stage 1 report",
                "steps": [],
                "findings": [],
            },
        )
        save_agent_document(
            store,
            "agent_reports",
            {
                "report_id": "rep_inv_1",
                "agent_name": "Scout Investigator 01",
                "stage": "investigator",
                "status": "in_motion",
                "headline": "Checking Maya Vance public credits and live history",
                "steps": [
                    {
                        "step_number": 1,
                        "phase": "looking_at",
                        "title": "Checking YouTube channel & MusicBrainz",
                        "looking_at": "Maya Vance public links",
                        "finding": "Found 1,420 YouTube subscribers.",
                        "analysis": "Early DSP inflection regime.",
                    }
                ],
                "findings": [],
            },
        )

        # Verify GET /api/dossiers returns sanitized dossiers and supports lead_id filter
        code_d, _, body_d = dispatch_http_request(store, "GET", "/api/dossiers")
        self.assertEqual(code_d, 200)
        d_payload = json.loads(body_d)
        self.assertEqual(d_payload["count"], 1)
        dos = d_payload["dossiers"][0]
        self.assertEqual(dos["lead_id"], "lead_maya_01")
        self.assertNotIn("interaction_id", dos)
        self.assertNotIn("environment_id", dos)
        self.assertNotIn("metadata", dos)
        self.assertNotIn("trace_id", dos["public_footprint"])
        self.assertEqual(dos["identity_and_contact"]["home_city"], "New York")

        code_df, _, body_df = dispatch_http_request(store, "GET", "/api/dossiers?lead_id=nonexistent")
        self.assertEqual(code_df, 200)
        self.assertEqual(json.loads(body_df)["count"], 0)

        # Verify GET /api/leads deduplicates leads across collections and strips telemetry
        code_l, _, body_l = dispatch_http_request(store, "GET", "/api/leads")
        self.assertEqual(code_l, 200)
        l_payload = json.loads(body_l)
        self.assertEqual(l_payload["count"], 2)
        lead_ids = {item["lead_id"] for item in l_payload["leads"]}
        self.assertEqual(lead_ids, {"lead_maya_01", "lead_clara_02"})
        for item in l_payload["leads"]:
            self.assertNotIn("interaction_id", item)

        # Verify GET /api/field-news?stage=investigator returns only Stage 2 reports
        code_fn, _, body_fn = dispatch_http_request(store, "GET", "/api/field-news?stage=investigator")
        self.assertEqual(code_fn, 200)
        fn_payload = json.loads(body_fn)
        self.assertEqual(fn_payload["count"], 1)
        self.assertEqual(fn_payload["reports"][0]["report_id"], "rep_inv_1")
        self.assertEqual(fn_payload["reports"][0]["stage"], "investigator")

    def test_historical_fleet_runs_backfill_and_soft_archive(self) -> None:
        store = self.store
        legacy_batch = {
            "batch_id": "disc_legacy001",
            "kind": "discovery_batch",
            "mode": "live",
            "agent_id": "staging-simon-discovery-scout",
            "search_brief": "Historical NYC indie soul vocalists",
            "created_at": "2026-11-20T18:00:00Z",
            "updated_at": "2026-11-20T18:05:00Z",
            "workers": [
                {
                    "index": 0,
                    "worker_id": "agent_01",
                    "interaction_id": "int_legacy_hidden",
                    "environment_id": "env_legacy_hidden",
                    "status": "completed",
                    "assigned_sources": [
                        {
                            "source_id": "yt_sofar_sounds",
                            "name": "Sofar Sounds",
                            "url": "https://www.youtube.com/@SofarSounds",
                            "source_channel": "youtube_live_session",
                            "city": "Global",
                        }
                    ],
                    "contract_valid": True,
                    "lead_count": 1,
                    "output_json": {
                        "contract_version": "1.0.0",
                        "run_id": "disc_legacy001_w1",
                        "search_brief": "Historical NYC indie soul vocalists",
                        "requested_count": 1,
                        "leads": [
                            {
                                "lead_id": "lead_hist_01",
                                "stage_name": "Elena Soto",
                                "seed_sources": [
                                    {
                                        "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                                        "source_channel": "youtube_live_session",
                                        "seed_query_or_venue_node": "Sofar Sounds",
                                    }
                                ],
                                "attribution_status": "verified",
                                "context_snippet": "Acoustic vocal set in Brooklyn.",
                            }
                        ],
                        "discovered_sources": [],
                    },
                }
            ],
        }
        save_agent_document(store, "fleet_runs", legacy_batch, doc_id="disc_legacy001")

        # 1. GET /api/reports automatically backfills legacy fleet_runs without telemetry
        code, _, body = dispatch_http_request(store, "GET", "/api/reports")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["count"], 1)
        rep = payload["reports"][0]
        self.assertEqual(rep["report_id"], "rep_disc_legacy001_w1")
        self.assertEqual(rep["findings"][0]["title"], "Elena Soto")
        self.assertEqual(rep["output"]["leads"][0]["stage_name"], "Elena Soto")
        self.assertNotIn("interaction_id", rep)
        self.assertNotIn("environment_id", rep)
        self.assertNotIn("metadata", rep)

        # 2. POST /api/reports/archive (Clear / Start Over) hides reports by default
        code_a, _, body_a = dispatch_http_request(
            store,
            "POST",
            "/api/reports/archive",
            json.dumps({"archived": True}).encode("utf-8"),
        )
        self.assertEqual(code_a, 200)
        self.assertEqual(json.loads(body_a)["updated_count"], 1)

        # Default GET /api/reports is now clean (0 active reports) and does NOT re-create archived report
        code_empty, _, body_empty = dispatch_http_request(store, "GET", "/api/reports")
        self.assertEqual(code_empty, 200)
        self.assertEqual(json.loads(body_empty)["count"], 0)

        # include_archived=1 reveals historical archived reports
        code_inc, _, body_inc = dispatch_http_request(store, "GET", "/api/reports?include_archived=1")
        self.assertEqual(code_inc, 200)
        inc_payload = json.loads(body_inc)
        self.assertEqual(inc_payload["count"], 1)
        self.assertTrue(inc_payload["reports"][0]["archived"])

        # Restore brings it back
        code_res, _, body_res = dispatch_http_request(
            store,
            "POST",
            "/api/reports/archive",
            json.dumps({"report_ids": ["rep_disc_legacy001_w1"], "archived": False}).encode("utf-8"),
        )
        self.assertEqual(code_res, 200)
        self.assertEqual(json.loads(body_res)["updated_count"], 1)
        code_after, _, body_after = dispatch_http_request(store, "GET", "/api/reports")
        self.assertEqual(json.loads(body_after)["count"], 1)

        # UI controls present on /field-news and /reports
        for route in ("/field-news", "/reports"):
            _, _, html = dispatch_http_request(store, "GET", route)
            self.assertIn(b"Clear / Start Over", html)
            self.assertIn(b"Show archived", html)

    def test_discovery_dashboard_removes_third_section_and_expands_selector(self) -> None:
        store = self.store
        code, ctype, html = dispatch_http_request(store, "GET", "/discovery")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"1. Orchestrate Discovery Fleet", html)
        self.assertIn(b"2. Select Discovery Sources", html)
        self.assertLess(
            html.index(b"1. Orchestrate Discovery Fleet"),
            html.index(b"2. Select Discovery Sources"),
        )

        self.assertNotIn(b"3. Per-Agent Contract Outputs", html)
        self.assertNotIn(b"outputsContainer", html)
        self.assertNotIn(b"interaction_id", html)

        for expected in (
            b"wrap-wide",
            b"selector-toolbar",
            b"searchFilter",
            b"sourceSearchInput",
            b"genreFilter",
            b"channelChips",
            b"regionPills",
            b"selectedTray",
            b"selectFilteredBtn",
            b"toggleExpandBtn",
            b"showMoreSourcesBtn",
            b"presetIdolBtn",
            b"fleetScaleBanner",
            b"cascadeBtn",
            b"huntFocusInput",
            b"huntSourcesBtn",
            b"toastContainer",
            b"minmax(340px, 1fr)",
        ):
            self.assertIn(expected, html)

        reg = load_source_registry(store)
        self.assertIn("genres", reg)
        self.assertIn("soul", reg["genres"])
        self.assertIn("indie", reg["genres"])

    def test_nationwide_8_region_pipeline_and_source_hunter_api(self) -> None:
        import re
        import shutil
        import subprocess

        store = self.store
        _, _, raw_html = dispatch_http_request(store, "GET", "/discovery")
        html_str = raw_html.decode("utf-8")

        # Validate inline <script> JS syntax
        scripts = re.findall(r"<script>(.*?)</script>", html_str, flags=re.DOTALL)
        self.assertGreaterEqual(len(scripts), 1)
        node_bin = shutil.which("node")
        if node_bin:
            js_path = Path(self._tmpdir.name) / "discovery_check.js"
            js_path.write_text("\n;\n".join(scripts), encoding="utf-8")
            proc = subprocess.run([node_bin, "--check", str(js_path)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"Discovery JS syntax error:\n{proc.stderr}")

        # Verify 42 seeded sources including all 6 new US regional hubs
        reg = load_source_registry(store)
        self.assertEqual(reg["count"], 42)
        source_ids = {s["source_id"] for s in reg["sources"]}
        nationwide_sources = [
            "nyc_rockwood_music_hall",
            "src_nashville_bluebird",
            "src_atlanta_eddies",
            "src_austin_kutx",
            "yt_audiotree",
            "src_nola_wwoz",
            "src_la_hotelcafe",
            "yt_kexp_live",
        ]
        for sid in nationwide_sources:
            self.assertIn(sid, source_ids)

        # Verify POST /api/sources/hunt + GET /api/sources/schedule + pinned is_new sources
        code_sched, _, body_sched = dispatch_http_request(store, "GET", "/api/sources/schedule")
        self.assertEqual(code_sched, 200)
        self.assertEqual(json.loads(body_sched)["schedule"]["cron"], "0 9 * * *")

        code_hunt, _, body_hunt = dispatch_http_request(
            store,
            "POST",
            "/api/sources/hunt",
            json.dumps({"focus": "Detroit soul", "count": 3, "live": False}).encode("utf-8"),
        )
        self.assertEqual(code_hunt, 200)
        hunt_payload = json.loads(body_hunt)
        self.assertEqual(hunt_payload["added_count"], 3)
        self.assertEqual(len(hunt_payload["added_sources"]), 3)

        code_srcs, _, body_srcs = dispatch_http_request(store, "GET", "/api/sources?limit=100")
        self.assertEqual(code_srcs, 200)
        srcs_payload = json.loads(body_srcs)
        self.assertEqual(srcs_payload["count"], 45)
        self.assertTrue(srcs_payload["sources"][0].get("is_new"))

        # Verify 8-agent x 2-lead = 16 unique US finalists across all 8 US cities
        code_disp, _, body_disp = dispatch_http_request(
            store,
            "POST",
            "/api/discovery/dispatch",
            json.dumps(
                {
                    "source_ids": nationwide_sources,
                    "brief": "American Idol Nationwide Search across 8 US music regions",
                    "agent_count": 8,
                    "leads_per_agent": 2,
                    "live": False,
                    "reset_previous": True,
                }
            ).encode("utf-8"),
        )
        self.assertEqual(code_disp, 200)
        disp = json.loads(body_disp)
        self.assertEqual(disp["agent_count"], 8)
        all_stage_names = [
            lead["stage_name"]
            for w in disp["workers"]
            for lead in w["output_json"]["leads"]
        ]
        self.assertEqual(len(all_stage_names), 16)
        self.assertEqual(len(set(all_stage_names)), 16)
        for w in disp["workers"]:
            self.assertTrue(w["contract_valid"], w["contract_errors"])

        code_inv, _, body_inv = dispatch_http_request(store, "POST", "/api/investigate/run", b"{}")
        self.assertEqual(code_inv, 200)
        inv = json.loads(body_inv)
        self.assertEqual(inv["count"], 16)
        home_cities = {d["identity_and_contact"]["home_city"] for d in inv["dossiers"]}
        self.assertEqual(
            home_cities,
            {
                "New York, NY",
                "Nashville, TN",
                "Atlanta, GA",
                "Austin, TX",
                "Chicago, IL",
                "New Orleans, LA",
                "Los Angeles, CA",
                "Seattle, WA",
            },
        )
        for d in inv["dossiers"]:
            media_url = d["source_and_media_queue"]["media_links"][0]["url"]
            self.assertRegex(media_url, r"^https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}$")


if __name__ == "__main__":
    unittest.main()
