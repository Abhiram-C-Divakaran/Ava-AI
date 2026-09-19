#!/usr/bin/env python3
"""
scripts/load_test.py — Lightweight Concurrency & Load Test for Ava AI.

Simulates multiple concurrent users to measure latency distribution (p50, p95, p99),
throughput (req/sec), and verify SQLite concurrency under write load without lock contention.

Usage:
    python scripts/load_test.py [--base-url http://127.0.0.1:8000] [--users 25] [--requests-per-user 4]
"""

import sys
import time
import uuid
import argparse
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests


def simulate_user(base_url: str, user_index: int, requests_per_user: int) -> dict:
    session = requests.Session()
    latencies = []
    errors = []
    user_id = None

    try:
        # Signup
        email = f"load_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "LoadTestPassword123!"
        t0 = time.time()
        r = session.post(f"{base_url}/api/auth/signup", json={"name": f"User {user_index}", "email": email, "password": pwd}, timeout=10)
        latencies.append((time.time() - t0) * 1000)
        if r.status_code != 200:
            errors.append(f"Signup failed: {r.status_code}")
            return {"user_index": user_index, "latencies": latencies, "errors": errors}
        user_id = r.json().get("user_id")

        # Login
        t0 = time.time()
        r = session.post(f"{base_url}/api/auth/login", json={"email": email, "password": pwd}, timeout=10)
        latencies.append((time.time() - t0) * 1000)
        if r.status_code != 200:
            errors.append(f"Login failed: {r.status_code}")
            return {"user_index": user_index, "latencies": latencies, "errors": errors}

        # Chat and feedback requests
        for i in range(requests_per_user):
            # Chat
            t0 = time.time()
            r = session.post(f"{base_url}/api/chat", json={"message": f"User {user_index} load query {i}", "user_id": user_id}, timeout=15)
            latencies.append((time.time() - t0) * 1000)
            if r.status_code != 200:
                errors.append(f"Chat failed: {r.status_code} - {r.text[:100]}")
                continue
            chat_data = r.json()
            msg_id = chat_data.get("message_id")
            session_id = chat_data.get("session_id")

            # Feedback
            t0 = time.time()
            r = session.post(f"{base_url}/api/feedback", json={"message_id": msg_id, "session_id": session_id, "helpful": True, "user_id": user_id}, timeout=10)
            latencies.append((time.time() - t0) * 1000)
            if r.status_code != 200:
                errors.append(f"Feedback failed: {r.status_code}")

    except Exception as e:
        errors.append(str(e))

    return {
        "user_index": user_index,
        "latencies": latencies,
        "errors": errors
    }


def run_load_test(base_url: str, num_users: int, reqs_per_user: int):
    base_url = base_url.rstrip("/")
    print(f"\n======================================================================")
    print(f"  Ava AI — Concurrency & Load Benchmark")
    print(f"  Target: {base_url} | Concurrent Users: {num_users} | Reqs/User: {reqs_per_user * 2 + 2}")
    print(f"======================================================================\n")

    start_time = time.time()
    all_latencies = []
    all_errors = []

    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = [
            executor.submit(simulate_user, base_url, i, reqs_per_user)
            for i in range(num_users)
        ]
        for f in as_completed(futures):
            res = f.result()
            all_latencies.extend(res["latencies"])
            all_errors.extend(res["errors"])

    total_duration = time.time() - start_time
    total_requests = len(all_latencies)

    print(f"----------------------------------------------------------------------")
    print(f"  Performance Results:")
    print(f"----------------------------------------------------------------------")
    print(f"  Total Duration:     {total_duration:.2f} seconds")
    print(f"  Total Requests:     {total_requests}")
    print(f"  Throughput:         {total_requests / total_duration:.1f} req/sec")

    if all_latencies:
        sorted_lat = sorted(all_latencies)
        p50 = statistics.median(sorted_lat)
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
        avg = statistics.mean(sorted_lat)
        print(f"  Latency Avg:        {avg:.2f} ms")
        print(f"  Latency p50:        {p50:.2f} ms")
        print(f"  Latency p95:        {p95:.2f} ms")
        print(f"  Latency p99:        {p99:.2f} ms")

    # Check for SQLite lock contention
    lock_errors = [e for e in all_errors if "database is locked" in e.lower() or "busy" in e.lower()]

    print(f"\n  Total Errors:       {len(all_errors)}")
    print(f"  SQLite Lock Errors: {len(lock_errors)}")

    if all_errors:
        print("\n  Sample Errors:")
        for err in all_errors[:5]:
            print(f"    * {err}")

    print(f"----------------------------------------------------------------------")
    success = (len(lock_errors) == 0 and len(all_errors) <= total_requests * 0.05)
    if success:
        print(f"  [PASS] Concurrency and throughput thresholds met!\n")
    else:
        print(f"  [FAIL] Errors exceeded tolerance threshold.\n")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ava AI Concurrency Benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of Ava server")
    parser.add_argument("--users", type=int, default=15, help="Number of concurrent users")
    parser.add_argument("--requests-per-user", type=int, default=3, help="Chat+Feedback pairs per user")
    args = parser.parse_args()

    ok = run_load_test(args.base_url, args.users, args.requests_per_user)
    sys.exit(0 if ok else 1)
