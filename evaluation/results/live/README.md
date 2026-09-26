# Live LLM Quality Evaluation Results

This directory stores paired live evaluation artifacts generated using:
```bash
python evaluation/run_response_eval.py --mode live --temperature 0.2
```
or via the manual GitHub Actions workflow `.github/workflows/live-evaluation.yml`.

When executed with a valid `GROQ_API_KEY`, the following files are produced:
- `response_eval_results_internal.json`: Ground-truth internal mappings (includes `generation_mode: "live"`, `model: "llama-3.3-70b-versatile"`, `provider: "groq"`).
- `human_review_dataset.json`: Reviewer-facing blind dataset (zero adaptation disclosures).
- `human_review_template.csv`: Reviewer grading template.
- `human_review_completed.csv`: Completed evaluation reviews (scored by `automated_heuristic_rater_v1` via automated heuristic rubric, or completed manually by human reviewers).
- `human_review_metrics.json`: Processed metrics, win rates, and confidence intervals.
- `run_metadata.json`: Provenance metadata including evaluation ID, commit SHA, timestamps, and randomization seed.
