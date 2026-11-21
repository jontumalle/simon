"""Tests for the remodeled Agency Studio UI, static serving, Phase Runner, and Agent Evals."""

from __future__ import annotations

import json
import unittest

from simon.store import SimonStore
from simon.web import dispatch_http_request


class TestAgencyStudioUIAndPhases(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SimonStore(":memory:")

    def test_static_frontend_assets_and_traversal_block(self) -> None:
        code, ctype, html = dispatch_http_request(self.store, "GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"Discovery", html)
        self.assertIn(b'id="tab-discovery"', html)
        self.assertIn(b'id="phaseLeadSelect"', html)
        self.assertIn(b"Talent Review", html)
        self.assertIn(b"Pipeline Runner", html)
        self.assertIn(b"Agent Lab", html)

        code, ctype, css = dispatch_http_request(self.store, "GET", "/static/app.css")
        self.assertEqual(code, 200)
        self.assertIn("text/css", ctype)
        self.assertIn(b"--accent", css)

        code, ctype, js = dispatch_http_request(self.store, "GET", "/static/app.js")
        self.assertEqual(code, 200)
        self.assertIn("javascript", ctype)
        self.assertIn(b"/api/phases/run", js)

        # Directory traversal must be rejected
        code, _, _ = dispatch_http_request(self.store, "GET", "/static/../web.py")
        self.assertEqual(code, 404)

    def test_phases_list_and_step_by_step_execution(self) -> None:
        code, _, body = dispatch_http_request(self.store, "GET", "/api/phases")
        self.assertEqual(code, 200)
        data = json.loads(body)
        phase_ids = [p["id"] for p in data["phases"]]
        self.assertEqual(
            phase_ids,
            ["1_discovery", "2a_identity", "2b_investigators", "2c_dossier", "3_screening", "4_producer"],
        )

        # Run Phase 1 -> 2A -> 2B -> 2C -> 3 -> 4 chaining handoffs
        handoff = {}
        for pid in phase_ids:
            code, _, resp = dispatch_http_request(
                self.store,
                "POST",
                "/api/phases/run",
                json.dumps({"phase_id": pid, "payload": handoff, "live": False}).encode("utf-8"),
            )
            self.assertEqual(code, 200, f"Phase {pid} failed: {resp}")
            rec = json.loads(resp)
            self.assertEqual(rec["phase_id"], pid)
            self.assertTrue(rec["passed"], f"Phase {pid} checks failed: {rec['checks']}")
            self.assertGreaterEqual(len(rec["cards"]), 1)
            if pid == "2b_investigators":
                self.assertEqual(len(rec["cards"]), 3)
            handoff = rec.get("next_handoff") or {}

        # Verify checkpoints persisted
        code, _, body = dispatch_http_request(self.store, "GET", "/api/phases")
        self.assertEqual(code, 200)
        saved_runs = json.loads(body)["phase_runs"]
        self.assertEqual(len(saved_runs), 6)

    def test_agent_evals_auto_checks_and_persistence(self) -> None:
        # Auto-check without saving catches forbidden ranking key on investigator
        code, _, body = dispatch_http_request(
            self.store,
            "POST",
            "/api/evals",
            json.dumps(
                {
                    "agent_id": "signal-forensics",
                    "output": {"comments_sampled": 10, "score": 9.5},
                    "save": False,
                }
            ).encode("utf-8"),
        )
        self.assertEqual(code, 200)
        res = json.loads(body)
        self.assertFalse(res["auto_passed"])

        # Save a passing human eval
        code, _, body = dispatch_http_request(
            self.store,
            "POST",
            "/api/evals",
            json.dumps(
                {
                    "agent_id": "signal-forensics",
                    "verdict": "pass",
                    "note": "Clean intent buckets and zero ranking drift",
                    "output": {"comments_sampled": 10},
                    "save": True,
                }
            ).encode("utf-8"),
        )
        self.assertEqual(code, 201)
        saved = json.loads(body)
        self.assertTrue(saved["auto_passed"])
        self.assertEqual(saved["verdict"], "pass")

        # List saved evals filtered by agent_id
        code, _, body = dispatch_http_request(self.store, "GET", "/api/evals?agent_id=signal-forensics")
        self.assertEqual(code, 200)
        evals = json.loads(body)["evals"]
        self.assertEqual(len(evals), 1)
        self.assertEqual(evals[0]["note"], "Clean intent buckets and zero ranking drift")

    def test_phase_1_discovery_links_source_registry_and_standalone_bridges(self) -> None:
        code, _, resp = dispatch_http_request(
            self.store,
            "POST",
            "/api/phases/run",
            json.dumps(
                {
                    "phase_id": "1_discovery",
                    "payload": {
                        "brief": "NYC live soul vocalists",
                        "source_ids": ["yt_sofar_sounds", "nyc_babys_all_right"],
                        "agent_count": 2,
                        "leads_per_agent": 2,
                    },
                    "live": False,
                }
            ).encode("utf-8"),
        )
        self.assertEqual(code, 200, f"Phase 1 discovery failed: {resp}")
        rec = json.loads(resp)
        self.assertTrue(rec["passed"])
        out = rec["output"]
        self.assertTrue(out.get("batch_id", "").startswith("disc_"))
        self.assertEqual(out.get("selected_source_ids"), ["yt_sofar_sounds", "nyc_babys_all_right"])
        self.assertGreaterEqual(len(out.get("artist_leads", [])), 2)

        # Discovery batch & leads must be visible to the shared Discovery/Leads endpoints
        code, _, batches_body = dispatch_http_request(self.store, "GET", "/api/discovery/batches")
        self.assertEqual(code, 200)
        batch_ids = [b["batch_id"] for b in json.loads(batches_body)["batches"]]
        self.assertIn(out["batch_id"], batch_ids)

        code, _, leads_body = dispatch_http_request(self.store, "GET", "/api/leads")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(json.loads(leads_body)["count"], 2)

        # Standalone pages link back into the unified Studio
        for route, expected in [
            ("/discovery", b"/?tab=discovery"),
            ("/reports", b"/?tab=pipeline&amp;phase=2a_identity"),
            ("/investigate", b"/?tab=pipeline&amp;phase=2a_identity"),
            ("/screen", b"/?tab=pipeline&amp;phase=4_producer"),
            ("/screen", b"/?tab=review&amp;subtab=screened"),
        ]:
            code, _, html = dispatch_http_request(self.store, "GET", route)
            self.assertEqual(code, 200)
            self.assertIn(expected, html)

    def test_agents_endpoint_returns_tailored_default_inputs(self) -> None:
        code, _, body = dispatch_http_request(self.store, "GET", "/api/agents")
        self.assertEqual(code, 200)
        agents = {a["package"]: a for a in json.loads(body)["agents"]}

        expected_keys = {
            "discovery-scout": {"search_brief", "requested_count"},
            "identity-resolver": {"lead_id", "stage_name", "seed_sources"},
            "footprint-profiler": {"lead_id", "identity_and_contact", "source_and_media_queue"},
            "signal-forensics": {"lead_id", "identity_and_contact", "comment_sampling_targets"},
            "track-record-mapper": {"lead_id", "identity_and_contact", "focus"},
            "performance-critic": {"brief", "auditions"},
            "booking-critic": {"brief", "auditions"},
            "showcase-producer": {"lead_id", "stage_name", "screening_verdict", "advocate_case", "skeptic_case", "judge_decision"},
            "screen-advocate": {"lead_id", "dossier"},
            "screen-skeptic": {"lead_id", "dossier"},
            "screening-judge": {"lead_id", "dossier", "advocate_case", "skeptic_case"},
        }
        for pkg, req_keys in expected_keys.items():
            self.assertIn(pkg, agents, f"Missing agent package {pkg} in /api/agents")
            self.assertTrue(agents[pkg].get("input_hint"), f"Missing input_hint for {pkg}")
            default_input = agents[pkg].get("default_input")
            self.assertIsInstance(default_input, dict, f"default_input must be a dict for {pkg}")
            self.assertTrue(
                req_keys.issubset(set(default_input.keys())),
                f"{pkg} default_input missing keys {req_keys - set(default_input.keys())}",
            )

        # Verify frontend uses agent.default_input instead of a single hardcoded payload
        code, _, js = dispatch_http_request(self.store, "GET", "/static/app.js")
        self.assertEqual(code, 200)
        self.assertIn(b"agent.default_input", js)
        self.assertIn(b"agent.input_hint", js)

    def test_phase_2c_persists_dossier_for_investigate_and_screening(self) -> None:
        code, _, resp = dispatch_http_request(
            self.store,
            "POST",
            "/api/phases/run",
            json.dumps({"phase_id": "2c_dossier", "payload": {}, "live": False}).encode("utf-8"),
        )
        self.assertEqual(code, 200, f"Phase 2C failed: {resp}")
        rec = json.loads(resp)
        self.assertTrue(rec["passed"])
        self.assertTrue(rec["output"]["dossier_saved"])
        lead_id = rec["output"]["lead_id"]

        # Dossier must now be visible in /api/dossiers
        code, _, dossiers_body = dispatch_http_request(self.store, "GET", f"/api/dossiers?lead_id={lead_id}")
        self.assertEqual(code, 200)
        dossiers = json.loads(dossiers_body)["dossiers"]
        self.assertGreaterEqual(len(dossiers), 1)

        # And immediately runnable in Stage 3 Screening
        code, _, screen_body = dispatch_http_request(
            self.store,
            "POST",
            "/api/screening/run",
            json.dumps({"lead_id": lead_id, "live": False}).encode("utf-8"),
        )
        self.assertEqual(code, 200, f"Screening run failed: {screen_body}")
        screen_data = json.loads(screen_body)
        self.assertTrue(screen_data["ok"])
        self.assertGreaterEqual(screen_data["count"], 1)

    def test_cross_screen_nav_parity_and_flow_handoffs(self) -> None:
        # 1. Root Studio `/` has all 5 primary stage links matching standalone pages, without duplicating Tools links
        code, _, root_html = dispatch_http_request(self.store, "GET", "/")
        self.assertEqual(code, 200)
        for token in (
            b'data-tab="discovery"',
            b'href="/investigate"',
            b'href="/screen"',
            b'href="/taste-profile"',
            b'data-tab="review"',
            b'id="discResetPrevToggle"',
            b'id="discClearOldRunsBtn"',
            b'href="/investigate?autorun=1"',
        ):
            self.assertIn(token, root_html)
        self.assertNotIn(b'<a href="/?tab=pipeline">Pipeline Stepper</a>', root_html)

        # 2. Standalone pages retain Pipeline Stepper & Agent Lab links inside Tools
        for route in ("/investigate", "/screen", "/taste-profile", "/discovery", "/evals"):
            code, _, html = dispatch_http_request(self.store, "GET", route)
            self.assertEqual(code, 200)
            self.assertIn(b'href="/taste-profile"', html)
            self.assertIn(b'<a href="/?tab=pipeline">Pipeline Stepper</a>', html)

        # 3. app.js wires end-to-end handoffs across Discovery -> Investigate -> Screening -> Talent Review -> Phase 4
        code, _, js = dispatch_http_request(self.store, "GET", "/static/app.js")
        self.assertEqual(code, 200)
        for token in (
            b"/api/demo/reset",
            b"reset_previous",
            b"buildProducerHandoffFromPacket",
            b"refreshScreeningPackets",
            b"renderScreenedPackets(reqLead)",
            b"href=\"/investigate?subject=",
        ):
            self.assertIn(token, js)

    def test_discovery_subflow_nav_and_plain_english_agent_rules(self) -> None:
        # Discovery Sub-Flow strip is accessible on /, /discovery, /field-news, and /reports
        for route in ("/", "/discovery", "/field-news", "/reports"):
            code, _, html = dispatch_http_request(self.store, "GET", route)
            self.assertEqual(code, 200)
            for token in (
                b'class="subflow-nav"',
                b'id="subflowDiscoveryLink"',
                b'id="subflowFieldNewsLink"',
                b'id="subflowReportsLink"',
                b'Next: Investigate',
            ):
                self.assertIn(token, html, f"Missing {token!r} on {route}")

        # Shared field-reporting skill and all curated agent SYSTEM.md files enforce Plain-English output
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[1]
        field_skill = (repo_root / "agents" / "_shared" / "skills" / "field-reporting" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Plain-English", field_skill)
        system_files = sorted((repo_root / "agents").glob("*/SYSTEM.md"))
        self.assertGreaterEqual(len(system_files), 11)
        for sf in system_files:
            self.assertIn("Plain-English Output Standard", sf.read_text(encoding="utf-8"), f"Missing rule in {sf}")

        code, _, home_html = dispatch_http_request(self.store, "GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"subtabScreenedBtn", home_html)
        self.assertNotIn(b"subtabShortlistBtn", home_html)
        self.assertNotIn(b"briefDrawer", home_html)


if __name__ == "__main__":
    unittest.main()
