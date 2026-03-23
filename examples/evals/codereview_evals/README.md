# Code Review Evals

This folder contains a small CLI app for building code review evals on top of
cached GitHub pull request data. The harnesses are numbered to match the guide:
Level 1, Level 2, and Level 3.

Only `1_benchmark_harness` is implemented right now. Levels 2 and 3 are stubbed
out so the folder structure already matches the notebook.

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

`evalcr benchmark run` now requires `--type`:

- `--type benchmark`: Level 1 benchmark harness
- `--type pairwise`: Level 2 pairwise harness placeholder (not implemented yet)
- `--type optimizer`: Level 3 optimization harness placeholder (not implemented yet)

Re-render the HTML report for an existing run:

```bash
evalcr benchmark report --run-dir 1_benchmark_harness/results/<run_id>
```

## Directory layout

- `codereview_evals/`: packaged CLI and shared implementation
- `data/cache/`: gitignored cached GitHub PR snapshots
- `1_benchmark_harness/`: runnable Level 1 harness assets
- `2_pairwise_harness/`: Level 2 placeholder
- `3_optimization_harness/`: Level 3 placeholder

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

For Level 1, `eval_config.json` sets the reviewer model and grader model, while
`AGENTS.md` is injected into both the reviewer and grader inputs.

## Tests

Run the unit tests from this folder with:

```bash
python -m unittest discover tests
```
