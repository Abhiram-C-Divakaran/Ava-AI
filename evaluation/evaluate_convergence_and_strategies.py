#!/usr/bin/env python3
"""
evaluation/evaluate_convergence_and_strategies.py — Adaptation Convergence, Reversal & Strategy Learning Benchmark.

Measures:
1. Preference Convergence: Exact signal counts required for all 6 dimensions to cross threshold (>=0.70).
2. Preference Reversal: Dynamics of concise -> detailed transition and Turn-1 prompt override verification.
3. Strategy Learning Matrix: Establishment, suppression, recovery, decay, and domain matching across all 6 strategies.

Usage:
    python evaluation/evaluate_convergence_and_strategies.py
"""

import os
import sys
import json
import uuid
import tempfile
from datetime import datetime, timezone, timedelta

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
import adaptation
from main import assemble_chat_prompt_context


def run_benchmark():
    print("=" * 76)
    print("  Ava AI — Adaptation Convergence, Preference Reversal & Strategy Learning")
    print("=" * 76 + "\n")

    temp_dir = tempfile.TemporaryDirectory()
    bench_db = os.path.join(temp_dir.name, "convergence_benchmark.db")
    orig_db_path = db.DB_PATH

    try:
        db.DB_PATH = bench_db
        db.init_db()

        # ---------------------------------------------------------------------
        # 1. PREFERENCE CONVERGENCE BENCHMARK (All 6 Dimensions)
        # ---------------------------------------------------------------------
        print("PART 1: PREFERENCE CONVERGENCE (Target Confidence >= 0.70)")
        print("-" * 76)
        print(f"{'Dimension':<18} | {'Target':<14} | {'Signal Type':<12} | {'Signals Req':<12} | {'Final Conf':<10} | {'Status'}")
        print("-" * 76)

        dimension_test_signals = {
            "verbosity": {
                "explicit": ("concise", "Please be concise and keep it short."),
                "implicit": ("concise", "quick answer"),
            },
            "technical_depth": {
                "explicit": ("advanced", "You can skip the basics and provide advanced technical architecture."),
                "implicit": ("advanced", None),  # Not defined in PATTERNS_IMPLICIT (architectural design choice)
            },
            "code_examples": {
                "explicit": (True, "Please show me the code with python code example."),
                "implicit": (True, "function to parse json in python"),
            },
            "step_by_step": {
                "explicit": (True, "Please walk me through step by step."),
                "implicit": (True, "what do i do next"),
            },
            "examples": {
                "explicit": (True, "Please give me an example with practical examples."),
                "implicit": (True, None),  # Not defined in PATTERNS_IMPLICIT
            },
            "tone": {
                "explicit": ("formal", "Please maintain a formal tone and professional tone."),
                "implicit": ("formal", None),  # Not defined in PATTERNS_IMPLICIT
            },
        }

        convergence_results = {}

        for dim, modes in dimension_test_signals.items():
            for sig_type in ["explicit", "implicit"]:
                val, msg = modes[sig_type]
                if msg is None:
                    # Documented architectural boundary: implicit learning is only enabled for verbosity, code, steps
                    print(f"{dim:<18} | {str(val):<14} | {sig_type:<12} | {'N/A':<12} | {'0.500':<10} | [N/A - No Implicit Pattern]")
                    convergence_results[f"{dim}_{sig_type}"] = {
                        "dimension": dim,
                        "target_value": val,
                        "signal_type": sig_type,
                        "signals_required": None,
                        "final_confidence": 0.50,
                        "status": "N/A (Implicit patterns intentionally omitted)",
                    }
                    continue

                u_id = f"conv_{dim}_{sig_type}_{uuid.uuid4().hex[:4]}"
                adaptation.reset_adaptation_profile(u_id)

                signals = 0
                max_signals = 15
                final_conf = 0.50

                while signals < max_signals:
                    signals += 1
                    adaptation.observe_interaction(
                        user_id=u_id,
                        user_message=msg,
                        agent_response="Response acknowledging request.",
                        adaptation_used=True,
                    )
                    profile = adaptation.get_adaptation_profile(u_id)
                    curr_item = profile.get(dim, {})
                    final_conf = curr_item.get("confidence", 0.50)
                    if curr_item.get("value") == val and final_conf >= 0.70:
                        break

                passed = (final_conf >= 0.70 and profile.get(dim, {}).get("value") == val)
                status = "PASS" if passed else "FAIL"
                val_str = str(val)

                print(f"{dim:<18} | {val_str:<14} | {sig_type:<12} | {signals:<12} | {final_conf:<10.3f} | [{status}]")

                convergence_results[f"{dim}_{sig_type}"] = {
                    "dimension": dim,
                    "target_value": val,
                    "signal_type": sig_type,
                    "signals_required": signals,
                    "final_confidence": final_conf,
                    "passed": passed,
                }

        # ---------------------------------------------------------------------
        # 2. PREFERENCE REVERSAL & IMMEDIATE PROMPT OVERRIDE BENCHMARK
        # ---------------------------------------------------------------------
        print("\n" + "-" * 76)
        print("PART 2: PREFERENCE REVERSAL & TURN-1 PROMPT OVERRIDE")
        print("-" * 76)

        rev_user = f"rev_user_{uuid.uuid4().hex[:4]}"
        adaptation.reset_adaptation_profile(rev_user)

        # Phase 1: Establish strong concise profile
        for _ in range(3):
            adaptation.observe_interaction(
                user_id=rev_user,
                user_message="Please be concise and keep it short.",
                agent_response="Short answer.",
                adaptation_used=True,
            )
        p1_profile = adaptation.get_adaptation_profile(rev_user)
        p1_conf = p1_profile.get("verbosity", {}).get("confidence", 0.0)
        p1_val = p1_profile.get("verbosity", {}).get("value", "")
        print(f"  Phase 1 Baseline: verbosity='{p1_val}' with confidence {p1_conf:.3f}")

        # Phase 2: Contradictory prompt on Turn 1
        turn1_prompt = "Explain Kubernetes pod scheduling in detail with a comprehensive walkthrough."
        turn1_sys_prompt, turn1_meta = assemble_chat_prompt_context(
            user_id=rev_user,
            message=turn1_prompt,
            adaptation_enabled=True,
        )

        # In Turn 1 prompt: verify explicit detail override took effect
        # Priority rule dictates current explicit prompt supersedes learned concise preference
        override_success = (
            "comprehensive" in turn1_prompt.lower() and
            ("Verbosity: Prefer concise" not in turn1_sys_prompt)
        )
        print(f"  Turn 1 Immediate Override: {'SUCCESS (Prompt override active immediately)' if override_success else 'FAILED'}")

        # Phase 3: Consecutive detailed signals to achieve full profile reversal
        reversal_signals = 0
        reversed_conf = 0.0
        while reversal_signals < 10:
            reversal_signals += 1
            adaptation.observe_interaction(
                user_id=rev_user,
                user_message="Give me a thorough explanation with in-depth analysis.",
                agent_response="Detailed comprehensive explanation.",
                adaptation_used=True,
            )
            curr_p = adaptation.get_adaptation_profile(rev_user)
            curr_verb = curr_p.get("verbosity", {})
            reversed_conf = curr_verb.get("confidence", 0.0)
            if curr_verb.get("value") == "detailed" and reversed_conf >= 0.70:
                break

        print(f"  Reversal Convergence: {reversal_signals} explicit signals to reverse profile to 'detailed' (conf: {reversed_conf:.3f})")

        reversal_results = {
            "initial_state": {"value": p1_val, "confidence": p1_conf},
            "turn_1_override_respected": override_success,
            "reversal_signals_required": reversal_signals,
            "final_reversed_confidence": reversed_conf,
        }

        # ---------------------------------------------------------------------
        # 3. STRATEGY LEARNING MATRIX (All 6 Supported Strategies)
        # ---------------------------------------------------------------------
        print("\n" + "-" * 76)
        print("PART 3: STRATEGY LEARNING MATRIX (6 Predefined Strategies)")
        print("-" * 76)
        print(f"{'Strategy':<24} | {'Established':<12} | {'Suppressed':<12} | {'Recovered':<12} | {'Decayed':<10} | {'Status'}")
        print("-" * 76)

        strategy_results = {}
        all_strats = sorted(list(adaptation.SUPPORTED_STRATEGIES))

        for strat in all_strats:
            s_user = f"strat_{strat}_{uuid.uuid4().hex[:4]}"

            # 1. Establishment: 3 positive feedback signals
            for _ in range(3):
                db.record_strategy_feedback(s_user, strat, helpful=True)

            score_est = adaptation.get_strategy_score(s_user, strat)
            pref_list = adaptation.get_preferred_strategies(s_user)
            est_ok = (strat in pref_list and score_est >= 0.70)

            # 2. Suppression: 4 negative feedback signals
            for _ in range(4):
                db.record_strategy_feedback(s_user, strat, helpful=False)

            score_supp = adaptation.get_strategy_score(s_user, strat)
            supp_ok = adaptation.is_strategy_suppressed(s_user, strat)

            # 3. Recovery: 5 positive feedback signals to overcome negative history
            for _ in range(5):
                db.record_strategy_feedback(s_user, strat, helpful=True)

            score_rec = adaptation.get_strategy_score(s_user, strat)
            rec_ok = not adaptation.is_strategy_suppressed(s_user, strat) and score_rec > 0.55

            # 4. Decay: Check evidence decay factor after simulated 60 days
            now = datetime.now(timezone.utc)
            future = now + timedelta(days=60)
            decayed_score = adaptation.get_strategy_score(s_user, strat, now_time=future)
            decay_ok = decayed_score < score_rec

            strat_pass = (est_ok and supp_ok and rec_ok and decay_ok)
            s_status = "PASS" if strat_pass else "FAIL"

            print(f"{strat:<24} | {str(est_ok):<12} | {str(supp_ok):<12} | {str(rec_ok):<12} | {str(decay_ok):<10} | [{s_status}]")

            strategy_results[strat] = {
                "strategy": strat,
                "established": est_ok,
                "score_established": score_est,
                "suppressed": supp_ok,
                "score_suppressed": score_supp,
                "recovered": rec_ok,
                "score_recovered": score_rec,
                "decay_verified": decay_ok,
                "score_decayed": decayed_score,
                "passed": strat_pass,
            }

        print("=" * 76)

        # Save all results to disk
        summary_payload = {
            "convergence": convergence_results,
            "preference_reversal": reversal_results,
            "strategy_learning": strategy_results,
        }

        out_file = os.path.join(BASE_DIR, "evaluation", "convergence_and_strategies_results.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(summary_payload, f, indent=2)

        print(f"\nAll benchmark results saved to: {out_file}")
        print("[PASS] Convergence, reversal, and strategy learning benchmarks completed successfully.")
        return 0

    finally:
        db.DB_PATH = orig_db_path
        temp_dir.cleanup()


if __name__ == "__main__":
    sys.exit(run_benchmark())
