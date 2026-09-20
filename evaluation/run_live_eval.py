#!/usr/bin/env python3
"""
evaluation/run_live_eval.py — Live End-to-End Groq LLM Behavioral Adaptation Evaluator.

OPTIONAL script for manual validation against the live Groq API.
Excluded from automated CI/CD pipelines.

Usage:
    GROQ_API_KEY="gsk_..." python evaluation/run_live_eval.py
"""

import os
import sys
import uuid
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
import adaptation
from llm import call_llm
from main import assemble_chat_prompt_context


def run_live_evaluation():
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("[SKIP] GROQ_API_KEY is not configured in environment. Skipping live evaluation.")
        print("To run live Groq validation: export GROQ_API_KEY='gsk_...' && python evaluation/run_live_eval.py")
        return 0

    print("======================================================================")
    print("  Ava AI — Live Groq Behavioral Adaptation Validation")
    print("======================================================================")

    test_user_id = f"live_eval_{uuid.uuid4().hex[:6]}"
    adaptation.reset_adaptation_profile(test_user_id)

    print(f"\n[1] Training user '{test_user_id}' with 'concise_with_code' preference...")
    for msg in [
        "Please keep answers concise with Python code.",
        "Code snippets only, minimal explanation.",
        "Quick python function please."
    ]:
        adaptation.observe_interaction(
            user_id=test_user_id,
            user_message=msg,
            agent_response="def fn(): pass",
            adaptation_used=True,
        )
        db.record_strategy_feedback(test_user_id, "concise_with_code", helpful=True)

    policy = adaptation.build_behavior_policy(test_user_id)
    print(f"    Resolved Policy: strategy={policy.get('preferred_strategy')}, verbosity={policy.get('verbosity')}")

    test_prompt = "Write a function to check if a string is a palindrome."
    sys_prompt, meta = assemble_chat_prompt_context(
        user_id=test_user_id,
        message=test_prompt,
    )
    print(f"\n[2] Assembled System Prompt with Adaptation Context:")
    print("    " + "\n    ".join(sys_prompt.splitlines()[:6]) + "\n    ...")

    print(f"\n[3] Calling Groq API (llama-3.3-70b-versatile)...")
    t0 = time.time()
    try:
        response = call_llm(test_prompt, system_prompt=sys_prompt)
        elapsed = time.time() - t0
        print(f"    Response received in {elapsed:.2f}s:")
        print("    " + "-" * 50)
        print("    " + "\n    ".join(response.splitlines()))
        print("    " + "-" * 50)
        print("\n[SUCCESS] Live Groq adaptation evaluation completed successfully.")
        return 0
    except Exception as e:
        print(f"\n[ERROR] Live Groq call failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_live_evaluation())
