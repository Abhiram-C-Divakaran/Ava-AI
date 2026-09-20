#!/usr/bin/env python3
"""
scripts/run_controlled_load_test.py — Controlled Concurrency Benchmark Runner for Ava AI.

Runs realistic concurrency benchmarks against an active local Ava instance with
mocked LLM inference (ensuring zero external Groq API dependencies or rate limits).

Benchmarks 10, 25, and 50 concurrent users.
Measures:
  - Total requests
  - Success rate (%)
  - Error rate (%)
  - Average latency (ms)
  - Latency percentiles: p50, p95, p99 (ms)
  - SQLite lock errors (target: 0)
"""

import os
import sys
import time
import json
import uuid
import tempfile
import threading
import statistics
from unittest.mock import patch
import uvicorn
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def mock_call_llm(prompt, system_prompt=None, model=None, temperature=0.7, max_tokens=1024, json_mode=False):
    if json_mode:
        return '{"response": "Mocked JSON load response"}'
    return "Mocked fast response for controlled concurrency benchmark."


def simulate_load_user(base_url: str, user_idx: int, requests_per_user: int = 3) -> dict:
    session = requests.Session()
    latencies = []
    errors = []
    lock_errors = 0
    email = f"load_{user_idx}_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "LoadPassword123!"

    try:
        # 1. Signup
        t0 = time.time()
        r = session.post(f"{base_url}/api/auth/signup", json={"name": f"User {user_idx}", "email": email, "password": pwd}, timeout=10)
        latencies.append((time.time() - t0) * 1000)
        if r.status_code != 200:
            errors.append(f"Signup: {r.status_code}")
            return {"latencies": latencies, "errors": errors, "lock_errors": lock_errors}
        user_id = r.json().get("user_id")

        # 2. Login
        t0 = time.time()
        r = session.post(f"{base_url}/api/auth/login", json={"email": email, "password": pwd}, timeout=10)
        latencies.append((time.time() - t0) * 1000)
        if r.status_code != 200:
            errors.append(f"Login: {r.status_code}")
            return {"latencies": latencies, "errors": errors, "lock_errors": lock_errors}

        # 3. Chat and Feedback cycles
        for i in range(requests_per_user):
            # Chat request
            t0 = time.time()
            r = session.post(f"{base_url}/api/chat", json={"message": f"Query {i} from user {user_idx}", "user_id": user_id}, timeout=15)
            lat = (time.time() - t0) * 1000
            latencies.append(lat)
            if r.status_code != 200:
                err_text = r.text
                if "locked" in err_text.lower() or "busy" in err_text.lower():
                    lock_errors += 1
                errors.append(f"Chat: {r.status_code}")
                continue

            chat_data = r.json()
            msg_id = chat_data.get("message_id")
            session_id = chat_data.get("session_id")

            # Feedback request
            t0 = time.time()
            r = session.post(
                f"{base_url}/api/feedback",
                json={"message_id": msg_id, "session_id": session_id, "helpful": True, "user_id": user_id},
                timeout=10
            )
            lat = (time.time() - t0) * 1000
            latencies.append(lat)
            if r.status_code != 200:
                err_text = r.text
                if "locked" in err_text.lower() or "busy" in err_text.lower():
                    lock_errors += 1
                errors.append(f"Feedback: {r.status_code}")

    except Exception as e:
        err_str = str(e)
        if "locked" in err_str.lower() or "busy" in err_str.lower():
            lock_errors += 1
        errors.append(err_str)

    return {
        "latencies": latencies,
        "errors": errors,
        "lock_errors": lock_errors
    }


