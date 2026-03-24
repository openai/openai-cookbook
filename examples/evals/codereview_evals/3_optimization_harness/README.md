# 3 Optimization Harness

**Best for:** iterative prompt and policy improvement where pairwise wins alone
are not enough and the candidate must preserve a strong overall benchmark score.

This harness starts from a fixed baseline champion and an editable candidate. At
each step it:

1. runs a pairwise comparison between champion and candidate
2. runs a pointwise benchmark on the candidate alone
3. computes a composite score using pairwise win rate and benchmark pass rate
4. applies a benchmark guardrail so pairwise gains do not come from sacrificing
   overall review quality
5. asks an optimizer model to revise the candidate `AGENTS.md` and reviewer
   system prompt for the next round

The loop stops when the composite score threshold is reached or the step cap is
exhausted.

## Run

```bash
evalcr benchmark run --type optimizer --cache-key openai_codex --max-prs 5
```

Optional overrides:

```bash
evalcr benchmark run --type optimizer --cache-key openai_codex --max-steps 4 --score-threshold 0.8
```

Pointwise benchmark results are cached persistently across optimizer runs when
the full benchmark input fingerprint is unchanged. Disable that cache for a
forced refresh with:

```bash
evalcr benchmark run --type optimizer --cache-key openai_codex --disable-benchmark-cache
```

## Bundled assets

- `AGENTS.md`: optimization objective and guardrail framing
- `baseline_AGENTS.md`: initial champion policy
- `baseline_reviewer_system.txt`: initial champion reviewer system prompt
- `candidate_AGENTS.md`: seed candidate policy
- `candidate_reviewer_system.txt`: seed candidate reviewer system prompt
- `benchmark_grader_system.txt`: pointwise benchmark judge prompt
- `pairwise_judge_system.txt`: pairwise judge prompt
- `optimizer_system.txt`: optimizer prompt for proposing the next candidate
- `review_output_schema.json`: reviewer output schema
- `benchmark_grader_output_schema.json`: pointwise grader schema
- `pairwise_output_schema.json`: pairwise judge schema
- `optimizer_output_schema.json`: optimizer revision schema

## Outputs

Each run writes into `results/<run_id>/`:

- `iterations.json`
- `iterations.csv`
- `summary.json`
- `report.html`
- `final_candidate_AGENTS.md`
- `final_candidate_reviewer_system.txt`
- `baseline/`: saved baseline benchmark artifacts
- `steps/step_XX/`: pairwise artifacts, benchmark artifacts, optimizer output,
  and the next candidate revision for each step
