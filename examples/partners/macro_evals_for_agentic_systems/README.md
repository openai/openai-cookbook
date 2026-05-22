# Macro Evals for Agentic Systems

This example is a self-contained OpenAI Cookbook notebook for macro-level
evaluation of a traced multi-agent system. It starts from synthetic exported
trace bundles plus saved lower-level eval labels, turns each run into compact
analysis documents, discovers recurring behavior patterns, and drills into one
pattern with an AgentTrace-style diagnosis pass.

No OpenAI API key is required. The notebook runs entirely offline from the
packaged synthetic data.

## Cookbook Location

Recommended Cookbook repo path:

```text
examples/partners/macro_evals_for_agentic_systems/
```

## Required Files

Upload only these files and folders:

```text
examples/partners/macro_evals_for_agentic_systems/
  macro_evals_for_agentic_systems.ipynb
  requirements.txt
  README.md
  run_notebook.sh
  data/
    trace_results.jsonl
    run_summary.json
    eval_labels.jsonl
    trace_bundles.zip
  helpers/
    data_prep.py
    macro_eval_pipeline.py
images/
  agentic-system-architecture.svg
```

Do not upload generated or local-only files such as `.venv/`, `outputs/`,
`.jupyter/`, `.ipython/`, `.cache/`, `data/.macro_eval_cache/`,
`data/trace_bundles/`, `data/trace_snapshot.sqlite`, or `__pycache__/`.

## Data

The packaged dataset is synthetic. It includes:

- `data/trace_results.jsonl`: run-level metadata for 1,000 simulated orders.
- `data/run_summary.json`: aggregate run summary.
- `data/eval_labels.jsonl`: saved lower-level eval labels for bundle-backed runs.
- `data/trace_bundles.zip`: exported trace bundles, expanded locally on first run.

The full SQLite trace snapshot is intentionally not included because it is large
and is not needed for the notebook. If you have it locally, the notebook can use
`data/trace_snapshot.sqlite` for optional enrichment.

## Run

Use Python 3.11 or newer.

```bash
./run_notebook.sh
```

For a faster smoke test:

```bash
MACRO_EVALS_TRACE_LIMIT=48 ./run_notebook.sh
```

The script creates a local virtual environment, installs dependencies, executes
the notebook, and writes generated artifacts under `outputs/`.

## Notes

- `trace_bundles.zip` is expanded automatically into
  `data/.macro_eval_cache/trace_bundles/`.
- Saved eval labels are used as offline evidence; the notebook does not call
  model APIs or re-run Promptfoo.
- The Agents SDK reference in the notebook points to the official OpenAI
  developer docs for code-first orchestration with agents, tools, handoffs,
  guardrails, tracing, and sandbox execution.
