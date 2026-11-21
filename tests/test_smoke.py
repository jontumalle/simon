from pathlib import Path
import unittest

from simon.__main__ import run_showcase


class ShowcaseSmokeTest(unittest.TestCase):
    def test_demo_showcase_runs_deterministically(self):
        manifest = Path(__file__).resolve().parents[1] / "examples" / "showcase.json"
        result = run_showcase(manifest, live=False)
        self.assertEqual(result["mode"], "fictional_demo")
        self.assertEqual(result["audition_ids"], ["a01", "a02"])
        self.assertEqual(result["decision_status"], "pending_human_review")
        self.assertIn("performance", result["reviews"])
        self.assertIn("booking", result["reviews"])
        self.assertIn("producer", result["reviews"])


if __name__ == "__main__":
    unittest.main()
