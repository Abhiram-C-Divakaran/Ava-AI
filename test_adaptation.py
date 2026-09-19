"""
test_adaptation.py — Comprehensive Test Suite for Phase 2.5: Behavioral Adaptation Engine Hardening.

Required Test Cases (21 tests):
1.  Concise preference learning
2.  Detailed preference learning
3.  Code preference learning
4.  Step-by-step preference learning
5.  Examples preference learning
6.  Technical depth learning
7.  Tone learning
8.  Persistence across sessions
9.  User isolation (profiles and factual memory)
10. Adaptation reset semantics (preserves account, sessions, messages, memory, feedback)
11. Current-request override priority
12. Strategy tracking (successes / failures)
13. Strategy minimum-evidence rule (>= 3 evidence threshold)
14. Conflicting preference updates (gradual decay, no instant oscillation)
15. Invalid preference value rejection (HTTP 400)
16. Invalid confidence value rejection (HTTP 400)
17. Malformed stored profile recovery
18. Prompt contains user memory exactly once (no duplicate injection)
19. Prompt contains adaptation exactly once
20. Session isolation (no cross-session conversation bleed)
21. Feedback conservative attribution (no false positive / false negative inversion)

Phase 3 (Tests 22-37):
22. Three positive strategy signals can establish preferred strategy
23. One positive signal cannot establish preferred strategy
24. Repeated negative feedback suppresses previously successful strategy
25. Preferred strategy appears in behavior policy
26. Preferred strategy affects generated prompt
27. Current request overrides preferred strategy
28. Programming request selects appropriate code strategy
29. Conceptual request does not blindly use code strategy
30. Strategy conflicts resolve deterministically
31. Older evidence decays gradually
32. Recent explicit preference overrides stale strategy
33. Adaptation failure does not break prompt generation
34. Unknown strategy is ignored
35. Strategy metrics are correctly calculated
36. User A's strategy never affects User B
37. Behavioral integration test (end-to-end mocked closed loop)
"""

import os
import sys
import unittest
import uuid
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Reconfigure stdout for utf-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
import database as db
import adaptation
import memory
from main import app, assemble_chat_prompt_context


