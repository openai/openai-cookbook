# Agent Regression Tests with Foundry Evaluators

> **Status: DRAFT outline.** This PR is opened early so cookbook maintainers
> can give scope feedback before the code cells are written. See the open
> questions in the notebook header.

This cookbook example shows how to build a **regression-test suite for an
OpenAI-powered agent** using the open-source
[`azure-ai-evaluation`](https://pypi.org/project/azure-ai-evaluation/)
evaluator catalog. The evaluators are LLM-as-judge graders backed by
whatever model you point them at — including OpenAI models via the
Responses API — so there is no vendor lock-in.

## What you will build

1. A small two-tool agent (planner + retriever) on the OpenAI Responses API.
2. A 20-item golden dataset with reference answers and expected tool calls.
3. A regression run that scores each turn on:
   - `GroundednessEvaluator`
   - `RelevanceEvaluator`
   - `IntentResolutionEvaluator`
   - `ToolCallAccuracyEvaluator`
   - one custom criterion (`AnswerStyleEvaluator`)
4. A side-by-side comparison across **two prompt variants** and **two
   models**, plus a "fail the suite on regression" gate.

## How this differs from existing cookbook content

- [`examples/partners/macro_evals_for_agentic_systems/`](../../partners/macro_evals_for_agentic_systems/)
  (merged 2026-05-19) does *macro-pattern discovery* — clustering trace
  signals to surface recurring behaviors. This notebook does the
  complementary *micro-eval regression* loop on a fixed golden set.
- [`examples/evals/`](../../evals/) covers the OpenAI Evals product.
  This notebook uses an external evaluator library so you can run the
  same suite in CI without a hosted dependency.

## Layout

```text
agent_regression_tests_with_foundry_evaluators/
  agent_regression_tests_with_foundry_evaluators.ipynb
  requirements.txt
  README.md
  data/                # golden set + recorded baseline scores (added in next commit)
```
