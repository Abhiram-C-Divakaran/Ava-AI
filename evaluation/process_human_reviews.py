#!/usr/bin/env python3
"""
evaluation/process_human_reviews.py — Process Blind Human Reviews & Compute Quality Metrics.

Computes:
1. Adapted Win Rate, Baseline Win Rate, Tie Rate
2. Wilson Score 95% Binomial Confidence Intervals
3. Average Rubric Dimensions (1-5 scale):
   - Instruction Adherence (Adapted vs Baseline)
   - Clarity (Adapted vs Baseline)
   - Usefulness (Adapted vs Baseline)
   - Personalization Fit (Adapted vs Baseline)
   - Correctness (Adapted vs Baseline)
4. Category-by-Category Win/Loss/Tie Breakdown

Usage:
    python evaluation/process_human_reviews.py [--reviews evaluation/human_review_completed.csv]
"""

import os
import sys
import json
import csv
import math
import argparse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """
    Calculates the Wilson score interval for a binomial proportion.
    More accurate than normal approximation for moderate sample sizes (e.g. N=60).
    """
    if total == 0:
        return (0.0, 0.0)
    z = 1.959964  # 95% confidence standard normal quantile
    p_hat = successes / total
    denominator = 1.0 + (z ** 2) / total
    center = (p_hat + (z ** 2) / (2 * total)) / denominator
    spread = (z * math.sqrt((p_hat * (1 - p_hat) / total) + (z ** 2) / (4 * (total ** 2)))) / denominator
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return round(lower * 100, 2), round(upper * 100, 2)


