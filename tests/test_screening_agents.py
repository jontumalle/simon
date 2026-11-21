"""Unit tests for Stage 3 gemini-4-neon screening agents and rubric validators."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from simon.deploy import _parse_simple_yaml, compile_agent_package, repo_root


def _load_module(module_name: str, script_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = repo_root()
AGENTS_DIR = ROOT / "agents"

VERIFY_ADVOCATE_PATH = (
    AGENTS_DIR / "screen-advocate" / "skills" / "advocate-rubric" / "scripts" / "verify_advocate.py"
)
VERIFY_SKEPTIC_PATH = (
    AGENTS_DIR / "screen-skeptic" / "skills" / "skeptic-rubric" / "scripts" / "verify_skeptic.py"
)
VERIFY_JUDGMENT_PATH = (
    AGENTS_DIR / "screening-judge" / "skills" / "judge-rubric" / "scripts" / "verify_judgment.py"
)

verify_advocate = _load_module("verify_advocate", VERIFY_ADVOCATE_PATH)
verify_skeptic = _load_module("verify_skeptic", VERIFY_SKEPTIC_PATH)
verify_judgment = _load_module("verify_judgment", VERIFY_JUDGMENT_PATH)


def _sample_advocate() -> Dict[str, Any]:
    return {
        "lead_id": "lead_maya_01",
        "stage_name": "Maya Vance",
        "headline": "Unsigned Brooklyn vocalist with 3 embeddable live sessions and strong fan pull.",
        "pros": [
            {
                "skill": "dossier-media",
                "title": "Verified multi-take live session proof",
                "evidence": "3 oembed_live_embeddable YouTube room sessions with verified attribution.",
            },
            {
                "skill": "dossier-comments",
                "title": "High-intent listener demand",
                "evidence": "9 release_requests and 5 live_show_requests across 42 sampled comments.",
            },
        ],
        "standout_hook": "Pulling repeat release requests and Brooklyn club slots with zero label lockup.",
    }


def _sample_skeptic() -> Dict[str, Any]:
    return {
        "lead_id": "lead_maya_01",
        "stage_name": "Maya Vance",
        "headline": "Top session holds 79% of views and Bandcamp supporter count is unavailable.",
        "cons": [
            {
                "skill": "dossier-footprint",
                "title": "Moderately concentrated YouTube reach",
                "evidence": "top_release_view_share_pct is 79.0% across 2 released tracks.",
            }
        ],
        "missing_evidence_flags": [
            "public_footprint.public_reach.bandcamp_supporters_count",
        ],
        "dealbreakers_checked": [
            "one_clip_view_concentration_gt_85pct",
            "studio_only_media",
            "uncertain_attribution",
            "contact_route_none",
            "major_label_lockup",
            "spam_comments",
        ],
    }


def _sample_packet() -> Dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "packet_id": "sp_run_01_lead_maya_01",
        "run_id": "run_01",
        "lead_id": "lead_maya_01",
        "stage_name": "Maya Vance",
        "screened_at": "2026-11-21T21:55:00Z",
        "verdict": "elevate",
        "confidence": 0.85,
        "total_score": 8,
        "rubric_scores": {
            "identity_reachability": 2,
            "live_vocal_proof": 2,
            "early_window_depth": 1,
            "listener_pull_cosigns": 2,
            "stage_momentum_whitespace": 1,
        },
        "rationale": "Verified multi-clip live vocal proof, direct bio_email contact, and 14 release/show requests outweigh moderate top-video view concentration.",
        "advocate_case": _sample_advocate(),
        "skeptic_case": _sample_skeptic(),
    }


class TestScreeningAgentPackages(unittest.TestCase):
    EXPECTED_AGENTS = {
        "screen-advocate": (
            "simon-screen-advocate",
            ".agents/skills/advocate-rubric/scripts/verify_advocate.py",
            "gemini-4-carbon",
        ),
        "screen-skeptic": (
            "simon-screen-skeptic",
            ".agents/skills/skeptic-rubric/scripts/verify_skeptic.py",
            "gemini-4-carbon",
        ),
        "screening-judge": (
            "simon-screening-judge",
            ".agents/skills/judge-rubric/scripts/verify_judgment.py",
            "gemini-4-neon",
        ),
    }

    def test_compile_all_three_neon_screening_agents(self) -> None:
        for pkg_name, (expected_id, expected_script_mount, expected_model) in self.EXPECTED_AGENTS.items():
            with self.subTest(agent=pkg_name):
                agent_dir = AGENTS_DIR / pkg_name
                compiled = compile_agent_package(agent_dir, prefix="staging-")
                self.assertEqual(compiled["deployed_id"], f"staging-{expected_id}")

                payload = compiled["payload"]
                self.assertEqual(payload["base_agent"], "antigravity-preview-09-2026")
                self.assertEqual(
                    payload["agent_config"],
                    {
                        "type": "antigravity",
                        "model": expected_model,
                        "max_total_tokens": "64000",
                    },
                )
                self.assertEqual(payload["tools"], [{"type": "code_execution"}])

                env = payload["base_environment"]
                self.assertEqual(env["type"], "remote")
                self.assertEqual(
                    env["env"],
                    {
                        "SIMON_DOMAIN": "music",
                        "SIMON_DB_URL": "https://simon-staging-139550420825.us-east1.run.app",
                        "SIMON_AGENT_DB_TOKEN": {"credential": "simon-db-token"},
                    },
                )

                targets = {src["target"] for src in env["sources"]}
                self.assertIn(".agents/AGENTS.md", targets)
                self.assertIn(expected_script_mount, targets)
                for shared_skill in (
                    "simon-db",
                    "field-reporting",
                    "dossier-identity",
                    "dossier-media",
                    "dossier-footprint",
                    "dossier-audience",
                    "dossier-track-record",
                ):
                    self.assertIn(f".agents/skills/{shared_skill}/SKILL.md", targets)

    def test_agent_json_and_yaml_parity(self) -> None:
        for pkg_name in self.EXPECTED_AGENTS:
            with self.subTest(agent=pkg_name):
                agent_dir = AGENTS_DIR / pkg_name
                from_json = json.loads((agent_dir / "agent.json").read_text(encoding="utf-8"))
                from_yaml = _parse_simple_yaml((agent_dir / "agent.yaml").read_text(encoding="utf-8"))
                self.assertEqual(from_json, from_yaml)


class TestVerifyAdvocate(unittest.TestCase):
    def test_valid_advocate_case_passes(self) -> None:
        ok, errors = verify_advocate.validate_advocate_case(_sample_advocate())
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])

    def test_empty_pros_rejected(self) -> None:
        bad = _sample_advocate()
        bad["pros"] = []
        ok, errors = verify_advocate.validate_advocate_case(bad)
        self.assertFalse(ok)
        self.assertTrue(any("non-empty list" in e for e in errors))

    def test_forbidden_keys_rejected(self) -> None:
        bad = _sample_advocate()
        bad["interaction_id"] = "int_12345"
        bad["pros"][0]["environment_id"] = "env_999"
        ok, errors = verify_advocate.validate_advocate_case(bad)
        self.assertFalse(ok)
        self.assertTrue(any("interaction_id" in e for e in errors))
        self.assertTrue(any("environment_id" in e for e in errors))

    def test_cli_execution(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(_sample_advocate(), tmp)
            tmp_path = Path(tmp.name)
        try:
            proc = subprocess.run(
                [sys.executable, str(VERIFY_ADVOCATE_PATH), str(tmp_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            out = json.loads(proc.stdout)
            self.assertTrue(out["ok"])
            self.assertEqual(out["pros_count"], 2)
        finally:
            tmp_path.unlink(missing_ok=True)


class TestVerifySkeptic(unittest.TestCase):
    def test_valid_skeptic_case_passes(self) -> None:
        ok, errors = verify_skeptic.validate_skeptic_case(_sample_skeptic())
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])

    def test_missing_fields_from_dossier_enforced(self) -> None:
        dossier = {
            "missing_fields": [
                "public_footprint.public_reach.bandcamp_supporters_count",
                "live_history_and_credits.highest_venue_cap_observed",
            ]
        }
        ok, errors = verify_skeptic.validate_skeptic_case(_sample_skeptic(), dossier=dossier)
        self.assertFalse(ok)
        self.assertTrue(any("highest_venue_cap_observed" in e for e in errors))

        fixed = _sample_skeptic()
        fixed["missing_evidence_flags"].append("live_history_and_credits.highest_venue_cap_observed")
        ok2, errors2 = verify_skeptic.validate_skeptic_case(fixed, dossier=dossier)
        self.assertTrue(ok2, errors2)

    def test_forbidden_keys_and_empty_dealbreakers_rejected(self) -> None:
        bad = _sample_skeptic()
        bad["dealbreakers_checked"] = []
        bad["environment_id"] = "env_secret"
        ok, errors = verify_skeptic.validate_skeptic_case(bad)
        self.assertFalse(ok)
        self.assertTrue(any("dealbreakers_checked" in e for e in errors))
        self.assertTrue(any("environment_id" in e for e in errors))

    def test_cli_execution(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(_sample_skeptic(), tmp)
            tmp_path = Path(tmp.name)
        try:
            proc = subprocess.run(
                [sys.executable, str(VERIFY_SKEPTIC_PATH), str(tmp_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            out = json.loads(proc.stdout)
            self.assertTrue(out["ok"])
        finally:
            tmp_path.unlink(missing_ok=True)


class TestVerifyJudgment(unittest.TestCase):
    def test_valid_screening_packet_passes(self) -> None:
        ok, errors = verify_judgment.validate_screening_packet(_sample_packet())
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])

    def test_score_bounds_and_sum_mismatch_rejected(self) -> None:
        bad_sum = _sample_packet()
        bad_sum["total_score"] = 9
        ok, errors = verify_judgment.validate_screening_packet(bad_sum)
        self.assertFalse(ok)
        self.assertTrue(any("does not equal sum" in e for e in errors))

        bad_rubric = _sample_packet()
        bad_rubric["rubric_scores"]["live_vocal_proof"] = 3
        ok2, errors2 = verify_judgment.validate_screening_packet(bad_rubric)
        self.assertFalse(ok2)
        self.assertTrue(any("live_vocal_proof" in e for e in errors2))

        bool_score = _sample_packet()
        bool_score["rubric_scores"]["early_window_depth"] = True
        ok3, errors3 = verify_judgment.validate_screening_packet(bool_score)
        self.assertFalse(ok3)
        self.assertTrue(any("early_window_depth" in e for e in errors3))

    def test_invalid_verdict_confidence_and_forbidden_keys_rejected(self) -> None:
        bad = _sample_packet()
        bad["verdict"] = "promote"
        bad["confidence"] = 1.4
        bad["advocate_case"]["interaction_id"] = "int_leak"
        ok, errors = verify_judgment.validate_screening_packet(bad)
        self.assertFalse(ok)
        self.assertTrue(any("verdict" in e for e in errors))
        self.assertTrue(any("confidence" in e for e in errors))
        self.assertTrue(any("interaction_id" in e for e in errors))

    def test_lead_id_mismatch_rejected(self) -> None:
        bad = _sample_packet()
        bad["skeptic_case"]["lead_id"] = "lead_other_99"
        ok, errors = verify_judgment.validate_screening_packet(bad)
        self.assertFalse(ok)
        self.assertTrue(any("skeptic_case.lead_id" in e for e in errors))

    def test_cli_execution(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(_sample_packet(), tmp)
            tmp_path = Path(tmp.name)
        try:
            proc = subprocess.run(
                [sys.executable, str(VERIFY_JUDGMENT_PATH), str(tmp_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            out = json.loads(proc.stdout)
            self.assertTrue(out["ok"])
            self.assertEqual(out["verdict"], "elevate")
            self.assertEqual(out["total_score"], 8)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
