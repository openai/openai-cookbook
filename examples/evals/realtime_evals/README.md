# Realtime Evals

This folder contains three evaluation harnesses for the Realtime API that increase in complexity:
**crawl → walk → run**.

- **crawl**: synthetic single-turn (TTS → stream → grade)
- **walk**: deterministic replay of saved phone-audio (more realistic, still comparable)
- **run**: model-simulated multi-turn conversations (finds multi-turn/tooling failures)

Depending on your realtime eval maturity, point Codex (or your preferred coding assistant) to the folder that fits your use case so it can adapt the harness and bootstrap sample data; you can also have it run the included tests to confirm everything works.

## Quickstart

Python 3.9+ required.

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key"
```

Run a first command per harness:

- Crawl: `python crawl_harness/run_realtime_evals.py`
- Walk: install ffmpeg (`brew install ffmpeg`), then:
  - `python walk_harness/generate_audio.py`
  - `python walk_harness/run_realtime_evals.py`
- Run: `python run_harness/run_realtime_evals.py --max-examples 1`

## [Crawl (synthetic single-turn)](./crawl_harness)

**Best for:** Fast iteration and controlled comparisons.

- Uses text prompts from a CSV and synthesizes TTS audio per row.
- Streams fixed-size audio chunks into a realtime session.
- Captures the first assistant turn and grades tool-call correctness.
- Writes results, summary metrics, audio, and event logs per datapoint.

Run:

```
python crawl_harness/run_realtime_evals.py
```

## [Walk (saved audio replay)](./walk_harness)

**Best for:** Realism with reproducibility.

- Replays saved, phone-compressed audio (G.711 mu-law WAV at 8 kHz).
- Keeps chunking and turn boundaries fixed (VAD off).
- Captures responses, tool calls, latencies, and event logs per datapoint.
- Output audio is saved as PCM16 WAV for easy listening.

Run:

```
python walk_harness/generate_audio.py
python walk_harness/run_realtime_evals.py
```

## [Run (multi-turn simulation)](./run_harness)

**Best for:** Discovering multi-turn failures and tool behavior.

- Uses a simulator model to generate user turns and an assistant model under test.
- Streams simulator audio into the assistant with fixed chunking.
- Mocks tool outputs deterministically and grades with LLM-as-judge.
- Writes results, summaries, transcripts, and event logs per simulation.

Run:

```
python run_harness/run_realtime_evals.py
```

## Results layout

Each harness writes into its own `results/` folder:

- `results/<run_id>/results.csv`: per-example outputs and grades
- `results/<run_id>/summary.json`: aggregate metrics
- `results/<run_id>/events/*.jsonl`: full realtime event stream per datapoint

## Common CLI flags

All harnesses share a core set of flags so you can switch between them easily:

- `--data-csv`, `--results-dir`, `--run-name`
- `--model` (assistant under test), `--system-prompt-file`, `--tools-file`
- `--chunk-ms`, `--sample-rate-hz`, `--real-time`
- `--max-examples` (quick smoke tests)

Run harness adds multi-turn and simulator-specific flags (see its README).
