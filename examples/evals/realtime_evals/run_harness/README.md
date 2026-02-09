# Run Harness

Model-simulated multi-turn eval harness for the Realtime API. This harness uses
one realtime model as the user simulator (audio-only) and another realtime model
as the assistant under test. It replays fixed chunking (VAD off), mocks tools
from the simulation JSON, and records full traces.

## What it does

- Loads `run_harness/data/simulations.csv` with pandas.
- Reads per-simulation JSON files defining scenario, simulator identity, tool mocks,
  and LLM-as-judge grading criteria.
- Generates user audio turns via a realtime simulator model (audio-only).
- Streams user audio to the assistant in fixed-size chunks and commits manually.
- Captures assistant audio/text, tool calls, tool outputs, and latencies.
- Grades turn-level and trace-level criteria with an LLM-as-judge.
- Writes `results.csv`, `summary.json`, and full trace logs under `run_harness/results/`.

## Files

- `run_harness/run_realtime_evals.py`: Run harness script.
- `run_harness/data/simulations.csv`: Index of simulation files.
- `run_harness/data/sim_*.json`: Simulation definitions (this repo currently ships 3 examples).
- `run_harness/results/<run_id>/events/*.jsonl`: Full event trace per simulation.
- `run_harness/results/<run_id>/conversations/*.txt`: Human-readable transcript with tool calls.

## Simulation definitions (high level)

Each `sim_*.json` file defines:

- **the scenario** (what the user is trying to do)
- **tool mocks** (what each tool should return when called)
- **judge rubric** (what should be graded per turn / overall)

This lets you run repeatable multi-turn evals without needing live backend integrations.

## How to run

From repo root:

```bash
python run_harness/run_realtime_evals.py --max-examples 1
```

Common options:

- `--data-csv`: Simulation index CSV.
- `--model`: Alias for the assistant model under test.
- `--assistant-model`: Realtime model under test (overrides `--model`).
- `--simulator-model`: Realtime model used as the user.
- `--system-prompt-file`: Alias for assistant system prompt file.
- `--tools-file`: Alias for assistant tools file.
- `--assistant-system-prompt-file`: Override assistant system prompt file (more specific).
- `--assistant-tools-file`: Override tools file for the assistant (more specific).
- `--simulator-system-prompt`: Override simulator system prompt (string).
- `--chunk-ms`, `--sample-rate-hz`, `--real-time`.
- `--max-turns`, `--max-examples`.

Notes:

- Temperature and max output tokens are intentionally not supported.
- The simulator emits audio only. Transcripts are captured from audio deltas if available.
- Tool outputs are mocked deterministically from each simulation JSON.
- `results.csv` includes an `event_log_path` column pointing to the JSONL trace.