def process_reviews(reviews_path: str, internal_key_path: str, output_path: str):
    if not os.path.exists(reviews_path):
        print(f"Error: Review file not found: {reviews_path}")
        return 1
    if not os.path.exists(internal_key_path):
        print(f"Error: Internal truth key not found: {internal_key_path}")
        return 1

    with open(internal_key_path, "r", encoding="utf-8") as f:
        internal_data = json.load(f)
    internal_map = {item["case_id"]: item for item in internal_data}

    # Read review CSV
    reviews = []
    with open(reviews_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("case_id"):
                reviews.append(row)

    total_reviewed = len(reviews)
    if total_reviewed == 0:
        print("Error: No reviewed cases found in CSV.")
        return 1

    adapted_wins = 0
    baseline_wins = 0
    ties = 0

    scores_adapted = {
        "instruction_adherence": [],
        "clarity": [],
        "usefulness": [],
        "personalization_fit": [],
        "correctness": [],
    }
    scores_baseline = {
        "instruction_adherence": [],
        "clarity": [],
        "usefulness": [],
        "personalization_fit": [],
        "correctness": [],
    }

    category_breakdown = {}

    for row in reviews:
        cid = row["case_id"]
        cat = row.get("category", "unknown")
        if cat not in category_breakdown:
            category_breakdown[cat] = {"count": 0, "adapted_wins": 0, "baseline_wins": 0, "ties": 0}
        category_breakdown[cat]["count"] += 1

        internal = internal_map.get(cid)
        if not internal:
            print(f"Warning: Case ID {cid} not in internal truth key. Skipping.")
            continue

        a_is_adapted = internal["a_is_adapted"]
        pref = row.get("preferred_response", "").strip().upper()

        if pref == "A":
            if a_is_adapted:
                adapted_wins += 1
                category_breakdown[cat]["adapted_wins"] += 1
            else:
                baseline_wins += 1
                category_breakdown[cat]["baseline_wins"] += 1
        elif pref == "B":
            if a_is_adapted:
                baseline_wins += 1
                category_breakdown[cat]["baseline_wins"] += 1
            else:
                adapted_wins += 1
                category_breakdown[cat]["adapted_wins"] += 1
        elif pref in ("TIE", "T"):
            ties += 1
            category_breakdown[cat]["ties"] += 1
        else:
            print(f"Warning: Invalid preferred_response '{pref}' for {cid}. Defaulting to Tie.")
            ties += 1
            category_breakdown[cat]["ties"] += 1

        # Extract dimension scores (1-5)
        for dim, key_a, key_b in [
            ("instruction_adherence", "instruction_adherence_A", "instruction_adherence_B"),
            ("clarity", "clarity_A", "clarity_B"),
            ("usefulness", "usefulness_A", "usefulness_B"),
            ("personalization_fit", "personalization_fit_A", "personalization_fit_B"),
            ("correctness", "correctness_A", "correctness_B"),
        ]:
            val_a = float(row.get(key_a) or 4.0)
            val_b = float(row.get(key_b) or 4.0)
            if a_is_adapted:
                scores_adapted[dim].append(val_a)
                scores_baseline[dim].append(val_b)
            else:
                scores_adapted[dim].append(val_b)
                scores_baseline[dim].append(val_a)

    # Calculate metrics
    adapted_win_rate = (adapted_wins / total_reviewed) * 100.0
    baseline_win_rate = (baseline_wins / total_reviewed) * 100.0
    tie_rate = (ties / total_reviewed) * 100.0

    ci_low, ci_high = wilson_score_interval(adapted_wins, total_reviewed, 0.95)

    def mean(lst):
        return round(sum(lst) / len(lst), 2) if lst else 0.0

    dim_means = {
        "instruction_adherence": {"adapted": mean(scores_adapted["instruction_adherence"]), "baseline": mean(scores_baseline["instruction_adherence"])},
        "clarity": {"adapted": mean(scores_adapted["clarity"]), "baseline": mean(scores_baseline["clarity"])},
        "usefulness": {"adapted": mean(scores_adapted["usefulness"]), "baseline": mean(scores_baseline["usefulness"])},
        "personalization_fit": {"adapted": mean(scores_adapted["personalization_fit"]), "baseline": mean(scores_baseline["personalization_fit"])},
        "correctness": {"adapted": mean(scores_adapted["correctness"]), "baseline": mean(scores_baseline["correctness"])},
    }

    # Print summary table
    print("=" * 76)
    print("  BLIND HUMAN EVALUATION QUALITY METRICS (N = 60 Paired Responses)")
    print("=" * 76)
    print(f"  • Total Cases Reviewed:         {total_reviewed}")
    print(f"  • Adapted Preferred (Wins):     {adapted_wins} ({adapted_win_rate:.1f}%)")
    print(f"  • Baseline Preferred (Wins):    {baseline_wins} ({baseline_win_rate:.1f}%)")
    print(f"  • Ties:                         {ties} ({tie_rate:.1f}%)")
    print(f"  • Adapted Win Rate 95% CI:      [{ci_low:.1f}%, {ci_high:.1f}%] (Wilson Score Interval)")
    print("-" * 76)
    print("DIMENSION SCORE COMPARISON (1.00 – 5.00 Scale):")
    print(f"{'Dimension':<24} | {'Adapted':<12} | {'Baseline':<12} | {'Delta':<10}")
    print("-" * 76)
    for dim, vals in dim_means.items():
        delta = vals['adapted'] - vals['baseline']
        sign = "+" if delta >= 0 else ""
        print(f"{dim:<24} | {vals['adapted']:<12.2f} | {vals['baseline']:<12.2f} | {sign}{delta:.2f}")
    print("-" * 76)
    print("CATEGORY BREAKDOWN:")
    print(f"{'Category':<18} | {'Total':<6} | {'Adapted Wins':<14} | {'Baseline Wins':<14} | {'Ties':<6}")
    print("-" * 76)
    for cat, data in category_breakdown.items():
        print(f"{cat:<18} | {data['count']:<6} | {data['adapted_wins']:<14} | {data['baseline_wins']:<14} | {data['ties']:<6}")
    print("=" * 76)

    payload = {
        "total_reviewed": total_reviewed,
        "adapted_wins": adapted_wins,
        "adapted_win_rate_pct": round(adapted_win_rate, 2),
        "baseline_wins": baseline_wins,
        "baseline_win_rate_pct": round(baseline_win_rate, 2),
        "ties": ties,
        "tie_rate_pct": round(tie_rate, 2),
        "wilson_ci_95": {"lower_pct": ci_low, "upper_pct": ci_high},
        "dimension_means": dim_means,
        "category_breakdown": category_breakdown,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nSaved metrics summary to: {output_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process human evaluation reviews.")
    parser.add_argument("--reviews", default=os.path.join(BASE_DIR, "evaluation", "human_review_completed.csv"))
    parser.add_argument("--internal-key", default=os.path.join(BASE_DIR, "evaluation", "response_eval_results_internal.json"))
    parser.add_argument("--output", default=os.path.join(BASE_DIR, "evaluation", "human_review_metrics.json"))
    args = parser.parse_args()
    sys.exit(process_reviews(args.reviews, args.internal_key, args.output))
