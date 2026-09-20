# Offline Controlled Quality Evaluation Results

This directory stores paired offline deterministic evaluation artifacts generated using:
```bash
python evaluation/run_response_eval.py --mode offline
```

The offline suite uses the local deterministic behavioral generator reflecting exact system prompt directives, learned profiles, and current-request overrides:
- `response_eval_results_internal.json`: Ground-truth internal mappings (`generation_mode: "offline"`, `provider: "local_deterministic_generator"`).
- `human_review_dataset.json`: Reviewer-facing blind dataset (zero adaptation disclosures).
- `human_review_template.csv`: Reviewer grading template.
- `human_review_completed.csv`: Completed evaluations scored against the 5-dimension rubric with reviewer provenance (`reviewer_01`, timestamps, round).
- `human_review_metrics.json`: Formal metrics, win rates (55.0% adapted wins, 86.8% decided win rate), Wilson 95% CI, and dimension means.
- `run_metadata.json`: Provenance metadata including evaluation ID, commit SHA, timestamps, and randomization seed.
