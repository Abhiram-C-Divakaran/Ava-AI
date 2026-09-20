#!/usr/bin/env python3
"""
evaluation/evaluate_memory.py — Independent Factual Memory Benchmark.

Evaluates persistent cross-session factual memory independently of subjective style:
1. Memory Recall Accuracy (%): Precision of retrieving stored user facts.
2. Memory Omission Rate (%): Accurate omission of unmentioned/unstored facts without hallucination.
3. False-Memory Rate (%): Rate of asserting false or prohibited facts.
4. Cross-User Leakage Rate (%): Rate of facts leaking between distinct user accounts (strictly 0.0%).

Usage:
    python evaluation/evaluate_memory.py
"""

import os
import sys
import json
import uuid
import tempfile
import sqlite3

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
import memory
from main import assemble_chat_prompt_context


def run_memory_benchmark():
    cases_file = os.path.join(BASE_DIR, "evaluation", "memory_benchmark_cases.json")
    with open(cases_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print("=" * 76)
    print("  Ava AI — Independent Factual Memory & Cross-User Isolation Benchmark")
    print("=" * 76)
    print(f"Loaded {len(cases)} benchmark cases from {cases_file}\n")

    # Isolated evaluation database
    temp_dir = tempfile.TemporaryDirectory()
    bench_db = os.path.join(temp_dir.name, "memory_benchmark.db")
    orig_db_path = db.DB_PATH

    try:
        db.DB_PATH = bench_db
        db.init_db()

        total_cases = len(cases)
        correct_recalls = 0
        total_recall_opportunities = 0
        omissions_correct = 0
        total_omission_opportunities = 0
        false_memories = 0
        cross_user_leakages = 0
        cross_user_tests = 0

        case_results = []

        for case in cases:
            case_id = case["id"]
            category = case["category"]
            user_id = f"{case['user_id']}_{uuid.uuid4().hex[:4]}"
            query = case["query"]
            stored_facts = case.get("stored_facts", "")
            expected_facts = case.get("expected_facts", [])
            prohibited_facts = case.get("prohibited_facts", [])
            is_negative = case.get("is_negative_control", False)
            is_cross_user = case.get("is_cross_user_test", False)

            # Store memory for primary test user
            if stored_facts:
                db.set_user_memory(user_id, stored_facts, message_count_at_update=10)
            elif case.get("stored_facts_user"):
                db.set_user_memory(user_id, case["stored_facts_user"], message_count_at_update=10)

            # If cross-user test, store distinct facts for other user
            if is_cross_user:
                cross_user_tests += 1
                other_user_id = f"{case['other_user_id']}_{uuid.uuid4().hex[:4]}"
                db.set_user_memory(other_user_id, case["stored_facts_other"], message_count_at_update=10)

            # Assemble chat prompt context for primary user
            sys_prompt, aug_meta = assemble_chat_prompt_context(
                user_id=user_id,
                message=query,
                adaptation_enabled=True,
            )

            user_mem_context = aug_meta.get("user_memory_context", "")

            # 1. Recall Check
            case_recalled = True
            if expected_facts:
                total_recall_opportunities += 1
                for ef in expected_facts:
                    if ef.lower() not in user_mem_context.lower():
                        case_recalled = False
                if case_recalled:
                    correct_recalls += 1

            # 2. False Memory / Prohibited Fact Check
            has_false_memory = False
            for pf in prohibited_facts:
                if pf.lower() in user_mem_context.lower():
                    has_false_memory = True
                    break
            if has_false_memory:
                false_memories += 1

            # 3. Negative Control / Omission Check
            if is_negative:
                total_omission_opportunities += 1
                if not has_false_memory:
                    omissions_correct += 1

            # 4. Cross-User Leakage Check
            leaked = False
            if is_cross_user:
                other_facts = case.get("stored_facts_other", "")
                # Extract key identifiers
                for line in other_facts.splitlines():
                    clean_line = line.replace("•", "").strip()
                    if clean_line and clean_line.lower() in user_mem_context.lower():
                        leaked = True
                        break
                if leaked:
                    cross_user_leakages += 1

            status = "PASS" if (case_recalled and not has_false_memory and not leaked) else "FAIL"
            case_results.append({
                "case_id": case_id,
                "category": category,
                "recalled": case_recalled,
                "false_memory": has_false_memory,
                "cross_user_leakage": leaked,
                "status": status,
            })

            print(f"[{status}] {case_id:<8} | Category: {category:<20} | Recalled: {case_recalled} | FalseMem: {has_false_memory} | Leak: {leaked}")

        # Summary calculations
        recall_accuracy = (correct_recalls / total_recall_opportunities * 100.0) if total_recall_opportunities else 100.0
        omission_rate = (omissions_correct / total_omission_opportunities * 100.0) if total_omission_opportunities else 100.0
        false_memory_rate = (false_memories / total_cases * 100.0)
        cross_user_leakage_rate = (cross_user_leakages / cross_user_tests * 100.0) if cross_user_tests else 0.0

        print("\n" + "=" * 76)
        print("  FACTUAL MEMORY BENCHMARK METRICS SUMMARY")
        print("=" * 76)
        print(f"  • Total Benchmark Cases:        {total_cases}")
        print(f"  • Memory Recall Opportunities:  {total_recall_opportunities}")
        print(f"  • Successful Recalls:           {correct_recalls}")
        print(f"  • Memory Recall Accuracy:       {recall_accuracy:.2f}%")
        print(f"  • Memory Omission Accuracy:     {omission_rate:.2f}% (No unprompted hallucinations)")
        print(f"  • False-Memory Rate:            {false_memory_rate:.2f}%")
        print(f"  • Cross-User Leakage Tests:     {cross_user_tests}")
        print(f"  • Cross-User Leakage Rate:      {cross_user_leakage_rate:.2f}% (Target: strictly 0.0%)")
        print("=" * 76)

        results_payload = {
            "total_cases": total_cases,
            "recall_accuracy_pct": recall_accuracy,
            "omission_accuracy_pct": omission_rate,
            "false_memory_rate_pct": false_memory_rate,
            "cross_user_leakage_rate_pct": cross_user_leakage_rate,
            "cases": case_results,
        }

        output_path = os.path.join(BASE_DIR, "evaluation", "memory_benchmark_results.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results_payload, f, indent=2)
        print(f"\nBenchmark results saved to: {output_path}")

        if cross_user_leakage_rate > 0.0:
            print("\n[CRITICAL ERROR] Cross-user memory leakage detected!")
            return 1

        if recall_accuracy < 100.0 or false_memory_rate > 0.0:
            print("\n[WARNING] Memory benchmark did not achieve 100% accuracy.")
            return 1

        print("\n[PASS] Factual memory benchmark passed all gates.")
        return 0

    finally:
        db.DB_PATH = orig_db_path
        temp_dir.cleanup()


if __name__ == "__main__":
    sys.exit(run_memory_benchmark())
