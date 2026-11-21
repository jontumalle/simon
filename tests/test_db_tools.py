from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from simon.db_tools import validate_collection_payload, verify_agent_db_auth
from simon.deploy import compile_agent_package, list_agent_packages, sync_env_credential
from simon.store import SimonStore
from simon.web import dispatch_http_request


class TestSharedAgentDBTools(unittest.TestCase):
    def test_verify_agent_db_auth_enforces_bearer_token(self) -> None:
        ok, _ = verify_agent_db_auth({}, expected_token="")
        self.assertTrue(ok)

        ok_missing, _ = verify_agent_db_auth({}, expected_token="secret-123")
        self.assertFalse(ok_missing)

        ok_bad, _ = verify_agent_db_auth({"Authorization": "Bearer wrong"}, expected_token="secret-123")
        self.assertFalse(ok_bad)

        ok_good, _ = verify_agent_db_auth({"Authorization": "Bearer secret-123"}, expected_token="secret-123")
        self.assertTrue(ok_good)

        ok_alt, _ = verify_agent_db_auth({"X-Simon-Agent-Token": "secret-123"}, expected_token="secret-123")
        self.assertTrue(ok_alt)

    def test_contract_validation_rejects_bad_payload_and_accepts_valid_handoff(self) -> None:
        errs, _ = validate_collection_payload("discovered_sources", {"url": "https://example.com"})
        self.assertTrue(errs)

        valid_handoff = {
            "contract_version": "1.0.0",
            "run_id": "run_abc123",
            "search_brief": "Find live NYC soul vocalists",
            "requested_count": 1,
            "leads": [
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
        }
        errs2, doc_id = validate_collection_payload("discovery_handoffs", valid_handoff)
        self.assertEqual(errs2, [])
        self.assertEqual(doc_id, "run_abc123")

    def test_http_api_db_auth_allowlist_validation_and_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SimonStore(Path(tmp) / "test.db")
            prev = os.environ.get("SIMON_AGENT_DB_TOKEN")
            os.environ["SIMON_AGENT_DB_TOKEN"] = "agent-secret"
            try:
                # 1. Missing token -> 401
                s1, _, _ = dispatch_http_request(store, "GET", "/api/db/discovered_sources")
                self.assertEqual(s1, 401)

                auth = {"Authorization": "Bearer agent-secret"}

                # 2. Disallowed collection -> 403
                s2, _, _ = dispatch_http_request(store, "GET", "/api/db/users_private", headers=auth)
                self.assertEqual(s2, 403)

                # 3. Invalid schema payload -> 422
                bad_body = json.dumps({"url": "https://youtube.com/@SofarSounds"}).encode("utf-8")
                s3, _, _ = dispatch_http_request(store, "POST", "/api/db/discovered_sources", bad_body, headers=auth)
                self.assertEqual(s3, 422)

                # 4. Valid save -> 201, then GET + LIST
                good_body = json.dumps(
                    {
                        "doc_id": "src_sofar",
                        "url": "https://www.youtube.com/@SofarSounds",
                        "source_channel": "youtube_live_session",
                        "why_useful": "Live vocal sessions with clear artist attribution.",
                    }
                ).encode("utf-8")
                s4, _, b4 = dispatch_http_request(store, "POST", "/api/db/discovered_sources", good_body, headers=auth)
                self.assertEqual(s4, 201)
                saved = json.loads(b4.decode("utf-8"))
                self.assertEqual(saved["doc_id"], "src_sofar")

                s5, _, b5 = dispatch_http_request(store, "GET", "/api/db/discovered_sources/src_sofar", headers=auth)
                self.assertEqual(s5, 200)
                self.assertEqual(json.loads(b5.decode("utf-8"))["document"]["source_channel"], "youtube_live_session")

                s6, _, b6 = dispatch_http_request(store, "GET", "/api/db/discovered_sources?limit=5", headers=auth)
                self.assertEqual(s6, 200)
                self.assertEqual(json.loads(b6.decode("utf-8"))["count"], 1)
            finally:
                if prev is None:
                    os.environ.pop("SIMON_AGENT_DB_TOKEN", None)
                else:
                    os.environ["SIMON_AGENT_DB_TOKEN"] = prev

    def test_deploy_bundles_shared_simon_db_skill_and_ignores_shared_dir(self) -> None:
        pkgs = [p.name for p in list_agent_packages()]
        self.assertNotIn("_shared", pkgs)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared_dst = root / "_shared" / "skills" / "simon-db" / "scripts"
            shared_dst.mkdir(parents=True)
            repo_shared = Path(__file__).resolve().parents[1] / "agents" / "_shared" / "skills" / "simon-db"
            (root / "_shared" / "skills" / "simon-db" / "SKILL.md").write_text(
                (repo_shared / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8"
            )
            (shared_dst / "simon_db.py").write_text(
                (repo_shared / "scripts" / "simon_db.py").read_text(encoding="utf-8"), encoding="utf-8"
            )

            agent_dir = root / "test-scout"
            agent_dir.mkdir()
            (agent_dir / "SYSTEM.md").write_text("# Test Scout\n", encoding="utf-8")
            (agent_dir / "agent.json").write_text(
                json.dumps(
                    {
                        "id": "simon-test-scout",
                        "base_agent": "antigravity-preview-09-2026",
                        "shared_skills": ["simon-db"],
                        "tools": [{"type": "code_execution"}],
                        "base_environment": {"type": "remote"},
                    }
                ),
                encoding="utf-8",
            )

            compiled = compile_agent_package(agent_dir, prefix="staging-")
            targets = {s["target"] for s in compiled["payload"]["base_environment"]["sources"]}
            self.assertIn(".agents/skills/simon-db/SKILL.md", targets)
            self.assertIn(".agents/skills/simon-db/scripts/simon_db.py", targets)

    def test_sync_env_credential_recreates_existing(self) -> None:
        calls = []

        def fake_req(method, url, api_key, body=None, timeout=60):
            calls.append((method, url, body))
            if method == "GET":
                return 200, {"id": "simon-db-token"}
            if method == "DELETE":
                return 204, {}
            if method == "POST":
                return 201, {"id": body["id"]}
            raise AssertionError(method)

        res = sync_env_credential(
            credential_id="simon-db-token",
            value="secret-val",
            trusted_domains=["simon-staging-139550420825.us-east1.run.app"],
            api_key="test-key",
            request_fn=fake_req,
        )
        self.assertEqual(res["action"], "recreated")
        self.assertEqual([c[0] for c in calls], ["GET", "DELETE", "POST"])
        self.assertEqual(calls[2][2]["type"], "environment_variable")
        self.assertEqual(calls[2][2]["injection_location"], "header")


if __name__ == "__main__":
    unittest.main()
