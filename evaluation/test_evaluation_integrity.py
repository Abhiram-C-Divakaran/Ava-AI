#!/usr/bin/env python3
"""
evaluation/test_evaluation_integrity.py — Evaluation Integrity & Scientific Rigor Unit Tests.

Verifies:
1. Live mode fails immediately without GROQ_API_KEY.
2. Live mode rejects dummy/mock keys.
3. Live provider failure raises EvaluationGenerationError without offline fallback.
4. Offline mode explicitly records 'offline' generation mode and local provider.
5. Live mode records 'live' generation mode and Groq provider.
6. Paired variants in internal records use identical model and generation mode.
7. Missing review score is strictly rejected with ValueError.
8. Review score < 1 is rejected with ValueError.
9. Review score > 5 is rejected with ValueError.
10. Malformed preferred_response is rejected with ValueError.
11. Duplicate case ID in reviews is rejected with ValueError.
12. Missing case in reviews is rejected with ValueError.
13. Unknown case ID in reviews is rejected with ValueError.
14. Blind dataset contains zero adaptation disclosures.
15. Randomization seed is recorded in metadata.
"""

import os
import sys
import json
import csv
import tempfile
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from evaluation.run_response_eval import (
    validate_groq_api_key_for_live,
    generate_live_groq_response,
    generate_offline_deterministic_response,
    run_response_evaluation,
    EvaluationGenerationError,
)
from evaluation.process_human_reviews import (
    validate_and_parse_score,
    validate_and_parse_preference,
    validate_review_completeness,
    process_reviews,
)