def run_benchmark_tier(base_url: str, num_users: int, reqs_per_user: int = 3) -> dict:
    start_time = time.time()
    all_latencies = []
    all_errors = []
    total_locks = 0

    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = [
            executor.submit(simulate_load_user, base_url, i, reqs_per_user)
            for i in range(num_users)
        ]
        for f in as_completed(futures):
            res = f.result()
            all_latencies.extend(res["latencies"])
            all_errors.extend(res["errors"])
            total_locks += res["lock_errors"]

    duration = time.time() - start_time
    total_reqs = len(all_latencies)
    err_count = len(all_errors)
    success_rate = ((total_reqs - err_count) / total_reqs * 100.0) if total_reqs > 0 else 0.0
    err_rate = (err_count / total_reqs * 100.0) if total_reqs > 0 else 0.0

    sorted_lat = sorted(all_latencies) if all_latencies else [0]
    p50 = statistics.median(sorted_lat)
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) > 1 else sorted_lat[0]
    p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if len(sorted_lat) > 1 else sorted_lat[0]
    avg = statistics.mean(sorted_lat)

    return {
        "users": num_users,
        "total_requests": total_reqs,
        "duration_sec": round(duration, 2),
        "throughput_rps": round(total_reqs / duration, 1) if duration > 0 else 0,
        "success_rate_pct": round(success_rate, 2),
        "error_rate_pct": round(err_rate, 2),
        "avg_ms": round(avg, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "sqlite_lock_errors": total_locks
    }


def main():
    print(f"\n======================================================================")
    print(f"  Ava AI — Controlled Load Benchmark (Mocked LLM, High Concurrency)")
    print(f"======================================================================\n")

    os.environ["ENVIRONMENT"] = "development"
    os.environ["DISABLE_RATE_LIMIT"] = "true"
    os.environ["SECRET_KEY"] = "dev_secret_key_for_controlled_load_test_12345"

    temp_dir = tempfile.TemporaryDirectory()
    test_db = os.path.join(temp_dir.name, "load_test.db")

    import database as db
    original_db = db.DB_PATH
    db.DB_PATH = test_db
    db.init_db()

    # Import and patch app
    import main as ava_main
    ava_main.call_llm = mock_call_llm

    # Start Uvicorn server on port 8899
    port = 8899
    server_config = uvicorn.Config(
        ava_main.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    # Wait for server readiness
    print("[*] Waiting for test server on 127.0.0.1:8899...")
    ready = False
    for _ in range(30):
        try:
            r = requests.get(f"{base_url}/health", timeout=1)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            time.sleep(0.2)

    if not ready:
        print("[-] Error: Failed to start test server.")
        sys.exit(1)
    print("[+] Test server running and healthy.\n")

    tiers = [10, 25, 50]
    results = []

    try:
        for u in tiers:
            print(f"[*] Benchmarking concurrency tier: {u} concurrent users...")
            res = run_benchmark_tier(base_url, num_users=u, reqs_per_user=3)
            results.append(res)
            print(f"    Total: {res['total_requests']} reqs | Success: {res['success_rate_pct']}% | Avg: {res['avg_ms']}ms | p50: {res['p50_ms']}ms | p95: {res['p95_ms']}ms | Locks: {res['sqlite_lock_errors']}")
            time.sleep(0.5)

        print("\n" + "=" * 70)
        print("  CONCURRENCY BENCHMARK REPORT")
        print("=" * 70)
        print(f"{'Users':<8} {'Requests':<10} {'Success %':<11} {'Avg (ms)':<10} {'p50 (ms)':<10} {'p95 (ms)':<10} {'p99 (ms)':<10} {'DB Locks':<8}")
        print("-" * 70)
        for r in results:
            print(f"{r['users']:<8} {r['total_requests']:<10} {r['success_rate_pct']:<11} {r['avg_ms']:<10} {r['p50_ms']:<10} {r['p95_ms']:<10} {r['p99_ms']:<10} {r['sqlite_lock_errors']:<8}")
        print("-" * 70)

        # Integrity check
        integrity = db.check_database_integrity()
        print(f"\n[+] Post-Benchmark Database Integrity: {integrity}")

        all_locks_zero = all(r["sqlite_lock_errors"] == 0 for r in results)
        all_success_high = all(r["success_rate_pct"] >= 99.0 for r in results)

        if all_locks_zero and all_success_high and integrity == "ok":
            print("[SUCCESS] All concurrency criteria met (0 SQLite locks, >99% success rate, integrity ok)!\n")
            # Save results json for release reporting
            report_file = os.path.join(BASE_DIR, "load_test_results.json")
            with open(report_file, "w") as f:
                json.dump({"benchmark_results": results, "integrity": integrity, "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}, f, indent=2)
            sys.exit(0)
        else:
            print("[-] Concurrency benchmark failed criteria.")
            sys.exit(1)

    finally:
        server.should_exit = True
        db.DB_PATH = original_db
        temp_dir.cleanup()


if __name__ == "__main__":
    main()
