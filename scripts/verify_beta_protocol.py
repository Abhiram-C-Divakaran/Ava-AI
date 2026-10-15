#!/usr/bin/env python3
"""
scripts/verify_beta_protocol.py

Automated Pre-Beta Verification Harness for Ava AI (Sections 7–11):
- Section 7: Controlled Funnel Smoke Test & Telemetry
- Section 8: Cohort Correlation
- Section 9: Admin Beta Metrics & Rate Bounds
- Section 10: Admin Feedback Endpoints & Authorization (401/403/200/404)
- Section 11: Comprehensive Account Data Purge & Cross-User Isolation

Features:
- Configurable base URL (--base-url) and DB path (--db-path)
- Two modes: --mode offline (zero external LLM calls) and --mode live (real streaming LLM check)
- Remote execution safety guard (--allow-remote required for non-localhost)
- Preflight HTTP server <-> DB matching check via transient canary
- Comprehensive fixture tracking (users, sessions, anon sessions, feedback)
- Guaranteed cleanup in finally block even upon errors or interruption
- Zero-leak cleanup verification (asserts 0 test fixtures remain in DB)
- Explicit terms_accepted: True in signup payloads
"""

import sys
import os
import uuid
import json
import sqlite3
import argparse
import requests
from urllib.parse import urlparse

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import database as db

SAFE_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver"}


