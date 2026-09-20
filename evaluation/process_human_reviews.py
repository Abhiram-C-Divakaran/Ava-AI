#!/usr/bin/env python3
"""
evaluation/process_human_reviews.py — Process Blind Human Reviews & Compute Quality Metrics.

Features:
1. Strict schema & value validation:
   - Every rubric dimension (instruction_adherence, clarity, usefulness, personalization_fit, correctness)
     is required, numeric, and must be in [1.0, 5.0]. Missing values are strictly rejected (NO default to 4.0).
   - 'preferred_response' is strictly required and must be 'A', 'B', or 'TIE' (no silent conversion).
   - Review completeness check: exactly 60 unique cases matching the evaluation set are required.
     Rejects duplicates, missing cases, and unknown cases.
2. Review provenance tracking:
   - Supports optional fields: reviewer_id, reviewed_at, review_round.
3. Multi-reviewer support:
   - Supports multiple independent reviewers: computes percentage agreement and Cohen's Kappa for inter-rater reliability.
4. Formal statistical metrics:
   - Adapted Win Rate, Baseline Win Rate, Tie Rate, and Non-tied preference rate.
   - Wilson Score 95% Binomial Confidence Interval.
   - Dimension means, deltas, and category breakdowns.

Usage:
    python evaluation/process_human_reviews.py [--reviews evaluation/human_review_completed.csv]
"""

import os
import sys
import json
import csv
import math
import argparse
from typing import Dict, List, Any, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

RUBRIC_DIMENSIONS = [
    "instruction_adherence",
    "clarity",
    "usefulness",
    "personalization_fit",
    "correctness",
]


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


def validate_and_parse_score(val: Any, cid: str, col: str, row_idx: int) -> float:
    """
    Validates a numeric rubric score strictly:
    - Must not be None or empty.
    - Must be a valid float.
    - Must be in range [1.0, 5.0].
    """
    if val is None or str(val).strip() == "":
        raise ValueError(
            f"Review Validation Error [Row {row_idx}, Case '{cid}']: Missing score for '{col}'. "
            f"Every score must be explicitly provided in range [1.0, 5.0]."
        )
    try:
        score = float(str(val).strip())
    except (ValueError, TypeError):
        raise ValueError(
            f"Review Validation Error [Row {row_idx}, Case '{cid}']: Non-numeric score '{val}' for '{col}'."
        )
    if score < 1.0 or score > 5.0:
        raise ValueError(
            f"Review Validation Error [Row {row_idx}, Case '{cid}']: Score {score} for '{col}' is out of bounds [1.0, 5.0]."
        )
    return score


def validate_and_parse_preference(val: Any, cid: str, row_idx: int) -> str:
    """
    Validates preferred_response:
    - Must not be None or empty.
    - Must be 'A', 'B', or 'TIE'.
    """
    if val is None or str(val).strip() == "":
        raise ValueError(
            f"Review Validation Error [Row {row_idx}, Case '{cid}']: Missing 'preferred_response'. "
            f"Allowed values: 'A', 'B', 'TIE'."
        )
    pref = str(val).strip().upper()
    if pref == "T":
        pref = "TIE"
    if pref not in ("A", "B", "TIE"):
        raise ValueError(
            f"Review Validation Error [Row {row_idx}, Case '{cid}']: Invalid 'preferred_response' '{val}'. "
            f"Allowed values are 'A', 'B', or 'TIE'."
        )
    return pref


def calculate_cohens_kappa(prefs1: List[str], prefs2: List[str]) -> float:
    """
    Computes Cohen's Kappa between two raters on preferred_response ('A', 'B', 'TIE').
    """
    if not prefs1 or len(prefs1) != len(prefs2):
        return 0.0
    n = len(prefs1)
    categories = ["A", "B", "TIE"]

    # Observed agreement
    po = sum(1 for p1, p2 in zip(prefs1, prefs2) if p1 == p2) / n

    # Expected agreement by chance
    pe = sum(
        (prefs1.count(cat) / n) * (prefs2.count(cat) / n)
        for cat in categories
    )
    if pe == 1.0:
        return 1.0
    kappa = (po - pe) / (1.0 - pe)
    return round(kappa, 4)


