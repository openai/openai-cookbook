# 2 Pairwise Harness

**Best for:** side-by-side comparison between two review policies while holding
the reviewer model and reviewer system prompt fixed.

This harness reads cached pull request data, generates one review with
`baseline_AGENTS.md`, generates a second review with `candidate_AGENTS.md`, and
then uses a pairwise judge to choose which review is better overall.

## Run

```bash
evalcr benchmark run --type pairwise --cache-key openai_codex --max-prs 5
```

## Bundled assets

- `AGENTS.md`: experiment description passed to the pairwise judge
- `baseline_AGENTS.md`: baseline code review guidance
- `candidate_AGENTS.md`: candidate code review guidance
- `eval_config.json`: default reviewer and judge model names
- `reviewer_system.txt`: shared reviewer system prompt used for both sides
- `pairwise_judge_system.txt`: pairwise judge prompt
- `review_output_schema.json`: structured reviewer output schema
- `pairwise_output_schema.json`: structured judge output schema

## Outputs

Each run writes into `results/<run_id>/`:

- `results.json`
- `results.csv`
- `summary.json`
- `report.html`
