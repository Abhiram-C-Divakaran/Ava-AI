#!/usr/bin/env python3
"""
scripts/smoke_test.py — Deployment Smoke Test for Ava AI.

Performs automated operational smoke testing against an active Ava instance.
Supports:
  --offline: exercises core functionality (health, readiness, signup, login,
             session access, memory access, adaptation access, preferences,
             cross-user authorization denial, logout, post-logout denial)
             without requiring external Groq LLM network calls.
  online (default): includes live chat completion and feedback loop.

Usage:
    python scripts/smoke_test.py [--base-url http://127.0.0.1:8000] [--offline]
"""

import sys
import uuid
import argparse
import requests


def run_smoke_test(base_url: str, offline: bool = False) -> bool:
    base_url = base_url.rstrip("/")
    session = requests.Session()
    mode_label = "OFFLINE CORE" if offline else "FULL ONLINE"
    print(f"\n======================================================================")
    print(f"  Ava AI — Deployment Smoke Test [{mode_label}] ({base_url})")
    print(f"======================================================================\n")

    passed = 0
    failed = 0

    def record(success: bool, step_name: str, detail: str = ""):
        nonlocal passed, failed
        if success:
            passed += 1
            print(f"  [PASS] {step_name} {detail}")
        else:
            failed += 1
            print(f"  [FAIL] {step_name} {detail}")

    try:
        # 1. Health
        resp = session.get(f"{base_url}/health", timeout=5)
        h_ok = (resp.status_code == 200 and resp.json().get("status") == "ok")
        version_str = resp.json().get("version", "unknown") if h_ok else ""
        record(h_ok, "1. Health Check", f"-> 200 OK (version: {version_str})")
        if not h_ok:
            return False

        # 2. Readiness
        resp = session.get(f"{base_url}/ready", timeout=5)
        r_ok = (resp.status_code == 200 and resp.json().get("status") == "ready")
        ready_data = resp.json() if r_ok else {}
        record(r_ok, "2. Readiness Check", f"-> 200 Ready (db: {ready_data.get('database')}, storage: {ready_data.get('storage')})")
        if not r_ok:
            return False

        # 3. User Registration
        test_email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "SmokeTestPassword123!"
        resp = session.post(
            f"{base_url}/api/auth/signup",
            json={"name": "Smoke Tester", "email": test_email, "password": test_password},
            timeout=5
        )
        s_ok = (resp.status_code == 200 and "user_id" in resp.json())
        user_id = resp.json().get("user_id") if s_ok else None
        record(s_ok, "3. User Signup", f"-> user_id: {user_id}")
        if not s_ok:
            return False

        # 4. User Login
        resp = session.post(
            f"{base_url}/api/auth/login",
            json={"email": test_email, "password": test_password},
            timeout=5
        )
        l_ok = (resp.status_code == 200)
        record(l_ok, "4. User Login", "-> authenticated session cookie established")
        if not l_ok:
            return False

        # 5. Session Listing
        resp = session.get(f"{base_url}/api/sessions/{user_id}", timeout=5)
        sess_ok = (resp.status_code == 200 and isinstance(resp.json().get("sessions"), list))
        record(sess_ok, "5. Session Listing", f"-> 200 OK (count: {len(resp.json().get('sessions', []))})")
        if not sess_ok:
            return False

        # 6. User Memory Access
        resp = session.get(f"{base_url}/api/user-memory/{user_id}", timeout=5)
        mem_ok = (resp.status_code == 200 and "memory_text" in resp.json())
        record(mem_ok, "6. User Memory Access", "-> 200 OK")
        if not mem_ok:
            return False

        # 7. Adaptation Profile Inspection
        resp = session.get(f"{base_url}/api/adaptation/{user_id}", timeout=5)
        prof_ok = (resp.status_code == 200 and "user_id" in resp.json() and "metrics" in resp.json())
        prof_data = resp.json().get("metrics", {}) if prof_ok else {}
        record(prof_ok, "7. Adaptation Profile Access", f"-> 200 OK (interactions: {prof_data.get('interaction_count', 0)})")
        if not prof_ok:
            return False

        # 8. User Preferences Inspection
        resp = session.get(f"{base_url}/api/user/preferences/{user_id}", timeout=5)
        pref_ok = (resp.status_code == 200 and "personality" in resp.json())
        record(pref_ok, "8. User Preferences Access", "-> 200 OK")
        if not pref_ok:
            return False

        # 9. Cross-User Authorization Denial (IDOR Prevention)
        foreign_id = "user_foreign_attacker_9999"
        resp = session.get(f"{base_url}/api/adaptation/{foreign_id}", timeout=5)
        idor_ok = (resp.status_code == 403)
        record(idor_ok, "9. Cross-User Authorization Denial", f"-> {resp.status_code} Forbidden (expected 403)")
        if not idor_ok:
            return False

        # Online-only chat & feedback verification
        if not offline:
            test_msg = "Hello Ava, this is an automated deployment smoke test."
            resp = session.post(
                f"{base_url}/api/chat",
                json={"message": test_msg, "user_id": user_id},
                timeout=15
            )
            chat_ok = (resp.status_code == 200 and "message_id" in resp.json())
            chat_data = resp.json() if chat_ok else {}
            msg_id = chat_data.get("message_id")
            session_id = chat_data.get("session_id")
            record(chat_ok, "10. Chat Interaction", f"-> 200 OK (session_id: {session_id}, msg_id: {msg_id})")
            if not chat_ok:
                return False

            resp = session.post(
                f"{base_url}/api/feedback",
                json={"message_id": msg_id, "session_id": session_id, "helpful": True, "user_id": user_id},
                timeout=5
            )
            fb_ok = (resp.status_code == 200)
            record(fb_ok, "11. Feedback Recording", "-> 200 Recorded")
            if not fb_ok:
                return False

        # Logout
        resp = session.post(f"{base_url}/api/auth/logout", timeout=5)
        logout_ok = (resp.status_code == 200)
        record(logout_ok, "10. User Logout" if offline else "12. User Logout", "-> 200 OK")
        if not logout_ok:
            return False

        # Post-Logout Access Denied
        resp = session.get(f"{base_url}/api/adaptation/{user_id}", timeout=5)
        post_logout_ok = (resp.status_code == 401)
        record(post_logout_ok, "11. Post-Logout Authorization Check" if offline else "13. Post-Logout Authorization Check", f"-> {resp.status_code} Unauthorized (expected 401)")
        if not post_logout_ok:
            return False

        total = passed + failed
        print(f"\n----------------------------------------------------------------------")
        print(f"  [SUMMARY] Smoke test completed: {passed} passed, {failed} failed (Total: {total})")
        print(f"----------------------------------------------------------------------\n")
        return (failed == 0)

    except requests.RequestException as e:
        print(f"\n  [ERROR] Connection failed: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ava AI Deployment Smoke Test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of Ava server")
    parser.add_argument("--offline", action="store_true", help="Run offline core tests without external Groq calls")
    args = parser.parse_args()

    success = run_smoke_test(args.base_url, offline=args.offline)
    sys.exit(0 if success else 1)
