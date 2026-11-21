from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from simon.deploy import compile_agent_package, deploy_agents, validate_agent_id
from simon.fleet import dispatch_fleet
from simon.store import SimonStore
from simon.web import dispatch_http_request


class TestDeployAndFleet(unittest.TestCase):
    def test_compile_discovery_scout_inlines_system_md_and_prefix(self) -> None:
        agent_dir = Path(__file__).resolve().parents[1] / "agents" / "discovery-scout"
        compiled = compile_agent_package(
            agent_dir,
            prefix="kevin-",
            model_override="gemini-3.8-flash",
        )
        payload = compiled["payload"]
        self.assertEqual(compiled["deployed_id"], "kevin-simon-discovery-scout")
        self.assertEqual(payload["id"], "kevin-simon-discovery-scout")
        self.assertEqual(payload["agent_config"]["model"], "gemini-3.8-flash")
        self.assertIn("Public YouTube Only", payload["system_instruction"])
        sources = payload["base_environment"]["sources"]
        targets = {s["target"] for s in sources if s.get("type") == "inline"}
        self.assertIn(".agents/AGENTS.md", targets)

    def test_compile_bundles_skills_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "investigator"
            (pkg / "skills" / "music" / "scripts").mkdir(parents=True)
            (pkg / "agent.json").write_text(
                json.dumps(
                    {
                        "id": "simon-investigator",
                        "base_agent": "antigravity-preview-09-2026",
                        "agent_config": {"type": "antigravity", "model": "gemini-3.8-flash"},
                        "tools": [{"type": "code_execution"}],
                        "base_environment": {"type": "remote"},
                    }
                ),
                encoding="utf-8",
            )
            (pkg / "SYSTEM.md").write_text("# General Investigator Process\n", encoding="utf-8")
            (pkg / "skills" / "music" / "SKILL.md").write_text("# Music Skill\n", encoding="utf-8")
            (pkg / "skills" / "music" / "scripts" / "check.py").write_text("print('ok')\n", encoding="utf-8")

            compiled = compile_agent_package(pkg, prefix="prod-")
            sources = compiled["payload"]["base_environment"]["sources"]
            targets = {s["target"] for s in sources}
            self.assertEqual(compiled["deployed_id"], "prod-simon-investigator")
            self.assertIn(".agents/AGENTS.md", targets)
            self.assertIn(".agents/skills/music/SKILL.md", targets)
            self.assertIn(".agents/skills/music/scripts/check.py", targets)

    def test_validate_agent_id_rejects_reserved_prefixes(self) -> None:
        with self.assertRaises(ValueError):
            validate_agent_id("gemini-custom-scout")
        with self.assertRaises(ValueError):
            validate_agent_id("antigravity-scout")
        self.assertEqual(validate_agent_id("prod-simon-scout"), "prod-simon-scout")

    def test_deploy_agents_recreates_existing_agent(self) -> None:
        calls = []

        def fake_request(method, url, api_key, body=None, timeout=60):
            calls.append((method, url))
            if method == "GET":
                return 200, {"id": "kevin-simon-discovery-scout"}
            if method == "DELETE":
                return 204, {}
            if method == "POST":
                return 201, {"id": body["id"], "state": "ACTIVE"}
            raise AssertionError(f"Unexpected {method}")

        res = deploy_agents(
            agent_names=["discovery-scout"],
            prefix="kevin-",
            dry_run=False,
            recreate=True,
            api_key="test-key",
            request_fn=fake_request,
        )
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["agents"][0]["action"], "recreated")
        self.assertEqual([c[0] for c in calls], ["GET", "DELETE", "POST"])

    def test_dispatch_fleet_dry_run_and_webhook_metadata(self) -> None:
        res = dispatch_fleet(
            agent_id="prod-simon-investigator",
            targets=["Olivia Dean", "Allen Stone", "YEBBA"],
            max_concurrency=2,
            webhook_url="https://api.example.com/webhooks/gemini",
            dry_run=True,
        )
        self.assertEqual(res["mode"], "dry_run")
        self.assertEqual(res["total"], 3)
        self.assertEqual(res["max_concurrency"], 2)
        first_req = res["workers"][0]["request"]
        self.assertTrue(first_req["background"])
        self.assertTrue(first_req["store"])
        self.assertEqual(
            first_req["webhook_config"]["uris"],
            ["https://api.example.com/webhooks/gemini"],
        )
        self.assertEqual(first_req["webhook_config"]["user_metadata"]["target"], "Olivia Dean")

    def test_dispatch_fleet_retries_429_and_polls_on_wait(self) -> None:
        attempts = {"post": 0}

        def fake_http(method, url, api_key, body=None, timeout=60):
            if method == "POST":
                attempts["post"] += 1
                if attempts["post"] == 1:
                    return 429, {"error": "rate_limited"}
                return 200, {"id": f"int_{attempts['post']}", "status": "in_progress"}
            if method == "GET":
                return 200, {
                    "id": url.rsplit("/", 1)[-1],
                    "status": "completed",
                    "environment_id": "env_123",
                    "outputs": [{"type": "text", "text": "Factual dossier complete."}],
                }
            raise AssertionError(f"Unexpected {method}")

        res = dispatch_fleet(
            agent_id="kevin-simon-investigator",
            targets=["Artist A", "Artist B"],
            max_concurrency=2,
            wait=True,
            api_key="test-key",
            request_fn=fake_http,
            sleep_fn=lambda _: None,
        )
        self.assertEqual(res["failed"], 0)
        self.assertEqual(res["dispatched"], 2)
        self.assertEqual(res["workers"][0]["output_text"], "Factual dossier complete.")
        self.assertGreaterEqual(attempts["post"], 3)

    def test_web_api_agents_and_fleet_run_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SimonStore(Path(tmp) / "test.db")
            status, _, body = dispatch_http_request(store, "GET", "/api/agents")
            self.assertEqual(status, 200)
            data = json.loads(body.decode("utf-8"))
            pkg_names = {a["package"] for a in data["agents"]}
            self.assertIn("discovery-scout", pkg_names)

            req_payload = json.dumps(
                {
                    "agent": "kevin-simon-discovery-scout",
                    "targets": ["Country vocals", "NYC Soul"],
                    "dry_run": True,
                }
            ).encode("utf-8")
            status2, _, body2 = dispatch_http_request(store, "POST", "/api/fleet/run", req_payload)
            self.assertEqual(status2, 200)
            fleet_data = json.loads(body2.decode("utf-8"))
            self.assertEqual(fleet_data["total"], 2)
            self.assertEqual(fleet_data["mode"], "dry_run")

            # Contract-agnostic structured JSON assignments (e.g., DiscoveryLead objects)
            structured_payload = json.dumps(
                {
                    "agent": "staging-simon-investigator",
                    "assignments": [
                        {
                            "lead_id": "lead_01",
                            "stage_name": "Olivia Dean",
                            "seed_sources": [
                                {
                                    "url": "https://www.youtube.com/watch?v=3-K26i1go0s",
                                    "source_channel": "youtube_live_session",
                                }
                            ],
                        }
                    ],
                    "webhook_url": "https://api.example.com/webhooks/gemini",
                    "dry_run": True,
                }
            ).encode("utf-8")
            status3, _, body3 = dispatch_http_request(store, "POST", "/api/fleet/run", structured_payload)
            self.assertEqual(status3, 200)
            fleet_struct = json.loads(body3.decode("utf-8"))
            worker = fleet_struct["workers"][0]
            self.assertEqual(worker["assignment"]["lead_id"], "lead_01")
            sent_text = worker["request"]["input"][0]["text"]
            self.assertEqual(json.loads(sent_text)["stage_name"], "Olivia Dean")
            self.assertEqual(
                worker["request"]["webhook_config"]["user_metadata"]["target"],
                "lead_01",
            )


if __name__ == "__main__":
    unittest.main()
