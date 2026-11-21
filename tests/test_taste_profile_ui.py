from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from simon.discovery_ui import render_top_nav
from simon.store import SimonStore
from simon.taste_profile_ui import TASTE_PROFILE_HTML, render_taste_profile_page
from simon.web import dispatch_http_request


class TestTasteProfileUI(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = SimonStore(Path(self._tmpdir.name) / "test_taste.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_top_nav_sequential_numbering_and_active_taste_profile(self) -> None:
        nav_taste = render_top_nav("/taste-profile")
        self.assertIn('<a href="/evals" id="evalsNavLink">6. Evals</a>', nav_taste)
        self.assertIn('<a href="/screen" id="screenNavLink">7. Screening Deck</a>', nav_taste)
        self.assertIn(
            '<a href="/taste-profile" id="tasteProfileNavLink" class="active">8. Taste Profile</a>',
            nav_taste,
        )
        self.assertIn('id="simonNavThemeBtn"', nav_taste)

    def test_get_taste_profile_html_and_three_pillars(self) -> None:
        code, ctype, raw_html = dispatch_http_request(self.store, "GET", "/taste-profile")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        html = raw_html.decode("utf-8")
        self.assertEqual(html, TASTE_PROFILE_HTML)
        self.assertEqual(html, render_taste_profile_page())

        # Three human-first pillars + controls
        self.assertIn("1. Where We Are", html)
        self.assertIn("2. What We Care About", html)
        self.assertIn("3. Our Methodology: How Simon Separates Facts from Taste", html)
        self.assertIn("What You Taught Us", html)
        self.assertIn("Re-Compile Taste Profile", html)
        self.assertIn("← Back to Screening Deck", html)
        self.assertIn('id="policyVersionSelect"', html)

        # Light / dark theme variables + XSS escaping + zero raw telemetry leakage
        self.assertIn('[data-theme="dark"]', html)
        self.assertIn("function escapeHtml(", html)
        self.assertNotIn("interaction_id", html)
        self.assertNotIn("environment_id", html)

    def test_api_taste_profile_auto_compiles_policy_v1_and_evolves_with_overrides(self) -> None:
        # First call on fresh DB auto-seeds candidates and compiles policy_v1
        code, ctype, raw = dispatch_http_request(self.store, "GET", "/api/taste-profile")
        self.assertEqual(code, 200)
        self.assertIn("application/json", ctype)
        payload = json.loads(raw.decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertIsNotNone(payload["active_policy"])
        self.assertEqual(payload["active_policy"]["policy_id"], "policy_v1")
        self.assertEqual(payload["active_policy"]["target_model"], "gemini-decision-1")
        self.assertGreaterEqual(len(payload["models"]), 1)
        self.assertEqual(len(payload["input_criteria"]), 5)
        self.assertEqual(payload["summary"]["calibration_stage"], "Bootstrapping")
        self.assertGreaterEqual(payload["summary"]["candidates_screened"], 1)
        self.assertIn("layers", payload["rubric_spec"])

        expected_skills = [
            "dossier-identity",
            "dossier-media",
            "dossier-footprint",
            "dossier-audience",
            "dossier-track-record",
        ]
        self.assertEqual([c["skill"] for c in payload["input_criteria"]], expected_skills)

        # Log a human override with XSS-probe note to verify storage + sanitization + policy_v2 evolution
        packets_code, _, packets_raw = dispatch_http_request(self.store, "GET", "/api/screening/packets")
        self.assertEqual(packets_code, 200)
        first_pkt = json.loads(packets_raw.decode("utf-8"))["packets"][0]
        model_verdict = (first_pkt.get("judge_decision") or {}).get("verdict", "elevate")
        override_verdict = "pass" if model_verdict != "pass" else "elevate"
        xss_reason = 'I like their look <script>alert("xss")</script> & live room feel'

        lbl_code, _, _ = dispatch_http_request(
            self.store,
            "POST",
            "/api/screening/labels",
            json.dumps(
                {
                    "lead_id": first_pkt["lead_id"],
                    "packet_id": first_pkt["packet_id"],
                    "stage_name": first_pkt["stage_name"],
                    "human_verdict": override_verdict,
                    "reason": xss_reason,
                }
            ).encode("utf-8"),
        )
        self.assertEqual(lbl_code, 201)

        train_code, _, train_raw = dispatch_http_request(
            self.store, "POST", "/api/screening/train", b"{}"
        )
        self.assertEqual(train_code, 200)
        trained = json.loads(train_raw.decode("utf-8"))
        self.assertEqual(trained["policy_id"], "policy_v2")

        code2, _, raw2 = dispatch_http_request(self.store, "GET", "/api/taste-profile")
        self.assertEqual(code2, 200)
        payload2 = json.loads(raw2.decode("utf-8"))
        self.assertEqual(payload2["active_policy"]["policy_id"], "policy_v2")
        self.assertEqual(len(payload2["models"]), 2)
        self.assertEqual(payload2["summary"]["human_reviews_count"], 1)
        self.assertEqual(payload2["summary"]["overrides_count"], 1)
        self.assertEqual(payload2["summary"]["calibration_stage"], "Learning Your Taste")

        # Confirm human scout guidance is baked into taste_verdict criteria
        tv_criteria = payload2["active_policy"]["questions_config"]["taste_verdict"]["criteria"]
        self.assertIn(f"Human scout {override_verdict} guidance:", tv_criteria[override_verdict])
        self.assertIn("I like their look", tv_criteria[override_verdict])

        # Confirm zero forbidden telemetry keys in payload dicts
        from simon.screening import _find_forbidden_keys_raw

        self.assertEqual(_find_forbidden_keys_raw(payload2), [])

    def test_inline_script_syntax_and_xss_escaping_valid(self) -> None:
        html = render_taste_profile_page()
        scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
        self.assertGreaterEqual(len(scripts), 1)
        script_src = "\n;\n".join(scripts)

        node_bin = shutil.which("node")
        if node_bin:
            with tempfile.TemporaryDirectory() as tmpdir:
                js_path = Path(tmpdir) / "taste_profile.js"
                js_path.write_text(script_src, encoding="utf-8")
                proc = subprocess.run(
                    [node_bin, "--check", str(js_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, f"JS syntax error:\n{proc.stderr}")
            return

        osascript_bin = shutil.which("osascript")
        if not osascript_bin:
            self.skipTest("Neither node nor osascript installed")
        proc = subprocess.run(
            [osascript_bin, "-l", "JavaScript", "-e", f"new Function({script_src!r}); 'OK'"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"JS syntax error:\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
