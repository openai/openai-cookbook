# Offline Tool-Calling Eval Harness

A dependency-free evaluation harness for testing tool-calling agents without any API calls. Uses deterministic mock tools, task fixtures, and a policy-based agent loop to measure sequence accuracy, argument correctness, and step efficiency.

## Quick Start

```bash
cd examples/agent_optimization/offline_tool_eval
python -m pytest test_harness.py -v
```

## Architecture

```
offline_tool_eval/
├── __init__.py       # Package marker
├── tools.py          # ToolRouter, mock tools (search_files, read_file, calc, check_total)
├── policies.py       # Agent policies: oracle_policy (correct), buggy_policy (for testing)
├── tasks.py          # Task fixtures with expected tool calls
├── runner.py         # run_task, run_suite with max_steps guard
├── metrics.py        # score_trace, aggregate, markdown_report
└── test_harness.py   # Meta-tests: oracle perfect, buggy caught, unknown tool fails, step guard
```

## How It Works

1. **Tools** — `ToolRouter` registers mock tools (`search_files`, `read_file`, `calc`, `check_total`) that operate on in-memory fixtures. No external dependencies.

2. **Policies** — An agent is a policy function: `(task, trace) -> ToolCall`. `oracle_policy` returns the expected calls. `buggy_policy` intentionally drops the final call and mistypes expressions — used to verify the harness catches errors.

3. **Runner** — `run_task` executes a policy against a task for up to `max_steps=8` steps, recording a `TaskTrace` of all calls and results. `run_suite` runs all tasks and aggregates metrics.

4. **Metrics** — Each trace is scored on:
   - `seq_match` — did the tool names appear in the correct order?
   - `arg_match_rate` — what fraction of arguments were exactly correct?
   - `all_ok` — did every step succeed?

5. **Meta-tests** — The harness tests itself:
   - Oracle policy achieves 4/4 pass rate, 1.0 arg-match
   - Buggy policy caught at 0/4 pass rate, 0.75 arg-match
   - Unknown tool calls are rejected
   - Step guard prevents infinite loops
   - Markdown report renders correctly

## Verified Results

| Policy   | Pass Rate | Arg Match | Steps |
|----------|-----------|-----------|-------|
| oracle   | 1.00      | 1.00      | 2.0   |
| buggy    | 0.00      | 0.75      | 2.0   |

## Use Cases

- **Prompt iteration** — Test whether a new prompt improves tool selection before spending API credits
- **Regression testing** — Catch regressions in agent logic when refactoring
- **CI/CD gate** — Block merges that degrade tool-calling accuracy
- **Educational** — Learn how eval harnesses work without API costs

## Extending

Add new tools in `tools.py`, new tasks in `tasks.py`, and new policies in `policies.py`. The runner and metrics work automatically with any additions.
