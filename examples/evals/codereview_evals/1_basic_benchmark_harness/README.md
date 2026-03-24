# 1 Basic Benchmark Harness

This harness runs a simple pointwise benchmark over cached GitHub pull requests.

Flow:

1. `evalcr fetch-prs` stores raw PR snapshots.
2. `evalcr prepare-dataset --level 1` writes a benchmark JSONL file with raw review context.
3. `evalcr run-evals --level 1` uploads that dataset, creates or reuses an Evals config, and runs the benchmark asynchronously.

The primary outputs are:

- the OpenAI Evals dashboard `report_url`
- a thin local `summary.json`
- saved copies of the uploaded file, eval config, run object, and output items