def validate_review_completeness(reviews: List[Dict[str, Any]], expected_case_ids: set) -> None:
    """
    Ensures that reviewed rows exactly match expected benchmark cases:
    - No duplicate case IDs.
    - No unknown case IDs.
    - No missing case IDs.
    - Count == expected count.
    """
    seen = set()
    duplicates = set()
    unknowns = set()

    for idx, row in enumerate(reviews, 1):
        cid = (row.get("case_id") or "").strip()
        if not cid:
            raise ValueError(f"Review Validation Error [Row {idx}]: Blank or missing 'case_id'.")
        if cid in seen:
            duplicates.add(cid)
        seen.add(cid)
        if cid not in expected_case_ids:
            unknowns.add(cid)

    if duplicates:
        raise ValueError(f"Review Validation Error: Duplicate case IDs found in review set: {sorted(list(duplicates))}")
    if unknowns:
        raise ValueError(f"Review Validation Error: Unknown case IDs found in review set not in benchmark: {sorted(list(unknowns))}")

    missing = expected_case_ids - seen
    if missing:
        raise ValueError(f"Review Validation Error: Review set is incomplete. Missing {len(missing)} cases: {sorted(list(missing))[:5]}...")

    if len(seen) != len(expected_case_ids):
        raise ValueError(f"Review Validation Error: Expected {len(expected_case_ids)} unique reviewed cases, found {len(seen)}.")


