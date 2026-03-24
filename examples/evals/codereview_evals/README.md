# Code Review Evals

This example shows how to evaluate AI code reviews with cached GitHub pull requests and the Evals API.

The three levels now progress like this:

1. `1_basic_benchmark_harness`: a pointwise benchmark over benchmark-eligible cached PR snapshots
2. `2_normalized_benchmark_harness`: the same benchmark after normalizing PR records with a cached `pr_brief` and distilled `reference_findings_json`
3. `3_pairwise_harness`: pairwise judging over normalized records with baseline and candidate reviews

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

Prepare each dataset shape:

```bash
evalcr prepare-dataset --level 1 --cache-key openai_codex
evalcr prepare-dataset --level 2 --cache-key openai_codex
evalcr prepare-dataset --level 3 --cache-key openai_codex
```

Run the Evals-backed examples:

```bash
evalcr run-evals --level 1 --cache-key openai_codex
evalcr run-evals --level 2 --cache-key openai_codex
evalcr run-evals --level 3 --cache-key openai_codex
```

Reset local state:

```bash
evalcr reset --cache-key openai_codex
```

## Command Surface

- `evalcr fetch-prs`: fetch benchmark-eligible PR snapshots from GitHub and keep scanning until `--limit` accepted PRs are cached
- `evalcr prepare-dataset --level 1|2|3`: write upload-ready JSONL datasets
- `evalcr run-evals --level 1|2|3`: upload the dataset, create or reuse the eval version matching the current local harness config, run it, and save a thin local summary
- `evalcr reset`: remove cached PRs, prepared datasets, and saved run artifacts

## Data Layout

- `data/cache/github/<cache_key>/`: raw GitHub PR snapshots plus a manifest
- `data/prepared/<cache_key>/`: prepared JSONL datasets, cached `pr_brief` files, and cached baseline/candidate reviews
- `<harness>/results/<run_name>/`: uploaded file metadata, eval config, run object, output items, and `summary.json`

## Notes

- `fetch-prs` remains GitHub-only. Preparation happens in a separate step.
- `fetch-prs --limit N` now means "cache N benchmark-eligible PRs", so the command may scan more than `N` recently closed PRs before it stops.
- Historical comments are filtered down to substantive human comments; trigger text, pure approvals, and connector boilerplate are dropped before dataset preparation.
- Level 2 keeps the benchmark objective fixed and changes the input representation plus the grading target: it normalizes both PR context and expected findings.
- Level 3 uses normalized records and cached baseline/candidate reviews before pairwise judging.
- The primary result surface for all three levels is the Evals API run plus its `report_url`, not a local HTML report.
- `summary.json` includes the resolved remote eval name and spec fingerprint so config drift is visible in saved artifacts.

## Tests

Run the unit tests from this folder with:

```bash
python -m unittest discover tests
```
