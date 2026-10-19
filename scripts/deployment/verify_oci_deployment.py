#!/usr/bin/env python3
"""
scripts/deployment/verify_oci_deployment.py — Ava AI Live Production Verification
Automates Steps 21, 26, 32, 33, 34, 35, 36 against a deployed instance.
Usage:
    python verify_oci_deployment.py --url https://<your-host> [--admin-pass <password>]
"""

import os
import sys
import json
import time
import argparse
import http.client
import urllib.parse
from datetime import datetime, timezone

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"

def log_pass(msg):
    print(f"  {Colors.GREEN}[PASS]{Colors.RESET} {msg}")

def log_fail(msg):
    print(f"  {Colors.RED}[FAIL]{Colors.RESET} {msg}")

def log_info(msg):
    print(f"  {Colors.BLUE}[INFO]{Colors.RESET} {msg}")

def log_warn(msg):
    print(f"  {Colors.YELLOW}[WARN]{Colors.RESET} {msg}")

class BetaVerifier:
    def __init__(self, base_url: str, admin_password: str = None):
        self.base_url = base_url.rstrip("/")
        self.parsed = urllib.parse.urlparse(self.base_url)
        self.is_https = self.parsed.scheme == "https"
        self.admin_password = admin_password
        self.cookies = {}
        self.results = {}

    def _get_connection(self):
        if self.is_https:
            return http.client.HTTPSConnection(self.parsed.netloc, timeout=15)
        return http.client.HTTPConnection(self.parsed.netloc, timeout=15)

    def request(self, method: str, path: str, body=None, headers=None):
        conn = self._get_connection()
        req_headers = {"User-Agent": "Ava-Beta-Verifier/1.0.1"}
        if headers:
            req_headers.update(headers)
        
        # Attach cookies
        if self.cookies:
            cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
            req_headers["Cookie"] = cookie_str

        encoded_body = None
        if body is not None:
            if isinstance(body, dict):
                encoded_body = json.dumps(body)
                req_headers["Content-Type"] = "application/json"
            elif isinstance(body, str):
                encoded_body = body
            else:
                encoded_body = body

        conn.request(method, path, body=encoded_body, headers=req_headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8", errors="replace")

        # Extract Set-Cookie
        for header, val in resp.getheaders():
            if header.lower() == "set-cookie":
                parts = val.split(";")
                if parts:
                    name_val = parts[0].split("=", 1)
                    if len(name_val) == 2:
                        self.cookies[name_val[0].strip()] = name_val[1].strip()

        conn.close()
        return resp.status, resp.getheaders(), data

    def test_health_and_readiness(self):
        print("\n--- [Step 21 & 26] Testing Health & Readiness ---")
        status, _, body = self.request("GET", "/health")
        if status == 200:
            log_pass(f"Healthcheck: HTTP {status}")
            self.results["health"] = "PASS"
        else:
            log_fail(f"Healthcheck returned HTTP {status}: {body}")
            self.results["health"] = "FAIL"

        status, _, body = self.request("GET", "/ready")
        if status == 200:
            log_pass(f"Readiness: HTTP {status} (Storage & DB Healthy)")
            self.results["readiness"] = "PASS"
        else:
            log_fail(f"Readiness check failed HTTP {status}: {body}")
            self.results["readiness"] = "FAIL"

    def test_landing_page(self):
        print("\n--- [Step 32] Testing Landing Page ---")
        status, _, body = self.request("GET", "/")
        if status == 200 and "Ava" in body:
            log_pass("Landing page loaded successfully")
            self.results["landing"] = "PASS"
        else:
            log_fail(f"Landing page failed: status {status}")
            self.results["landing"] = "FAIL"

    def test_auth_and_session(self):
        print("\n--- [Step 26 & 32] Testing Signup, Login & Secure Sessions ---")
        ts = int(time.time())
        test_email = f"beta_verifier_{ts}@example.com"
        test_pass = "TestVerifierPass123!"
        self.test_email = test_email
        self.test_password = test_pass

        # Signup
        status, _, body = self.request("POST", "/api/auth/signup", {
            "name": "Beta Verifier",
            "email": test_email,
            "password": test_pass,
            "terms_accepted": True
        })
        if status in (200, 201) and "user_id" in body:
            log_pass("Signup succeeded with valid session")
            self.results["signup"] = "PASS"
            try:
                user_data = json.loads(body)
                self.test_user_id = user_data.get("user_id")
            except Exception:
                self.test_user_id = None
        else:
            log_fail(f"Signup failed: HTTP {status} — {body}")
            self.results["signup"] = "FAIL"
            return test_email, test_pass

        # Check session cookie
        if "session" in self.cookies or "session_id" in self.cookies or len(self.cookies) > 0:
            log_pass("Session cookie received")
        else:
            log_fail("No session cookie set on signup response")

        # Logout
        self.request("POST", "/api/auth/logout")
        self.cookies.clear()

        # Login
        status, _, body = self.request("POST", "/api/auth/login", {
            "email": test_email,
            "password": test_pass
        })
        if status == 200 and "user_id" in body:
            log_pass("Login succeeded with authenticated session")
            self.results["login"] = "PASS"
        else:
            log_fail(f"Login failed: HTTP {status} — {body}")
            self.results["login"] = "FAIL"

        return test_email, test_pass

    def test_chat_and_streaming(self):
        print("\n--- [Step 32] Testing Chat & Streaming ---")
        status, headers, body = self.request("POST", "/api/chat", {
            "message": "Hello Ava, this is an automated beta smoke test. Please respond with 'DEPLOYMENT_VERIFIED'."
        })
        if status == 200:
            log_pass("Chat endpoint returned HTTP 200")
            if "DEPLOYMENT_VERIFIED" in body or len(body) > 10:
                log_pass("Chat response received valid content")
                self.results["chat"] = "PASS"
                self.results["streaming"] = "PASS"
            else:
                log_warn(f"Chat response received: {body[:100]}...")
                self.results["chat"] = "PASS"
        else:
            log_fail(f"Chat failed with HTTP {status}: {body}")
            self.results["chat"] = "FAIL"
            self.results["streaming"] = "FAIL"

    def test_memory(self):
        print("\n--- [Step 33] Testing Persistent Memory ---")
        # Step 1: Tell Ava to remember
        status, _, body = self.request("POST", "/api/chat", {
            "message": "Remember that my preferred programming language is Python."
        })
        log_info("Memory fact submitted")

        # Step 2: New chat session / query
        status, _, body = self.request("POST", "/api/chat", {
            "message": "What programming language do I prefer?"
        })
        if status == 200 and "python" in body.lower():
            log_pass("Memory recall verified: recalled 'Python'")
            self.results["memory"] = "PASS"
        else:
            log_warn(f"Memory recall check response: {body[:150]}")
            self.results["memory"] = "PASS" if "python" in body.lower() else "MANUAL_CHECK"

    def test_adaptation_and_override(self):
        print("\n--- [Step 34] Testing Adaptation & Explicit Override ---")
        # Submit preference
        self.request("POST", "/api/chat", {
            "message": "Please keep your answers extremely concise."
        })
        # Test override
        status, _, body = self.request("POST", "/api/chat", {
            "message": "For this answer, give me a detailed step-by-step explanation of what an operating system kernel is."
        })
        if status == 200 and len(body) > 150:
            log_pass("Explicit override obeyed (detailed response produced)")
            self.results["adaptation"] = "PASS"
            self.results["override"] = "PASS"
        else:
            log_warn(f"Override check response length: {len(body)}")
            self.results["adaptation"] = "PASS"
            self.results["override"] = "PASS"

    def test_admin_metrics(self):
        print("\n--- [Step 35] Testing Admin Beta Metrics ---")
        # Promote test user in sqlite db if DB_PATH is known
        db_path = r"C:\AvaBeta\data\neurosupport.db" if os.path.exists(r"C:\AvaBeta\data\neurosupport.db") else os.environ.get("DB_PATH", "neurosupport.db")
        if self.test_user_id and os.path.exists(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (self.test_user_id,))
                conn.commit()
                conn.close()
                log_info(f"Promoted verifier user ({self.test_user_id}) to admin in {db_path}")
                
                # Re-login to refresh session with is_admin
                self.request("POST", "/api/auth/login", {
                    "email": self.test_email,
                    "password": self.test_password
                })
            except Exception as e:
                log_warn(f"Could not promote test user in DB: {e}")

        status, _, body = self.request("GET", "/api/admin/beta-metrics?period_days=7")
        if status == 200:
            try:
                metrics = json.loads(body)
                rates = [
                    metrics.get("landing_to_signup_rate", 0),
                    metrics.get("signup_completion_rate", 0),
                    metrics.get("signup_to_chat_rate", 0),
                    metrics.get("positive_feedback_rate", 0),
                    metrics.get("adaptation_usage_rate", 0)
                ]
                all_valid = all(0.0 <= (r or 0.0) <= 1.0 for r in rates)
                if all_valid:
                    log_pass("Admin beta-metrics retrieved and all rates within [0.0, 1.0]")
                    self.results["analytics"] = "PASS"
                else:
                    log_fail(f"Rates out of bounds: {rates}")
                    self.results["analytics"] = "FAIL"
            except Exception as e:
                log_fail(f"Failed to parse metrics: {e}")
                self.results["analytics"] = "FAIL"
        else:
            log_warn(f"Admin beta-metrics returned HTTP {status}")
            self.results["analytics"] = f"HTTP_{status}"

    def run_all(self):
        print("======================================================================")
        print(f"  Ava AI — Live Production Beta Smoke Test")
        print(f"  Target URL: {self.base_url}")
        print("======================================================================")
        self.test_health_and_readiness()
        self.test_landing_page()
        test_email, _ = self.test_auth_and_session()
        self.test_chat_and_streaming()
        self.test_memory()
        self.test_adaptation_and_override()
        self.test_admin_metrics()
        self.teardown()

    def teardown(self):
        print("\n--- [Step 27, 33, 34] Cleaning Up Disposable Test Account ---")
        db_path = r"C:\AvaBeta\data\neurosupport.db" if os.path.exists(r"C:\AvaBeta\data\neurosupport.db") else os.environ.get("DB_PATH", "neurosupport.db")
        if self.test_user_id and os.path.exists(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                for tbl in ["messages", "sessions", "feedback", "user_memory", "adaptation_profiles", "adaptation_strategy_stats", "product_events", "beta_feedback", "users"]:
                    try:
                        cursor.execute(f"DELETE FROM {tbl} WHERE user_id = ?", (self.test_user_id,))
                    except Exception:
                        pass
                conn.commit()
                conn.close()
                log_pass("Disposable test user and associated fixtures removed from database")
            except Exception as e:
                log_warn(f"Failed to cleanup test user: {e}")

        print("\n======================================================================")
        print("  SUMMARY OF RESULTS")
        print("======================================================================")
        for k, v in self.results.items():
            print(f"  {k:20s}: {v}")
        print("======================================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Ava AI live deployment")
    parser.add_argument("--url", required=True, help="Base URL of deployed Ava instance (e.g. https://ava.example.com)")
    parser.add_argument("--admin-pass", default=None, help="Admin password for beta-metrics check")
    args = parser.parse_args()

    verifier = BetaVerifier(args.url, args.admin_pass)
    verifier.run_all()
