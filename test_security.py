"""
test_security.py — Phase 4 Production Hardening Security Test Suite

Covers 20 security scenarios:
1. Unauthenticated chat rejected (HTTP 401)
2. Authenticated chat accepted (HTTP 200)
3. Mismatched body user_id rejected (HTTP 403)
4. User A cannot read User B sessions (HTTP 403)
5. User A cannot read User B messages (HTTP 403)
6. User A cannot read User B factual memory (HTTP 403)
7. User A cannot modify User B adaptation (HTTP 403)
8. User A cannot clear User B adaptation (HTTP 403)
9. User A cannot export User B data (HTTP 403)
10. User A cannot delete User B data (HTTP 403)
11. Invalid session ID rejected (HTTP 404)
12. Session ownership checked (HTTP 403)
13. Generic login errors for wrong password and unknown email (HTTP 401)
14. Login rate limiting (HTTP 429 on >5 attempts)
15. Chat rate limiting (HTTP 429 on >30 attempts)
16. CORS origins configurable and enforced
17. Missing SECRET_KEY in production fails startup (RuntimeError)
18. Request size limits enforced (HTTP 422 on message > 20000 chars)
19. Path traversal in upload fails safely (filename sanitized)
20. Admin endpoints require admin session (HTTP 401)
"""

import os
import sys
import unittest
import uuid
import json
import tempfile
import subprocess
from unittest.mock import patch
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
from main import app, limiter


