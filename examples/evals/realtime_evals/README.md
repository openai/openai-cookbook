# Realtime Evals

This folder contains three evaluation harnesses for the Realtime API that increase in complexity:
**crawl → walk → run**.

- **crawl**: synthetic single-turn (TTS → stream → grade)
- **walk**: deterministic replay of saved phone-audio (more realistic, still comparable)
- **run**: model-simulated multi-turn conversations (finds multi-turn/tooling failures)

Depending on your realtime eval maturity, point Codex (or your preferred coding assistant) to the folder that fits your use case so it can adapt the harness and bootstrap sample data; you can also have it run the included tests to confirm everything works.

## Quickstart

Python 3.12+ required.

```bash
make install
source .venv/bin/activate
export OPENAI_API_KEY="your_api_key"
```

`make install` creates the local `.venv` and installs both runtime and dev dependencies. It uses `uv` when available and otherwise falls back to `python -m venv` plus `pip install -r requirements.txt -r requirements-dev.txt`.

Run a first command per harness. If uv is not installed, replace `uv run` with `python` and run these scripts with your `.venv` activated:

- Crawl: `uv run python crawl_harness/run_realtime_evals.py`
- Walk: install ffmpeg (`brew install ffmpeg`), then:
  - `uv run python walk_harness/generate_audio.py`
  - `uv run python walk_harness/run_realtime_evals.py`
- Run: `uv run python run_harness/run_realtime_evals.py --max-examples 1`

## Dev commands
Use the root `Makefile` for common checks. Run `make install` first to create `.venv`. These targets work with or without `uv`: when `uv` is installed they run through `uv run`, and otherwise they use the matching tool binaries from the local `.venv`.

- `make install`
- `make streamlit`
- `make format`
- `make lint`
- `make lint-fix`
- `make typecheck`
- `make test`

## [Crawl (synthetic single-turn)](./crawl_harness)

**Best for:** Fast iteration and controlled comparisons.

- Uses text prompts from a CSV and synthesizes TTS audio per row.
- Streams fixed-size audio chunks into a realtime session.
- Captures the first assistant turn and grades tool-call correctness.
- Writes results, summary metrics, audio, and event logs per datapoint.

Run:

```
uv run python crawl_harness/run_realtime_evals.py
```

## [Walk (saved audio replay)](./walk_harness)

**Best for:** Realism with reproducibility.

- Replays saved, phone-compressed audio (G.711 mu-law WAV at 8 kHz).
- Keeps chunking and turn boundaries fixed (VAD off).
- Captures responses, tool calls, latencies, and event logs per datapoint.
- Output audio is saved as PCM16 WAV for easy listening.

Run:

```
uv run python walk_harness/generate_audio.py
uv run python walk_harness/run_realtime_evals.py
```

## [Run (multi-turn simulation)](./run_harness)

**Best for:** Discovering multi-turn failures and tool behavior.

- Uses a simulator model to generate user turns and an assistant model under test.
- Streams simulator audio into the assistant with fixed chunking.
- Mocks tool outputs deterministically and grades with LLM-as-judge.
- Writes results, summaries, transcripts, and event logs per simulation.

Run:

```
uv run python run_harness/run_realtime_evals.py
```

## Results layout

Each harness writes into its own `results/` folder:

- `results/<run_id>/results.csv`: per-example outputs and grades
- `results/<run_id>/summary.json`: aggregate metrics
- `results/<run_id>/plots/*.png`: warm-editorial summary charts for scores, latency, tokens, and run shape
- `results/<run_id>/events/*.jsonl`: full realtime event stream per datapoint

The shared typed representation of these artifacts for the crawl, walk, and run harnesses lives in `shared/result_types.py`.

To render charts for an existing run after the fact:

```bash
uv run python plot_eval_results.py --run-dir run_harness/results/<run_id>
```

## Results Viewer

Use the Streamlit results viewer to browse saved runs from `crawl_harness`, `walk_harness`, and `run_harness` without opening the raw artifacts by hand.

- `Comparison View`: select a harness, choose one or more saved runs, and compare summary metrics, scores, latency, and token usage across runs.
- `Run Viewer`: inspect one saved run in detail. Crawl and walk runs show row-level audio artifacts and event logs; run-harness runs use a Simulation Viewer with transcripts, event logs, and turn audio.

Run it from this directory with either:

```bash
make streamlit
```

or:

```bash
cd results_viewer
uv run streamlit run app.py
```

Then open the local Streamlit URL, usually `http://localhost:8501`.

## Common CLI flags

All harnesses share a core set of flags so you can switch between them easily:

- `--data-csv`, `--results-dir`, `--run-name`
- `--model` (assistant under test), `--system-prompt-file`, `--tools-file`
- `--chunk-ms`, `--sample-rate-hz`, `--real-time`
- `--max-examples` (quick smoke tests)
- `--skip-plots` (skip post-run PNG chart generation)

Run harness adds multi-turn and simulator-specific flags (see its README).
