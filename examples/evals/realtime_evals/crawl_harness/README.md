# Crawl Harness

Deterministic single-turn replay for Realtime evals. This harness feeds fixed audio
inputs to a Realtime session so you can compare runs with minimal variance.
It is best for quick iteration and controlled comparisons.

## What it does

- Loads a CSV of eval prompts from `crawl_harness/data/`.
- Uses TTS to synthesize a fixed input audio file per row.
- Streams audio into the Realtime API in fixed-size chunks.
- Captures the first assistant turn (text/audio/tool calls).
- Grades tool-call correctness and tool-call-arg correctness only.
- Writes artifacts into `crawl_harness/results/<run_id>/`.

## Inputs

CSV columns (required):

- `example_id`: Unique ID for the datapoint.
- `user_text`: Text prompt to synthesize into audio.
- `gt_tool_call`: Expected tool name or empty if no tool call is expected.
- `gt_tool_call_arg`: Expected tool arguments as JSON string or empty.

## Outputs

Each run writes:

- `results.csv`: Per-example outputs and grades.
- `summary.json`: Aggregate metrics (latency + correctness).
- `audio/<example_id>/input.wav`: The TTS input audio.
- `audio/<example_id>/output.wav`: The model output audio (if any).
- `events/<example_id>.jsonl`: Realtime event stream for the datapoint.

## How it works

1. TTS generates PCM audio for each row.
2. PCM is wrapped into a WAV file for easy playback.
3. Audio is streamed into a Realtime session with fixed chunk sizes.
4. The harness listens for `response.done` and records tool calls + output.
5. Grades are computed:
   - `tool_call_correctness`: correct tool chosen (or no tool call when none expected).
   - `tool_call_arg_correctness`: expected args present in the tool call.

## Run

From repo root:

```bash
python crawl_harness/run_realtime_evals.py
```

Common options:

- `--data-csv`: Path to a CSV file.
- `--results-dir`: Output folder (defaults to `crawl_harness/results`).
- `--run-name`: Optional run name (defaults to timestamp).
- `--model`: Realtime model name.
- `--tts-model`: TTS model name.
- `--system-prompt-file`: System prompt file path.
- `--tools-file`: Tools JSON file path.
- `--voice`: Output voice name.
- `--chunk-ms`: Audio chunk size in ms.
- `--sample-rate-hz`: Input sample rate in Hz.
- `--input-audio-format`: Input audio format (default `pcm16`).
- `--output-audio-format`: Output audio format (default `pcm16`).
- `--real-time`: Stream audio in real-time cadence.
- `--max-examples`: Limit number of examples for quick checks.

## Adapt

- Add or replace rows in `crawl_harness/data/customer_service_synthetic.csv`.
- Change tools or system prompt in `shared/`.
- Update grading logic in `run_realtime_evals.py`.

## Notes

- The harness only evaluates the first assistant turn and does not provide tool outputs.
- `results.csv` includes an `event_log_path` column pointing to the JSONL trace.
- If you expect tools to be called reliably, adjust the system prompt or tool choice.
