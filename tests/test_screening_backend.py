"""Unit and integration tests for Simon's Stage 3 Screening Backend (`simon/screening.py`)."""

from __future__ import annotations

from contextlib import redirect_stdout
from http import HTTPStatus
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from simon.__main__ import main as simon_cli_main
from simon.db_tools import (
    ALLOWED_AGENT_COLLECTIONS,
    REPORT_FORBIDDEN_KEYS,
    get_agent_document,
    list_agent_documents,
    save_agent_document,
    validate_collection_payload,
)
from simon.screening import (
    RUBRIC_ORDER,
    build_builtin_demo_dossiers,
    compile_judging_model,
    evaluate_with_taste_engine,
    list_judging_models,
    list_screening_deck,
    list_screening_evals,
    list_taste_scores,
    run_screening_evals,
    run_screening_for_dossier,
    save_screening_label,
    score_dossier_inputs,
)
from simon.store import SimonStore
from simon.web import dispatch_http_request


class TestScreeningDBCollections(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = SimonStore(Path(self._tmp.name) / "screening_db.sqlite")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_allowed_collections_and_payload_validation(self) -> None:
        for col in ("screening_packets", "screening_labels", "judging_models", "taste_scores"):
            self.assertIn(col, ALLOWED_AGENT_COLLECTIONS)

        # 1. screening_packets validation + default doc_id + telemetry sanitization
        bad_pkt_errs, _ = validate_collection_payload(
            "screening_packets",
            {"lead_id": "lead_x", "stage_name": "Artist X", "judge_decision": {"verdict": "maybe"}},
        )
        self.assertTrue(bad_pkt_errs)

        dirty_packet = {
            "lead_id": "lead_mira",
            "stage_name": "Mira Sol",
            "judge_decision": {"verdict": "elevate", "confidence": 0.91},
            "interaction_id": "v1_secret_trace_123",
            "environment_id": "env_secret_456",
            "nested": {"metadata": {"internal": True}, "trace_id": "tr_99", "keep": "ok"},
        }
        errs, suggested_id = validate_collection_payload("screening_packets", dirty_packet)
        self.assertEqual(errs, [])
        self.assertEqual(suggested_id, "scr_lead_mira")

        saved_pkt = save_agent_document(self.store, "screening_packets", dirty_packet)
        self.assertEqual(saved_pkt["doc_id"], "scr_lead_mira")
        stored_doc = get_agent_document(self.store, "screening_packets", "scr_lead_mira")
        self.assertIsNotNone(stored_doc)
        assert stored_doc is not None
        for forbidden in REPORT_FORBIDDEN_KEYS:
            self.assertNotIn(forbidden, stored_doc)
            self.assertNotIn(forbidden, stored_doc.get("nested", {}))
        self.assertEqual(stored_doc["nested"]["keep"], "ok")

        # 2. screening_labels validation + generated lbl_<uuid8>
        bad_lbl_errs, _ = validate_collection_payload(
            "screening_labels", {"lead_id": "lead_mira", "human_verdict": "invalid"}
        )
        self.assertTrue(bad_lbl_errs)

        ok_lbl_errs, gen_lbl_id = validate_collection_payload(
            "screening_labels", {"lead_id": "lead_mira", "human_verdict": "watch"}
        )
        self.assertEqual(ok_lbl_errs, [])
        assert gen_lbl_id is not None
        self.assertTrue(gen_lbl_id.startswith("lbl_"))
        self.assertEqual(len(gen_lbl_id), 12)

        # 3. judging_models validation + policy_id doc_id
        bad_pol_errs, _ = validate_collection_payload("judging_models", {"policy_id": "policy_v1"})
        self.assertTrue(bad_pol_errs)

        ok_pol_errs, pol_doc_id = validate_collection_payload(
            "judging_models", {"policy_id": "policy_v1", "version": 1}
        )
        self.assertEqual(ok_pol_errs, [])
        self.assertEqual(pol_doc_id, "policy_v1")


class TestScreeningOrchestratorAndTraining(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = SimonStore(Path(self._tmp.name) / "screening_orch.sqlite")
        self.demos = build_builtin_demo_dossiers()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_five_rubric_scorer_and_dynamic_skill_loader(self) -> None:
        mira, soraia, devon = self.demos
        s_mira = score_dossier_inputs(mira)
        s_soraia = score_dossier_inputs(soraia)
        s_devon = score_dossier_inputs(devon)

        self.assertEqual(tuple(s_mira["rubric_scores"].keys()), RUBRIC_ORDER)
        self.assertGreaterEqual(s_mira["total_score"], 8)
        self.assertTrue(4 <= s_soraia["total_score"] <= 7)
        self.assertLessEqual(s_devon["total_score"], 3)
        self.assertTrue(s_mira["pros"])
        self.assertTrue(s_devon["cons"])
        self.assertIn("source_and_media_queue.verified_attribution", s_devon["missing_evidence_flags"])

        # Dynamic skill script override check
        fake_skills_root = Path(self._tmp.name) / "skills"
        script_dir = fake_skills_root / "dossier-identity-reachability" / "scripts"
        script_dir.mkdir(parents=True)
        (script_dir / "score_identity.py").write_text(
            "def score(dossier):\n"
            "    return {'rubric_id': 'identity_reachability', 'score': 2, "
            "'pros': ['Dynamic skill verified booking contact'], 'rationale': 'Dynamic skill check'}\n",
            encoding="utf-8",
        )
        with patch("simon.screening.SHARED_SKILLS_ROOT", fake_skills_root):
            dyn_res = score_dossier_inputs(devon)
            self.assertEqual(dyn_res["rubric_scores"]["identity_reachability"], 2)
            self.assertIn("dossier-identity-reachability", dyn_res["dynamic_skills_loaded"])
            self.assertIn("Dynamic skill verified booking contact", dyn_res["pros"])

    def test_offline_and_mocked_live_parallel_advocate_skeptic_judge(self) -> None:
        mira = self.demos[0]
        offline_pkt = run_screening_for_dossier(self.store, mira, live=False)
        self.assertEqual(offline_pkt["mode"], "deterministic_baseline")
        self.assertEqual(offline_pkt["judge_decision"]["verdict"], "elevate")

        # Verify human-first agent_reports entry was published with zero telemetry
        reports = list_agent_documents(self.store, "agent_reports", limit=10)
        self.assertTrue(any(r.get("stage") == "screening" for r in reports))

        # Mocked live mode: verify parallel Advocate + Skeptic execution AND fallback to gemini-4-neon
        barrier = threading.Barrier(2, timeout=3.0)
        call_log = []
        lock = threading.Lock()

        class FakeGemini:
            def interact(self, body, include_trace=False, poll_timeout_s=180):
                agent_name = body.get("agent")
                model_name = body.get("model")
                prompt_text = body["input"][0]["text"]
                with lock:
                    call_log.append((agent_name, model_name))

                if agent_name == "staging-simon-screen-advocate":
                    barrier.wait()
                    return {
                        "interaction_id": "int_adv_01",
                        "report": json.dumps(
                            {
                                "thesis": "Mira Sol is ready for an immediate paid First Listen NYC slot.",
                                "strongest_points": ["2 live clips verified", "Producer Jonah Reyes cosign"],
                                "cited_evidence": ["Sofar NYC + Baby's All Right"],
                                "upside_bet": "Pre-label NYC soul breakout.",
                                "interaction_id": "should_be_stripped",
                            }
                        ),
                    }
                if agent_name == "staging-simon-screen-skeptic":
                    barrier.wait()
                    # Simulate custom agent not deployed yet -> triggers gemini-4-neon fallback!
                    raise RuntimeError("Gemini returned HTTP 404: agent not found")

                if model_name == "gemini-4-neon" and "Screen Skeptic" in prompt_text:
                    return {
                        "interaction_id": "int_skp_neon_fallback",
                        "report": json.dumps(
                            {
                                "counter_thesis": "Confirm quartet input list for 15-minute changeover.",
                                "risk_points": ["No booking agent listed yet"],
                                "missing_proof": ["stage_plot_inputs"],
                                "verification_needed": "Confirm stage plot with North Star Artists.",
                            }
                        ),
                    }

                if agent_name == "staging-simon-screening-judge":
                    # Confirm Judge received both Advocate and Skeptic outputs
                    assert "Mira Sol is ready for an immediate paid First Listen NYC slot." in prompt_text
                    assert "Confirm quartet input list for 15-minute changeover." in prompt_text
                    return {
                        "interaction_id": "int_judge_01",
                        "report": json.dumps(
                            {
                                "verdict": "elevate",
                                "confidence": 0.93,
                                "rubric_scores": {
                                    "identity_reachability": 2,
                                    "live_vocal_proof": 2,
                                    "early_window_depth": 2,
                                    "listener_pull_cosigns": 2,
                                    "stage_momentum_whitespace": 2,
                                },
                                "headline": "Elevate Mira Sol — unanimous live vocal & NYC club momentum.",
                                "rationale": "Advocate proof outweighs minor changeover logistics.",
                                "decisive_factors": ["2 verified live clips", "Unsigned NYC club draw"],
                                "next_action": "Send $250 First Listen NYC callback offer to mgmt.",
                                "metadata": {"raw": "must_be_stripped"},
                            }
                        ),
                    }
                raise AssertionError(f"Unexpected call: agent={agent_name}, model={model_name}")

        live_pkt = run_screening_for_dossier(
            self.store,
            mira,
            live=True,
            prefix="staging-",
            gemini=FakeGemini(),  # type: ignore[arg-type]
        )
        self.assertEqual(live_pkt["mode"], "live")
        self.assertEqual(live_pkt["judge_decision"]["verdict"], "elevate")
        self.assertEqual(live_pkt["judge_decision"]["confidence"], 0.93)
        self.assertEqual(live_pkt["total_score"], 10)
        for forbidden in REPORT_FORBIDDEN_KEYS:
            self.assertNotIn(forbidden, json.dumps(live_pkt))

        # Verify Advocate + Skeptic ran first, Skeptic fell back to gemini-4-neon, then Judge ran
        self.assertIn(("staging-simon-screen-advocate", None), call_log[:3])
        self.assertIn(("staging-simon-screen-skeptic", None), call_log[:3])
        self.assertIn((None, "gemini-4-neon"), call_log)
        self.assertEqual(call_log[-1], ("staging-simon-screening-judge", None))

    def test_deck_labels_judging_compiler_and_three_layer_evals(self) -> None:
        # 1. Deck loader seeds 3 demo packets when DB is empty
        deck = list_screening_deck(self.store)
        self.assertEqual(deck["total"], 3)
        self.assertEqual(deck["elevate_count"], 1)
        self.assertEqual(deck["watch_count"], 1)
        self.assertEqual(deck["pass_count"], 1)
        self.assertEqual(deck["human_labeled_count"], 0)

        # 2. Bootstrap compile with <3 human labels -> policy_v1
        p1 = compile_judging_model(self.store)
        self.assertEqual(p1["policy_id"], "policy_v1")
        self.assertEqual(p1["target_model"], "gemini-decision-1")
        self.assertTrue(p1["is_active"])
        self.assertGreaterEqual(p1["train_count"], 3)

        # 3. Record human agreement + human override (2x weight)
        lbl_agree = save_screening_label(
            self.store,
            {
                "lead_id": "lead_scr_01",
                "human_verdict": "elevate",
                "reason": "Mahogany + BBC live vocal phrasing and Mercury Lounge bill are undeniable.",
            },
        )
        self.assertTrue(lbl_agree["agreed_with_model"])
        self.assertEqual(lbl_agree["training_features"]["total_score"], 9)

        lbl_override = save_screening_label(
            self.store,
            {
                "lead_id": "lead_scr_02",
                "human_verdict": "elevate",
                "reason": "Elevate acoustic R&B vocalists early when comment release requests exceed 4.",
            },
        )
        self.assertFalse(lbl_override["agreed_with_model"])

        refreshed_deck = list_screening_deck(self.store)
        self.assertEqual(refreshed_deck["human_labeled_count"], 2)
        kieran_card = next(p for p in refreshed_deck["packets"] if p["lead_id"] == "lead_scr_02")
        self.assertEqual(kieran_card["human_review"]["human_verdict"], "elevate")
        self.assertFalse(kieran_card["human_review"]["agreed_with_model"])

        # 4. Recompile -> policy_v2 with override reason embedded in questions_config
        p2 = compile_judging_model(self.store)
        self.assertEqual(p2["policy_id"], "policy_v2")
        self.assertEqual(p2["version"], 2)
        self.assertEqual(p2["override_count"], 1)
        self.assertTrue(p2["is_active"])
        self.assertIn(
            "comment release requests exceed 4",
            p2["questions_config"]["screening_verdict"]["criteria"]["elevate"],
        )

        # Verify v1 was deactivated
        models = list_judging_models(self.store)
        by_id = {m["policy_id"]: m for m in models}
        self.assertFalse(by_id["policy_v1"]["is_active"])
        self.assertTrue(by_id["policy_v2"]["is_active"])

        # Validate questions_config against google.genai.decisions.CreateDecisionRequest if installed
        q_cfg = p2["questions_config"]
        self.assertEqual(q_cfg["live_signable"]["type"], "noul")
        self.assertEqual(q_cfg["composite_fit"]["type"], "score")
        self.assertEqual(len(q_cfg["composite_fit"]["criteria"]), 5)
        self.assertEqual(q_cfg["taste_verdict"]["type"], "choice")
        self.assertEqual(q_cfg["sufficient_live_evidence"]["type"], "noul")
        self.assertEqual(q_cfg["screening_verdict"]["type"], "choice")
        for r_key in RUBRIC_ORDER:
            self.assertEqual(q_cfg[r_key]["type"], "score")
            self.assertEqual(len(q_cfg[r_key]["criteria"]), 3)

        try:
            from google.genai import decisions

            req_obj = decisions.CreateDecisionRequest(
                model="models/gemini-decision-1",
                input="Sample artist dossier text",
                questions=q_cfg,
            )
            self.assertGreaterEqual(len(req_obj.questions), 8)
        except ImportError:
            pass

        # 5. Taste Engine (`gemini-decision-1` · 0 output tokens) offline + mocked live wire check
        offline_ts = evaluate_with_taste_engine(self.store, "lead_scr_01", live=False)
        self.assertEqual(offline_ts["taste_verdict"], "elevate")
        self.assertEqual(offline_ts["policy_id"], "policy_v2")
        self.assertEqual(offline_ts["usage"]["output_tokens"], 0)
        self.assertGreater(offline_ts["probabilities"]["elevate"], 0.6)

        captured_req = {}

        def _fake_decisions_post(body):
            captured_req.update(body)
            return {
                "answers": {
                    "live_signable": {"type": "noul", "noul": 0.94, "confidence": 0.94},
                    "composite_fit": {
                        "type": "score",
                        "score": 3.76,
                        "confidence": 0.81,
                        "probabilities": {"0": 0.0, "1": 0.01, "2": 0.03, "3": 0.15, "4": 0.81},
                    },
                    "taste_verdict": {
                        "type": "choice",
                        "choice": "elevate",
                        "confidence": 0.92,
                        "probabilities": {"elevate": 0.92, "watch": 0.07, "pass": 0.01},
                    },
                },
                "usage": {"total_input_tokens": 842, "total_output_tokens": 0},
            }

        live_ts = evaluate_with_taste_engine(
            self.store, "lead_scr_01", live=True, http_post=_fake_decisions_post
        )
        self.assertEqual(captured_req["model"], "gemini-decision-1")
        self.assertIn("live_signable", captured_req["questions"])
        self.assertIn("composite_fit", captured_req["questions"])
        self.assertIn("taste_verdict", captured_req["questions"])
        self.assertEqual(live_ts["mode"], "live_gemini_decision_1")
        self.assertEqual(live_ts["taste_verdict"], "elevate")
        self.assertAlmostEqual(live_ts["probabilities"]["elevate"], 0.92)
        self.assertEqual(live_ts["usage"]["output_tokens"], 0)
        self.assertEqual(len(list_taste_scores(self.store, lead_id="lead_scr_01")), 1)

        deck_with_ts = list_screening_deck(self.store)
        nadia_card = next(p for p in deck_with_ts["packets"] if p["lead_id"] == "lead_scr_01")
        self.assertEqual(nadia_card["latest_taste_score"]["taste_verdict"], "elevate")

        # 5. Run 3-layer Stage 3 screening evals
        eval_report = run_screening_evals(self.store, trigger="unittest")
        self.assertEqual(eval_report["stage"], "stage_3_screening")
        self.assertTrue(eval_report["passed_gates"])
        self.assertGreaterEqual(eval_report["overall_score"], 0.85)
        layers_present = {d["layer"] for d in eval_report["dimensions"]}
        self.assertEqual(layers_present, {"layer_1_gates", "layer_2_process", "layer_3_quality"})

        listed_evals = list_screening_evals(self.store)
        self.assertEqual(listed_evals["count"], 1)


class TestScreeningHTTPRoutesAndCLI(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "screening_http.sqlite"
        self.store = SimonStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_http_routes_end_to_end(self) -> None:
        # 1. GET /screen renders HTML (fallback when screening_ui not merged yet)
        st, ctype, body = dispatch_http_request(self.store, "GET", "/screen")
        self.assertEqual(st, HTTPStatus.OK)
        self.assertIn("text/html", ctype)
        self.assertIn("Screening Deck", body.decode("utf-8"))

        # 2. GET /api/screening/packets seeds and returns deck
        st, _, body = dispatch_http_request(self.store, "GET", "/api/screening/packets")
        self.assertEqual(st, HTTPStatus.OK)
        deck = json.loads(body.decode("utf-8"))
        self.assertEqual(deck["total"], 3)

        # 3. POST /api/screening/run on a single lead_id
        st, _, body = dispatch_http_request(
            self.store,
            "POST",
            "/api/screening/run",
            json.dumps({"lead_id": "lead_demo_mira_sol", "live": False}).encode("utf-8"),
        )
        self.assertEqual(st, HTTPStatus.OK)
        run_res = json.loads(body.decode("utf-8"))
        self.assertTrue(run_res["ok"])
        self.assertEqual(run_res["packet"]["lead_id"], "lead_demo_mira_sol")

        # 4. POST /api/screening/labels & GET /api/screening/labels
        st_bad, _, _ = dispatch_http_request(
            self.store,
            "POST",
            "/api/screening/labels",
            json.dumps({"lead_id": "lead_demo_mira_sol", "human_verdict": "nope"}).encode("utf-8"),
        )
        self.assertEqual(st_bad, HTTPStatus.UNPROCESSABLE_ENTITY)

        st_lbl, _, body = dispatch_http_request(
            self.store,
            "POST",
            "/api/screening/labels",
            json.dumps(
                {
                    "lead_id": "lead_demo_devon_k",
                    "human_verdict": "watch",
                    "reason": "Raw vocal timbre worth watching once a clean clip drops.",
                }
            ).encode("utf-8"),
        )
        self.assertEqual(st_lbl, HTTPStatus.CREATED)
        lbl_res = json.loads(body.decode("utf-8"))
        self.assertFalse(lbl_res["agreed_with_model"])

        st_get_lbls, _, body = dispatch_http_request(self.store, "GET", "/api/screening/labels")
        self.assertEqual(st_get_lbls, HTTPStatus.OK)
        self.assertEqual(json.loads(body.decode("utf-8"))["count"], 1)

        # 5. POST /api/screening/train & GET /api/screening/models
        st_train, _, body = dispatch_http_request(self.store, "POST", "/api/screening/train", b"{}")
        self.assertEqual(st_train, HTTPStatus.OK)
        train_res = json.loads(body.decode("utf-8"))
        self.assertEqual(train_res["policy_id"], "policy_v1")

        st_models, _, body = dispatch_http_request(self.store, "GET", "/api/screening/models")
        self.assertEqual(st_models, HTTPStatus.OK)
        models_res = json.loads(body.decode("utf-8"))
        self.assertEqual(models_res["count"], 1)
        self.assertEqual(models_res["active_model"]["policy_id"], "policy_v1")

        # 5b. POST /api/screening/taste-score & GET /api/screening/taste-scores
        st_ts, _, body = dispatch_http_request(
            self.store,
            "POST",
            "/api/screening/taste-score",
            json.dumps({"lead_id": "lead_scr_01", "live": False}).encode("utf-8"),
        )
        self.assertEqual(st_ts, HTTPStatus.OK)
        ts_res = json.loads(body.decode("utf-8"))
        self.assertTrue(ts_res["ok"])
        self.assertEqual(ts_res["taste_verdict"], "elevate")
        self.assertEqual(ts_res["usage"]["output_tokens"], 0)

        st_get_ts, _, body = dispatch_http_request(self.store, "GET", "/api/screening/taste-scores")
        self.assertEqual(st_get_ts, HTTPStatus.OK)
        self.assertEqual(json.loads(body.decode("utf-8"))["count"], 1)

        # 6. POST /api/screening/evals/run & GET /api/screening/evals
        st_eval, _, body = dispatch_http_request(self.store, "POST", "/api/screening/evals/run", b"{}")
        self.assertEqual(st_eval, HTTPStatus.OK)
        eval_res = json.loads(body.decode("utf-8"))
        self.assertTrue(eval_res["passed_gates"])

        st_get_evals, _, body = dispatch_http_request(self.store, "GET", "/api/screening/evals")
        self.assertEqual(st_get_evals, HTTPStatus.OK)
        self.assertEqual(json.loads(body.decode("utf-8"))["count"], 1)

    def test_cli_screen_subcommand(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            simon_cli_main(["screen", "--train", "--eval", "--db", str(self.db_path)])
        cli_out = json.loads(buf.getvalue())
        self.assertTrue(cli_out["ok"])
        self.assertEqual(cli_out["deck"]["total"], 3)
        self.assertEqual(cli_out["policy"]["policy_id"], "policy_v1")
        self.assertTrue(cli_out["eval_run"]["passed_gates"])


if __name__ == "__main__":
    unittest.main()