class TestBehavioralAdaptationHardened(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(app)

    # 1. Concise preference learning
    def test_01_concise_preference(self):
        """Test 1 — Concise preference shifts verbosity to concise and increases confidence."""
        user_id = f"test_concise_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        init_profile = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(init_profile["verbosity"]["value"], "balanced")
        self.assertEqual(init_profile["verbosity"]["confidence"], 0.50)

        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Please keep your answers short and concise.",
            agent_response="Sure thing! Keeping it brief from now on.",
        )

        updated_profile = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(updated_profile["verbosity"]["value"], "concise")
        self.assertGreater(updated_profile["verbosity"]["confidence"], 0.50)
        self.assertLessEqual(updated_profile["verbosity"]["confidence"], 1.0)

    # 2. Detailed preference learning
    def test_02_detailed_preference(self):
        """Test 2 — Detailed preference shifts verbosity toward detailed."""
        user_id = f"test_detailed_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Explain this in much more detail.",
            agent_response="Here is an in-depth breakdown of the system architecture...",
        )

        profile = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(profile["verbosity"]["value"], "detailed")
        self.assertGreater(profile["verbosity"]["confidence"], 0.50)

    # 3. Code preference learning
    def test_03_code_preference(self):
        """Test 3 — Code preference sets code_examples=True with higher confidence."""
        user_id = f"test_code_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        adaptation.observe_interaction(
            user_id=user_id,
            user_message="I prefer Python code examples when possible.",
            agent_response="```python\ndef example():\n    return True\n```",
        )

        profile = adaptation.get_adaptation_profile(user_id)
        self.assertTrue(profile["code_examples"]["value"])
        self.assertGreater(profile["code_examples"]["confidence"], 0.50)

    # 4. Step-by-step preference learning
    def test_04_step_by_step_preference(self):
        """Test 4 — Step-by-step preference sets step_by_step=True."""
        user_id = f"test_step_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Please explain things step by step.",
            agent_response="1. First step\n2. Second step\n3. Third step",
        )

        profile = adaptation.get_adaptation_profile(user_id)
        self.assertTrue(profile["step_by_step"]["value"])
        self.assertGreater(profile["step_by_step"]["confidence"], 0.50)

    # 5. Examples preference learning
    def test_05_examples_preference_learning(self):
        """Test 5 — Complete examples dimension learning (positive and negative signals)."""
        user_id = f"test_ex_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # Explicit positive examples request
        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Give me an example, show me an example with practical examples.",
            agent_response="Here is a concrete example for your scenario...",
        )
        prof_pos = adaptation.get_adaptation_profile(user_id)
        self.assertTrue(prof_pos["examples"]["value"])
        self.assertGreater(prof_pos["examples"]["confidence"], 0.50)

        # Context generation includes examples when confidence meets threshold
        ctx_pos = adaptation.get_adaptation_context(user_id)
        self.assertIn("Include practical examples when useful", ctx_pos)

        # Explicit negative examples request shifts to False
        user_id_neg = f"test_no_ex_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id_neg)
        adaptation.observe_interaction(
            user_id=user_id_neg,
            user_message="No examples, skip examples, just explain the concept.",
            agent_response="Explaining purely conceptually without examples.",
        )
        prof_neg = adaptation.get_adaptation_profile(user_id_neg)
        self.assertFalse(prof_neg["examples"]["value"])
        self.assertGreater(prof_neg["examples"]["confidence"], 0.50)
        ctx_neg = adaptation.get_adaptation_context(user_id_neg)
        self.assertIn("Avoid unnecessary examples unless explicitly requested", ctx_neg)

    # 6. Technical depth learning
    def test_06_technical_depth_learning(self):
        """Test 6 — Technical depth learning (advanced vs beginner)."""
        user_id = f"test_depth_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # Advanced technical depth
        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Skip the basics, give me deep technical details and architecture.",
            agent_response="At the kernel level, memory pages are mapped using...",
        )
        prof = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof["technical_depth"]["value"], "advanced")
        self.assertGreater(prof["technical_depth"]["confidence"], 0.50)

        # Beginner technical depth
        user_b = f"test_beg_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_b)
        adaptation.observe_interaction(
            user_b,
            "Explain like I'm 5, in plain English for beginners.",
            "Imagine a computer is like a giant library...",
        )
        prof_b = adaptation.get_adaptation_profile(user_b)
        self.assertEqual(prof_b["technical_depth"]["value"], "beginner")
        self.assertGreater(prof_b["technical_depth"]["confidence"], 0.50)

    # 7. Tone learning
    def test_07_tone_learning(self):
        """Test 7 — Tone preference learning (direct, formal, friendly)."""
        user_id = f"test_tone_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Be direct and cut to the chase with no fluff.",
            agent_response="Direct answer: Use Python 3.12.",
        )
        prof = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof["tone"]["value"], "direct")
        self.assertGreater(prof["tone"]["confidence"], 0.50)

    # 8. Persistence
    def test_08_persistence(self):
        """Test 8 — Behavioral adaptation persists across sessions in SQLite."""
        user_id = f"test_persist_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Always keep your answers concise.",
            agent_response="Understood.",
        )

        # Simulate new session re-fetch
        persisted_profile = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(persisted_profile["verbosity"]["value"], "concise")
        self.assertGreater(persisted_profile["verbosity"]["confidence"], 0.50)

        context = adaptation.get_adaptation_context(user_id)
        self.assertIn("concise", context.lower())

    # 9. User isolation
    def test_09_user_isolation(self):
        """Test 9 — User A and User B profiles and factual memory remain strictly isolated."""
        user_a = f"user_a_{uuid.uuid4().hex[:8]}"
        user_b = f"user_b_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_a)
        adaptation.reset_adaptation_profile(user_b)

        # User A: concise, code_examples = True
        adaptation.set_manual_preference(user_a, "verbosity", "concise", 0.85)
        adaptation.set_manual_preference(user_a, "code_examples", True, 0.85)
        db.set_user_memory(user_a, "User A is an embedded C++ engineer.", 1)

        # User B: detailed, code_examples = False
        adaptation.set_manual_preference(user_b, "verbosity", "detailed", 0.85)
        adaptation.set_manual_preference(user_b, "code_examples", False, 0.85)
        db.set_user_memory(user_b, "User B is an economics professor.", 1)

        # Verify profile isolation
        prof_a = adaptation.get_adaptation_profile(user_a)
        prof_b = adaptation.get_adaptation_profile(user_b)
        self.assertEqual(prof_a["verbosity"]["value"], "concise")
        self.assertTrue(prof_a["code_examples"]["value"])
        self.assertEqual(prof_b["verbosity"]["value"], "detailed")
        self.assertFalse(prof_b["code_examples"]["value"])

        # Verify factual memory isolation
        mem_a = db.get_user_memory(user_a)
        mem_b = db.get_user_memory(user_b)
        self.assertIn("embedded C++", mem_a["memory_text"])
        self.assertIn("economics professor", mem_b["memory_text"])
        self.assertNotIn("economics", mem_a["memory_text"])
        self.assertNotIn("embedded", mem_b["memory_text"])

    # 10. Adaptation reset
    def test_10_adaptation_reset(self):
        """Test 10 — DELETE /api/adaptation/{user_id} resets adaptation and strategy stats but preserves all other data."""
        user_id = f"test_reset_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())
        email = f"{user_id}@example.com"

        # 1. Create user account
        db.create_user(user_id=user_id, name="Test User", email=email, password="password123")

        # 2. Establish factual memory
        fact_memory = "User specializes in database query optimization."
        db.set_user_memory(user_id, fact_memory, 1)

        # 3. Create session & message
        db.create_session(session_id, user_id, title="Reset Test Session")
        db.save_message(
            message_id=msg_id,
            session_id=session_id,
            user_id=user_id,
            user_message="Hello Ava",
            agent_response="Hello!",
            intent="greeting",
            sentiment={"label": "neutral"},
            frustration=0.0,
            latency_ms=10,
        )

        # 4. Add feedback
        db.save_feedback(user_id=user_id, session_id=session_id, message_id=msg_id, helpful=True)

        # 5. Add document
        doc_id = str(uuid.uuid4())
        db.save_document(doc_id, user_id, "notes.txt", "/fake/path/notes.txt", "Important notes.")

        # 6. Establish learned adaptation & strategy stats
        adaptation.set_manual_preference(user_id, "verbosity", "concise", 0.90)
        db.record_strategy_feedback(user_id, "concise_direct", True)

        # Confirm adaptation profile & strategy stats exist before reset
        self.assertEqual(adaptation.get_adaptation_profile(user_id)["verbosity"]["value"], "concise")
        self.assertIn("concise_direct", db.get_strategy_stats(user_id))

        # 7. Call DELETE endpoint
        resp = self.client.delete(f"/api/adaptation/{user_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "reset")

        # 8. Assert adaptation profile and strategy stats are reset/empty
        prof_after = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof_after["verbosity"]["value"], "balanced")
        self.assertEqual(prof_after["verbosity"]["confidence"], 0.50)
        self.assertEqual(len(db.get_strategy_stats(user_id)), 0)

        # 9. Assert ALL other data classes are 100% INTACT
        user_check = db.get_user_by_id(user_id)
        self.assertIsNotNone(user_check)
        self.assertEqual(user_check["email"], email)

        mem_check = db.get_user_memory(user_id)
        self.assertIsNotNone(mem_check)
        self.assertEqual(mem_check["memory_text"], fact_memory)

        sessions = db.get_sessions_for_user(user_id)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], session_id)

        messages = db.get_session_messages(session_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_id"], msg_id)

        doc_check = db.get_document(doc_id)
        self.assertIsNotNone(doc_check)
        self.assertEqual(doc_check["filename"], "notes.txt")

    # 11. Current-request override
    def test_11_current_request_override(self):
        """Test 11 — Stored adaptation never overrides the current explicit user request."""
        user_id = f"test_override_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)
        adaptation.set_manual_preference(user_id, "verbosity", "concise", 0.95)

        context = adaptation.get_adaptation_context(user_id)
        self.assertIn("IMPORTANT PRIORITY RULE", context)
        self.assertIn("The user's CURRENT explicit request in this prompt (overrides any learned preference)", context)
        self.assertIn("ALWAYS follow the current explicit request", context)

    # 12. Strategy tracking
    def test_12_strategy_tracking(self):
        """Test 12 — Response strategies are accurately classified and recorded upon feedback."""
        user_id = f"test_strat_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())

        db.create_session(session_id, user_id)
        db.save_message(
            message_id=msg_id,
            session_id=session_id,
            user_id=user_id,
            user_message="How do I read a file in Python?",
            agent_response="```python\nwith open('file.txt') as f:\n    data = f.read()\n```",
            intent="general_inquiry",
            sentiment={"label": "neutral"},
            frustration=0.0,
            latency_ms=20,
        )

        adaptation.process_feedback(user_id=user_id, message_id=msg_id, helpful=True)
        stats = db.get_strategy_stats(user_id)
        self.assertIn("concise_with_code", stats)
        self.assertEqual(stats["concise_with_code"]["successes"], 1)
        self.assertEqual(stats["concise_with_code"]["failures"], 0)

    # 13. Strategy minimum-evidence rule
    def test_13_strategy_minimum_evidence_rule(self):
        """Test 13 — Minimum evidence rule: 1 success does not make a strategy preferred; requires >= 3 evidence."""
        user_id = f"test_minevid_{uuid.uuid4().hex[:8]}"
        db.clear_adaptation_profile(user_id)

        # Record 1 success / 0 failures
        db.record_strategy_feedback(user_id, "code_first", helpful=True)
        stats = db.get_strategy_stats(user_id)
        self.assertEqual(stats["code_first"]["successes"], 1)

        # Check Bayesian smoothed score: (1 + 1) / (1 + 0 + 2) = 2/3 = 0.667
        score_1 = adaptation.get_strategy_score(user_id, "code_first")
        self.assertAlmostEqual(score_1, 0.667, places=2)

        # Minimum evidence rule check: with total=1 (< 3), code_first MUST NOT be considered preferred
        preferred = adaptation.get_preferred_strategies(user_id, min_evidence=3)
        self.assertNotIn("code_first", preferred)

        # Now record 2 more successes (total = 3, >= 3)
        db.record_strategy_feedback(user_id, "code_first", helpful=True)
        db.record_strategy_feedback(user_id, "code_first", helpful=True)

        preferred_3 = adaptation.get_preferred_strategies(user_id, min_evidence=3)
        self.assertIn("code_first", preferred_3)

    # 14. Conflicting preference updates
    def test_14_conflicting_preference_updates(self):
        """Test 14 — Preference switching: old preference weakens first before switching without oscillation."""
        user_id = f"test_conflict_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # 3 explicit concise instructions build high confidence in concise
        for _ in range(3):
            adaptation.observe_interaction(user_id, "Keep your answers short and concise.", "Brief reply.")

        prof1 = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof1["verbosity"]["value"], "concise")
        initial_conf = prof1["verbosity"]["confidence"]
        self.assertGreaterEqual(initial_conf, 0.74)

        # New contradictory instruction: "Explain this in much more detail."
        adaptation.observe_interaction(user_id, "Explain this in much more detail.", "Detailed breakdown.")
        prof2 = adaptation.get_adaptation_profile(user_id)

        # Old preference should WEAKEN first, but NOT instantly flip!
        self.assertEqual(prof2["verbosity"]["value"], "concise")
        self.assertLess(prof2["verbosity"]["confidence"], initial_conf)

        # Repeated detailed instructions eventually switch the preference
        for _ in range(3):
            adaptation.observe_interaction(user_id, "Explain this in much more detail.", "Detailed breakdown.")

        prof3 = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof3["verbosity"]["value"], "detailed")
        self.assertGreater(prof3["verbosity"]["confidence"], 0.50)

    # 15. Invalid preference value rejection
    def test_15_invalid_preference_value(self):
        """Test 15 — Reject invalid preference values with HTTP 400."""
        user_id = f"test_inv_val_{uuid.uuid4().hex[:8]}"

        # Invalid verbosity value
        r1 = self.client.patch(f"/api/adaptation/{user_id}", json={"preference": "verbosity", "value": "banana"})
        self.assertEqual(r1.status_code, 400)
        self.assertIn("Invalid value", r1.json()["detail"])

        # Invalid technical_depth (integer instead of allowed string)
        r2 = self.client.patch(f"/api/adaptation/{user_id}", json={"preference": "technical_depth", "value": 500})
        self.assertEqual(r2.status_code, 400)

        # Invalid code_examples (string "yes" instead of bool)
        r3 = self.client.patch(f"/api/adaptation/{user_id}", json={"preference": "code_examples", "value": "yes"})
        self.assertEqual(r3.status_code, 400)

        # Invalid dimension name
        r4 = self.client.patch(f"/api/adaptation/{user_id}", json={"preference": "super_intelligence", "value": True})
        self.assertEqual(r4.status_code, 400)

    # 16. Invalid confidence value rejection
    def test_16_invalid_confidence_value(self):
        """Test 16 — Reject invalid confidence values with HTTP 400 (do not silently clamp API requests)."""
        user_id = f"test_inv_conf_{uuid.uuid4().hex[:8]}"

        # Confidence > 1.0
        r1 = self.client.patch(f"/api/adaptation/{user_id}", json={"preference": "verbosity", "value": "concise", "confidence": 1.5})
        self.assertEqual(r1.status_code, 400)
        self.assertIn("Invalid confidence", r1.json()["detail"])

        # Confidence < 0.0
        r2 = self.client.patch(f"/api/adaptation/{user_id}", json={"preference": "verbosity", "value": "concise", "confidence": -0.2})
        self.assertEqual(r2.status_code, 400)

        # Confidence of wrong type
        r3 = self.client.patch(f"/api/adaptation/{user_id}", json={"preference": "verbosity", "value": "concise", "confidence": "maximum"})
        self.assertEqual(r3.status_code, 400)

    # 17. Malformed stored profile recovery
    def test_17_malformed_stored_profile(self):
        """Test 17 — Gracefully recover from invalid JSON or corrupted fields in adaptation_profiles."""
        user_id = f"test_malformed_{uuid.uuid4().hex[:8]}"

        # 1. Corrupted profile: invalid JSON string directly in DB
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO adaptation_profiles (user_id, profile_json, updated_at, interaction_count) VALUES (?, ?, ?, ?)",
                (user_id, "{invalid json [[", "2026-09-20 00:00:00", 1)
            )

        prof_recovered = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof_recovered["verbosity"]["value"], "balanced")
        self.assertEqual(prof_recovered["verbosity"]["confidence"], 0.50)

        # 2. Corrupted profile: partial dimensions and wrong types
        bad_profile = {
            "verbosity": {"value": 99999, "confidence": "high"},
            "code_examples": {"value": "invalid", "confidence": -5.0},
            "unknown_dimension": {"value": True, "confidence": 0.9},
        }
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE adaptation_profiles SET profile_json = ? WHERE user_id = ?",
                (json.dumps(bad_profile), user_id)
            )

        prof_recovered2 = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof_recovered2["verbosity"]["value"], "balanced")
        self.assertEqual(prof_recovered2["verbosity"]["confidence"], 0.50)
        self.assertEqual(prof_recovered2["code_examples"]["value"], False)
        self.assertEqual(prof_recovered2["code_examples"]["confidence"], 0.50)

    # 18. Prompt contains user memory exactly once
    def test_18_prompt_contains_user_memory_exactly_once(self):
        """Test 18 — Factual user memory appears exactly once in the assembled system prompt."""
        user_id = f"test_mem_once_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        db.create_session(session_id, user_id, title="Memory Check Session")

        factual_memory = "User is building a high-frequency trading system in C++."
        db.set_user_memory(user_id, factual_memory, 1)

        # Non-streaming prompt path check
        sys_prompt, meta = assemble_chat_prompt_context(
            user_id=user_id,
            message="What are the performance bottlenecks?",
            session_id=session_id,
        )

        self.assertEqual(sys_prompt.count("--- What Ava remembers about this user ---"), 1)
        self.assertEqual(sys_prompt.count(factual_memory), 1)

    # 19. Prompt contains adaptation exactly once
    def test_19_prompt_contains_adaptation_exactly_once(self):
        """Test 19 — Behavioral adaptation section appears exactly once in the prompt."""
        user_id = f"test_adapt_once_{uuid.uuid4().hex[:8]}"
        adaptation.set_manual_preference(user_id, "verbosity", "concise", 0.90)

        sys_prompt, meta = assemble_chat_prompt_context(
            user_id=user_id,
            message="Give me a summary",
            session_id=None,
        )

        self.assertEqual(sys_prompt.count("--- User response preferences ---"), 1)
        self.assertIn("Prefer concise, direct, and to-the-point answers", sys_prompt)

    # 20. Session isolation
    def test_20_session_isolation(self):
        """Test 20 — Current-session context contains only the active session, no cross-session leakage."""
        user_id = f"test_sess_iso_{uuid.uuid4().hex[:8]}"
        session_1 = str(uuid.uuid4())
        session_2 = str(uuid.uuid4())

        db.create_session(session_1, user_id, title="Session 1")
        db.create_session(session_2, user_id, title="Session 2")

        # Message in Session 1
        db.save_message(
            message_id=str(uuid.uuid4()),
            session_id=session_1,
            user_id=user_id,
            user_message="Secret code for Session 1 is DELTA-FORCE-99",
            agent_response="Acknowledged delta code.",
            intent="general",
            sentiment={"label": "neutral"},
            frustration=0.0,
            latency_ms=10,
        )

        # Message in Session 2
        db.save_message(
            message_id=str(uuid.uuid4()),
            session_id=session_2,
            user_id=user_id,
            user_message="Session 2 active topic is Astrophysics",
            agent_response="Astrophysics is fascinating.",
            intent="general",
            sentiment={"label": "neutral"},
            frustration=0.0,
            latency_ms=10,
        )

        # Assemble prompt for Session 2
        sys_prompt_s2, _ = assemble_chat_prompt_context(
            user_id=user_id,
            message="Tell me more about stars",
            session_id=session_2,
        )

        # Session 2 message MUST be present
        self.assertIn("Astrophysics", sys_prompt_s2)
        # Session 1 message MUST NOT be present (no cross-session bleed)
        self.assertNotIn("DELTA-FORCE-99", sys_prompt_s2)

    # 21. Feedback conservative attribution
    def test_21_feedback_conservative_attribution(self):
        """Test 21 — Conservative feedback attribution: single thumbs-up on code does not set code preference."""
        user_id = f"test_cons_fb_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())

        db.create_session(session_id, user_id)
        # Assistant response contains code, but user just asked a generic question without requesting code
        db.save_message(
            message_id=msg_id,
            session_id=session_id,
            user_id=user_id,
            user_message="How do computers add numbers?",
            agent_response="Computers use logic gates. Here is an example:\n```python\na + b\n```",
            intent="general_inquiry",
            sentiment={"label": "neutral"},
            frustration=0.0,
            latency_ms=15,
        )

        # Initial baseline: code_examples is False @ 0.50
        init_prof = adaptation.get_adaptation_profile(user_id)
        self.assertFalse(init_prof["code_examples"]["value"])
        self.assertEqual(init_prof["code_examples"]["confidence"], 0.50)

        # Single thumbs up
        adaptation.process_feedback(user_id=user_id, message_id=msg_id, helpful=True)

        # Verify strategy is tracked
        stats = db.get_strategy_stats(user_id)
        self.assertIn("concise_with_code", stats)
        self.assertEqual(stats["concise_with_code"]["successes"], 1)

        # Conservative attribution check: code preference MUST NOT be established from a single thumbs-up!
        prof_after = adaptation.get_adaptation_profile(user_id)
        self.assertFalse(prof_after["code_examples"]["value"])
        self.assertEqual(prof_after["code_examples"]["confidence"], 0.50)

    # 22. Three positive strategy signals can establish preferred strategy
    def test_22_three_positive_signals_establish_strategy(self):
        """Test 22 — >= 3 positive feedback signals establish a preferred strategy."""
        user_id = f"test_strat_3pos_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        for _ in range(3):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        preferred = adaptation.get_preferred_strategies(user_id, min_evidence=3, threshold=0.60)
        self.assertIn("concise_with_code", preferred)
        self.assertGreaterEqual(adaptation.get_strategy_score(user_id, "concise_with_code"), 0.60)

    # 23. One positive signal cannot establish preferred strategy
    def test_23_one_positive_signal_cannot_establish_strategy(self):
        """Test 23 — A single positive signal (< 3) is insufficient evidence to establish a preferred strategy."""
        user_id = f"test_strat_1pos_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        preferred = adaptation.get_preferred_strategies(user_id, min_evidence=3, threshold=0.60)
        self.assertEqual(preferred, [])

    # 24. Repeated negative feedback suppresses previously successful strategy
    def test_24_negative_feedback_suppresses_strategy(self):
        """Test 24 — Repeated negative feedback suppresses a previously successful strategy."""
        user_id = f"test_strat_supp_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # 3 positive feedbacks establish preferred strategy
        for _ in range(3):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)
        self.assertIn("concise_with_code", adaptation.get_preferred_strategies(user_id))

        # 4 consecutive negative feedbacks arrive
        for _ in range(4):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=False)

        # Now total = 7 (3 successes, 4 failures). Strategy is suppressed!
        self.assertTrue(adaptation.is_strategy_suppressed(user_id, "concise_with_code"))
        self.assertNotIn("concise_with_code", adaptation.get_preferred_strategies(user_id))
        self.assertIn("concise_with_code", adaptation.get_avoided_strategies(user_id))

    # 25. Preferred strategy appears in behavior policy
    def test_25_preferred_strategy_in_behavior_policy(self):
        """Test 25 — Preferred strategy appears in behavior policy with all dimensions present."""
        user_id = f"test_policy_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        for _ in range(4):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        policy = adaptation.build_behavior_policy(user_id)
        self.assertEqual(policy["preferred_strategy"], "concise_with_code")
        self.assertIn("verbosity", policy)
        self.assertIn("technical_depth", policy)
        self.assertIn("code_examples", policy)
        self.assertIn("step_by_step", policy)
        self.assertIn("examples", policy)
        self.assertIn("tone", policy)
        self.assertIn("avoided_strategies", policy)

    # 26. Preferred strategy affects generated prompt
    def test_26_preferred_strategy_affects_prompt(self):
        """Test 26 — Preferred strategy guidance is injected into the generated prompt context."""
        user_id = f"test_prompt_strat_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        for _ in range(4):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        prompt_context = adaptation.get_adaptation_context(user_id, "How do I filter a list in Python?")
        self.assertIn("--- Learned Response Strategy (Behavior Policy) ---", prompt_context)
        self.assertIn("clean, focused code", prompt_context)
        self.assertIn("Apply this format when relevant", prompt_context)

    # 27. Current request overrides preferred strategy
    def test_27_current_request_overrides_preferred_strategy(self):
        """Test 27 — Current user request explicitly asking for NO code overrides learned concise_with_code."""
        user_id = f"test_req_override_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        for _ in range(4):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        # Explicit user request forbids code
        override_message = "Explain the architecture conceptually in detail and do not include code."
        resolved = adaptation.resolve_preferred_strategy(user_id, override_message)
        self.assertNotEqual(resolved, "concise_with_code")

        context = adaptation.get_adaptation_context(user_id, override_message)
        # Should NOT mandate code
        self.assertNotIn("focused, clean code example", context)
        # Must emphasize priority order
        self.assertIn("2. The user's CURRENT explicit request in this prompt (overrides any learned preference)", context)

    # 28. Programming request selects appropriate code strategy
    def test_28_programming_request_selects_code_strategy(self):
        """Test 28 — Programming request deterministically prioritizes code-oriented strategy."""
        user_id = f"test_prog_domain_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        for _ in range(4):
            db.record_strategy_feedback(user_id, "detailed_step_by_step", helpful=True)
        for _ in range(4):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        resolved = adaptation.resolve_preferred_strategy(user_id, "Write a Python script to parse a CSV file")
        self.assertEqual(resolved, "concise_with_code")

    # 29. Conceptual request does not blindly use code strategy
    def test_29_conceptual_request_does_not_use_code_strategy(self):
        """Test 29 — Conceptual request prioritizes conceptual depth over code."""
        user_id = f"test_concept_domain_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        for _ in range(4):
            db.record_strategy_feedback(user_id, "detailed_explanation", helpful=True)
        for _ in range(4):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        resolved = adaptation.resolve_preferred_strategy(
            user_id, "Explain the concept and theory of polymorphic recursion and its tradeoffs"
        )
        self.assertEqual(resolved, "detailed_explanation")

    # 30. Strategy conflicts resolve deterministically
    def test_30_strategy_conflicts_resolve_deterministically(self):
        """Test 30 — Strategy conflict resolution produces identical deterministic output on repeated evaluation."""
        user_id = f"test_conflict_det_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        for _ in range(5):
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)
        for _ in range(4):
            db.record_strategy_feedback(user_id, "concise_direct", helpful=True)
        for _ in range(3):
            db.record_strategy_feedback(user_id, "detailed_step_by_step", helpful=True)

        first_resolution = adaptation.resolve_preferred_strategy(user_id, "General query about technology")
        self.assertIsNotNone(first_resolution)
        for _ in range(10):
            repeated = adaptation.resolve_preferred_strategy(user_id, "General query about technology")
            self.assertEqual(repeated, first_resolution)

    # 31. Older evidence decays gradually
    def test_31_older_evidence_decays_gradually(self):
        """Test 31 — Evidence decays gradually over time via smooth half-life formula."""
        now = datetime.now(timezone.utc)

        # Decay factor tests
        decay_now = adaptation.calculate_evidence_decay(now.isoformat(), now_time=now)
        decay_60d = adaptation.calculate_evidence_decay((now - timedelta(days=60)).isoformat(), now_time=now)
        decay_180d = adaptation.calculate_evidence_decay((now - timedelta(days=180)).isoformat(), now_time=now)

        self.assertAlmostEqual(decay_now, 1.0, places=2)
        self.assertAlmostEqual(decay_60d, 0.50, delta=0.03)
        self.assertAlmostEqual(decay_180d, 0.125, delta=0.03)
        self.assertGreater(decay_180d, 0.0)

        # Comparison between fresh vs stale user evidence
        user_fresh = f"test_decay_fresh_{uuid.uuid4().hex[:8]}"
        user_stale = f"test_decay_stale_{uuid.uuid4().hex[:8]}"
        stale_time = (now - timedelta(days=120)).isoformat()

        for _ in range(4):
            db.record_strategy_feedback(user_fresh, "concise_direct", helpful=True, timestamp=now.isoformat())
            db.record_strategy_feedback(user_stale, "concise_direct", helpful=True, timestamp=stale_time)

        score_fresh = adaptation.get_strategy_score(user_fresh, "concise_direct", apply_decay=True, now_time=now)
        score_stale = adaptation.get_strategy_score(user_stale, "concise_direct", apply_decay=True, now_time=now)

        self.assertGreater(score_fresh, score_stale)
        # Stale score still has evidence (greater than unevidenced prior 0.50)
        self.assertGreater(score_stale, 0.50)

    # 32. Recent explicit preference overrides stale strategy
    def test_32_recent_explicit_preference_overrides_stale_strategy(self):
        """Test 32 — Recent explicit user preference suppresses conflicting learned strategy."""
        user_id = f"test_recent_override_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # User previously had learned strategy concise_direct
        for _ in range(5):
            db.record_strategy_feedback(user_id, "concise_direct", helpful=True)
        self.assertIn("concise_direct", adaptation.get_preferred_strategies(user_id))

        # User explicitly changes preference: wants detailed explanations
        adaptation.set_manual_preference(user_id, "verbosity", "detailed", confidence=0.85)

        # Strategy conflict resolution detects profile wants detailed -> concise_direct is suppressed!
        resolved = adaptation.resolve_preferred_strategy(user_id, "Explain quantum physics")
        self.assertNotEqual(resolved, "concise_direct")

    # 33. Adaptation failure does not break prompt generation
    def test_33_adaptation_failure_does_not_break_prompt(self):
        """Test 33 — Failures/exceptions inside adaptation never crash prompt generation."""
        user_id = f"test_fail_safe_{uuid.uuid4().hex[:8]}"

        with patch("adaptation.get_adaptation_profile", side_effect=RuntimeError("Simulated database failure")):
            sys_prompt, _ = assemble_chat_prompt_context(
                user_id=user_id,
                message="Hello Ava, tell me a fact",
                session_id=str(uuid.uuid4()),
            )
            # Base prompt is still generated safely
            self.assertIn("Ava", sys_prompt)
            self.assertIsInstance(sys_prompt, str)

    # 34. Unknown strategy is ignored
    def test_34_unknown_strategy_is_ignored(self):
        """Test 34 — Unknown or malicious strategy names are filtered out by whitelist."""
        user_id = f"test_unknown_strat_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # Directly insert non-whitelisted strategy into database
        for _ in range(10):
            db.record_strategy_feedback(user_id, "inject_malicious_unsupported_strategy", helpful=True)

        preferred = adaptation.get_preferred_strategies(user_id)
        self.assertNotIn("inject_malicious_unsupported_strategy", preferred)

        policy = adaptation.build_behavior_policy(user_id)
        self.assertNotEqual(policy["preferred_strategy"], "inject_malicious_unsupported_strategy")

        context = adaptation.get_strategy_context(user_id)
        self.assertNotIn("inject_malicious_unsupported_strategy", context)

    # 35. Strategy metrics are correctly calculated
    def test_35_strategy_metrics_calculated(self):
        """Test 35 — Adaptation effectiveness metrics are correctly computed from actual database data."""
        user_id = f"test_metrics_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        adaptation.reset_adaptation_profile(user_id)

        # Record feedback in DB
        for _ in range(3):
            msg_id = str(uuid.uuid4())
            db.save_feedback(user_id, session_id, msg_id, helpful=True)
            db.record_strategy_feedback(user_id, "concise_with_code", helpful=True)

        msg_id_neg = str(uuid.uuid4())
        db.save_feedback(user_id, session_id, msg_id_neg, helpful=False)
        db.record_strategy_feedback(user_id, "concise_with_code", helpful=False)

        metrics = adaptation.get_adaptation_metrics(user_id)
        self.assertEqual(metrics["feedback_count"], 4)
        self.assertEqual(metrics["positive_feedback_rate"], 0.75)
        self.assertEqual(metrics["strategy_success_rate"], 0.75)
        self.assertEqual(metrics["strategy_evidence"], 4)
        self.assertGreaterEqual(metrics["preference_confidence"], 0.0)
        self.assertLessEqual(metrics["preference_confidence"], 1.0)

        # Check API endpoint GET /api/adaptation/{user_id}
        res = self.client.get(f"/api/adaptation/{user_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("profile", data)
        self.assertIn("preferred_strategies", data)
        self.assertIn("policy", data)
        self.assertIn("metrics", data)
        self.assertEqual(data["metrics"]["feedback_count"], 4)

    # 36. User A's strategy never affects User B
    def test_36_user_strategy_isolation(self):
        """Test 36 — User A's learned strategies and policy never bleed into User B."""
        user_a = f"test_user_a_{uuid.uuid4().hex[:8]}"
        user_b = f"test_user_b_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_a)
        adaptation.reset_adaptation_profile(user_b)

        for _ in range(4):
            db.record_strategy_feedback(user_a, "concise_with_code", helpful=True)

        self.assertIn("concise_with_code", adaptation.get_preferred_strategies(user_a))
        self.assertEqual(adaptation.get_preferred_strategies(user_b), [])

        policy_a = adaptation.build_behavior_policy(user_a)
        policy_b = adaptation.build_behavior_policy(user_b)
        self.assertEqual(policy_a["preferred_strategy"], "concise_with_code")
        self.assertIsNone(policy_b["preferred_strategy"])

        ctx_a = adaptation.get_strategy_context(user_a)
        ctx_b = adaptation.get_strategy_context(user_b)
        self.assertIn("clean, focused code", ctx_a)
        self.assertEqual(ctx_b, "")

    # 37. Behavioral Integration Test: End-to-End Mocked Closed-Loop
    def test_37_behavioral_closed_loop_integration(self):
        """
        Test 37 — Phase 3 Behavioral Integration Test (End-to-End Mocked Closed Loop):
        1. User asks for Python help.
        2. Ava responds with concise + code.
        3. User provides positive feedback (repeated 3 times to establish evidence).
        4. Next related request arrives -> Prompt contains learned concise + code strategy guidance.
        5. User explicitly asks: "Explain conceptually, in detail, with no code."
        6. Learned strategy is overridden; no code is mandated; current explicit request wins.
        """
        user_id = f"test_e2e_closed_loop_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        adaptation.reset_adaptation_profile(user_id)
        db.create_session(session_id, user_id)

        # Simulate 3 interactions where Ava answers concise + code and user gives thumbs up
        for i in range(3):
            msg_id = str(uuid.uuid4())
            user_question = f"How do I read a file line by line in Python? (variation {i})"
            assistant_response = "Use a `with` statement and iterate:\n```python\nwith open('f.txt') as f:\n    for line in f:\n        print(line)\n```"

            db.save_message(
                message_id=msg_id,
                session_id=session_id,
                user_id=user_id,
                user_message=user_question,
                agent_response=assistant_response,
                intent="programming",
                sentiment={"label": "neutral"},
                frustration=0.0,
                latency_ms=20,
            )

            # User gives thumbs up
            adaptation.process_feedback(user_id=user_id, message_id=msg_id, helpful=True)

        # Verify strategy is now evidenced
        stats = db.get_strategy_stats(user_id)
        self.assertIn("concise_with_code", stats)
        self.assertGreaterEqual(stats["concise_with_code"]["successes"], 3)
        self.assertIn("concise_with_code", adaptation.get_preferred_strategies(user_id))

        # Next related request arrives
        next_request = "How do I write JSON to a file in Python?"
        prompt_with_learned_strategy, _ = assemble_chat_prompt_context(
            user_id=user_id,
            message=next_request,
            session_id=session_id,
        )

        # Verify prompt contains learned guidance equivalent to:
        # "Prefer concise responses with focused code examples when appropriate."
        self.assertIn("--- Learned Response Strategy (Behavior Policy) ---", prompt_with_learned_strategy)
        self.assertIn("Prefer concise responses with focused code examples when appropriate", prompt_with_learned_strategy)
        self.assertIn("clean, focused code", prompt_with_learned_strategy)
        self.assertIn("Apply this format when relevant", prompt_with_learned_strategy)

        # Now send explicit override: "Explain conceptually, in detail, with no code."
        override_request = "Explain conceptually, in detail, with no code."
        prompt_with_override, _ = assemble_chat_prompt_context(
            user_id=user_id,
            message=override_request,
            session_id=session_id,
        )

        # Verify learned code strategy is overridden / suppressed
        self.assertNotIn("clean, focused code", prompt_with_override)
        # Verify strict priority rule is present in the prompt
        self.assertIn("2. The user's CURRENT explicit request in this prompt (overrides any learned preference)", prompt_with_override)


if __name__ == "__main__":
    unittest.main(verbosity=2)
