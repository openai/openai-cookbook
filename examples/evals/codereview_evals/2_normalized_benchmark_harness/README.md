# 2 Normalized Benchmark Harness

This harness keeps the benchmark objective fixed and stabilizes the reviewer and grader inputs.

Compared with Level 1, dataset preparation adds one cached model-generated `pr_brief` per pull request. The benchmark still evaluates the same task, but the reviewer and graders consume a more normalized PR representation.

Flow:

1. `evalcr prepare-dataset --level 2` reuses cached PR snapshots and writes normalized JSONL records.
2. Missing `pr_brief` values are generated once and cached under `data/prepared/<cache_key>/shared/pr_briefs/`.
3. `evalcr run-evals --level 2` creates or reuses the eval version matching the current local harness config, then runs the same pointwise benchmark shape as Level 1 with the normalized records as input.