class TestEvaluationIntegrity(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sample_cases = [
            {
                "id": f"test_{i:03d}",
                "category": "programming",
                "prompt": f"Test prompt {i}",
                "user_profile": {"verbosity": "concise"},
                "constraints": {"requires_code": True},
            }
            for i in range(1, 5)
        ]
        self.cases_path = os.path.join(self.temp_dir.name, "test_cases.json")
        with open(self.cases_path, "w", encoding="utf-8") as f:
            json.dump(self.sample_cases, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    # 1. Live mode fails without GROQ_API_KEY
    def test_live_mode_fails_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                validate_groq_api_key_for_live()
            self.assertIn("Live evaluation requires a real GROQ_API_KEY", str(ctx.exception))

    # 2. Live mode rejects dummy keys
    def test_live_mode_rejects_dummy_keys(self):
        for dummy in ["dummy_key_12345", "mock_key_99999", "test_key_00000", "short"]:
            with patch.dict(os.environ, {"GROQ_API_KEY": dummy}):
                with self.assertRaises(RuntimeError) as ctx:
                    validate_groq_api_key_for_live()
                self.assertIn("rejects dummy or invalid GROQ_API_KEY", str(ctx.exception))

    # 3. Live provider failure does not fall back offline
    @patch("evaluation.run_response_eval.call_llm")
    def test_live_provider_failure_does_not_fallback_offline(self, mock_llm):
        mock_llm.side_effect = TimeoutError("Connection timed out to Groq")
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_live_valid_api_key_here"}):
            with self.assertRaises(EvaluationGenerationError) as ctx:
                generate_live_groq_response("Test prompt", "System prompt")
            self.assertIn("Live Groq generation failed", str(ctx.exception))

    # 4. Offline mode explicitly records 'offline'
    def test_offline_mode_records_offline(self):
        out_dir = os.path.join(self.temp_dir.name, "offline_out")
        ret = run_response_evaluation(self.cases_path, mode="offline", seed=100, out_dir=out_dir)
        self.assertEqual(ret, 0)

        meta_path = os.path.join(out_dir, "run_metadata.json")
        self.assertTrue(os.path.exists(meta_path))
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.assertEqual(meta["generation_mode"], "offline")
        self.assertEqual(meta["provider"], "local_deterministic_generator")
        self.assertEqual(meta["model"], "deterministic_engine")

    # 5. Live mode records 'live'
    @patch("evaluation.run_response_eval.call_llm")
    def test_live_mode_records_live(self, mock_llm):
        mock_llm.return_value = "Mocked real Groq LLM response output."
        out_dir = os.path.join(self.temp_dir.name, "live_out")

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_live_valid_key_for_testing_12345"}):
            ret = run_response_evaluation(self.cases_path, mode="live", seed=200, out_dir=out_dir)
            self.assertEqual(ret, 0)

        meta_path = os.path.join(out_dir, "run_metadata.json")
        self.assertTrue(os.path.exists(meta_path))
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.assertEqual(meta["generation_mode"], "live")
        self.assertEqual(meta["provider"], "groq")
        self.assertEqual(meta["model"], "llama-3.3-70b-versatile")

    # 6. Paired variants use same model
    def test_paired_variants_use_same_model(self):
        out_dir = os.path.join(self.temp_dir.name, "offline_out")
        run_response_evaluation(self.cases_path, mode="offline", seed=42, out_dir=out_dir)

        internal_path = os.path.join(out_dir, "response_eval_results_internal.json")
        with open(internal_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        self.assertEqual(len(records), len(self.sample_cases))
        for r in records:
            self.assertEqual(r["generation_mode_A"], r["generation_mode_B"])
            self.assertEqual(r["model_A"], r["model_B"])
            self.assertIn("a_is_adapted", r)

    # 7. Missing review score is rejected
    def test_missing_review_score_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_and_parse_score("", "prog_001", "instruction_adherence_A", 1)
        self.assertIn("Missing score", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_and_parse_score(None, "prog_001", "clarity_A", 2)
        self.assertIn("Missing score", str(ctx.exception))

    # 8. Score < 1 rejected
    def test_score_less_than_one_rejected(self):
        for invalid in [0.0, 0.9, -1.0]:
            with self.assertRaises(ValueError) as ctx:
                validate_and_parse_score(invalid, "prog_001", "usefulness_A", 1)
            self.assertIn("out of bounds", str(ctx.exception))

    # 9. Score > 5 rejected
    def test_score_greater_than_five_rejected(self):
        for invalid in [5.1, 6.0, 10.0]:
            with self.assertRaises(ValueError) as ctx:
                validate_and_parse_score(invalid, "prog_001", "correctness_A", 1)
            self.assertIn("out of bounds", str(ctx.exception))

    # 10. Malformed preferred_response rejected
    def test_malformed_preferred_response_rejected(self):
        for invalid in ["C", "TIES", "X", "1", "", "None", "tie_break"]:
            with self.assertRaises(ValueError) as ctx:
                validate_and_parse_preference(invalid, "prog_001", 1)
            self.assertIn("preferred_response", str(ctx.exception).lower())

        # Valid choices pass
        self.assertEqual(validate_and_parse_preference("A", "prog_001", 1), "A")
        self.assertEqual(validate_and_parse_preference("b", "prog_001", 1), "B")
        self.assertEqual(validate_and_parse_preference("tie", "prog_001", 1), "TIE")
        self.assertEqual(validate_and_parse_preference("T", "prog_001", 1), "TIE")

    # 11. Duplicate case ID rejected
    def test_duplicate_case_id_rejected(self):
        expected_ids = {f"test_{i:03d}" for i in range(1, 61)}
        reviews = [{"case_id": f"test_{i:03d}"} for i in range(1, 60)]
        reviews.append({"case_id": "test_001"})  # Duplicate test_001

        with self.assertRaises(ValueError) as ctx:
            validate_review_completeness(reviews, expected_ids)
        self.assertIn("Duplicate case IDs", str(ctx.exception))

    # 12. Missing case rejected
    def test_missing_case_rejected(self):
        expected_ids = {f"test_{i:03d}" for i in range(1, 61)}
        reviews = [{"case_id": f"test_{i:03d}"} for i in range(1, 55)]  # Missing 6 cases

        with self.assertRaises(ValueError) as ctx:
            validate_review_completeness(reviews, expected_ids)
        self.assertIn("Review set is incomplete", str(ctx.exception))

    # 13. Unknown case rejected
    def test_unknown_case_rejected(self):
        expected_ids = {f"test_{i:03d}" for i in range(1, 61)}
        reviews = [{"case_id": f"test_{i:03d}"} for i in range(1, 60)]
        reviews.append({"case_id": "unknown_999"})

        with self.assertRaises(ValueError) as ctx:
            validate_review_completeness(reviews, expected_ids)
        self.assertIn("Unknown case IDs", str(ctx.exception))

    # 14. Blind dataset contains no a_is_adapted field
    def test_blind_dataset_contains_no_adaptation_field(self):
        out_dir = os.path.join(self.temp_dir.name, "offline_out")
        run_response_evaluation(self.cases_path, mode="offline", seed=42, out_dir=out_dir)

        blind_json = os.path.join(out_dir, "human_review_dataset.json")
        with open(blind_json, "r", encoding="utf-8") as f:
            items = json.load(f)

        for item in items:
            self.assertNotIn("a_is_adapted", item)
            self.assertNotIn("strategy_selected", item)
            self.assertNotIn("adaptation_used", item)
            self.assertNotIn("policy_adapted", item)
            self.assertNotIn("generation_mode", item)

        csv_file = os.path.join(out_dir, "human_review_template.csv")
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
            self.assertNotIn("a_is_adapted", headers)
            self.assertNotIn("strategy_selected", headers)
            self.assertNotIn("adaptation_used", headers)

    # 15. Randomization seed is recorded
    def test_randomization_seed_recorded(self):
        out_dir = os.path.join(self.temp_dir.name, "seed_test_out")
        run_response_evaluation(self.cases_path, mode="offline", seed=98765, out_dir=out_dir)

        meta_path = os.path.join(out_dir, "run_metadata.json")
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.assertEqual(meta["randomization_seed"], 98765)
        self.assertIn("evaluation_id", meta)
        self.assertIn("git_commit", meta)


if __name__ == "__main__":
    unittest.main()
