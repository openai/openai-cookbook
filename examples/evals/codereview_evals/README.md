# Code Review Evals

This folder contains a small CLI app for building code review evals on top of
cached GitHub pull request data. The harnesses are numbered to match the guide:
Level 1, Level 2, and Level 3.

Levels 1, 2, and 3 are implemented.

## Prerequisites

- Python 3.10+
- `OPENAI_API_KEY`
- GitHub CLI (`gh`) installed and authenticated

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Fetch and cache pull requests once:

```bash
evalcr fetch-prs --repo openai/codex --limit 50
```

Reset the app to a clean local state:

```bash
evalcr reset --repo openai/codex
```

Run the Level 1 benchmark:

```bash
evalcr benchmark run --type benchmark --cache-key openai_codex --max-prs 5
```

Run the benchmark with faster runtime overrides:

```bash
evalcr benchmark run \
  --type benchmark \
  --cache-key openai_codex \
  --max-prs 20 \
  --reviewer-model gpt-5.1 \
  --reviewer-reasoning-effort none \
  --grader-reasoning-effort minimal \
  --reviewer-max-output-tokens 1000 \
  --grader-max-output-tokens 200 \
  --max-concurrency 8
```

Run the Level 2 pairwise comparison harness:

```bash
evalcr benchmark run --type pairwise --cache-key openai_codex --max-prs 5
```

Run the Level 3 optimization loop:

```bash
evalcr benchmark run --type optimizer --cache-key openai_codex --max-prs 5
```

Serve the generated HTML report for a saved run on `http://127.0.0.1:8000/report.html`:

```bash
evalcr visualize --run-id <run_id>
```

For pairwise and optimizer runs, pass the harness type explicitly:

```bash
evalcr visualize --type pairwise --run-id <run_id>
evalcr visualize --type optimizer --run-id <run_id>
```

`evalcr benchmark run` now requires `--type`:

- `--type benchmark`: Level 1 benchmark harness
- `--type pairwise`: Level 2 pairwise comparison harness
- `--type optimizer`: Level 3 optimization loop with pairwise and pointwise guardrails

Re-render the HTML report for an existing run:

```bash
evalcr benchmark report --run-dir 1_benchmark_harness/results/<run_id>
```

## Directory layout

- `codereview_evals/`: packaged CLI and shared implementation
- `data/cache/`: gitignored cached GitHub PR snapshots
- `1_benchmark_harness/`: runnable Level 1 harness assets
- `2_pairwise_harness/`: runnable Level 2 pairwise harness assets
- `3_optimization_harness/`: runnable Level 3 optimizer harness assets

## What gets cached

`evalcr fetch-prs` stores one JSON file per pull request plus a manifest. Each
snapshot includes PR metadata, a patch diff, changed files, issue comments,
reviews, and inline review comments. That cache is shared across all harnesses.

`evalcr reset` removes the selected repo cache under `data/cache/github/` and
deletes generated run directories under `1_benchmark_harness/results/`, while
preserving checked-in files such as `.gitkeep`.

## Harness-local config

Each harness owns its own:

- `AGENTS.md`
- `eval_config.json`

For Level 1, `eval_config.json` sets the reviewer model and grader model, and
can also pin reviewer/grader reasoning effort, cap output tokens, and control
per-run concurrency. `AGENTS.md` is injected into both the reviewer and grader
inputs. For Level 2,
the harness also includes `baseline_AGENTS.md` and `candidate_AGENTS.md`, which
are compared side-by-side while reusing the same reviewer model and reviewer
system prompt. For Level 3, the harness stores baseline and candidate reviewer
policies plus an optimizer prompt, and each step combines pairwise win rate with
pointwise benchmark pass rate so the loop does not chase pairwise wins alone.

## Tests

Run the unit tests from this folder with:

```bash
python -m unittest discover tests
```

## Performance Notes

- The Level 1 benchmark now parallelizes PR evaluation across a configurable worker pool via `max_concurrency`.
- Reviewer and grader requests now support explicit `reasoning.effort` and `max_output_tokens` controls through both `eval_config.json` and `evalcr benchmark run`.
- The checked-in Level 1 defaults favor speed: `minimal` reasoning for reviewer and grader, bounded output tokens, and concurrency set to `4`.
- For even lower latency, the current OpenAI docs recommend pinning reasoning effort explicitly and evaluating newer GPT-5.x models such as `gpt-5.1` for low-latency use cases instead of relying on older defaults.
