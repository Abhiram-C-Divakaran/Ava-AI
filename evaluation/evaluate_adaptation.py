#!/usr/bin/env python3
"""
evaluation/evaluate_adaptation.py — Offline Adaptation Evaluation Suite for Ava AI.

Evaluates behavioral adaptation accuracy, policy generation, and prompt assembly
against 8 canonical behavioral scenarios without calling external LLM APIs.
"""

import os
import sys
import json
import time
import uuid
import tempfile

# Ensure workspace root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
import adaptation
from main import assemble_chat_prompt_context


def run_evaluation(cases_path: str = None) -> bool:
    if not cases_path:
        cases_path = os.path.join(os.path.dirname(__file__), "adaptation_cases.json")

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Use an isolated temporary database for evaluation
    temp_dir = tempfile.TemporaryDirectory()
    test_db_path = os.path.join(temp_dir.name, "eval_adaptation.db")
    orig_db = db.DB_PATH
    db.DB_PATH = test_db_path
    db.init_db()

    total = len(cases)
    passed = 0
    failed = 0
    results = []

    print(f"\n======================================================================")
    print(f"  Ava AI — Behavioral Adaptation Quality Evaluation ({total} cases)")
    print(f"======================================================================\n")

    try:
        for idx, case in enumerate(cases, 1):
            case_id = case["id"]
            name = case["name"]
            user_id = f"eval_{case_id}_{uuid.uuid4().hex[:6]}"
            session_id = str(uuid.uuid4())
            t0 = time.time()
            errors = []

            # 1. Reset user adaptation profile
            adaptation.reset_adaptation_profile(user_id)
            db.create_session(session_id, user_id, title="Eval Session")

            # 2. Simulate interactions
            for inter in case.get("interactions", []):
                user_msg = inter["user_message"]
                agent_resp = inter.get("agent_response", "Acknowledged.")
                strategy = inter.get("strategy")
                feedback = inter.get("feedback", True)

                adaptation.observe_interaction(
                    user_id=user_id,
                    user_message=user_msg,
                    agent_response=agent_resp,
                    adaptation_used=(strategy is not None),
                )
                if strategy:
                    db.record_strategy_feedback(user_id, strategy, helpful=feedback)

            # 3. Build behavior policy
            policy = adaptation.build_behavior_policy(user_id)

            # 4. Check expected policy attributes
            expected_policy = case.get("expected_policy", {})
            for k, v in expected_policy.items():
                actual_v = policy.get(k)
                if actual_v != v:
                    errors.append(f"Policy mismatch for '{k}': expected '{v}', got '{actual_v}'")

            # 5. Assemble prompt context
            test_query = case.get("test_query", "Hello")
            sys_prompt, meta = assemble_chat_prompt_context(
                user_id=user_id,
                message=test_query,
                session_id=session_id,
            )

            prompt_lower = sys_prompt.lower()
            for must_contain in case.get("expected_system_prompt_contains", []):
                if must_contain.lower() not in prompt_lower:
                    errors.append(f"System prompt missing expected text: '{must_contain}'")

            for must_exclude in case.get("expected_system_prompt_excludes", []):
                if must_exclude.lower() in prompt_lower:
                    errors.append(f"System prompt unexpectedly contained: '{must_exclude}'")

            elapsed_ms = (time.time() - t0) * 1000

            if not errors:
                passed += 1
                status = "PASS"
                print(f"  [{idx}/{total}] PASS  — {name} ({elapsed_ms:.1f}ms)")
            else:
                failed += 1
                status = "FAIL"
                print(f"  [{idx}/{total}] FAIL  — {name} ({elapsed_ms:.1f}ms)")
                for err in errors:
                    print(f"        * {err}")

            results.append({
                "id": case_id,
                "name": name,
                "status": status,
                "elapsed_ms": round(elapsed_ms, 2),
                "errors": errors
            })

    finally:
        db.DB_PATH = orig_db
        try:
            temp_dir.cleanup()
        except Exception:
            pass

    print(f"\n----------------------------------------------------------------------")
    print(f"  Evaluation Summary: {passed}/{total} Passed, {failed} Failed")
    print(f"----------------------------------------------------------------------\n")

    return failed == 0


if __name__ == "__main__":
    success = run_evaluation()
    sys.exit(0 if success else 1)
