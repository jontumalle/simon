"""Unit tests for Discovery Scout Vertex AI rubrics, eval runner, and /evals platform UI."""

from __future__ import annotations

from http import HTTPStatus
import json
from pathlib import Path
import tempfile
import unittest

from simon.store import SimonStore
from simon.vertex_eval import (
    format_markdown_summary,
    load_discovery_rubrics,
    run_discovery_eval,
)
from simon.web import dispatch_http_request


class VertexEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test_evals.db"
        self.store = SimonStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_rubric_spec_covers_three_layers_and_five_skills(self) -> None:
        spec = load_discovery_rubrics()
        self.assertEqual(spec["rubric_set_id"], "discovery-scout-v1")
        self.assertEqual(len(spec["layers"]), 3)
        self.assertEqual(
            set(spec["skills_covered"]),
            {"simon-db", "music", "youtube", "source-discovery", "field-reporting"},
        )
        rubric_ids = [r["id"] for layer in spec["layers"] for r in layer["rubrics"]]
        for expected in ("gate_contract", "gate_no_sys_leak", "proc_db_first", "proc_yt_quota", "qual_zero_ranking"):
            self.assertIn(expected, rubric_ids)

    def test_offline_eval_runner_and_markdown_summary(self) -> None:
        result = run_discovery_eval(
            mode="offline",
            sample_source="golden_dataset",
            store=self.store,
            trigger="unittest",
        )
        self.assertTrue(result["passed_gates"])
        # Offline mode must not award fake 100% on LLM-only rubrics.
        self.assertLess(result["overall_score"], 1.0)
        llm_only = [d for d in result["dimensions"] if "Requires Vertex AI LLM judge" in d.get("detail", "")]
        self.assertGreaterEqual(len(llm_only), 1)
        self.assertTrue(all(not d["passed"] and d["score"] == 0.0 for d in llm_only))
        self.assertEqual(result["runner"], "offline_baseline")
        self.assertGreaterEqual(len(result["dimensions"]), 10)

        md = format_markdown_summary(result)
        self.assertIn(result["eval_run_id"], md)
        self.assertIn("| Layer | Rubric | Skill |", md)

    def test_evals_ui_and_api_endpoints(self) -> None:
        # 1. GET /evals HTML page
        status, ctype, body = dispatch_http_request(self.store, "GET", "/evals")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", ctype)
        self.assertIn("6. Evals (Vertex AI)", body.decode("utf-8"))

        # 2. GET /api/evals/agents lists all 9 fleet agents
        status, _, body = dispatch_http_request(self.store, "GET", "/api/evals/agents")
        self.assertEqual(status, HTTPStatus.OK)
        agents_resp = json.loads(body.decode("utf-8"))
        self.assertGreaterEqual(agents_resp["count"], 9)

        # 3. GET /api/evals/rubrics
        status, _, body = dispatch_http_request(self.store, "GET", "/api/evals/rubrics?agent=discovery-scout")
        self.assertEqual(status, HTTPStatus.OK)
        spec = json.loads(body.decode("utf-8"))
        self.assertEqual(spec["rubric_set_id"], "discovery-scout-v1")

        # 3. POST /api/eval-runs/run (UI trigger)
        payload = json.dumps({"mode": "offline", "sample_source": "golden_dataset"}).encode("utf-8")
        status, _, body = dispatch_http_request(self.store, "POST", "/api/eval-runs/run", payload)
        self.assertEqual(status, HTTPStatus.CREATED)
        created = json.loads(body.decode("utf-8"))
        self.assertEqual(created["trigger"], "platform_ui")
        self.assertTrue(created["passed_gates"])

        # 4. POST /api/eval-runs (GitHub Actions Vertex AI ingest)
        vertex_run = dict(created)
        vertex_run["eval_run_id"] = "eval_vertex_ci_01"
        vertex_run["runner"] = "hybrid_vertex_offline"
        vertex_run["mode"] = "vertex"
        vertex_run["trigger"] = "github_actions_vertex"
        vertex_run["vertex_console_url"] = (
            "https://console.cloud.google.com/vertex-ai/experiments/locations/us-east1"
            "/experiments/simon-discovery-eval/runs?project=gemini4nyc26nyc-2203"
        )
        status, _, body = dispatch_http_request(
            self.store,
            "POST",
            "/api/eval-runs",
            json.dumps(vertex_run).encode("utf-8"),
        )
        self.assertEqual(status, HTTPStatus.CREATED)

        # 5. GET /api/eval-runs lists both runs
        status, _, body = dispatch_http_request(self.store, "GET", "/api/eval-runs")
        self.assertEqual(status, HTTPStatus.OK)
        listed = json.loads(body.decode("utf-8"))
        self.assertEqual(listed["count"], 2)
        ids = {r["eval_run_id"] for r in listed["eval_runs"]}
        self.assertIn("eval_vertex_ci_01", ids)
        self.assertIn(created["eval_run_id"], ids)

    def test_trace_selection_endpoint_and_incomplete_trace_fails_gates(self) -> None:
        # Seed one incomplete agent_run trace (simulating a 64k-token truncation)
        self.store.save_document(
            "agent_runs",
            "run_incomplete_01",
            {
                "agent_run_id": "run_incomplete_01",
                "agent_id": "staging-simon-discovery-scout",
                "stage": "discovery",
                "status": "incomplete",
                "assignment": "Emerging NYC indie acts",
                "output_text": "",
                "steps": [{"index": 1, "type": "thought", "preview": "Reading skills"}],
                "created_at": "2026-11-21T22:25:00Z",
            },
        )
        # 1. GET /api/evals/traces?agent=discovery-scout lists the trace
        status, _, body = dispatch_http_request(self.store, "GET", "/api/evals/traces?agent=discovery-scout")
        self.assertEqual(status, HTTPStatus.OK)
        tdata = json.loads(body.decode("utf-8"))
        self.assertEqual(tdata["count"], 1)
        self.assertEqual(tdata["traces"][0]["trace_id"], "run_incomplete_01")

        # 2. POST /api/eval-runs/run targeting that exact trace fails Layer 1 gates honestly
        req = json.dumps(
            {
                "agent": "discovery-scout",
                "mode": "offline",
                "trace_id": "run_incomplete_01",
                "trace_collection": "agent_runs",
            }
        ).encode("utf-8")
        status, _, body = dispatch_http_request(self.store, "POST", "/api/eval-runs/run", req)
        self.assertEqual(status, HTTPStatus.CREATED)
        ev = json.loads(body.decode("utf-8"))
        self.assertEqual(ev["sample_source"], "trace:run_incomplete_01")
        self.assertFalse(ev["passed_gates"])
        self.assertEqual(ev["status"], "failed")


if __name__ == "__main__":
    unittest.main()
