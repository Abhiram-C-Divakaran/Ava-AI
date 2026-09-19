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
"""

import os
import sys
import unittest
import uuid
import json

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
