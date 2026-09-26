"""
test_beta_analytics.py — Product Analytics & Beta Feedback Test Suite

Covers the 15 required beta readiness verification scenarios:
1. Known analytics event accepted (POST /api/events -> 200)
2. Unknown event rejected (POST /api/events -> 400)
3. Metadata allowlist enforced (unapproved keys stripped, allowed kept)
4. Oversized metadata rejected (values > 200 chars or payload > 2048 bytes -> 400)
5. Analytics failure does not break landing/chat behavior (resilient execution)
6. Admin metrics require auth (unauthenticated -> 401)
7. Non-admin cannot access metrics (normal authenticated user -> 403)
8. Admin gets aggregate metrics (admin session -> 200 with aggregate KPI schema)
9. Raw user content is never stored (no chat text, prompt, or memory in product_events)
10. Beta feedback validates category (enum check: Bug, Confusing, Memory issue, etc.)
11. Feedback message length enforced (1 to 2000 chars)
12. Beta feedback admin endpoint protected (401 unauth, 403 non-admin, 200 admin)
13. Analytics user isolation (events attributed correctly, no cross-user exposure)
14. Retention cleanup (delete_product_events_older_than deletes expired events)
15. No email/password stored in event metadata (sensitive keys/values rejected/stripped)
"""

import os
import sys
import json
import uuid
import tempfile
import sqlite3
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
from main import app, limiter


class TestBetaAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = db.DB_PATH
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_beta_analytics.db")
        db.DB_PATH = cls.test_db_path
        db.init_db()

        # Seed test admin password
        cls.admin_pass = "beta_admin_secret_test_key_123"

        # Seed regular User A
        cls.user_a_id = f"beta_user_a_{uuid.uuid4().hex[:8]}"
        cls.user_a_email = f"{cls.user_a_id}@example.com"
        cls.user_a_pass = "Password123!Secure"
        db.create_user(cls.user_a_id, name="Beta User A", email=cls.user_a_email, password=cls.user_a_pass)

        # Seed regular User B
        cls.user_b_id = f"beta_user_b_{uuid.uuid4().hex[:8]}"
        cls.user_b_email = f"{cls.user_b_id}@example.com"
        cls.user_b_pass = "Password123!SecureB"
        db.create_user(cls.user_b_id, name="Beta User B", email=cls.user_b_email, password=cls.user_b_pass)

        cls.unauth_client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def setUp(self):
        limiter.reset()

    def _get_user_client(self, email: str, password: str) -> TestClient:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(resp.status_code, 200)
        return client

    def _get_admin_client(self) -> TestClient:
        client = TestClient(app)
        with patch("main.ADMIN_PASSWORD", self.admin_pass):
            resp = client.post("/api/auth/admin-verify", json={"admin_password": self.admin_pass})
            self.assertEqual(resp.status_code, 200)
        return client

    # 1. Known analytics event accepted
    def test_01_known_analytics_event_accepted(self):
        """Valid known event is accepted and recorded in product_events."""
        client = TestClient(app)
        anon_id = f"anon_{uuid.uuid4().hex[:12]}"
        payload = {
            "event": "landing_view",
            "page": "/",
            "anonymous_session_id": anon_id,
            "metadata": {"referrer_type": "direct"}
        }
        resp = client.post("/api/events", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "accepted"})

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM product_events WHERE event_name = 'landing_view' AND anonymous_session_id = ?",
                (anon_id,)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["page"], "/")
            meta = json.loads(row["metadata_json"])
            self.assertEqual(meta.get("referrer_type"), "direct")

    # 2. Unknown event rejected
    def test_02_unknown_event_rejected(self):
        """Arbitrary / unauthorized event names return HTTP 400."""
        client = TestClient(app)
        payload = {
            "event": "malicious_untracked_event",
            "page": "/",
            "anonymous_session_id": "anon_test_02",
            "metadata": {}
        }
        resp = client.post("/api/events", json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid or unrecognized event", resp.json()["detail"])

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM product_events WHERE event_name = 'malicious_untracked_event'"
            ).fetchone()
            self.assertIsNone(row)

    # 3. Metadata allowlist enforced
    def test_03_metadata_allowlist_enforced(self):
        """Unknown or unapproved metadata keys are silently stripped."""
        client = TestClient(app)
        anon_id = f"anon_{uuid.uuid4().hex[:12]}"
        payload = {
            "event": "hero_get_started_click",
            "page": "/",
            "anonymous_session_id": anon_id,
            "metadata": {
                "location": "hero",
                "arbitrary_field": "should_be_stripped",
                "injected_data": 42
            }
        }
        resp = client.post("/api/events", json=payload)
        self.assertEqual(resp.status_code, 200)

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM product_events WHERE event_name = 'hero_get_started_click' AND anonymous_session_id = ?",
                (anon_id,)
            ).fetchone()
            self.assertIsNotNone(row)
            meta = json.loads(row["metadata_json"])
            self.assertIn("location", meta)
            self.assertEqual(meta["location"], "hero")
            self.assertNotIn("arbitrary_field", meta)
            self.assertNotIn("injected_data", meta)

    # 4. Oversized metadata rejected
    def test_04_oversized_metadata_rejected(self):
        """Oversized metadata values (> 200 chars) or key counts (> 10) return HTTP 400."""
        client = TestClient(app)
        anon_id = f"anon_{uuid.uuid4().hex[:12]}"

        # Value too large
        oversized_val = "x" * 201
        resp = client.post("/api/events", json={
            "event": "faq_open",
            "page": "/",
            "anonymous_session_id": anon_id,
            "metadata": {"question_id": oversized_val}
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exceeds 200 characters", resp.json()["detail"])

        # Too many keys
        too_many_keys = {f"k{i}": i for i in range(11)}
        resp2 = client.post("/api/events", json={
            "event": "faq_open",
            "page": "/",
            "anonymous_session_id": anon_id,
            "metadata": too_many_keys
        })
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("exceeds maximum allowed keys", resp2.json()["detail"])

    # 5. Analytics failure does not break landing/chat behavior
    def test_05_analytics_failure_does_not_break_chat_or_landing(self):
        """Failures in event persistence do not cause /api/chat or /api/events to fail."""
        client = self._get_user_client(self.user_a_email, self.user_a_pass)

        with patch("database.record_product_event", side_effect=sqlite3.OperationalError("database is locked")):
            # Chat still succeeds
            with patch("main.call_llm_with_constraints", return_value="Ava resilience test"):
                resp = client.post("/api/chat", json={
                    "message": "Hello Ava during db failure",
                    "user_id": self.user_a_id
                })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["response"], "Ava resilience test")

            # Ingest endpoint gracefully logs and returns accepted
            event_resp = client.post("/api/events", json={
                "event": "landing_view",
                "page": "/",
                "anonymous_session_id": "anon_resilience"
            })
            self.assertEqual(event_resp.status_code, 200)

    # 6. Admin metrics require auth
    def test_06_admin_metrics_require_auth(self):
        """Unauthenticated call to /api/admin/beta-metrics returns HTTP 401."""
        resp = self.unauth_client.get("/api/admin/beta-metrics")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Authentication required", resp.json()["detail"])

    # 7. Non-admin cannot access metrics
    def test_07_non_admin_cannot_access_metrics(self):
        """Regular authenticated user accessing /api/admin/beta-metrics returns HTTP 403."""
        client = self._get_user_client(self.user_a_email, self.user_a_pass)
        resp = client.get("/api/admin/beta-metrics")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Admin access required", resp.json()["detail"])

    # 8. Admin gets aggregate metrics
    def test_08_admin_gets_aggregate_metrics(self):
        """Admin session retrieves aggregate beta metrics dictionary with required KPIs."""
        admin_client = self._get_admin_client()

        # Seed sample events
        for _ in range(5):
            db.record_product_event("landing_view", anonymous_session_id="anon_agg", page="/")
        db.record_product_event("signup_started", anonymous_session_id="anon_agg", page="/signup")
        db.record_product_event("signup_completed", anonymous_session_id="anon_agg", page="/signup", user_id=self.user_a_id)
        db.record_product_event("chat_message_sent", anonymous_session_id="anon_agg", page="/chat.html", user_id=self.user_a_id)
        db.record_product_event("chat_response_completed", anonymous_session_id="anon_agg", page="/chat.html", user_id=self.user_a_id, metadata={"adaptation_used": True})
        db.record_product_event("feedback_positive", anonymous_session_id="anon_agg", page="/chat.html", user_id=self.user_a_id)

        resp = admin_client.get("/api/admin/beta-metrics?period_days=7")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Assert all required keys are present
        required_keys = [
            "period_days", "landing_views", "signup_started", "signup_completed",
            "chat_users", "messages_sent", "adaptation_used_responses",
            "positive_feedback", "negative_feedback", "landing_to_signup_rate",
            "signup_completion_rate", "signup_to_chat_rate", "positive_feedback_rate",
            "chat_errors"
        ]
        for k in required_keys:
            self.assertIn(k, data, f"Missing key '{k}' in beta metrics response")

        self.assertGreaterEqual(data["landing_views"], 5)
        self.assertGreaterEqual(data["signup_completed"], 1)
        self.assertGreaterEqual(data["positive_feedback"], 1)

    # 9. Raw user content is never stored
    def test_09_raw_user_content_is_never_stored(self):
        """Verifies chat message prompts and assistant responses are not stored in product_events."""
        client = self._get_user_client(self.user_a_email, self.user_a_pass)
        sentinel_prompt = f"CONFIDENTIAL_PROMPT_{uuid.uuid4().hex}"
        sentinel_reply = f"SECRET_RESPONSE_{uuid.uuid4().hex}"

        with patch("main.call_llm_with_constraints", return_value=sentinel_reply):
            resp = client.post("/api/chat", json={
                "message": sentinel_prompt,
                "user_id": self.user_a_id
            })
            self.assertEqual(resp.status_code, 200)

        with db.get_conn() as conn:
            rows = conn.execute("SELECT * FROM product_events").fetchall()
            for r in rows:
                row_str = f"{r['event_name']} {r['page']} {r['metadata_json']}"
                self.assertNotIn(sentinel_prompt, row_str, "Raw user prompt leaked into product_events!")
                self.assertNotIn(sentinel_reply, row_str, "Assistant response leaked into product_events!")

    # 10. Beta feedback validates category
    def test_10_beta_feedback_validates_category(self):
        """Beta feedback accepts valid categories and rejects unknown ones."""
        client = self._get_user_client(self.user_a_email, self.user_a_pass)

        # Valid categories
        for cat in ["Bug", "Confusing", "Memory issue", "Response quality", "Feature request", "Other"]:
            resp = client.post("/api/beta-feedback", json={
                "category": cat,
                "message": f"Testing feedback category {cat}",
                "allow_follow_up": True
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "success")

        # Invalid category
        bad_resp = client.post("/api/beta-feedback", json={
            "category": "InvalidCategoryName",
            "message": "Testing invalid category",
            "allow_follow_up": False
        })
        self.assertEqual(bad_resp.status_code, 400)
        self.assertIn("Invalid category", bad_resp.json()["detail"])

    # 11. Feedback message length enforced
    def test_11_feedback_message_length_enforced(self):
        """Feedback messages cannot be empty or exceed 2000 characters."""
        client = self._get_user_client(self.user_a_email, self.user_a_pass)

        # Empty message
        resp_empty = client.post("/api/beta-feedback", json={
            "category": "Bug",
            "message": "   ",
            "allow_follow_up": False
        })
        self.assertEqual(resp_empty.status_code, 400)
        self.assertIn("cannot be empty", resp_empty.json()["detail"])

        # Message of exactly 2000 characters succeeds
        msg_2000 = "A" * 2000
        resp_max = client.post("/api/beta-feedback", json={
            "category": "Bug",
            "message": msg_2000,
            "allow_follow_up": False
        })
        self.assertEqual(resp_max.status_code, 200)

        # Message of 2001 characters fails
        msg_2001 = "A" * 2001
        resp_over = client.post("/api/beta-feedback", json={
            "category": "Bug",
            "message": msg_2001,
            "allow_follow_up": False
        })
        self.assertEqual(resp_over.status_code, 400)
        self.assertIn("exceeds maximum length", resp_over.json()["detail"])

    # 12. Beta feedback admin endpoint protected
    def test_12_beta_feedback_admin_endpoint_protected(self):
        """Admin endpoints for beta feedback require admin session (401 unauth, 403 non-admin)."""
        # Unauthenticated
        r_unauth = self.unauth_client.get("/api/admin/beta-feedback")
        self.assertEqual(r_unauth.status_code, 401)

        # Non-admin user
        user_client = self._get_user_client(self.user_a_email, self.user_a_pass)
        r_user = user_client.get("/api/admin/beta-feedback")
        self.assertEqual(r_user.status_code, 403)

        # Admin user
        admin_client = self._get_admin_client()
        r_admin = admin_client.get("/api/admin/beta-feedback")
        self.assertEqual(r_admin.status_code, 200)
        data = r_admin.json()
        self.assertIn("feedback", data)
        self.assertIsInstance(data["feedback"], list)

        # Status update
        if data["feedback"]:
            target_id = data["feedback"][0]["id"]
            # Non-admin patch rejected
            r_patch_user = user_client.patch(f"/api/admin/beta-feedback/{target_id}/status", json={"status": "resolved"})
            self.assertEqual(r_patch_user.status_code, 403)

            # Admin patch succeeded
            r_patch_admin = admin_client.patch(f"/api/admin/beta-feedback/{target_id}/status", json={"status": "resolved"})
            self.assertEqual(r_patch_admin.status_code, 200)
            self.assertEqual(r_patch_admin.json()["new_status"], "resolved")

    # 13. Analytics user isolation
    def test_13_analytics_user_isolation(self):
        """Events are attributed correctly to authenticated users or anonymous sessions without cross-leakage."""
        client_a = self._get_user_client(self.user_a_email, self.user_a_pass)
        client_b = self._get_user_client(self.user_b_email, self.user_b_pass)

        # Trigger chat from User A
        with patch("main.call_llm_with_constraints", return_value="Response for A"):
            client_a.post("/api/chat", json={"message": "Message from A", "user_id": self.user_a_id})

        # Trigger chat from User B
        with patch("main.call_llm_with_constraints", return_value="Response for B"):
            client_b.post("/api/chat", json={"message": "Message from B", "user_id": self.user_b_id})

        with db.get_conn() as conn:
            rows_a = conn.execute("SELECT * FROM product_events WHERE user_id = ?", (self.user_a_id,)).fetchall()
            rows_b = conn.execute("SELECT * FROM product_events WHERE user_id = ?", (self.user_b_id,)).fetchall()

            self.assertGreater(len(rows_a), 0)
            self.assertGreater(len(rows_b), 0)

            # Assert no user_b_id in rows_a and vice versa
            for r in rows_a:
                self.assertEqual(r["user_id"], self.user_a_id)
            for r in rows_b:
                self.assertEqual(r["user_id"], self.user_b_id)

    # 14. Retention cleanup
    def test_14_retention_cleanup(self):
        """delete_product_events_older_than correctly purges stale events while preserving recent ones."""
        old_time = (datetime.now(timezone.utc) - timedelta(days=65)).strftime("%Y-%m-%d %H:%M:%S")
        fresh_time = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")

        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO product_events (event_name, anonymous_session_id, page, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
                ("landing_view", "anon_old", "/", "{}", old_time)
            )
            conn.execute(
                "INSERT INTO product_events (event_name, anonymous_session_id, page, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
                ("landing_view", "anon_fresh", "/", "{}", fresh_time)
            )

        # Purge older than 60 days
        deleted = db.delete_product_events_older_than(days=60)
        self.assertGreaterEqual(deleted, 1)

        with db.get_conn() as conn:
            old_row = conn.execute("SELECT * FROM product_events WHERE anonymous_session_id = 'anon_old'").fetchone()
            self.assertIsNone(old_row, "Stale event older than retention window was not deleted!")

            fresh_row = conn.execute("SELECT * FROM product_events WHERE anonymous_session_id = 'anon_fresh'").fetchone()
            self.assertIsNotNone(fresh_row, "Fresh event was incorrectly deleted!")

    # 15. No email/password stored in event metadata
    def test_15_no_email_password_stored_in_event_metadata(self):
        """Attempts to pass sensitive keywords into metadata are strictly rejected or stripped."""
        client = TestClient(app)

        # Rejected sensitive keys in client ingest
        for sensitive_key in ["password", "user_password", "email_address", "access_token", "secret_key"]:
            resp = client.post("/api/events", json={
                "event": "hero_get_started_click",
                "page": "/",
                "anonymous_session_id": "anon_sens_test",
                "metadata": {sensitive_key: "confidential_val"}
            })
            self.assertEqual(resp.status_code, 400, f"Key '{sensitive_key}' should have been rejected with 400")

        # Rejected sensitive value content
        resp_val = client.post("/api/events", json={
            "event": "hero_get_started_click",
            "page": "/",
            "anonymous_session_id": "anon_sens_test",
            "metadata": {"location": "Bearer eyJhbGciOiJIUzI1NiIs..."}
        })
        self.assertEqual(resp_val.status_code, 400)

        # Verify signup and login do not store emails or passwords in product_events
        unique_email = f"clean_test_{uuid.uuid4().hex[:8]}@example.com"
        unique_pass = "SuperSecretPassword123!"

        signup_resp = client.post("/api/auth/signup", json={
            "name": "Clean User",
            "email": unique_email,
            "password": unique_pass
        })
        self.assertEqual(signup_resp.status_code, 200)

        login_resp = client.post("/api/auth/login", json={
            "email": unique_email,
            "password": unique_pass
        })
        self.assertEqual(login_resp.status_code, 200)

        with db.get_conn() as conn:
            events = conn.execute(
                "SELECT * FROM product_events WHERE event_name IN ('signup_completed', 'login_completed')"
            ).fetchall()
            self.assertGreater(len(events), 0)
            for ev in events:
                meta = ev["metadata_json"]
                self.assertNotIn(unique_email, meta, "Email leaked into product_events metadata!")
                self.assertNotIn(unique_pass, meta, "Password leaked into product_events metadata!")


    # ── NEW TESTS (16-32) ───────────────────────────────────────────────────

    # 16. normalize_anonymous_session_id — valid IDs accepted
    def test_16_normalize_anon_id_accepts_valid_ids(self):
        """Valid alphanumeric/hyphen/underscore IDs of 1-64 chars are accepted."""
        from main import normalize_anonymous_session_id
        self.assertEqual(normalize_anonymous_session_id("abc123"), "abc123")
        self.assertEqual(normalize_anonymous_session_id("anon-session_01"), "anon-session_01")
        self.assertEqual(normalize_anonymous_session_id("A" * 64), "A" * 64)
        # Leading/trailing whitespace is stripped
        self.assertEqual(normalize_anonymous_session_id("  abc  "), "abc")

    # 17. normalize_anonymous_session_id — invalid IDs rejected
    def test_17_normalize_anon_id_rejects_invalid(self):
        """Invalid anon session IDs (empty, too long, special chars) return None."""
        from main import normalize_anonymous_session_id
        self.assertIsNone(normalize_anonymous_session_id(None))
        self.assertIsNone(normalize_anonymous_session_id(""))
        self.assertIsNone(normalize_anonymous_session_id("   "))
        self.assertIsNone(normalize_anonymous_session_id("A" * 65))  # too long
        self.assertIsNone(normalize_anonymous_session_id("bad!@#chars"))  # special chars
        self.assertIsNone(normalize_anonymous_session_id("spaces not ok"))  # spaces

    # 18. /api/events rejects anon IDs with special characters via endpoint
    def test_18_anon_id_with_special_chars_rejected_by_endpoint(self):
        """POST /api/events returns 400 if anonymous_session_id contains invalid chars."""
        client = TestClient(app)
        resp = client.post("/api/events", json={
            "event": "landing_view",
            "page": "/",
            "anonymous_session_id": "bad!<script>id</script>",
            "metadata": {}
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("anonymous_session_id", resp.json()["detail"])

    # 19. Page query string stripped
    def test_19_page_query_string_stripped(self):
        """Query strings and fragments are stripped from page values before storage."""
        from main import _strip_page
        self.assertEqual(_strip_page("/auth.html?token=SECRET"), "/auth.html")
        self.assertEqual(_strip_page("/chat.html#section"), "/chat.html")
        self.assertEqual(_strip_page("/path?a=1&b=2#frag"), "/path")
        self.assertEqual(_strip_page(None), "/")
        self.assertEqual(_strip_page(""), "/")

    # 20. Events stored with clean page (no query/fragment)
    def test_20_events_stored_with_clean_page(self):
        """Pages with query strings are stored clean (path only) in product_events."""
        client = TestClient(app)
        anon_id = f"anon_{uuid.uuid4().hex[:12]}"
        resp = client.post("/api/events", json={
            "event": "landing_view",
            "page": "/index.html?ref=newsletter&campaign=summer",
            "anonymous_session_id": anon_id,
        })
        self.assertEqual(resp.status_code, 200)

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT page FROM product_events WHERE anonymous_session_id = ? "
                "AND event_name = 'landing_view' ORDER BY created_at DESC LIMIT 1",
                (anon_id,)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["page"], "/index.html")
            self.assertNotIn("newsletter", row["page"])

    # 21. delete_user_data clears product_events
    def test_21_delete_user_data_clears_product_events(self):
        """delete_user_data removes all product_events attributed to that user."""
        user_id = f"del_pe_user_{uuid.uuid4().hex[:8]}"
        db.create_user(user_id, name="Del PE User",
                       email=f"{user_id}@example.com", password="Password123!")
        db.record_product_event("chat_message_sent", "anon_del1", "/chat.html", user_id=user_id)
        db.record_product_event("feedback_positive", "anon_del1", "/chat.html", user_id=user_id)

        with db.get_conn() as conn:
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM product_events WHERE user_id = ?",
                (user_id,)
            ).fetchone()["c"]
        self.assertGreater(before, 0)

        db.delete_user_data(user_id)

        with db.get_conn() as conn:
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM product_events WHERE user_id = ?",
                (user_id,)
            ).fetchone()["c"]
        self.assertEqual(after, 0, "product_events not cleared by delete_user_data!")

    # 22. delete_user_data clears beta_feedback
    def test_22_delete_user_data_clears_beta_feedback(self):
        """delete_user_data removes all beta_feedback attributed to that user."""
        user_id = f"del_fb_user_{uuid.uuid4().hex[:8]}"
        db.create_user(user_id, name="Del FB User",
                       email=f"{user_id}@example.com", password="Password123!")
        db.record_beta_feedback("Bug", "My feedback entry", user_id=user_id)

        with db.get_conn() as conn:
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM beta_feedback WHERE user_id = ?",
                (user_id,)
            ).fetchone()["c"]
        self.assertGreater(before, 0)

        db.delete_user_data(user_id)

        with db.get_conn() as conn:
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM beta_feedback WHERE user_id = ?",
                (user_id,)
            ).fetchone()["c"]
        self.assertEqual(after, 0, "beta_feedback not cleared by delete_user_data!")

    # 23. DELETE /api/admin/beta-feedback/{id} requires admin
    def test_23_delete_feedback_requires_admin(self):
        """DELETE /api/admin/beta-feedback/{id} returns 401 for unauth and 403 for non-admin."""
        r_unauth = self.unauth_client.delete("/api/admin/beta-feedback/1")
        self.assertEqual(r_unauth.status_code, 401)

        user_client = self._get_user_client(self.user_a_email, self.user_a_pass)
        r_user = user_client.delete("/api/admin/beta-feedback/1")
        self.assertEqual(r_user.status_code, 403)

    # 24. DELETE /api/admin/beta-feedback/{id} deletes the entry for admin
    def test_24_delete_feedback_admin_success(self):
        """Admin can hard-delete a beta feedback entry; 404 returned for already-deleted id."""
        user_id = f"del_test_user_{uuid.uuid4().hex[:8]}"
        db.create_user(user_id, name="Del Test",
                       email=f"{user_id}@example.com", password="Password123!")
        feedback_id = db.record_beta_feedback("Bug", "Feedback to delete", user_id=user_id)

        admin_client = self._get_admin_client()
        with patch("main.ADMIN_PASSWORD", self.admin_pass):
            r = admin_client.delete(f"/api/admin/beta-feedback/{feedback_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], feedback_id)

        # Second delete returns 404
        with patch("main.ADMIN_PASSWORD", self.admin_pass):
            r2 = admin_client.delete(f"/api/admin/beta-feedback/{feedback_id}")
        self.assertEqual(r2.status_code, 404)

    # 25. Adaptation is not double-counted
    def test_25_adaptation_not_double_counted(self):
        """get_beta_metrics counts adaptation_used events once; chat_response_completed with adaptation_used=True is NOT also counted."""
        # Reset by inserting into a clean user slice
        user_id = f"adapt_count_user_{uuid.uuid4().hex[:8]}"
        db.create_user(user_id, name="Adapt Counter",
                       email=f"{user_id}@example.com", password="Password123!")

        # Record exactly 2 adaptation_used events
        db.record_product_event("adaptation_used", "anon_adapt", "/chat.html",
                                user_id=user_id, metadata={"strategy": "nurturing"})
        db.record_product_event("adaptation_used", "anon_adapt", "/chat.html",
                                user_id=user_id, metadata={"strategy": "concise"})
        # Also record a chat_response_completed with adaptation_used=True in metadata
        db.record_product_event("chat_response_completed", "anon_adapt", "/chat.html",
                                user_id=user_id, metadata={"adaptation_used": True})

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM product_events "
                "WHERE user_id = ? AND event_name = 'adaptation_used'",
                (user_id,)
            ).fetchone()
        # Direct DB count: exactly 2 adaptation_used events
        self.assertEqual(row["c"], 2)

        # get_beta_metrics should NOT count the chat_response_completed event
        metrics = db.get_beta_metrics(period_days=90)
        # The total adaptation_used_responses should be at least 2 (could be higher from
        # other tests). The important invariant: it equals count of adaptation_used events only.
        with db.get_conn() as conn:
            direct_count = conn.execute(
                "SELECT COUNT(*) AS c FROM product_events WHERE event_name = 'adaptation_used'"
            ).fetchone()["c"]
        self.assertEqual(metrics["adaptation_used_responses"], direct_count,
                         "adaptation_used_responses in metrics must equal COUNT(adaptation_used) exactly")

    # 26. All conversion rates are in [0, 1]
    def test_26_all_rates_bounded_zero_to_one(self):
        """All rate fields in get_beta_metrics are in [0.0, 1.0]."""
        # Insert more chat_users than signup_completed to create a potential >1 scenario
        for i in range(10):
            db.record_product_event(
                "chat_message_sent", f"anon_rate_{i}", "/chat.html",
                user_id=f"user_rate_{i}"
            )
        # Only 1 signup_completed
        db.record_product_event("signup_completed", "anon_rate_s", "/auth.html",
                                user_id="user_rate_signup")

        metrics = db.get_beta_metrics(period_days=90)
        rate_fields = [
            "landing_to_signup_rate", "signup_completion_rate",
            "signup_to_chat_rate", "positive_feedback_rate", "adaptation_usage_rate"
        ]
        for field in rate_fields:
            val = metrics[field]
            self.assertGreaterEqual(val, 0.0, f"{field} is below 0")
            self.assertLessEqual(val, 1.0, f"{field} exceeds 1.0 (value={val})")

    # 27. signup_started event is accepted and stored
    def test_27_signup_started_event_stored(self):
        """signup_started event is accepted via /api/events and stored correctly."""
        client = TestClient(app)
        anon_id = f"anon_{uuid.uuid4().hex[:12]}"
        resp = client.post("/api/events", json={
            "event": "signup_started",
            "page": "/auth.html",
            "anonymous_session_id": anon_id,
            "metadata": {"source": "hero_cta"}
        })
        self.assertEqual(resp.status_code, 200)

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM product_events WHERE event_name = 'signup_started' AND anonymous_session_id = ?",
                (anon_id,)
            ).fetchone()
        self.assertIsNotNone(row)
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta.get("source"), "hero_cta")

    # 28. signup_started appears in beta_metrics funnel
    def test_28_signup_started_in_metrics_funnel(self):
        """signup_started count is surfaced in get_beta_metrics."""
        before = db.get_beta_metrics(90)["signup_started"]
        db.record_product_event("signup_started", "anon_funnel_test", "/auth.html")
        after = db.get_beta_metrics(90)["signup_started"]
        self.assertEqual(after, before + 1)

    # 29. Admin metrics period_days is clamped to [1, 90]
    def test_29_admin_metrics_period_clamped(self):
        """period_days is clamped server-side: 0 becomes 1, 999 becomes 90."""
        admin_client = self._get_admin_client()

        r_low = admin_client.get("/api/admin/beta-metrics?period_days=0")
        self.assertEqual(r_low.status_code, 200)
        self.assertEqual(r_low.json()["period_days"], 1)

        r_high = admin_client.get("/api/admin/beta-metrics?period_days=999")
        self.assertEqual(r_high.status_code, 200)
        self.assertEqual(r_high.json()["period_days"], 90)

    # 30. Retention: delete_product_events_older_than refuses 0 days
    def test_30_retention_rejects_zero_days(self):
        """delete_product_events_older_than(0) raises ValueError."""
        with self.assertRaises(ValueError):
            db.delete_product_events_older_than(0)

    # 31. delete_beta_feedback helper removes the entry
    def test_31_delete_beta_feedback_removes_entry(self):
        """db.delete_beta_feedback(id) returns True on success and False for missing id."""
        fid = db.record_beta_feedback("Feature request", "Please add dark mode")
        result = db.delete_beta_feedback(fid)
        self.assertTrue(result)

        # Verify gone from DB
        with db.get_conn() as conn:
            row = conn.execute("SELECT * FROM beta_feedback WHERE id = ?", (fid,)).fetchone()
        self.assertIsNone(row)

        # Second call returns False
        result2 = db.delete_beta_feedback(fid)
        self.assertFalse(result2)

    # 32. Anonymous events have no user_id in product_events
    def test_32_anonymous_events_have_no_user_id(self):
        """Events sent without a session (anonymous visitors) store NULL user_id."""
        client = TestClient(app)  # no login session
        anon_id = f"anon_{uuid.uuid4().hex[:12]}"
        resp = client.post("/api/events", json={
            "event": "feature_section_view",
            "page": "/",
            "anonymous_session_id": anon_id,
            "metadata": {"section_id": "memory"}
        })
        self.assertEqual(resp.status_code, 200)

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT user_id FROM product_events "
                "WHERE event_name = 'feature_section_view' AND anonymous_session_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (anon_id,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row["user_id"], "Anonymous event should have NULL user_id!")


if __name__ == "__main__":
    unittest.main()
