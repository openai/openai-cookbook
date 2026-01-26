# Walk Harness

The walk harness replays saved audio to make realtime eval runs comparable.
It streams G.711 mu-law WAV files in fixed-size chunks, commits the user turn
manually (VAD off), and records responses, tool calls, and latency metrics.

## What it does

- Loads a CSV with the crawl columns (excluding `expected_keywords`) plus `audio_path`.
- Streams saved audio in fixed chunk sizes (default 20 ms) at a deterministic cadence.
- Commits the input buffer explicitly to avoid VAD variability.
- Captures transcript deltas, audio deltas, tool calls, and completion events.
- Writes `results.csv` and `summary.json` with accuracy and latency stats.
- Stores a JSONL stream of all realtime events per example under `results/<run>/events/`.

## Files

- `walk_harness/generate_audio.py`: Generates G.711 mu-law WAV files from the
  crawl CSV using TTS + ffmpeg.
- `walk_harness/data/customer_service_synthetic.csv`: Walk dataset with
  `audio_path` pointing to WAV files.
- `walk_harness/run_realtime_evals.py`: Runs the walk evals.
- `walk_harness/results/<run>/events/*.jsonl`: Event logs per datapoint.
- `walk_harness/results/<run>/audio/<example_id>/output.wav`: Assistant output audio per datapoint.

## How to run

1) Install ffmpeg (required for mu-law WAV encoding):

```
brew install ffmpeg
```

2) Generate audio assets:

```
python walk_harness/generate_audio.py
```

3) Run the eval harness:

```
python walk_harness/run_realtime_evals.py
```

4) Quick smoke test:

```
python walk_harness/run_realtime_evals.py --max-examples 2
```

## Inputs and audio format

- The dataset CSV must include an `audio_path` column pointing to WAV files.
- This harness currently expects **G.711 mu-law** audio at **8 kHz** (`g711_ulaw`), which
  is a common telephony format and makes runs more realistic than pure PCM.
- Output audio is saved as **PCM16 WAV** (typically 24 kHz) for easy playback.

## Adapting the harness

- Change the model or voice via CLI flags (`--model`, `--voice`).
- Override the system prompt and tools with `--system-prompt-file` and `--tools-file`.
- Update chunking and cadence with `--chunk-ms` and `--real-time`.
- Swap datasets with `--data-csv` (ensure it includes `audio_path`).
- Use a different audio format only if the Realtime API supports it. The default
  is `g711_ulaw` at 8 kHz to match the saved WAV files. Output audio is stored
  as PCM16 WAV for easy listening.
- Replace `walk_harness/data/customer_service_synthetic.csv` with your own CSV
  and regenerate audio assets using `generate_audio.py`.
