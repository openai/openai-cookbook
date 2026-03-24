# 1 Benchmark Harness

**Best for:** a simple pointwise benchmark that grades one generated code review
per pull request.

This harness reads cached pull request data, loads its own `AGENTS.md` and
`eval_config.json`, runs the reviewer model, runs the grader model, and writes a
static HTML report alongside JSON and CSV artifacts.

## Run

```bash
evalcr benchmark run --type benchmark --cache-key openai_codex --max-prs 5
```

For a faster run, override the benchmark config from the CLI:

```bash
evalcr benchmark run \
  --type benchmark \
  --cache-key openai_codex \
  --max-prs 20 \
  --reviewer-model gpt-5.1 \
  --reviewer-reasoning-effort none \
  --grader-reasoning-effort minimal \
  --max-concurrency 8
```

## Bundled assets

- `AGENTS.md`: harness-local repo guidance passed to the reviewer and grader
- `eval_config.json`: default reviewer/grader models plus optional reasoning, token, and concurrency settings
- `reviewer_system.txt`: reviewer system prompt
- `grader_system.txt`: judge system prompt
- `review_output_schema.json`: structured reviewer output schema
- `grader_output_schema.json`: structured grader output schema

## Outputs

Each run writes into `results/<run_id>/`:

- `results.json`
- `results.csv`
- `summary.json`
- `report.html`
