#!/usr/bin/env python3
"""
scripts/verify_beta_protocol.py

Executes Sections 7 through 11 of the Real Beta Launch Verification Protocol:
- Section 7: Controlled Funnel Smoke Test
- Section 8: Cohort Correlation
- Section 9: Admin Beta Metrics & Rate Bounds
- Section 10: Admin Feedback Endpoints & Authorization (401/403/200/404)
- Section 11: Comprehensive Account Data Purge & Cross-User Isolation
"""

import sys
import os
import uuid
import json
import sqlite3
import requests

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db

BASE_URL = "http://127.0.0.1:8000"

def run_protocol_verification():
    print("=" * 70)
    print("  AVA AI — REAL BETA VERIFICATION SUITE (SECTIONS 7 - 11)")
    print("=" * 70)
    
    passed_steps = []
    failed_steps = []

    def check(condition: bool, step_name: str, details: str = ""):
        if condition:
            passed_steps.append(step_name)
            print(f"  [PASS] {step_name} {details}")
        else:
            failed_steps.append((step_name, details))
            print(f"  [FAIL] {step_name} {details}")

    # =========================================================================
    # SECTION 7: CONTROLLED FUNNEL SMOKE TEST & TELEMETRY
    # =========================================================================
    print("\n--- SECTION 7: Controlled Funnel Smoke Test ---")
    session = requests.Session()
    anon_id = f"anon_smoke_{uuid.uuid4().hex[:12]}"

    # Step 1: Visit landing page
    resp = session.post(
        f"{BASE_URL}/api/events",
        json={"event": "landing_view", "anonymous_session_id": anon_id, "page": "/"}
    )
    check(resp.status_code == 200, "1. Landing View Event", f"Status: {resp.status_code}")

    # Step 2: Click Get Started
    resp = session.post(
        f"{BASE_URL}/api/events",
        json={"event": "hero_get_started_click", "anonymous_session_id": anon_id, "page": "/"}
    )
    check(resp.status_code == 200, "2. Hero CTA Click Event", f"Status: {resp.status_code}")

    # Step 3: Begin signup
    resp = session.post(
        f"{BASE_URL}/api/events",
        json={"event": "signup_started", "anonymous_session_id": anon_id, "page": "/auth.html"}
    )
    check(resp.status_code == 200, "3. Signup Started Event", f"Status: {resp.status_code}")

    # Step 4: Complete signup
    test_email = f"tester_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "SecurePassword123!"
    headers = {"X-Anonymous-Session": anon_id}
    resp = session.post(
        f"{BASE_URL}/api/auth/signup",
        json={"name": "Beta Tester", "email": test_email, "password": test_password},
        headers=headers
    )
    check(resp.status_code == 200 and "user_id" in resp.json(), "4. Signup Completed", f"Status: {resp.status_code}")
    user_id = resp.json().get("user_id")

    # Step 5: Open chat
    resp = session.post(
        f"{BASE_URL}/api/events",
        json={"event": "chat_opened", "anonymous_session_id": anon_id, "page": "/chat.html"},
        headers=headers
    )
    check(resp.status_code == 200, "5. Chat Opened Event", f"Status: {resp.status_code}")

    # Step 6 & 7: Send message & receive response (streaming)
    stream_resp = session.post(
        f"{BASE_URL}/api/chat/stream",
        json={"message": "Hello Ava, I am testing the beta funnel.", "stream": True},
        headers=headers
    )
    check(stream_resp.status_code == 200, "6 & 7. Chat Stream Request", f"Status: {stream_resp.status_code}")
    
    # Read streamed SSE chunks
    full_text = ""
    session_id = None
    msg_id = None
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
    
    check(bool(full_text) and bool(session_id), "7b. Stream Response Received", f"Session: {session_id}, Chunks read: {len(full_text)} chars")

    # Step 8: Give thumbs feedback
    resp = session.post(
        f"{BASE_URL}/api/feedback",
        json={"session_id": session_id, "message_id": msg_id, "helpful": True},
        headers=headers
    )
    check(resp.status_code == 200, "8. Positive Thumbs Feedback", f"Status: {resp.status_code}")

    # Step 9: Submit beta feedback
    resp = session.post(
        f"{BASE_URL}/api/beta-feedback",
        json={"category": "Bug", "message": "Great beta testing experience!", "allow_follow_up": True},
        headers=headers
    )
    check(resp.status_code == 200, "9. Submit Beta Feedback", f"Status: {resp.status_code}")
    submitted_fb_id = resp.json().get("id")

    # Verify no raw prompt/response text in product_events
    with db.get_conn() as conn:
        events = conn.execute(
            "SELECT event_name, metadata_json FROM product_events WHERE anonymous_session_id = ?",
            (anon_id,)
        ).fetchall()
        
        has_raw_text = False
        for ev in events:
            meta = ev["metadata_json"] or ""
            if "Hello Ava" in meta or "testing the beta funnel" in meta:
                has_raw_text = True
                break
        check(not has_raw_text, "10. Privacy Check: No raw prompts in product_events")

    # =========================================================================
    # SECTION 8: COHORT CORRELATION
    # =========================================================================
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
        check(c1 and c2 and c3, "Cohort Correlated Anonymous Session", f"anon_id: {anon_id}")
        
        # Verify landing_view has NULL user_id, whereas signup_completed has user_id
        check(event_dict["landing_view"]["user_id"] is None, "Landing view user_id is NULL")
        check(event_dict["signup_completed"]["user_id"] == user_id, "Signup completed user_id matches authenticated user")

    # =========================================================================
    # SECTION 9: ADMIN BETA METRICS
    # =========================================================================
    print("\n--- SECTION 9: Admin Beta Metrics ---")
    # Promote a dedicated admin user
    admin_session = requests.Session()
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@example.com"
    resp = admin_session.post(
        f"{BASE_URL}/api/auth/signup",
        json={"name": "Admin Tester", "email": admin_email, "password": "AdminPassword123!"}
    )
    admin_user_id = resp.json().get("user_id")
    with db.get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (admin_user_id,))

    # Re-login to get updated is_admin in session cookie
    resp = admin_session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": admin_email, "password": "AdminPassword123!"}
    )
    check(resp.status_code == 200, "Admin Logged In")

    # Fetch beta metrics
    resp = admin_session.get(f"{BASE_URL}/api/admin/beta-metrics?period_days=7")
    check(resp.status_code == 200, "Fetch Beta Metrics (Admin)", f"Status: {resp.status_code}")
    metrics = resp.json()

    expected_keys = [
        "landing_views", "signup_started", "signup_completed", "chat_users",
        "messages_sent", "adaptation_used_responses", "positive_feedback",
        "negative_feedback", "chat_errors", "landing_to_signup_rate",
        "signup_completion_rate", "signup_to_chat_rate", "positive_feedback_rate",
        "adaptation_usage_rate"
    ]
    all_keys_present = all(k in metrics for k in expected_keys)
    check(all_keys_present, "All Beta Metric Keys Present")

    rates = [
        ("landing_to_signup_rate", metrics.get("landing_to_signup_rate")),
        ("signup_completion_rate", metrics.get("signup_completion_rate")),
        ("signup_to_chat_rate", metrics.get("signup_to_chat_rate")),
        ("positive_feedback_rate", metrics.get("positive_feedback_rate")),
        ("adaptation_usage_rate", metrics.get("adaptation_usage_rate"))
    ]
    rates_valid = all(0.0 <= r <= 1.0 for _, r in rates if r is not None)
    check(rates_valid, "All Conversion Rates Bounded in [0.0, 1.0]", str(rates))

    # =========================================================================
    # SECTION 10: ADMIN FEEDBACK ENDPOINTS & AUTHORIZATION
    # =========================================================================
    print("\n--- SECTION 10: Admin Feedback Endpoints & Authorization ---")
    anon_client = requests.Session()
    # Unauthenticated GET
    resp = anon_client.get(f"{BASE_URL}/api/admin/beta-feedback")
    check(resp.status_code == 401, "Unauthenticated GET /api/admin/beta-feedback -> 401", f"Got: {resp.status_code}")

    # Authenticated non-admin GET
    resp = session.get(f"{BASE_URL}/api/admin/beta-feedback")
    check(resp.status_code == 403, "Non-admin GET /api/admin/beta-feedback -> 403", f"Got: {resp.status_code}")

    # Admin GET
    resp = admin_session.get(f"{BASE_URL}/api/admin/beta-feedback")
    check(resp.status_code == 200, "Admin GET /api/admin/beta-feedback -> 200", f"Items: {len(resp.json().get('feedback', []))}")

    # Non-admin PATCH status
    fb_id = submitted_fb_id
    resp = session.patch(f"{BASE_URL}/api/admin/beta-feedback/{fb_id}/status", json={"status": "reviewing"})
    check(resp.status_code == 403, "Non-admin PATCH /api/admin/beta-feedback/{id}/status -> 403", f"Got: {resp.status_code}")

    # Admin PATCH status
    resp = admin_session.patch(f"{BASE_URL}/api/admin/beta-feedback/{fb_id}/status", json={"status": "reviewing"})
    check(resp.status_code == 200 and resp.json().get("new_status") == "reviewing", "Admin PATCH /api/admin/beta-feedback/{id}/status -> 200")

    # Non-admin DELETE
    resp = session.delete(f"{BASE_URL}/api/admin/beta-feedback/{fb_id}")
    check(resp.status_code == 403, "Non-admin DELETE /api/admin/beta-feedback/{id} -> 403", f"Got: {resp.status_code}")

    # Admin DELETE
    resp = admin_session.delete(f"{BASE_URL}/api/admin/beta-feedback/{fb_id}")
    check(resp.status_code == 200, "Admin DELETE /api/admin/beta-feedback/{id} -> 200")

    # Admin DELETE unknown ID -> 404
    resp = admin_session.delete(f"{BASE_URL}/api/admin/beta-feedback/99999999")
    check(resp.status_code == 404, "Admin DELETE unknown feedback ID -> 404", f"Got: {resp.status_code}")

    # =========================================================================
    # SECTION 11: ACCOUNT DATA PURGE & ISOLATION
    # =========================================================================
    print("\n--- SECTION 11: Account Data Purge & Isolation ---")
    user_purge = f"user_purge_{uuid.uuid4().hex[:8]}"
    user_control = f"user_control_{uuid.uuid4().hex[:8]}"

    db.create_user(user_purge, name="Purge User", email=f"{user_purge}@example.com", password="pwd")
    db.create_user(user_control, name="Control User", email=f"{user_control}@example.com", password="pwd")

    # Seed all tables for both users
    for u in (user_purge, user_control):
        s_id = f"s_{uuid.uuid4().hex[:8]}"
        m_id = f"m_{uuid.uuid4().hex[:8]}"
        db.create_session(s_id, u, title="Test Session")
        db.save_message(m_id, s_id, u, "Test Q", "Test A", "general_inquiry", {"label": "neutral", "score": 0.5}, 0.0, 10)
        db.save_feedback(u, s_id, m_id, True)
        db.save_failed_solution(u, s_id, "failed strategy text")
        db.save_document(f"doc_{uuid.uuid4().hex[:8]}", u, "doc.txt", "/fake/doc.txt", "doc text")
        db.set_user_memory(u, "user memory text", 1)
        db.set_adaptation_profile(u, {"verbosity": 0.5}, interaction_count=2)
        db.record_strategy_feedback(u, "code_first", True)
        db.record_product_event("chat_message_sent", f"anon_{u}", "/chat.html", user_id=u)
        db.record_beta_feedback(category="Bug", message="Test feedback", user_id=u)

    # Verify seed present
    with db.get_conn() as conn:
        for tbl in ["messages", "sessions", "feedback", "failed_solutions", "documents",
                    "user_memory", "adaptation_profiles", "adaptation_strategy_stats",
                    "product_events", "beta_feedback"]:
            c_purge = conn.execute(f"SELECT COUNT(*) as c FROM {tbl} WHERE user_id = ?", (user_purge,)).fetchone()["c"]
            assert c_purge > 0, f"Failed to seed {tbl} for {user_purge}"

    # Perform purge of user_purge
    db.delete_user_data(user_purge)

    # Verify user_purge has 0 records across all 10 tables
    purge_clean = True
    control_intact = True
    with db.get_conn() as conn:
        for tbl in ["messages", "sessions", "feedback", "failed_solutions", "documents",
                    "user_memory", "adaptation_profiles", "adaptation_strategy_stats",
                    "product_events", "beta_feedback"]:
            c_purge = conn.execute(f"SELECT COUNT(*) as c FROM {tbl} WHERE user_id = ?", (user_purge,)).fetchone()["c"]
            c_ctrl = conn.execute(f"SELECT COUNT(*) as c FROM {tbl} WHERE user_id = ?", (user_control,)).fetchone()["c"]
            if c_purge != 0:
                purge_clean = False
            if c_ctrl == 0:
                control_intact = False

    check(purge_clean, "Purged user has 0 records across all 10 tables")
    check(control_intact, "Control user records remain 100% intact")

    # Cleanup control user
    db.delete_user_data(user_control)

    print("\n" + "=" * 70)
    print(f"  PROTOCOL RESULTS: {len(passed_steps)} PASSED, {len(failed_steps)} FAILED")
    print("=" * 70)
    return len(failed_steps) == 0

if __name__ == "__main__":
    success = run_protocol_verification()
    sys.exit(0 if success else 1)
