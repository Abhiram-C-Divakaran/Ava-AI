"""
test_adaptation.py — Comprehensive Test Suite for Phase 2: Behavioral Adaptation Engine.

Tests:
1. Test 1 — Concise preference: "Please keep your answers short and concise."
2. Test 2 — Detailed preference: "Explain this in much more detail."
3. Test 3 — Code preference: "I prefer Python code examples when possible."
4. Test 4 — Step-by-step preference: "Please explain things step by step."
5. Test 5 — Persistence across sessions
6. Test 6 — User isolation: User A vs User B
7. Test 7 — Reset isolation: clears adaptation profile without touching long-term factual memory or messages
8. Test 8 — Current request override rule in adaptation context
9. Test 9 — Strategy tracking via feedback
10. Test 10 — FastAPI Endpoints (GET, DELETE, PATCH /api/adaptation/{user_id})
"""

import os
import sys
import unittest
import uuid

# Reconfigure stdout for utf-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure backend directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
import database as db
import adaptation
from main import app


class TestBehavioralAdaptation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(app)

    def test_01_concise_preference(self):
        """Test 1 — Concise preference shifts verbosity to concise and increases confidence."""
        user_id = f"test_concise_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        init_profile = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(init_profile["verbosity"]["value"], "balanced")
        self.assertEqual(init_profile["verbosity"]["confidence"], 0.50)

        # User gives concise instruction
        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Please keep your answers short and concise.",
            agent_response="Sure thing! Keeping it brief from now on.",
        )

        updated_profile = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(updated_profile["verbosity"]["value"], "concise")
        self.assertGreater(updated_profile["verbosity"]["confidence"], 0.50)
        self.assertLessEqual(updated_profile["verbosity"]["confidence"], 1.0)
        print(f"[PASS] Test 1: Verbosity={updated_profile['verbosity']['value']} Conf={updated_profile['verbosity']['confidence']}")

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
        print(f"[PASS] Test 2: Verbosity={profile['verbosity']['value']} Conf={profile['verbosity']['confidence']}")

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
        print(f"[PASS] Test 3: CodeExamples={profile['code_examples']['value']} Conf={profile['code_examples']['confidence']}")

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
        print(f"[PASS] Test 4: StepByStep={profile['step_by_step']['value']} Conf={profile['step_by_step']['confidence']}")

    def test_05_persistence(self):
        """Test 5 — Behavioral adaptation persists across multiple sessions for the same user."""
        user_id = f"test_persist_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # Session 1 interaction
        adaptation.observe_interaction(
            user_id=user_id,
            user_message="Always keep your answers concise.",
            agent_response="Understood.",
        )

        # Re-fetch profile simulating session 2 in a new request
        persisted_profile = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(persisted_profile["verbosity"]["value"], "concise")
        self.assertGreater(persisted_profile["verbosity"]["confidence"], 0.50)

        # Re-fetch context
        context = adaptation.get_adaptation_context(user_id)
        self.assertIn("concise", context.lower())
        print(f"[PASS] Test 5: Profile persisted across sessions.")

    def test_06_user_isolation(self):
        """Test 6 — User A and User B profiles remain completely independent."""
        user_a = f"user_a_{uuid.uuid4().hex[:8]}"
        user_b = f"user_b_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_a)
        adaptation.reset_adaptation_profile(user_b)

        # User A wants concise
        adaptation.observe_interaction(user_a, "Keep your answers short and concise.", "OK.")
        # User B wants detailed
        adaptation.observe_interaction(user_b, "Explain this in much more detail.", "Detailed breakdown.")

        profile_a = adaptation.get_adaptation_profile(user_a)
        profile_b = adaptation.get_adaptation_profile(user_b)

        self.assertEqual(profile_a["verbosity"]["value"], "concise")
        self.assertEqual(profile_b["verbosity"]["value"], "detailed")
        self.assertNotEqual(profile_a["verbosity"]["value"], profile_b["verbosity"]["value"])
        print(f"[PASS] Test 6: User isolation verified.")

    def test_07_reset_isolation(self):
        """Test 7 — Resetting adaptation profile preserves long-term factual memory and messages."""
        user_id = f"test_reset_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())

        # 1. Establish factual long-term memory
        fact_memory = "User works as a Senior Rust Engineer on distributed databases."
        db.set_user_memory(user_id, fact_memory, 1)

        # 2. Save a chat message
        db.create_session(session_id, user_id, title="Test Session")
        db.save_message(
            message_id=msg_id,
            session_id=session_id,
            user_id=user_id,
            user_message="I love Rust",
            agent_response="Rust is great!",
            intent="general_inquiry",
            sentiment={"label": "positive", "score": 0.9},
            frustration=0.0,
            latency_ms=10,
        )

        # 3. Establish learned adaptation
        adaptation.observe_interaction(user_id, "Always be concise.", "OK.")
        prof_before = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof_before["verbosity"]["value"], "concise")

        # 4. Reset adaptation
        adaptation.reset_adaptation_profile(user_id)

        # 5. Verify adaptation is back to defaults
        prof_after = adaptation.get_adaptation_profile(user_id)
        self.assertEqual(prof_after["verbosity"]["value"], "balanced")
        self.assertEqual(prof_after["verbosity"]["confidence"], 0.50)

        # 6. Verify factual memory and conversation history are 100% INTACT
        mem_check = db.get_user_memory(user_id)
        self.assertIsNotNone(mem_check)
        self.assertEqual(mem_check["memory_text"], fact_memory)

        msg_check = db.get_session_messages(session_id)
        self.assertEqual(len(msg_check), 1)
        self.assertEqual(msg_check[0]["user_message"], "I love Rust")
        print(f"[PASS] Test 7: Reset cleared adaptation while preserving long-term memory & history.")

    def test_08_current_request_override(self):
        """Test 8 — Adaptation context explicitly enforces that current user requests override learned preferences."""
        user_id = f"test_override_{uuid.uuid4().hex[:8]}"
        adaptation.reset_adaptation_profile(user_id)

        # Train strong concise preference
        for _ in range(3):
            adaptation.observe_interaction(user_id, "Always keep your answers concise.", "Brief response.")

        context = adaptation.get_adaptation_context(user_id)
        self.assertIn("Priority order", context)
        self.assertIn("The user's CURRENT explicit request in this prompt", context)
        self.assertIn("ALWAYS follow the current explicit request", context)
        print(f"[PASS] Test 8: Context enforces priority override for current explicit prompt.")

    def test_09_strategy_feedback(self):
        """Test 9 — Thumbs up / down feedback records strategy successes and failures."""
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
            sentiment={"label": "neutral", "score": 0.5},
            frustration=0.0,
            latency_ms=20,
        )

        # Positive feedback
        adaptation.process_feedback(user_id=user_id, message_id=msg_id, helpful=True)
        stats = db.get_strategy_stats(user_id)
        self.assertIn("concise_with_code", stats)
        self.assertEqual(stats["concise_with_code"]["successes"], 1)
        self.assertEqual(stats["concise_with_code"]["failures"], 0)
        print(f"[PASS] Test 9: Strategy feedback successfully tracked: {stats}")

    def test_10_api_endpoints(self):
        """Test 10 — GET, PATCH, and DELETE /api/adaptation/{user_id} endpoints."""
        user_id = f"api_user_{uuid.uuid4().hex[:8]}"

        # 1. GET initial
        resp = self.client.get(f"/api/adaptation/{user_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["user_id"], user_id)
        self.assertIn("profile", data)
        self.assertEqual(data["profile"]["verbosity"]["value"], "balanced")

        # 2. PATCH preference
        patch_resp = self.client.patch(
            f"/api/adaptation/{user_id}",
            json={"preference": "code_examples", "value": True, "confidence": 0.90}
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertTrue(patch_resp.json()["profile"]["code_examples"]["value"])
        self.assertEqual(patch_resp.json()["profile"]["code_examples"]["confidence"], 0.90)

        # 3. Verify via GET
        get_resp = self.client.get(f"/api/adaptation/{user_id}")
        self.assertTrue(get_resp.json()["profile"]["code_examples"]["value"])
        self.assertIn("Code Examples", get_resp.json()["context"])

        # 4. DELETE / reset
        del_resp = self.client.delete(f"/api/adaptation/{user_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json()["status"], "reset")

        # Verify reset
        reset_check = self.client.get(f"/api/adaptation/{user_id}")
        self.assertEqual(reset_check.json()["profile"]["code_examples"]["value"], False)
        self.assertEqual(reset_check.json()["profile"]["code_examples"]["confidence"], 0.50)
        print(f"[PASS] Test 10: GET, PATCH, DELETE API endpoints functioning perfectly.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