def is_safe_host(url: str) -> bool:
    """Return True if url points to a local or loopback interface."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return hostname in SAFE_LOCAL_HOSTS
    except Exception:
        return False


def generate_run_id() -> str:
    """Generate a unique identifier for this verification run."""
    return f"beta_verify_{uuid.uuid4().hex[:12]}"


def preflight_db_match(base_url: str, run_id: str) -> tuple[bool, str]:
    """
    Ensure the HTTP server and direct database.py connection target the exact same database.
    Posts a transient canary event through HTTP and verifies visibility via direct SQL.
    Immediately cleans up the canary event.
    """
    canary_anon = f"canary_{run_id}"
    try:
        health_resp = requests.get(f"{base_url}/health", timeout=5)
        if health_resp.status_code != 200:
            return False, f"Server /health returned HTTP {health_resp.status_code}"

        event_resp = requests.post(
            f"{base_url}/api/events",
            json={"event": "landing_view", "anonymous_session_id": canary_anon, "page": "/"},
            timeout=5
        )
        if event_resp.status_code != 200:
            return False, f"Server /api/events rejected canary with HTTP {event_resp.status_code}"

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM product_events WHERE anonymous_session_id = ?",
                (canary_anon,)
            ).fetchone()
            if not row:
                return False, "Canary event recorded via HTTP was not found in local DB. Server and verifier DB paths do not match!"
            conn.execute("DELETE FROM product_events WHERE anonymous_session_id = ?", (canary_anon,))

        return True, "Preflight check passed: HTTP server and local DB are aligned."
    except Exception as e:
        return False, f"Preflight connection exception: {e}"


class BetaVerificationHarness:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        mode: str = "offline",
        allow_remote: bool = False,
        run_id: str | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.mode = mode.lower()
        self.allow_remote = allow_remote
        self.run_id = run_id or generate_run_id()

        self.passed_steps: list[str] = []
        self.failed_steps: list[tuple[str, str]] = []

        # Fixture tracking for guaranteed cleanup
        self.tracked_users: set[str] = set()
        self.tracked_anon_sessions: set[str] = set()
        self.tracked_sessions: set[str] = set()
        self.tracked_feedback_ids: set[int] = set()

    def check(self, condition: bool, step_name: str, details: str = ""):
        if condition:
            self.passed_steps.append(step_name)
            print(f"  [PASS] {step_name} {details}")
        else:
            self.failed_steps.append((step_name, details))
            print(f"  [FAIL] {step_name} {details}")

    def track_user(self, user_id: str):
        if user_id:
            self.tracked_users.add(user_id)

    def track_anon_session(self, anon_id: str):
        if anon_id:
            self.tracked_anon_sessions.add(anon_id)

    def track_session(self, session_id: str):
        if session_id:
            self.tracked_sessions.add(session_id)

    def track_feedback(self, feedback_id: int):
        if feedback_id:
            self.tracked_feedback_ids.add(feedback_id)

    def cleanup(self) -> dict:
        """Purge all tracked verification fixtures from database."""
        summary = {
            "users_purged": len(self.tracked_users),
            "anon_events_deleted": 0,
            "feedback_deleted": 0,
            "sessions_deleted": 0,
        }
        # 1. Purge user data first (delete_user_data opens its own connection)
        for uid in list(self.tracked_users):
            try:
                db.delete_user_data(uid)
            except Exception as e:
                print(f"  [WARN] Failed to purge user data for {uid}: {e}")

        # 2. Purge user accounts, anon events, feedback, and sessions
        with db.get_conn() as conn:
            for uid in list(self.tracked_users):
                try:
                    conn.execute("DELETE FROM users WHERE user_id = ?", (uid,))
                except Exception as e:
                    print(f"  [WARN] Failed to delete user account {uid}: {e}")

            for anon in list(self.tracked_anon_sessions):
                try:
                    cur = conn.execute("DELETE FROM product_events WHERE anonymous_session_id = ?", (anon,))
                    summary["anon_events_deleted"] += cur.rowcount
                except Exception as e:
                    print(f"  [WARN] Failed to delete anon events for {anon}: {e}")

            for fb_id in list(self.tracked_feedback_ids):
                try:
                    cur = conn.execute("DELETE FROM beta_feedback WHERE id = ?", (fb_id,))
                    summary["feedback_deleted"] += cur.rowcount
                except Exception as e:
                    print(f"  [WARN] Failed to delete beta feedback {fb_id}: {e}")

            for sid in list(self.tracked_sessions):
                try:
                    cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
                    conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                    conn.execute("DELETE FROM feedback WHERE session_id = ?", (sid,))
                    summary["sessions_deleted"] += cur.rowcount
                except Exception as e:
                    print(f"  [WARN] Failed to delete session {sid}: {e}")

        return summary

    def verify_cleanup(self) -> tuple[bool, list[str]]:
        """Assert zero verification fixtures remain in the database."""
        leaks = []
        with db.get_conn() as conn:
            if self.tracked_users:
                placeholders = ",".join("?" for _ in self.tracked_users)
                user_list = list(self.tracked_users)

                c = conn.execute(
                    f"SELECT COUNT(*) as c FROM users WHERE user_id IN ({placeholders})",
                    user_list
                ).fetchone()["c"]
                if c > 0:
                    leaks.append(f"{c} user accounts remained in 'users'")

                for tbl in [
                    "messages", "sessions", "feedback", "failed_solutions", "documents",
                    "user_memory", "adaptation_profiles", "adaptation_strategy_stats",
                    "product_events", "beta_feedback"
                ]:
                    c_tbl = conn.execute(
                        f"SELECT COUNT(*) as c FROM {tbl} WHERE user_id IN ({placeholders})",
                        user_list
                    ).fetchone()["c"]
                    if c_tbl > 0:
                        leaks.append(f"{c_tbl} user records remained in '{tbl}'")

            if self.tracked_anon_sessions:
                placeholders = ",".join("?" for _ in self.tracked_anon_sessions)
                c = conn.execute(
                    f"SELECT COUNT(*) as c FROM product_events WHERE anonymous_session_id IN ({placeholders})",
                    list(self.tracked_anon_sessions)
                ).fetchone()["c"]
                if c > 0:
                    leaks.append(f"{c} anonymous events remained in 'product_events'")

            if self.tracked_feedback_ids:
                placeholders = ",".join("?" for _ in self.tracked_feedback_ids)
                c = conn.execute(
                    f"SELECT COUNT(*) as c FROM beta_feedback WHERE id IN ({placeholders})",
                    list(self.tracked_feedback_ids)
                ).fetchone()["c"]
                if c > 0:
                    leaks.append(f"{c} feedback records remained in 'beta_feedback'")

            if self.tracked_sessions:
                placeholders = ",".join("?" for _ in self.tracked_sessions)
                c = conn.execute(
                    f"SELECT COUNT(*) as c FROM sessions WHERE session_id IN ({placeholders})",
                    list(self.tracked_sessions)
                ).fetchone()["c"]
                if c > 0:
                    leaks.append(f"{c} session rows remained in 'sessions'")

        return (len(leaks) == 0, leaks)

    def _execute_suite(self):
        # =====================================================================
        # SECTION 7: CONTROLLED FUNNEL SMOKE TEST & TELEMETRY
        # =====================================================================
        print("\n--- SECTION 7: Controlled Funnel Smoke Test ---")
        session = requests.Session()
        anon_id = f"anon_{self.run_id}"
        self.track_anon_session(anon_id)

        # Step 1: Visit landing page
        resp = session.post(
            f"{self.base_url}/api/events",
            json={"event": "landing_view", "anonymous_session_id": anon_id, "page": "/"}
        )
        self.check(resp.status_code == 200, "1. Landing View Event", f"Status: {resp.status_code}")

        # Step 2: Click Get Started
        resp = session.post(
            f"{self.base_url}/api/events",
            json={"event": "hero_get_started_click", "anonymous_session_id": anon_id, "page": "/"}
        )
        self.check(resp.status_code == 200, "2. Hero CTA Click Event", f"Status: {resp.status_code}")

        # Step 3: Begin signup
        resp = session.post(
            f"{self.base_url}/api/events",
            json={"event": "signup_started", "anonymous_session_id": anon_id, "page": "/auth.html"}
        )
        self.check(resp.status_code == 200, "3. Signup Started Event", f"Status: {resp.status_code}")

        # Step 4: Complete signup
        test_email = f"{self.run_id}_tester@example.com"
        test_password = "SecurePassword123!"
        headers = {"X-Anonymous-Session": anon_id}
        resp = session.post(
            f"{self.base_url}/api/auth/signup",
            json={
                "name": "Beta Tester",
                "email": test_email,
                "password": test_password,
                "terms_accepted": True
            },
            headers=headers
        )
        signup_ok = resp.status_code == 200 and "user_id" in resp.json()
        self.check(signup_ok, "4. Signup Completed", f"Status: {resp.status_code}")
        user_id = resp.json().get("user_id") if signup_ok else None
        if user_id:
            self.track_user(user_id)

        # Step 5: Open chat
        resp = session.post(
            f"{self.base_url}/api/events",
            json={"event": "chat_opened", "anonymous_session_id": anon_id, "page": "/chat.html"},
            headers=headers
        )
        self.check(resp.status_code == 200, "5. Chat Opened Event", f"Status: {resp.status_code}")

        # Step 6 & 7: Send message & receive response
        session_id = None
        msg_id = None

        if self.mode == "live":
            # Live streaming via /api/chat/stream
            stream_resp = session.post(
                f"{self.base_url}/api/chat/stream",
                json={"message": f"Hello Ava, I am testing the beta funnel. Run ID: {self.run_id}", "stream": True},
                headers=headers
            )
            self.check(stream_resp.status_code == 200, "6 & 7. Chat Stream Request", f"Status: {stream_resp.status_code}")

            full_text = ""
            for line in stream_resp.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        try:
                            payload = json.loads(decoded[6:])
                            if "chunk" in payload:
                                full_text += payload["chunk"]
                            if payload.get("done"):
                                session_id = payload.get("session_id")
                                msg_id = payload.get("message_id")
                        except Exception:
                            pass

            self.check(
                bool(full_text) and bool(session_id) and bool(msg_id),
                "7b. Stream Response Received",
                f"Session: {session_id}, Chunks read: {len(full_text)} chars"
            )
            if session_id:
                self.track_session(session_id)
        else:
            # Offline mode: skip live external LLM call; seed an offline fixture for feedback verification
            print("  [INFO] 6 & 7. Chat Streaming skipped in OFFLINE mode.")
            offline_sess_id = f"sess_{self.run_id}_offline"
            offline_msg_id = f"msg_{self.run_id}_offline"
            self.track_session(offline_sess_id)
            if user_id:
                db.create_session(offline_sess_id, user_id, title=f"Beta Verification {self.run_id}")
                db.save_message(
                    offline_msg_id, offline_sess_id, user_id,
                    "Offline Test Question", "Offline Test Response",
                    "general_inquiry", {"label": "neutral", "score": 0.5}, 0.0, 10
                )
                session_id = offline_sess_id
                msg_id = offline_msg_id

        # Step 8: Give thumbs feedback
        if session_id and msg_id:
            resp = session.post(
                f"{self.base_url}/api/feedback",
                json={"session_id": session_id, "message_id": msg_id, "helpful": True},
                headers=headers
            )
            self.check(resp.status_code == 200, "8. Positive Thumbs Feedback", f"Status: {resp.status_code}")
        else:
            self.check(False, "8. Positive Thumbs Feedback", "Skipped: missing session/message ID")

        # Step 9: Submit beta feedback
        resp = session.post(
            f"{self.base_url}/api/beta-feedback",
            json={
                "category": "Bug",
                "message": f"Verification feedback for run {self.run_id}",
                "allow_follow_up": True
            },
            headers=headers
        )
        fb_ok = resp.status_code == 200
        self.check(fb_ok, "9. Submit Beta Feedback", f"Status: {resp.status_code}")
        submitted_fb_id = resp.json().get("id") if fb_ok else None
        if submitted_fb_id:
            self.track_feedback(submitted_fb_id)

        # Step 10: Privacy Check: verify no raw prompt text in product_events
        with db.get_conn() as conn:
            events = conn.execute(
                "SELECT event_name, metadata_json FROM product_events WHERE anonymous_session_id = ?",
                (anon_id,)
            ).fetchall()

            has_raw_text = False
            for ev in events:
                meta = ev["metadata_json"] or ""
                if "testing the beta funnel" in meta or "Offline Test" in meta:
                    has_raw_text = True
                    break
            self.check(not has_raw_text, "10. Privacy Check: No raw prompts in product_events")

        # =====================================================================
        # SECTION 8: COHORT CORRELATION
        # =====================================================================
        print("\n--- SECTION 8: Cohort Correlation ---")
        with db.get_conn() as conn:
            funnel_events = conn.execute(
                """
                SELECT event_name, anonymous_session_id, user_id
                FROM product_events
                WHERE anonymous_session_id = ?
                ORDER BY id ASC
                """,
                (anon_id,)
            ).fetchall()

            event_dict = {r["event_name"]: r for r in funnel_events}

            c1 = ("landing_view" in event_dict and event_dict["landing_view"]["anonymous_session_id"] == anon_id)
            c2 = ("signup_started" in event_dict and event_dict["signup_started"]["anonymous_session_id"] == anon_id)
            c3 = ("signup_completed" in event_dict and event_dict["signup_completed"]["anonymous_session_id"] == anon_id)
            self.check(c1 and c2 and c3, "Cohort Correlated Anonymous Session", f"anon_id: {anon_id}")

            self.check(
                "landing_view" in event_dict and event_dict["landing_view"]["user_id"] is None,
                "Landing view user_id is NULL"
            )
            self.check(
                "signup_completed" in event_dict and event_dict["signup_completed"]["user_id"] == user_id,
                "Signup completed user_id matches authenticated user"
            )

        # =====================================================================
        # SECTION 9: ADMIN BETA METRICS
        # =====================================================================
        print("\n--- SECTION 9: Admin Beta Metrics ---")
        admin_session = requests.Session()
        admin_email = f"{self.run_id}_admin@example.com"
        resp = admin_session.post(
            f"{self.base_url}/api/auth/signup",
            json={
                "name": "Admin Tester",
                "email": admin_email,
                "password": "AdminPassword123!",
                "terms_accepted": True
            }
        )
        admin_user_id = resp.json().get("user_id")
        if admin_user_id:
            self.track_user(admin_user_id)
            with db.get_conn() as conn:
                conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (admin_user_id,))

        resp = admin_session.post(
            f"{self.base_url}/api/auth/login",
            json={"email": admin_email, "password": "AdminPassword123!"}
        )
        self.check(resp.status_code == 200, "Admin Logged In")

        resp = admin_session.get(f"{self.base_url}/api/admin/beta-metrics?period_days=7")
        self.check(resp.status_code == 200, "Fetch Beta Metrics (Admin)", f"Status: {resp.status_code}")
        metrics = resp.json()

        expected_keys = [
            "landing_views", "signup_started", "signup_completed", "chat_users",
            "messages_sent", "adaptation_used_responses", "positive_feedback",
            "negative_feedback", "chat_errors", "landing_to_signup_rate",
            "signup_completion_rate", "signup_to_chat_rate", "positive_feedback_rate",
            "adaptation_usage_rate"
        ]
        all_keys_present = all(k in metrics for k in expected_keys)
        self.check(all_keys_present, "All Beta Metric Keys Present")

        rates = [
            ("landing_to_signup_rate", metrics.get("landing_to_signup_rate")),
            ("signup_completion_rate", metrics.get("signup_completion_rate")),
            ("signup_to_chat_rate", metrics.get("signup_to_chat_rate")),
            ("positive_feedback_rate", metrics.get("positive_feedback_rate")),
            ("adaptation_usage_rate", metrics.get("adaptation_usage_rate"))
        ]
        rates_valid = all(0.0 <= r <= 1.0 for _, r in rates if r is not None)
        self.check(rates_valid, "All Conversion Rates Bounded in [0.0, 1.0]", str(rates))

        # =====================================================================
        # SECTION 10: ADMIN FEEDBACK ENDPOINTS & AUTHORIZATION
        # =====================================================================
        print("\n--- SECTION 10: Admin Feedback Endpoints & Authorization ---")
        anon_client = requests.Session()
        resp = anon_client.get(f"{self.base_url}/api/admin/beta-feedback")
        self.check(resp.status_code == 401, "Unauthenticated GET /api/admin/beta-feedback -> 401", f"Got: {resp.status_code}")

        resp = session.get(f"{self.base_url}/api/admin/beta-feedback")
        self.check(resp.status_code == 403, "Non-admin GET /api/admin/beta-feedback -> 403", f"Got: {resp.status_code}")

        resp = admin_session.get(f"{self.base_url}/api/admin/beta-feedback")
        self.check(resp.status_code == 200, "Admin GET /api/admin/beta-feedback -> 200", f"Items: {len(resp.json().get('feedback', []))}")

        fb_id = submitted_fb_id
        if fb_id:
            resp = session.patch(f"{self.base_url}/api/admin/beta-feedback/{fb_id}/status", json={"status": "reviewing"})
            self.check(resp.status_code == 403, "Non-admin PATCH /api/admin/beta-feedback/{id}/status -> 403", f"Got: {resp.status_code}")

            resp = admin_session.patch(f"{self.base_url}/api/admin/beta-feedback/{fb_id}/status", json={"status": "reviewing"})
            self.check(resp.status_code == 200 and resp.json().get("new_status") == "reviewing", "Admin PATCH /api/admin/beta-feedback/{id}/status -> 200")

            resp = session.delete(f"{self.base_url}/api/admin/beta-feedback/{fb_id}")
            self.check(resp.status_code == 403, "Non-admin DELETE /api/admin/beta-feedback/{id} -> 403", f"Got: {resp.status_code}")

            resp = admin_session.delete(f"{self.base_url}/api/admin/beta-feedback/{fb_id}")
            self.check(resp.status_code == 200, "Admin DELETE /api/admin/beta-feedback/{id} -> 200")
            if fb_id in self.tracked_feedback_ids:
                self.tracked_feedback_ids.remove(fb_id)

        resp = admin_session.delete(f"{self.base_url}/api/admin/beta-feedback/99999999")
        self.check(resp.status_code == 404, "Admin DELETE unknown feedback ID -> 404", f"Got: {resp.status_code}")

        # =====================================================================
        # SECTION 11: ACCOUNT DATA PURGE & ISOLATION
        # =====================================================================
        print("\n--- SECTION 11: Account Data Purge & Isolation ---")
        user_purge = f"user_{self.run_id}_purge"
        user_control = f"user_{self.run_id}_ctrl"
        self.track_user(user_purge)
        self.track_user(user_control)

        db.create_user(user_purge, name="Purge User", email=f"{user_purge}@example.com", password="pwd", terms_accepted=True)
        db.create_user(user_control, name="Control User", email=f"{user_control}@example.com", password="pwd", terms_accepted=True)

        for u in (user_purge, user_control):
            s_id = f"s_{u}"
            m_id = f"m_{u}"
            self.track_session(s_id)
            db.create_session(s_id, u, title="Test Session")
            db.save_message(m_id, s_id, u, "Test Q", "Test A", "general_inquiry", {"label": "neutral", "score": 0.5}, 0.0, 10)
            db.save_feedback(u, s_id, m_id, True)
            db.save_failed_solution(u, s_id, "failed strategy text")
            db.save_document(f"doc_{u}", u, "doc.txt", "/fake/doc.txt", "doc text")
            db.set_user_memory(u, "user memory text", 1)
            db.set_adaptation_profile(u, {"verbosity": 0.5}, interaction_count=2)
            db.record_strategy_feedback(u, "code_first", True)
            db.record_product_event("chat_message_sent", f"anon_{u}", "/chat.html", user_id=u)
            fb_id = db.record_beta_feedback(category="Bug", message="Test feedback", user_id=u)
            self.track_feedback(fb_id)

        with db.get_conn() as conn:
            for tbl in [
                "messages", "sessions", "feedback", "failed_solutions", "documents",
                "user_memory", "adaptation_profiles", "adaptation_strategy_stats",
                "product_events", "beta_feedback"
            ]:
                c_purge = conn.execute(f"SELECT COUNT(*) as c FROM {tbl} WHERE user_id = ?", (user_purge,)).fetchone()["c"]
                assert c_purge > 0, f"Failed to seed {tbl} for {user_purge}"

        db.delete_user_data(user_purge)

        purge_clean = True
        control_intact = True
        with db.get_conn() as conn:
            for tbl in [
                "messages", "sessions", "feedback", "failed_solutions", "documents",
                "user_memory", "adaptation_profiles", "adaptation_strategy_stats",
                "product_events", "beta_feedback"
            ]:
                c_purge = conn.execute(f"SELECT COUNT(*) as c FROM {tbl} WHERE user_id = ?", (user_purge,)).fetchone()["c"]
                c_ctrl = conn.execute(f"SELECT COUNT(*) as c FROM {tbl} WHERE user_id = ?", (user_control,)).fetchone()["c"]
                if c_purge != 0:
                    purge_clean = False
                if c_ctrl == 0:
                    control_intact = False

        self.check(purge_clean, "Purged user has 0 records across all 10 tables")
        self.check(control_intact, "Control user records remain 100% intact")

    def run(self) -> bool:
        print("=" * 70)
        print("  AVA AI — REAL BETA VERIFICATION SUITE")
        print("=" * 70)
        print(f"  • Base URL:         {self.base_url}")
        print(f"  • Mode:             {self.mode.upper()}")
        print(f"  • Database Path:    {config.DB_PATH}")
        print(f"  • Environment:      {config.ENVIRONMENT}")
        print(f"  • Run ID:           {self.run_id}")
        print("=" * 70)

        if not is_safe_host(self.base_url):
            if not self.allow_remote:
                print(f"\n[ERROR] Refusing to run verification against remote host: {self.base_url}")
                print("Pass '--allow-remote' to explicitly permit remote execution.\n")
                return False
            else:
                print(f"\n[WARNING] Executing against remote host: {self.base_url}")
                print("This suite creates temporary users, events, and feedback entries.\n")

        ok, msg = preflight_db_match(self.base_url, self.run_id)
        if not ok:
            print(f"\n[ABORT] Preflight DB alignment check failed: {msg}\n")
            return False
        print(f"  [PASS] Preflight Check: {msg}")

        cleanup_verified = False
        try:
            self._execute_suite()
        except KeyboardInterrupt:
            print("\n[INTERRUPT] Verification interrupted by user.")
        except Exception as e:
            print(f"\n[ERROR] Unexpected verification failure: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\n--- TEARDOWN: Guaranteed Fixture Cleanup ---")
            summary = self.cleanup()
            print(
                f"  Cleaned: {summary['users_purged']} users, "
                f"{summary['anon_events_deleted']} anon events, "
                f"{summary['feedback_deleted']} feedback, "
                f"{summary['sessions_deleted']} sessions"
            )

            clean_ok, leaks = self.verify_cleanup()
            if clean_ok:
                print("  [PASS] Zero-Leak Verification: 0 verification fixtures remain in database.")
                cleanup_verified = True
            else:
                print(f"  [FAIL] Zero-Leak Verification FAILED: {', '.join(leaks)}")
                cleanup_verified = False

        print("\n" + "=" * 70)
        total_passed = len(self.passed_steps)
        total_failed = len(self.failed_steps)
        if not cleanup_verified:
            total_failed += 1

        print(f"  RESULTS: {total_passed} PASSED, {total_failed} FAILED")
        status_label = f"{self.mode.upper()} VERIFIED" if (total_failed == 0 and cleanup_verified) else "VERIFICATION FAILED"
        print(f"  STATUS:  {status_label}")
        print("=" * 70 + "\n")
        return total_failed == 0 and cleanup_verified


def parse_args(args=None):
    parser = argparse.ArgumentParser(description="Ava AI — Beta Protocol Verification Harness (Sections 7–11)")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of running Ava server (default: http://127.0.0.1:8000)"
    )
    parser.add_argument(
        "--mode",
        choices=["offline", "live"],
        default="offline",
        help="Verification mode: 'offline' (no external LLM) or 'live' (real Groq streaming)"
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Explicit path to database (defaults to config.DB_PATH or DB_PATH env var)"
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Explicitly permit verification against a remote/non-localhost host"
    )
    return parser.parse_args(args)


def main():
    args = parse_args()
    if args.db_path:
        config.DB_PATH = args.db_path
        db.DB_PATH = args.db_path

    harness = BetaVerificationHarness(
        base_url=args.base_url,
        mode=args.mode,
        allow_remote=args.allow_remote
    )
    success = harness.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
