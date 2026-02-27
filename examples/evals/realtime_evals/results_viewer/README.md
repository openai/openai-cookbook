# Results Viewer

This directory contains a [Streamlit](https://streamlit.io/) app for exploring
saved realtime eval runs from the crawl, walk, and run harnesses.

The app auto-discovers run directories under:

- `crawl_harness/results/`
- `walk_harness/results/`
- `run_harness/results/`

## What It Shows

- **Comparison View**: compare summary metrics across one or more saved runs
- **Run Viewer**: inspect a single saved crawl or walk run, including:
  - `results.csv` rows
  - input and output audio artifacts
  - per-example event logs

Current limitation: the detailed Run Viewer is not implemented for
`run_harness` yet.

## Run Locally

From `examples/evals/realtime_evals/`:

```bash
uv venv .venv
source .venv/bin/activate
uv sync --group dev
uv run streamlit run results_viewer/app.py
```

Then open the local URL that Streamlit prints, usually
`http://localhost:8501`.

If you are using the pip-based install path instead of `uv`, install the dev
dependencies first so `streamlit` is available:

```bash
pip install -r requirements.txt -r requirements-dev.txt
streamlit run results_viewer/app.py
```

## Expected Data Layout

The viewer expects each saved run directory to contain:

- `summary.json` for aggregate metrics
- `results.csv` for per-example results

For crawl and walk runs, the app can also display:

- `audio/<example_id>/input.wav`
- `audio/<example_id>/output.wav`
- `events/<example_id>.jsonl`

The app discovers runs recursively, so nested result directories are fine as
long as those files are present.
