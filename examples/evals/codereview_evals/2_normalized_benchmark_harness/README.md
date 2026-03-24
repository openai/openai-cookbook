# 2 Normalized Benchmark Harness

This harness keeps the benchmark objective fixed and stabilizes the reviewer and grader inputs for the benchmark-eligible PR set selected during fetch.

Compared with Level 1, dataset preparation adds:

- one cached model-generated `pr_brief` per pull request
- one cached `reference_findings_json` distilled from historical review comments only

The benchmark still evaluates the same task, but the reviewer and graders consume a more normalized PR representation. The reviewer now emits both review comments and a compact `Top findings` JSON block, while graders score against the distilled findings set rather than only the original comment text.

Flow:

1. `evalcr prepare-dataset --level 2` reuses cached PR snapshots and writes normalized JSONL records.
2. Missing `pr_brief` values are generated once and cached under `data/prepared/<cache_key>/shared/pr_briefs/`.
3. Missing `reference_findings_json` values are generated once and cached under `data/prepared/<cache_key>/shared/review_findings/`.
4. `evalcr run-evals --level 2` creates or reuses the eval version matching the current local harness config, then runs the same pointwise benchmark shape as Level 1 with the normalized records as input.

Reference findings can come from either path:

- Path 1: LLM distillation from historical comments, using just the comments and no diff/context.
- Path 2: Human-authored findings, dropped into the same cache location to use a golden set.
