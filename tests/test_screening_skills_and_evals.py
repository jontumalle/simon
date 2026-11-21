"""Unit tests for Stage 3 Screening Contract, 5 Shared Dossier Input Skills, Rubrics, and Demo."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List

from jsonschema import Draft202012Validator, ValidationError

from simon.investigator import evaluate_dossier_process

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENING_CONTRACT_PATH = REPO_ROOT / "data" / "screening_contract.json"
DISCOVERY_CONTRACT_PATH = REPO_ROOT / "data" / "discovery_investigator_contract.json"
SCREENING_RUBRICS_PATH = REPO_ROOT / "data" / "evals" / "screening_rubrics.json"
SCREENING_DEMO_PATH = REPO_ROOT / "examples" / "screening_demo.json"
TASTE_BRIEF_DEMO_PATH = REPO_ROOT / "examples" / "taste_brief_demo.json"
SHARED_SKILLS_DIR = REPO_ROOT / "agents" / "_shared" / "skills"

EXPECTED_SKILL_SPECS = [
    ("dossier-identity", "score_identity.py", "identity_reachability"),
    ("dossier-media", "score_media.py", "live_vocal_proof"),
    ("dossier-footprint", "score_footprint.py", "early_window_depth"),
    ("dossier-audience", "score_audience.py", "listener_pull_cosigns"),
    ("dossier-track-record", "score_track_record.py", "stage_momentum_whitespace"),
]

URL_RE = re.compile(r"https?://[^\s\"')\]>]+")
YOUTUBE_WATCH_RE = re.compile(r"^https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}$")
FORBIDDEN_SYS_KEYS = ("interaction_id", "environment_id", "trace_id")


def _load_skill_evaluator(skill_dir: str, script_name: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    script_path = SHARED_SKILLS_DIR / skill_dir / "scripts" / script_name
    module_name = f"_test_{skill_dir.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


def _collect_urls(obj: Any) -> List[str]:
    found: List[str] = []
    if isinstance(obj, str):
        for match in URL_RE.findall(obj):
            found.append(match.rstrip(".,;:"))
    elif isinstance(obj, dict):
        for val in obj.values():
            found.extend(_collect_urls(val))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_collect_urls(item))
    return found


def _subschema_validator(root_schema: Dict[str, Any], def_name: str) -> Draft202012Validator:
    schema = {
        "$schema": root_schema["$schema"],
        "$defs": root_schema["$defs"],
        "$ref": f"#/$defs/{def_name}",
    }
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class ScreeningContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(SCREENING_CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.discovery_contract = json.loads(DISCOVERY_CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.demo = json.loads(SCREENING_DEMO_PATH.read_text(encoding="utf-8"))

    def test_draft_2020_12_schema_and_dossier_parity(self) -> None:
        self.assertEqual(
            self.contract["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        Draft202012Validator.check_schema(self.contract)
        for required_def in (
            "ScreeningPacket",
            "ScreeningLabel",
            "JudgingModelPolicy",
            "ScreeningBatch",
            "InvestigatorDossier",
        ):
            self.assertIn(required_def, self.contract["$defs"])

        self.assertEqual(
            self.contract["$defs"]["InvestigatorDossier"],
            self.discovery_contract["$defs"]["InvestigatorDossier"],
        )

    def test_screening_packet_schema_accepts_valid_and_rejects_invalid(self) -> None:
        validator = _subschema_validator(self.contract, "ScreeningPacket")
        valid_pkt = copy.deepcopy(self.demo["packets"][0])
        validator.validate(valid_pkt)

        bad_model = copy.deepcopy(valid_pkt)
        bad_model["screening_model"] = "gemini-2.5-flash"
        with self.assertRaises(ValidationError):
            validator.validate(bad_model)

        missing_rubric = copy.deepcopy(valid_pkt)
        del missing_rubric["judge_decision"]["rubric_scores"]["stage_momentum_whitespace"]
        with self.assertRaises(ValidationError):
            validator.validate(missing_rubric)

        bad_score = copy.deepcopy(valid_pkt)
        bad_score["judge_decision"]["rubric_scores"]["live_vocal_proof"]["score"] = 3
        with self.assertRaises(ValidationError):
            validator.validate(bad_score)

    def test_screening_label_and_judging_policy_schemas(self) -> None:
        label_validator = _subschema_validator(self.contract, "ScreeningLabel")
        valid_label = {
            "label_id": "lbl_001",
            "packet_id": "pkt_scr_02",
            "lead_id": "lead_scr_02",
            "stage_name": "Kieran Vale",
            "model_verdict": "watch",
            "model_total_score": 6,
            "human_verdict": "elevate",
            "agreed_with_model": False,
            "reason": "Raw vocal tone is strong enough for a 15-minute acoustic showcase slot.",
            "labeled_at": "2026-11-21T22:00:00Z",
            "training_features": {
                "identity_reachability": 1,
                "live_vocal_proof": 1,
                "early_window_depth": 1,
                "listener_pull_cosigns": 2,
                "stage_momentum_whitespace": 1,
                "top_release_view_share_pct": 91.0,
            },
        }
        label_validator.validate(valid_label)

        bad_label = copy.deepcopy(valid_label)
        bad_label["human_verdict"] = "maybe"
        with self.assertRaises(ValidationError):
            label_validator.validate(bad_label)

        policy_validator = _subschema_validator(self.contract, "JudgingModelPolicy")
        valid_policy = {
            "policy_id": "pol_decision_v1",
            "version": "1.0.0",
            "target_model": "gemini-decision-1",
            "optimizer": "calibrated_few_shot_rubric_v1",
            "questions_config": {
                "verdict_bands": {"elevate_min": 7, "watch_min": 4, "pass_max": 3},
                "criteria_weights": {
                    "identity_reachability": 1.0,
                    "live_vocal_proof": 1.0,
                    "early_window_depth": 1.0,
                    "listener_pull_cosigns": 1.0,
                    "stage_momentum_whitespace": 1.0,
                },
            },
            "demos": [
                {
                    "lead_id": "lead_scr_01",
                    "verdict": "elevate",
                    "total_score": 9,
                }
            ],
            "train_count": 12,
            "val_accuracy": 0.92,
            "is_active": True,
            "created_at": "2026-11-21T22:05:00Z",
        }
        policy_validator.validate(valid_policy)

        bad_policy = copy.deepcopy(valid_policy)
        bad_policy["target_model"] = "gemini-4-neon"
        with self.assertRaises(ValidationError):
            policy_validator.validate(bad_policy)


class ScreeningRubricsTests(unittest.TestCase):
    def test_three_layer_rubrics_cover_gates_five_skills_abstention_and_calibration(self) -> None:
        spec = json.loads(SCREENING_RUBRICS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(spec["version"], "1.0.0")
        self.assertEqual(len(spec["layers"]), 3)

        by_id = {layer["layer_id"]: layer for layer in spec["layers"]}
        self.assertEqual(
            set(by_id.keys()),
            {"layer_1_code_gates", "layer_2_input_skills", "layer_3_adversarial_calibration"},
        )

        layer1 = by_id["layer_1_code_gates"]
        self.assertEqual(layer1["evaluator"], "deterministic")
        self.assertTrue(layer1["blocking"])
        l1_ids = {r["id"] for r in layer1["rubrics"]}
        self.assertEqual(
            l1_ids,
            {
                "gate_contract",
                "gate_rubric_sum",
                "gate_no_hallucinated_urls",
                "gate_no_sys_leak",
            },
        )

        layer2 = by_id["layer_2_input_skills"]
        self.assertEqual(layer2["evaluator"], "vertex_ai_pointwise")
        self.assertEqual(len(layer2["rubrics"]), 6)
        l2_skills = {r["skill"] for r in layer2["rubrics"]}
        self.assertEqual(
            l2_skills,
            {
                "dossier-identity",
                "dossier-media",
                "dossier-footprint",
                "dossier-audience",
                "dossier-track-record",
            },
        )
        for rubric in layer2["rubrics"]:
            self.assertEqual(rubric["scale"], "0_to_2")
            self.assertEqual(rubric["max_score"], 2)
            self.assertEqual(set(rubric["levels"].keys()), {"0", "1", "2"})
            self.assertIn("{response}", rubric["vertex_prompt_template"])
        self.assertIn("skill_missing_fields_abstention", {r["id"] for r in layer2["rubrics"]})

        layer3 = by_id["layer_3_adversarial_calibration"]
        self.assertEqual(layer3["evaluator"], "vertex_ai_pointwise")
        l3_ids = {r["id"] for r in layer3["rubrics"]}
        self.assertEqual(
            l3_ids,
            {
                "adv_steelman_upside",
                "skep_real_risks_and_gaps",
                "judge_fair_synthesis_and_bands",
            },
        )
        for rubric in layer3["rubrics"]:
            self.assertEqual(rubric["scale"], "0_to_2")
            self.assertEqual(rubric["max_score"], 2)


class SharedInputSkillsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.demo = json.loads(SCREENING_DEMO_PATH.read_text(encoding="utf-8"))
        cls.evaluators = {
            skill_name: _load_skill_evaluator(skill_dir=skill_name, script_name=script_name)
            for skill_name, script_name, _ in EXPECTED_SKILL_SPECS
        }

    def test_all_five_skill_markdowns_and_cli_scripts_exist_and_run(self) -> None:
        nadia_dossier = self.demo["packets"][0]["dossier_snapshot"]
        with tempfile.TemporaryDirectory() as tmp:
            dossier_path = Path(tmp) / "dossier.json"
            dossier_path.write_text(json.dumps(nadia_dossier), encoding="utf-8")

            for skill_name, script_name, expected_key in EXPECTED_SKILL_SPECS:
                skill_md = SHARED_SKILLS_DIR / skill_name / "SKILL.md"
                script_py = SHARED_SKILLS_DIR / skill_name / "scripts" / script_name
                self.assertTrue(skill_md.is_file(), f"Missing {skill_md}")
                self.assertTrue(script_py.is_file(), f"Missing {script_py}")

                md_text = skill_md.read_text(encoding="utf-8")
                self.assertTrue(md_text.startswith("---\n"))
                self.assertIn(f"name: {skill_name}", md_text)
                self.assertIn(expected_key, md_text)

                proc = subprocess.run(
                    [sys.executable, str(script_py), "--dossier", f"@{dossier_path}"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                out = json.loads(proc.stdout)
                self.assertEqual(out["rubric_key"], expected_key)
                self.assertEqual(out["skill"], skill_name)
                self.assertIn(out["score"], (0, 1, 2))
                self.assertEqual(out["max_score"], 2)
                self.assertIsInstance(out["note"], str)
                self.assertIsInstance(out["pros"], list)
                self.assertIsInstance(out["cons"], list)
                self.assertIsInstance(out["missing"], list)

    def test_identity_skill_tiers(self) -> None:
        ev = self.evaluators["dossier-identity"]
        nadia = self.demo["packets"][0]["dossier_snapshot"]
        kieran = self.demo["packets"][1]["dossier_snapshot"]
        velvet = self.demo["packets"][2]["dossier_snapshot"]

        self.assertEqual(ev(nadia)["score"], 2)
        self.assertEqual(ev(kieran)["score"], 1)
        self.assertEqual(ev(velvet)["score"], 0)
        self.assertIn("identity_and_contact.home_city", ev(velvet)["missing"])

    def test_media_skill_tiers_and_long_clip_filter(self) -> None:
        ev = self.evaluators["dossier-media"]
        nadia = self.demo["packets"][0]["dossier_snapshot"]
        kieran = self.demo["packets"][1]["dossier_snapshot"]
        velvet = self.demo["packets"][2]["dossier_snapshot"]

        self.assertEqual(ev(nadia)["score"], 2)
        self.assertEqual(ev(kieran)["score"], 1)
        self.assertEqual(ev(velvet)["score"], 0)

        # >=1hr compilation clip should be rejected as invalid media proof
        long_stream = copy.deepcopy(kieran)
        long_stream["source_and_media_queue"]["media_links"][0]["duration_seconds"] = 5400
        self.assertEqual(ev(long_stream)["score"], 0)

    def test_footprint_skill_concentration_and_regimes(self) -> None:
        ev = self.evaluators["dossier-footprint"]
        nadia = self.demo["packets"][0]["dossier_snapshot"]
        kieran = self.demo["packets"][1]["dossier_snapshot"]

        self.assertEqual(ev(nadia)["score"], 2)
        # Kieran has 91% single-clip concentration -> capped at 1
        res_kieran = ev(kieran)
        self.assertEqual(res_kieran["score"], 1)
        self.assertTrue(
            any("concentration" in c["title"].lower() for c in res_kieran["cons"])
        )

        empty_unknown = {
            "public_footprint": {
                "footprint_regime": "unknown",
                "public_reach": {},
                "top_release_view_share_pct": None,
            },
            "missing_fields": [],
        }
        self.assertEqual(ev(empty_unknown)["score"], 0)

    def test_audience_skill_intent_and_spam_detection(self) -> None:
        ev = self.evaluators["dossier-audience"]
        nadia = self.demo["packets"][0]["dossier_snapshot"]
        velvet = self.demo["packets"][2]["dossier_snapshot"]

        self.assertEqual(ev(nadia)["score"], 2)
        self.assertEqual(ev(velvet)["score"], 0)

        moderate = copy.deepcopy(nadia)
        moderate["comment_forensics"]["notable_commenters"] = []
        self.assertEqual(ev(moderate)["score"], 1)

    def test_track_record_skill_abstention_headliner_ceiling_and_major_label(self) -> None:
        ev = self.evaluators["dossier-track-record"]
        nadia = self.demo["packets"][0]["dossier_snapshot"]
        kieran = self.demo["packets"][1]["dossier_snapshot"]
        velvet = self.demo["packets"][2]["dossier_snapshot"]

        # Nadia has 2 past shows -> 1/2
        self.assertEqual(ev(nadia)["score"], 1)

        # Adding a 3rd past show unlocks 2/2
        three_shows = copy.deepcopy(nadia)
        three_shows["live_history_and_credits"]["show_history"].append(
            {
                "venue": "Union Pool",
                "city": "Brooklyn, NY",
                "date": "2026-06-14",
                "billing_slot": "opener",
                "source_url": "https://unionpool.com/events/2026-06-14",
            }
        )
        self.assertEqual(ev(three_shows)["score"], 2)

        # Kieran has 0 shows in missing_fields -> abstained as unknown (score 1, no invented flaw)
        kieran_res = ev(kieran)
        self.assertEqual(kieran_res["score"], 1)
        self.assertIn("live_history_and_credits.show_history", kieran_res["missing"])
        self.assertTrue(
            any("abstained" in c["title"].lower() for c in kieran_res["cons"])
        )

        # Velvet Static has Columbia Records -> major label dealbreaker (score 0)
        velvet_res = ev(velvet)
        self.assertEqual(velvet_res["score"], 0)
        self.assertTrue(
            any("major-label" in c["title"].lower() for c in velvet_res["cons"])
        )


class ScreeningDemoAndLayer1GatesTests(unittest.TestCase):
    def test_demo_packets_validate_contract_stage2_dossiers_urls_and_exact_skill_scores(
        self,
    ) -> None:
        contract = json.loads(SCREENING_CONTRACT_PATH.read_text(encoding="utf-8"))
        batch_validator = _subschema_validator(contract, "ScreeningBatch")
        demo = json.loads(SCREENING_DEMO_PATH.read_text(encoding="utf-8"))
        batch_validator.validate(demo)

        taste_demo = json.loads(TASTE_BRIEF_DEMO_PATH.read_text(encoding="utf-8"))
        allowed_yt_urls = {
            v["url"]
            for lead in taste_demo["artist_leads"]
            for v in lead["videos"]
        }

        packets = demo["packets"]
        self.assertEqual(len(packets), 3)

        expected_candidates = [
            ("lead_scr_01", "Nadia Sol", "elevate", 9),
            ("lead_scr_02", "Kieran Vale", "watch", 6),
            ("lead_scr_03", "Velvet Static", "pass", 2),
        ]

        evaluators = [
            (expected_key, skill_name, _load_skill_evaluator(skill_name, script_name))
            for skill_name, script_name, expected_key in EXPECTED_SKILL_SPECS
        ]

        for pkt, (exp_id, exp_name, exp_verdict, exp_total) in zip(
            packets, expected_candidates
        ):
            self.assertEqual(pkt["lead_id"], exp_id)
            self.assertEqual(pkt["stage_name"], exp_name)
            self.assertEqual(pkt["screening_model"], "gemini-4-neon")
            self.assertEqual(pkt["judge_decision"]["verdict"], exp_verdict)
            self.assertEqual(pkt["judge_decision"]["total_score"], exp_total)

            # 1. Stage 2 InvestigatorDossier process check passes 100%
            dossier = pkt["dossier_snapshot"]
            stage2_check = evaluate_dossier_process(dossier)
            self.assertTrue(
                stage2_check["passed"],
                f"Stage 2 dossier check failed for {exp_id}: {stage2_check['failures']}",
            )

            # 2. All media_links YouTube watch URLs come from examples/taste_brief_demo.json
            for media in dossier["source_and_media_queue"]["media_links"]:
                self.assertRegex(media["url"], YOUTUBE_WATCH_RE)
                self.assertIn(media["url"], allowed_yt_urls)

            # 3. Layer 1 Gate: Zero hallucinated URLs outside dossier_snapshot
            dossier_urls = set(_collect_urls(dossier))
            downstream_urls = set(
                _collect_urls(
                    {
                        "advocate_case": pkt["advocate_case"],
                        "skeptic_case": pkt["skeptic_case"],
                        "judge_decision": pkt["judge_decision"],
                    }
                )
            )
            self.assertTrue(
                downstream_urls.issubset(dossier_urls),
                f"Hallucinated URLs in {exp_id}: {downstream_urls - dossier_urls}",
            )

            # 4. Layer 1 Gate: Zero system telemetry leak
            serialized_pkt = json.dumps(pkt)
            for forbidden in FORBIDDEN_SYS_KEYS:
                self.assertNotIn(forbidden, serialized_pkt)

            # 5. Layer 1 & 2 Gate: All 5 shared input skills reproduce exact rubric_scores & sum
            rubric_scores = pkt["judge_decision"]["rubric_scores"]
            computed_sum = 0
            for rubric_key, skill_name, ev_fn in evaluators:
                skill_out = ev_fn(dossier)
                self.assertEqual(
                    rubric_scores[rubric_key]["score"],
                    skill_out["score"],
                    f"Mismatch on {exp_id}.{rubric_key}",
                )
                self.assertEqual(rubric_scores[rubric_key]["skill"], skill_name)
                self.assertEqual(
                    rubric_scores[rubric_key]["note"],
                    skill_out["note"],
                    f"Note mismatch on {exp_id}.{rubric_key}",
                )
                computed_sum += skill_out["score"]
            self.assertEqual(computed_sum, exp_total)


if __name__ == "__main__":
    unittest.main()
