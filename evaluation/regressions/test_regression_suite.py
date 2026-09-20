#!/usr/bin/env python3
"""
evaluation/regressions/test_regression_suite.py — Post-Release Regression Test Suite.

Ensures behavioral, security, and edge-case regressions are systematically captured and verified.
Pattern: Bug Report -> Regression Test -> Verified Invariant.
"""

import os
import sys
import unittest
import tempfile
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
import adaptation
import memory
from main import assemble_chat_prompt_context


class PostReleaseRegressionSuite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = os.path.join(self.temp_dir.name, "regression.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.test_db
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        self.temp_dir.cleanup()

    def test_regression_001_punctuation_in_explicit_overrides(self):
        """
        Regression: Trailing punctuation or sentence structures in override prompts
        must correctly trigger explicit prompt override over background learned profile.
        """
        user_id = f"reg_user_punc_{uuid.uuid4().hex[:6]}"
        adaptation.set_manual_preference(user_id, "verbosity", "concise", confidence=0.85)

        # Contradictory prompts with diverse punctuation
        test_queries = [
            "Explain Docker networking in detail!",
            "Can you give me a comprehensive overview???",
            "Please provide a thorough, in-depth explanation...",
        ]

        for q in test_queries:
            sys_prompt, meta = assemble_chat_prompt_context(user_id=user_id, message=q)
            self.assertNotIn("Verbosity: Prefer concise", sys_prompt, f"Failed for query: {q}")

    def test_regression_002_empty_or_none_session_id_handling(self):
        """
        Regression: None, empty string, or whitespace session_id must not raise exceptions
        and must not bleed into session history.
        """
        user_id = f"reg_user_sess_{uuid.uuid4().hex[:6]}"
        db.set_user_memory(user_id, "• User prefers Python.", message_count_at_update=5)

        for invalid_sess in [None, "", "   "]:
            sys_prompt, meta = assemble_chat_prompt_context(
                user_id=user_id,
                message="Hello Ava",
                session_id=invalid_sess,
            )
            self.assertIn("What you remember about this user from past conversations:", sys_prompt)
            self.assertIn("User prefers Python", sys_prompt)

    def test_regression_003_adaptation_enabled_bypass_isolation(self):
        """
        Regression: Internal adaptation_enabled=False switch must completely zero out
        adaptation context and strategy, while preserving persistent user factual memory.
        """
        user_id = f"reg_user_bypass_{uuid.uuid4().hex[:6]}"
        db.set_user_memory(user_id, "• Database is PostgreSQL 16.", message_count_at_update=5)
        adaptation.set_manual_preference(user_id, "verbosity", "concise", confidence=0.90)

        # Baseline: adaptation disabled
        sys_prompt_off, meta_off = assemble_chat_prompt_context(
            user_id=user_id,
            message="What database am I using?",
            adaptation_enabled=False,
        )
        self.assertFalse(meta_off.get("adaptation_used"))
        self.assertFalse(meta_off.get("adaptation_enabled"))
        self.assertEqual(meta_off.get("policy"), {})
        self.assertIsNone(meta_off.get("strategy"))
        self.assertNotIn("--- User response preferences ---", sys_prompt_off)
        # But memory MUST be preserved!
        self.assertIn("Database is PostgreSQL 16", sys_prompt_off)

        # Adapted: adaptation enabled
        sys_prompt_on, meta_on = assemble_chat_prompt_context(
            user_id=user_id,
            message="What database am I using?",
            adaptation_enabled=True,
        )
        self.assertTrue(meta_on.get("adaptation_enabled"))
        self.assertIn("--- User response preferences ---", sys_prompt_on)
        self.assertIn("Database is PostgreSQL 16", sys_prompt_on)

    def test_regression_004_unicode_and_symbols_in_factual_memory(self):
        """
        Regression: Special unicode symbols (e.g. arrows ->, Greek symbols λ, emojis, quotes)
        in factual memory must not cause format string errors or SQL injection.
        """
        user_id = f"reg_user_unicode_{uuid.uuid4().hex[:6]}"
        complex_mem = "• Lambda function λ -> μs latency; uses UTF-8: 日本語, é, 🚀, and single 'quotes' & double \"quotes\"."
        db.set_user_memory(user_id, complex_mem, message_count_at_update=5)

        sys_prompt, meta = assemble_chat_prompt_context(user_id=user_id, message="Hello")
        self.assertIn("λ -> μs latency", sys_prompt)
        self.assertIn("日本語", sys_prompt)

    def test_regression_005_invalid_strategy_feedback_handling(self):
        """
        Regression: Feedback submitted with invalid or unknown strategy must be safely filtered
        by the adaptation engine and never appear in preferred strategies, policy, or prompt context.
        """
        user_id = f"reg_user_strat_{uuid.uuid4().hex[:6]}"
        db.record_strategy_feedback(user_id, "invalid_nonexistent_strategy", helpful=True)
        
        preferred = adaptation.get_preferred_strategies(user_id)
        self.assertNotIn("invalid_nonexistent_strategy", preferred)

        policy = adaptation.build_behavior_policy(user_id)
        self.assertNotEqual(policy.get("preferred_strategy"), "invalid_nonexistent_strategy")

        context = adaptation.get_strategy_context(user_id)
        self.assertNotIn("invalid_nonexistent_strategy", context)


if __name__ == "__main__":
    unittest.main()
