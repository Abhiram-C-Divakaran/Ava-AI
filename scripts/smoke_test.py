#!/usr/bin/env python3
"""
scripts/smoke_test.py — Deployment Smoke Test for Ava AI.

Performs an automated end-to-end operational smoke test against an active Ava instance.
Tests health, readiness, user registration, authentication, chat completion,
feedback, session isolation, and logout.

Usage:
    python scripts/smoke_test.py [--base-url http://127.0.0.1:8000]
"""

import sys
import uuid
import argparse
import requests


def run_smoke_test(base_url: str) -> bool:
    base_url = base_url.rstrip("/")
    session = requests.Session()
    print(f"\n======================================================================")
    print(f"  Ava AI — Deployment Smoke Test ({base_url})")
    print(f"======================================================================\n")

    steps = [
        ("Health Check", "/health"),
        ("Readiness Check", "/ready"),
    ]

    try:
        # 1. Health
        resp = session.get(f"{base_url}/health", timeout=5)
        if resp.status_code != 200 or resp.json().get("status") != "ok":
            print(f"  [FAIL] /health returned {resp.status_code}: {resp.text}")
            return False
        print(f"  [PASS] /health -> 200 OK")

        # 2. Readiness
        resp = session.get(f"{base_url}/ready", timeout=5)
        if resp.status_code != 200 or resp.json().get("status") != "ready":
            print(f"  [FAIL] /ready returned {resp.status_code}: {resp.text}")
            return False
        ready_data = resp.json()
        print(f"  [PASS] /ready -> 200 Ready (version: {ready_data.get('version')}, db: {ready_data.get('database')})")

        # 3. User Registration
        test_email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "SmokeTestPassword123!"
        resp = session.post(
            f"{base_url}/api/auth/signup",
            json={"name": "Smoke Tester", "email": test_email, "password": test_password},
            timeout=5
        )
        if resp.status_code != 200:
            print(f"  [FAIL] User signup failed with {resp.status_code}: {resp.text}")
            return False
        user_data = resp.json()
        user_id = user_data["user_id"]
        print(f"  [PASS] User signup -> user_id: {user_id}")

        # 4. User Login
        resp = session.post(
            f"{base_url}/api/auth/login",
            json={"email": test_email, "password": test_password},
            timeout=5
        )
        if resp.status_code != 200:
            print(f"  [FAIL] User login failed with {resp.status_code}: {resp.text}")
            return False
        print(f"  [PASS] User login -> authenticated session cookie established")

        # 5. Chat Interaction
        test_msg = "Hello Ava, this is an automated deployment smoke test."
        resp = session.post(
            f"{base_url}/api/chat",
            json={"message": test_msg, "user_id": user_id},
            timeout=15
        )
        if resp.status_code != 200:
            print(f"  [FAIL] /api/chat failed with {resp.status_code}: {resp.text}")
            return False
        chat_data = resp.json()
        msg_id = chat_data.get("message_id")
        session_id = chat_data.get("session_id")
        print(f"  [PASS] /api/chat -> 200 OK (session_id: {session_id}, msg_id: {msg_id})")

        # 6. Feedback Recording
        resp = session.post(
            f"{base_url}/api/feedback",
            json={"message_id": msg_id, "session_id": session_id, "helpful": True, "user_id": user_id},
            timeout=5
        )
        if resp.status_code != 200:
            print(f"  [FAIL] /api/feedback failed with {resp.status_code}: {resp.text}")
            return False
        print(f"  [PASS] /api/feedback -> 200 Recorded")

        # 7. Adaptation Profile Inspection
        resp = session.get(f"{base_url}/api/adaptation/{user_id}", timeout=5)
        if resp.status_code != 200:
            print(f"  [FAIL] /api/adaptation failed with {resp.status_code}: {resp.text}")
            return False
        prof_data = resp.json()
        print(f"  [PASS] /api/adaptation -> 200 OK (interactions: {prof_data.get('interaction_count')})")

        # 8. User Logout
        resp = session.post(f"{base_url}/api/auth/logout", timeout=5)
        if resp.status_code != 200:
            print(f"  [FAIL] /api/auth/logout failed with {resp.status_code}: {resp.text}")
            return False
        print(f"  [PASS] /api/auth/logout -> 200 OK")

        # 9. Verify Post-Logout Access Denied
        resp = session.get(f"{base_url}/api/adaptation/{user_id}", timeout=5)
        if resp.status_code != 401:
            print(f"  [FAIL] Post-logout access expected 401, got {resp.status_code}")
            return False
        print(f"  [PASS] Post-logout authorization check -> 401 Unauthorized")

        print(f"\n----------------------------------------------------------------------")
        print(f"  [SUCCESS] All 9 smoke test verification steps passed!")
        print(f"----------------------------------------------------------------------\n")
        return True

    except requests.RequestException as e:
        print(f"\n  [ERROR] Connection failed: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ava AI Deployment Smoke Test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of Ava server")
    args = parser.parse_args()

    success = run_smoke_test(args.base_url)
    sys.exit(0 if success else 1)