class TestSecurityHardened(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure isolated temp directory and database
        cls._orig_db_path = db.DB_PATH
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_security.db")
        db.DB_PATH = cls.test_db_path
        db.init_db()

        # Seed User A and User B
        cls.user_a_id = f"sec_user_a_{uuid.uuid4().hex[:8]}"
        cls.user_a_email = f"{cls.user_a_id}@example.com"
        cls.user_a_pass = "password_a_123"
        db.create_user(cls.user_a_id, name="User A", email=cls.user_a_email, password=cls.user_a_pass)

        cls.user_b_id = f"sec_user_b_{uuid.uuid4().hex[:8]}"
        cls.user_b_email = f"{cls.user_b_id}@example.com"
        cls.user_b_pass = "password_b_123"
        db.create_user(cls.user_b_id, name="User B", email=cls.user_b_email, password=cls.user_b_pass)

        # Seed data for User B
        cls.user_b_session_id = str(uuid.uuid4())
        db.create_session(cls.user_b_session_id, cls.user_b_id, title="User B Private Session")
        cls.user_b_msg_id = str(uuid.uuid4())
        db.save_message(
            message_id=cls.user_b_msg_id,
            session_id=cls.user_b_session_id,
            user_id=cls.user_b_id,
            user_message="Secret B message",
            agent_response="Secret B response",
            intent="qa",
            sentiment={"label": "neutral"},
            frustration=0.0,
            latency_ms=10,
        )
        db.set_user_memory(cls.user_b_id, "User B highly confidential secret fact", 1)

        # Unauthenticated client
        cls.unauth_client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def setUp(self):
        # Reset limiter state before each test
        limiter.reset()

    def _get_client_a(self) -> TestClient:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": self.user_a_email, "password": self.user_a_pass})
        self.assertEqual(resp.status_code, 200)
        return client

    def _get_client_b(self) -> TestClient:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": self.user_b_email, "password": self.user_b_pass})
        self.assertEqual(resp.status_code, 200)
        return client

    # 1. Unauthenticated chat rejected
    def test_01_unauthenticated_chat_rejected(self):
        """Calling /api/chat without session cookie returns HTTP 401."""
        resp = self.unauth_client.post("/api/chat", json={"message": "Hello Ava", "user_id": self.user_a_id})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Authentication required", resp.json()["detail"])

    # 2. Authenticated chat accepted
    def test_02_authenticated_chat_accepted(self):
        """Calling /api/chat with valid session cookie returns HTTP 200."""
        client = self._get_client_a()
        with patch("main.call_llm_with_constraints", return_value="Hello, I am Ava."):
            resp = client.post("/api/chat", json={"message": "Hello Ava", "user_id": self.user_a_id})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("response", resp.json())
        self.assertEqual(resp.json()["response"], "Hello, I am Ava.")

    # 3. Mismatched body user_id rejected
    def test_03_mismatched_body_user_id_rejected(self):
        """Calling /api/chat with session of User A but body user_id of User B returns HTTP 403."""
        client = self._get_client_a()
        resp = client.post("/api/chat", json={"message": "Hello", "user_id": self.user_b_id})
        self.assertEqual(resp.status_code, 403)
        self.assertIn("user_id mismatch", resp.json()["detail"])

    # 4. User A cannot read User B sessions
    def test_04_user_a_cannot_read_user_b_sessions(self):
        """GET /api/sessions/{user_b} as User A returns HTTP 403."""
        client = self._get_client_a()
        resp = client.get(f"/api/sessions/{self.user_b_id}")
        self.assertEqual(resp.status_code, 403)

    # 5. User A cannot read User B messages
    def test_05_user_a_cannot_read_user_b_messages(self):
        """GET /api/sessions/{user_b}/{session_id}/messages as User A returns HTTP 403."""
        client = self._get_client_a()
        resp = client.get(f"/api/sessions/{self.user_b_id}/{self.user_b_session_id}/messages")
        self.assertEqual(resp.status_code, 403)

    # 6. User A cannot read User B factual memory
    def test_06_user_a_cannot_read_user_b_factual_memory(self):
        """GET /api/user-memory/{user_b} and /api/memory/{user_b} as User A returns HTTP 403."""
        client = self._get_client_a()
        resp1 = client.get(f"/api/user-memory/{self.user_b_id}")
        self.assertEqual(resp1.status_code, 403)
        resp2 = client.get(f"/api/memory/{self.user_b_id}")
        self.assertEqual(resp2.status_code, 403)

    # 7. User A cannot modify User B adaptation
    def test_07_user_a_cannot_modify_user_b_adaptation(self):
        """PATCH /api/adaptation/{user_b} as User A returns HTTP 403."""
        client = self._get_client_a()
        resp = client.patch(
            f"/api/adaptation/{self.user_b_id}",
            json={"preference": "verbosity", "value": "concise"}
        )
        self.assertEqual(resp.status_code, 403)

    # 8. User A cannot clear User B adaptation
    def test_08_user_a_cannot_clear_user_b_adaptation(self):
        """DELETE /api/adaptation/{user_b} as User A returns HTTP 403."""
        client = self._get_client_a()
        resp = client.delete(f"/api/adaptation/{self.user_b_id}")
        self.assertEqual(resp.status_code, 403)

    # 9. User A cannot export User B data
    def test_09_user_a_cannot_export_user_b_data(self):
        """GET /api/export/{user_b} as User A returns HTTP 403."""
        client = self._get_client_a()
        resp = client.get(f"/api/export/{self.user_b_id}")
        self.assertEqual(resp.status_code, 403)

    # 10. User A cannot delete User B data
    def test_10_user_a_cannot_delete_user_b_data(self):
        """DELETE /api/memory/{user_b} and DELETE /api/user-memory/{user_b} as User A returns HTTP 403."""
        client = self._get_client_a()
        resp1 = client.delete(f"/api/memory/{self.user_b_id}")
        self.assertEqual(resp1.status_code, 403)
        resp2 = client.delete(f"/api/user-memory/{self.user_b_id}")
        self.assertEqual(resp2.status_code, 403)

    # 11. Invalid session ID rejected
    def test_11_invalid_session_id_rejected(self):
        """Calling /api/chat with nonexistent session_id returns HTTP 404."""
        client = self._get_client_a()
        nonexistent_session = str(uuid.uuid4())
        resp = client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": nonexistent_session, "user_id": self.user_a_id}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Session not found", resp.json()["detail"])

    # 12. Session ownership checked
    def test_12_session_ownership_checked(self):
        """User A attempting to chat into User B's session returns HTTP 403."""
        client = self._get_client_a()
        resp = client.post(
            "/api/chat",
            json={"message": "Injecting message", "session_id": self.user_b_session_id, "user_id": self.user_a_id}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("session does not belong to you", resp.json()["detail"])

    # 13. Generic login errors
    def test_13_generic_login_errors(self):
        """Wrong password and nonexistent email return identical generic error messages."""
        r1 = self.unauth_client.post("/api/auth/login", json={"email": self.user_a_email, "password": "wrongpassword1"})
        self.assertEqual(r1.status_code, 401)
        self.assertEqual(r1.json()["detail"], "Invalid email or password")

        r2 = self.unauth_client.post("/api/auth/login", json={"email": "nonexistent@example.com", "password": "anypassword"})
        self.assertEqual(r2.status_code, 401)
        self.assertEqual(r2.json()["detail"], "Invalid email or password")

    # 14. Login rate limiting
    def test_14_login_rate_limiting(self):
        """More than 5 login attempts within a minute trigger HTTP 429."""
        limiter.reset()
        client = TestClient(app)
        statuses = []
        for i in range(6):
            r = client.post("/api/auth/login", json={"email": "rate_limit@example.com", "password": "wrong"})
            statuses.append(r.status_code)
        self.assertEqual(statuses[:5], [401, 401, 401, 401, 401])
        self.assertEqual(statuses[5], 429)

    # 15. Chat rate limiting
    def test_15_chat_rate_limiting(self):
        """More than 30 chat requests within a minute trigger HTTP 429."""
        limiter.reset()
        client = self._get_client_b()
        statuses = []
        with patch("main.call_llm_with_constraints", return_value="Rate limit test response"):
            for i in range(32):
                r = client.post("/api/chat", json={"message": f"Message {i}", "user_id": self.user_b_id})
                statuses.append(r.status_code)
        self.assertTrue(all(s == 200 for s in statuses[:30]))
        self.assertEqual(statuses[30], 429)

    # 16. CORS origins configurable
    def test_16_cors_origins_configurable(self):
        """CORS headers respect allowed origins and reject disallowed origins."""
        resp = self.unauth_client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:8000")

        resp_disallowed = self.unauth_client.options(
            "/api/chat",
            headers={
                "Origin": "http://evil-attacker.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotEqual(resp_disallowed.headers.get("access-control-allow-origin"), "http://evil-attacker.com")

    # 17. Missing SECRET_KEY in production fails startup
    def test_17_missing_secret_key_production_fails(self):
        """When ENVIRONMENT=production and SECRET_KEY is empty, startup raises RuntimeError."""
        env = os.environ.copy()
        env["ENVIRONMENT"] = "production"
        env.pop("SECRET_KEY", None)
        env["SECRET_KEY"] = ""
        result = subprocess.run(
            [sys.executable, "-c", "import main"],
            env=env,
            capture_output=True,
            text=True,
            cwd=BASE_DIR
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RuntimeError", result.stderr)
        self.assertIn("SECRET_KEY must be configured in production environment", result.stderr)

    # 18. Request size limits
    def test_18_request_size_limits(self):
        """Chat request with message exceeding 20,000 chars is rejected with HTTP 422."""
        client = self._get_client_a()
        huge_message = "A" * 20001
        resp = client.post("/api/chat", json={"message": huge_message, "user_id": self.user_a_id})
        self.assertEqual(resp.status_code, 422)

    # 19. Path traversal in upload fails safely
    def test_19_path_traversal_in_upload_fails_safely(self):
        """Upload with path traversal in filename is sanitized with os.path.basename."""
        client = self._get_client_a()
        content = b"Safe test file content"
        files = {"file": ("../../etc/passwd.txt", content, "text/plain")}
        data = {"user_id": self.user_a_id}
        resp = client.post("/api/upload-document", data=data, files=files)
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertEqual(json_data["filename"], "passwd.txt")
        self.assertFalse(os.path.exists("../../etc/passwd.txt"))

    # 20. Admin endpoints require admin session
    def test_20_admin_endpoints_require_admin_session(self):
        """Admin endpoints reject unauthenticated or non-admin requests with HTTP 401."""
        # Unauthenticated
        r1 = self.unauth_client.get("/admin.html")
        self.assertEqual(r1.status_code, 401)
        r2 = self.unauth_client.get("/api/analytics")
        self.assertEqual(r2.status_code, 401)
        r3 = self.unauth_client.get("/api/admin/reviews")
        self.assertEqual(r3.status_code, 401)

        # Non-admin user
        client_a = self._get_client_a()
        r4 = client_a.get("/admin.html")
        self.assertEqual(r4.status_code, 401)
        r5 = client_a.get("/api/analytics")
        self.assertEqual(r5.status_code, 401)
        r6 = client_a.get("/api/admin/reviews")
        self.assertEqual(r6.status_code, 401)

    # 21. Complete user data deletion flow
    def test_21_complete_user_data_deletion_flow(self):
        """Validates granular deletion controls vs full user data deletion."""
        user_del = f"user_del_{uuid.uuid4().hex[:8]}"
        db.create_user(user_del, name="Del User", email=f"{user_del}@example.com", password="del_password")

        # Seed messages, session, memory, adaptation, strategy stats, feedback, document
        sess_id = f"sess_{uuid.uuid4().hex[:8]}"
        db.create_session(sess_id, user_del, title="Del Session")
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        db.save_message(
            message_id=msg_id,
            session_id=sess_id,
            user_id=user_del,
            user_message="User question",
            agent_response="Agent answer",
            intent="general_inquiry",
            sentiment={"label": "neutral", "score": 0.5},
            frustration=0.0,
            latency_ms=15,
        )
        db.set_user_memory(user_del, "User prefers concise python", 1)
        db.set_adaptation_profile(user_del, {"verbosity": 0.3}, interaction_count=4)
        db.record_strategy_feedback(user_del, "code_first", True)
        db.save_feedback(user_del, sess_id, msg_id, True)
        db.save_document(f"doc_{uuid.uuid4().hex[:8]}", user_del, "file.txt", "/path/file.txt", "extracted text")

        # Step A: Clear factual memory only
        db.clear_user_memory(user_del)
        mem = db.get_user_memory(user_del)
        self.assertEqual(mem.get("memory_text"), "")
        # Verify adaptation and session are NOT touched
        self.assertEqual(db.get_adaptation_profile(user_del)["interaction_count"], 4)
        self.assertEqual(len(db.get_sessions_for_user(user_del)), 1)

        # Step B: Reset adaptation profile only
        db.clear_adaptation_profile(user_del)
        self.assertIsNone(db.get_adaptation_profile(user_del))
        # Verify session and document still exist
        self.assertEqual(len(db.get_sessions_for_user(user_del)), 1)
        self.assertEqual(len(db.get_user_documents(user_del)), 1)

        # Step C: Delete session only
        db.delete_session(user_del, sess_id)
        self.assertEqual(len(db.get_sessions_for_user(user_del)), 0)
        self.assertEqual(len(db.get_user_documents(user_del)), 1)

        # Step D: Delete all user data
        db.delete_user_data(user_del)
        self.assertEqual(len(db.get_user_documents(user_del)), 0)
        self.assertEqual(len(db.get_all_messages(user_del)), 0)
        self.assertEqual(db.get_strategy_stats(user_del), {})
        with db.get_conn() as conn:
            fb_count = conn.execute("SELECT COUNT(*) FROM feedback WHERE user_id = ?", (user_del,)).fetchone()[0]
            self.assertEqual(fb_count, 0)

    # 22. Check log redaction for secret sentinels
    def test_22_log_redaction_secrets(self):
        """Asserts structured log_event strips password, token, and secret sentinels."""
        import io
        import logging
        from main import logger, log_event

        sentinel_pass = "TEST_PASSWORD_SECRET"
        sentinel_bearer = "TEST_BEARER_SECRET"
        sentinel_groq = "TEST_GROQ_SECRET"

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger.addHandler(handler)
        try:
            log_event(
                "test_auth_event",
                user_id="user_123",
                password=sentinel_pass,
                token=sentinel_bearer,
                access_token=sentinel_bearer,
                secret=sentinel_groq,
                authorization=f"Bearer {sentinel_bearer}",
                status="success"
            )
            handler.flush()
            output = log_capture.getvalue()

            self.assertNotIn(sentinel_pass, output)
            self.assertNotIn(sentinel_bearer, output)
            self.assertNotIn(sentinel_groq, output)
            self.assertIn("test_auth_event", output)
            self.assertIn("user_123", output)
        finally:
            logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()

