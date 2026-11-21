from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

from simon.discovery_ui import INVESTIGATE_HTML, _SHARED_CSS, _render_top_nav, render_top_nav
from simon.screening_ui import SCREENING_HTML, render_screening_page


class TestScreeningDeckUI(unittest.TestCase):
    def test_top_nav_includes_screening_stage_and_active_state(self) -> None:
        nav_screen = _render_top_nav("/screen")
        self.assertEqual(nav_screen, render_top_nav("/screen"))
        self.assertIn('<div class="nav-group stage-screening">', nav_screen)
        self.assertIn('<span class="nav-group-label">Screening</span>', nav_screen)
        self.assertIn('<a href="/screen" id="screenNavLink" class="active">6. Screening Deck</a>', nav_screen)
        self.assertNotIn('href="/discovery" class="active"', nav_screen)

        nav_disc = _render_top_nav("/discovery")
        self.assertIn('<a href="/screen" id="screenNavLink">6. Screening Deck</a>', nav_disc)
        self.assertIn('<a href="/discovery" class="active">1. Discovery Dashboard</a>', nav_disc)

        # Shared CSS styles .nav-group.stage-screening cleanly
        self.assertIn(".nav-group.stage-screening", _SHARED_CSS)
        # Investigator Desk links cleanly into the Screening Deck
        self.assertIn('href="/screen"', INVESTIGATE_HTML)
        self.assertIn("Open Screening Deck", INVESTIGATE_HTML)

    def test_render_screening_page_structure_and_stepper_controls(self) -> None:
        html = render_screening_page()
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertEqual(html, SCREENING_HTML)
        self.assertIn("6. Screening Deck", html)
        self.assertIn('<a href="/screen" id="screenNavLink" class="active">6. Screening Deck</a>', html)

        # Top Control Strip: counter, 5 filter pills, fleet/DSPy/eval buttons, active model badge
        self.assertIn('id="deckCounterBadge"', html)
        for filt in ("all", "unlabeled", "ELEVATE", "WATCH", "PASS"):
            self.assertIn(f'data-filter="{filt}"', html)
        self.assertIn("Run Neon Screening Fleet", html)
        self.assertIn("Compile Judging Model (DSPy)", html)
        self.assertIn("Run Rubric Evals", html)
        self.assertIn('id="activeModelBadge"', html)

        # Stepper & keyboard navigation
        self.assertIn("← Previous Candidate", html)
        self.assertIn("Next Candidate →", html)
        self.assertIn('id="candidateJumpPills"', html)
        self.assertIn("ArrowLeft", html)
        self.assertIn("ArrowRight", html)

    def test_hero_rubric_advocate_skeptic_hitl_and_inspector_elements(self) -> None:
        html = render_screening_page()

        # Hero dossier fields & YouTube embed extraction
        for field in (
            "dossier_snapshot",
            "project_type",
            "home_city",
            "home_neighborhood",
            "primary_genre",
            "subgenres",
            "footprint_regime",
            "contact_route_type",
            "youtube_subscribers",
            "top_video_views",
            "top_release_view_share_pct",
            "highest_venue_cap_observed",
            "https://www.youtube.com/embed/",
            "media_links",
            "seed_source_url",
        ):
            self.assertIn(field, html, f"Missing hero/media field reference: {field}")

        # 5 Input-Skill Rubric Scoreboard dimensions + skill badges
        for rubric_key in (
            "identity_reachability",
            "live_vocal_proof",
            "early_window_depth",
            "listener_pull_cosigns",
            "stage_momentum_whitespace",
        ):
            self.assertIn(rubric_key, html, f"Missing rubric dimension: {rubric_key}")
        self.assertIn("dossier-identity", html)

        # Adversarial Debate Grid (Advocate vs. Skeptic)
        self.assertIn("simon-screen-advocate", html)
        self.assertIn("advocate_case", html)
        self.assertIn("standout_hook", html)
        self.assertIn("simon-screen-skeptic", html)
        self.assertIn("skeptic_case", html)
        self.assertIn("missing_evidence_flags", html)

        # Neon Judge synthesis + Human-in-the-Loop Calibration Footer
        self.assertIn("gemini-4-neon", html)
        for verdict in ("ELEVATE", "WATCH", "PASS"):
            self.assertIn(f'data-verdict="{verdict}"', html)
        self.assertIn("Why? (trains judging rubric — especially on overrides)", html)
        self.assertIn("Save &amp; Next →", html)
        self.assertIn("human_review", html)

        # Collapsible Rubric Eval Results & Active gemini-decision-1 Policy Inspector
        self.assertIn('id="policyInspectorDrawer"', html)
        self.assertIn("gemini-decision-1", html)
        self.assertIn("questions_config", html)

        # XSS protection & human-first telemetry hygiene
        self.assertIn("function escapeHtml(", html)
        self.assertNotIn("interaction_id", html)
        self.assertNotIn("environment_id", html)

    def test_absence_of_swipe_or_drag_gesture_handlers(self) -> None:
        html_lower = render_screening_page().lower()
        forbidden_swipe_tokens = (
            "touchstart",
            "touchmove",
            "touchend",
            "pointerdown",
            "pointermove",
            "pointerup",
            "ondragstart",
            'draggable="true"',
            "swipeleft",
            "swiperight",
            "onswipe",
        )
        for token in forbidden_swipe_tokens:
            self.assertNotIn(token, html_lower, f"Forbidden swipe/drag handler token found: {token}")

    def test_api_screening_endpoint_bindings(self) -> None:
        html = render_screening_page()
        for endpoint in (
            "/api/screening/packets",
            "/api/screening/run",
            "/api/screening/train",
            "/api/screening/evals/run",
            "/api/screening/models",
            "/api/screening/labels",
        ):
            self.assertIn(endpoint, html, f"Missing API binding: {endpoint}")

        # Label submission payload keys
        for key in ("packet_id", "lead_id", "stage_name", "human_verdict", "reason"):
            self.assertIn(key, html, f"Missing HITL label payload key: {key}")

    def test_inline_script_syntax_valid(self) -> None:
        html = render_screening_page()
        match = re.search(r"<script>(.*)</script>", html, flags=re.DOTALL)
        self.assertIsNotNone(match, "Expected inline <script> block in screening page")
        script_src = match.group(1)

        node_bin = shutil.which("node")
        if node_bin:
            with tempfile.TemporaryDirectory() as tmpdir:
                js_path = Path(tmpdir) / "screening_deck.js"
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