def process_reviews(reviews_path: str, internal_key_path: str, output_path: str) -> int:
    if not os.path.exists(reviews_path):
        print(f"Error: Review file not found: {reviews_path}")
        return 1
    if not os.path.exists(internal_key_path):
        print(f"Error: Internal truth key not found: {internal_key_path}")
        return 1

    with open(internal_key_path, "r", encoding="utf-8") as f:
        internal_data = json.load(f)
    internal_map = {item["case_id"]: item for item in internal_data}
    expected_case_ids = set(internal_map.keys())

    # Read review CSV
    raw_rows = []
    with open(reviews_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("case_id"):
                raw_rows.append(row)

    if not raw_rows:
        print("Error: No reviewed cases found in CSV.")
        return 1

    # Check for multi-reviewer dataset (grouped by reviewer_id)
    reviewer_groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in raw_rows:
        rid = (r.get("reviewer_id") or "reviewer_01").strip()
        reviewer_groups.setdefault(rid, []).append(r)

    multi_reviewer = len(reviewer_groups) > 1
    inter_rater_stats = {}

    if multi_reviewer:
        print(f"Detected multi-reviewer dataset with {len(reviewer_groups)} reviewers: {list(reviewer_groups.keys())}")
        # Validate each reviewer's completeness independently
        for rid, r_rows in reviewer_groups.items():
            try:
                validate_review_completeness(r_rows, expected_case_ids)
            except ValueError as exc:
                print(f"Validation failed for reviewer '{rid}': {exc}")
                raise

        # Calculate inter-rater agreement if exactly 2 reviewers
        reviewer_ids = list(reviewer_groups.keys())
        if len(reviewer_ids) == 2:
            r1_map = {r["case_id"]: validate_and_parse_preference(r.get("preferred_response"), r["case_id"], 0) for r in reviewer_groups[reviewer_ids[0]]}
            r2_map = {r["case_id"]: validate_and_parse_preference(r.get("preferred_response"), r["case_id"], 0) for r in reviewer_groups[reviewer_ids[1]]}
            common_cids = sorted(list(set(r1_map.keys()) & set(r2_map.keys())))
            p1_list = [r1_map[c] for c in common_cids]
            p2_list = [r2_map[c] for c in common_cids]
            raw_agree = sum(1 for a, b in zip(p1_list, p2_list) if a == b) / len(common_cids) * 100.0
            kappa = calculate_cohens_kappa(p1_list, p2_list)
            inter_rater_stats = {
                "reviewer_1": reviewer_ids[0],
                "reviewer_2": reviewer_ids[1],
                "cases_compared": len(common_cids),
                "percentage_agreement_pct": round(raw_agree, 2),
                "cohens_kappa": kappa,
            }

    # Primary review set to process: first reviewer or all rows
    primary_reviewer_id = list(reviewer_groups.keys())[0]
    primary_reviews = reviewer_groups[primary_reviewer_id]

    # Validate completeness strictly
    validate_review_completeness(primary_reviews, expected_case_ids)

    total_reviewed = len(primary_reviews)
    adapted_wins = 0
    baseline_wins = 0
    ties = 0

    scores_adapted = {dim: [] for dim in RUBRIC_DIMENSIONS}
    scores_baseline = {dim: [] for dim in RUBRIC_DIMENSIONS}
    category_breakdown = {}

    for row_idx, row in enumerate(primary_reviews, 1):
        cid = row["case_id"].strip()
        cat = row.get("category", "unknown").strip()
        if cat not in category_breakdown:
            category_breakdown[cat] = {"count": 0, "adapted_wins": 0, "baseline_wins": 0, "ties": 0}
        category_breakdown[cat]["count"] += 1

        internal = internal_map[cid]
        a_is_adapted = internal["a_is_adapted"]

        # Validate preference
        pref = validate_and_parse_preference(row.get("preferred_response"), cid, row_idx)

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
        elif pref == "TIE":
            ties += 1
            category_breakdown[cat]["ties"] += 1

        # Validate all rubric dimensions strictly (no defaults!)
        for dim in RUBRIC_DIMENSIONS:
            val_a = validate_and_parse_score(row.get(f"{dim}_A"), cid, f"{dim}_A", row_idx)
            val_b = validate_and_parse_score(row.get(f"{dim}_B"), cid, f"{dim}_B", row_idx)
            if a_is_adapted:
                scores_adapted[dim].append(val_a)
                scores_baseline[dim].append(val_b)
            else:
                scores_adapted[dim].append(val_b)
                scores_baseline[dim].append(val_a)

    # Calculate empirical rates
    adapted_win_rate = (adapted_wins / total_reviewed) * 100.0
    baseline_win_rate = (baseline_wins / total_reviewed) * 100.0
    tie_rate = (ties / total_reviewed) * 100.0

    decided_total = adapted_wins + baseline_wins
    non_tied_adapted_preference_rate = (adapted_wins / decided_total * 100.0) if decided_total > 0 else 0.0

    ci_low, ci_high = wilson_score_interval(adapted_wins, total_reviewed, 0.95)

    def mean(lst):
        return round(sum(lst) / len(lst), 2) if lst else 0.0

    dim_means = {
        dim: {
            "adapted": mean(scores_adapted[dim]),
            "baseline": mean(scores_baseline[dim]),
            "delta": round(mean(scores_adapted[dim]) - mean(scores_baseline[dim]), 2),
        }
        for dim in RUBRIC_DIMENSIONS
    }

    # Print summary table
    print("=" * 76)
    print(f"  BLIND HUMAN EVALUATION QUALITY METRICS (N = {total_reviewed} Paired Responses)")
    print("=" * 76)
    print(f"  • Primary Reviewer ID:          {primary_reviewer_id}")
    print(f"  • Total Cases Reviewed:         {total_reviewed}")
    print(f"  • Adapted Preferred (Wins):     {adapted_wins} ({adapted_win_rate:.1f}%)")
    print(f"  • Baseline Preferred (Wins):    {baseline_wins} ({baseline_win_rate:.1f}%)")
    print(f"  • Ties:                         {ties} ({tie_rate:.1f}%)")
    print(f"  • Decided Adapted Win Rate:     {non_tied_adapted_preference_rate:.1f}% ({adapted_wins}/{decided_total})")
    print(f"  • Adapted Win Rate 95% CI:      [{ci_low:.1f}%, {ci_high:.1f}%] (Wilson Score Interval)")

    if inter_rater_stats:
        print("-" * 76)
        print("INTER-RATER RELIABILITY:")
        print(f"  • Raters:                       {inter_rater_stats['reviewer_1']} vs {inter_rater_stats['reviewer_2']}")
        print(f"  • Percentage Agreement:         {inter_rater_stats['percentage_agreement_pct']:.1f}%")
        print(f"  • Cohen's Kappa:                {inter_rater_stats['cohens_kappa']:.4f}")

    print("-" * 76)
    print("DIMENSION SCORE COMPARISON (1.00 – 5.00 Scale):")
    print(f"{'Dimension':<24} | {'Adapted':<12} | {'Baseline':<12} | {'Delta':<10}")
    print("-" * 76)
    for dim, vals in dim_means.items():
        delta = vals["delta"]
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
        "primary_reviewer_id": primary_reviewer_id,
        "total_reviewed": total_reviewed,
        "adapted_wins": adapted_wins,
        "adapted_win_rate_pct": round(adapted_win_rate, 2),
        "baseline_wins": baseline_wins,
        "baseline_win_rate_pct": round(baseline_win_rate, 2),
        "ties": ties,
        "tie_rate_pct": round(tie_rate, 2),
        "non_tied_adapted_preference_rate_pct": round(non_tied_adapted_preference_rate, 2),
        "wilson_ci_95": {"lower_pct": ci_low, "upper_pct": ci_high},
        "dimension_means": dim_means,
        "category_breakdown": category_breakdown,
        "inter_rater_reliability": inter_rater_stats if inter_rater_stats else None,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nSaved metrics summary to: {output_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process human evaluation reviews with strict validation.")
    parser.add_argument("--reviews", default=os.path.join(BASE_DIR, "evaluation", "human_review_completed.csv"))
    parser.add_argument("--internal-key", default=os.path.join(BASE_DIR, "evaluation", "response_eval_results_internal.json"))
    parser.add_argument("--output", default=os.path.join(BASE_DIR, "evaluation", "human_review_metrics.json"))
    args = parser.parse_args()
    sys.exit(process_reviews(args.reviews, args.internal_key, args.output))
