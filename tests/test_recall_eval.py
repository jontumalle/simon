"""Unit tests for Option C Label-Signing Recall Eval runner (simon/recall_eval.py)."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from simon.recall_eval import (
    format_recall_markdown,
    load_recall_benchmark,
    load_seed_sources,
    normalize_name,
    run_recall_eval,
    validate_benchmark_integrity,
    validate_seed_source_coverage,
)
from simon.store import SimonStore


class RecallEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = SimonStore(Path(self._tmp.name) / "recall_test.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_benchmark_integrity_and_seed_source_coverage_pass(self) -> None:
        benchmark = load_recall_benchmark()
        seed_sources = load_seed_sources()
        ok_int, err_int = validate_benchmark_integrity(benchmark)
        self.assertTrue(ok_int, f"Integrity errors: {err_int}")
        ok_cov, err_cov = validate_seed_source_coverage(benchmark, seed_sources)
        self.assertTrue(ok_cov, f"Seed coverage errors: {err_cov}")

    def test_normalize_name_handles_diacritics_and_the_prefix(self) -> None:
        self.assertEqual(normalize_name("RÓIS"), "rois")
        self.assertEqual(normalize_name("The Sophs"), "sophs")
        self.assertEqual(normalize_name("Starcleaner Reunion!"), "starcleaner reunion")

    def test_recall_scoring_separates_in_map_and_out_of_map(self) -> None:
        sample_handoff = {
            "contract_version": "1.0.0",
            "leads": [
                {
                    "stage_name": "Starcleaner Reunion",
                    "seed_sources": [{"url": "https://www.youtube.com/watch?v=kjcHNty7nD8"}],
                },
                {
                    "stage_name": "Hello Mary",
                    "seed_sources": [{"url": "https://www.youtube.com/watch?v=-WMoZTedBT4"}],
                },
                {
                    "stage_name": "YHWH Nailgun",
                    "seed_sources": [{"url": "https://www.youtube.com/watch?v=41flmWt-9l8"}],
                },
                {
                    # Accent-stripped match for RÓIS (out_of_map)
                    "stage_name": "ROIS",
                    "seed_sources": [{"url": "https://www.youtube.com/watch?v=lxZX7OfvJbc"}],
                },
            ],
        }
        result = run_recall_eval(handoff_payloads=[sample_handoff], trigger="unittest")
        self.assertTrue(result["passed_gates"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["sample_count"], 10)

        dims = {d["rubric_id"]: d for d in result["dimensions"]}
        self.assertEqual(dims["recall_in_map"]["raw_score"], 3.0)
        self.assertAlmostEqual(dims["recall_in_map"]["score"], 0.5)
        self.assertEqual(dims["recall_out_of_map"]["raw_score"], 1.0)
        self.assertAlmostEqual(dims["recall_out_of_map"]["score"], 0.25)
        self.assertEqual(dims["recall_overall"]["raw_score"], 4.0)
        self.assertAlmostEqual(dims["recall_overall"]["score"], 0.4)

        md = format_recall_markdown(result)
        self.assertIn("Label-Signing Recall Eval", md)
        self.assertIn("3/6 in-map", md)

    def test_store_persistence_matches_eval_run_schema(self) -> None:
        result = run_recall_eval(store=self.store, trigger="unittest")
        self.store.save_document("eval_runs", result["eval_run_id"], result)
        saved = self.store.list_documents("eval_runs", limit=5)
        self.assertEqual(len(saved), 1)
        doc = saved[0].get("data", saved[0])
        self.assertEqual(doc["rubric_set_id"], "discovery-label-recall-v1")
        self.assertTrue(doc["passed_gates"])


if __name__ == "__main__":
    unittest.main()
