# Harness Selection

Use this table when the user is not sure which realtime eval harness to start with.

| Harness | Use when | Required starting material | Best first outcome |
| --- | --- | --- | --- |
| `crawl` | The user wants fast iteration on single-turn behavior, tool choice, or tool args, including basic synthetic audio generated from text. | Text prompts. Expected tool names and args are optional if the user wants tool-call grading. | A small CSV plus smoke/full commands that run immediately. |
| `walk` | The user cares about saved phone audio, wants more realistic audio replay, or needs synthetic audio with replay-specific characteristics such as noise, telephony artifacts, or speaker traits. | Either a CSV with `audio_path`, or text rows that can be turned into audio. | A walk dataset plus optional audio-generation step and replay commands. |
| `run` | The user needs multi-turn behavior, tool mocks, or conversation-level grading. | A scenario, starter user utterance, simulator prompt, tool mocks, and grader criteria. | `simulations.csv` plus one or more `sim_*.json` files. |

## Recommendation Rules

1. Recommend `crawl` by default when the user only has text rows or a rough task description.
2. Recommend `crawl` when the user asks for synthetic audio but does not mention any replay-specific audio characteristics.
3. Recommend `walk` when the user already has WAV files, cares about telephony realism, wants to validate the audio replay path, or wants synthetic audio with specific noise or speaker characteristics.
4. Recommend `run` only when the evaluation target depends on multiple turns, tool outputs, or conversation-level completion.

## Data Contracts

### Crawl

Required columns:

- `example_id`
- `user_text`

Optional columns for tool-call grading:

- `gt_tool_call`
- `gt_tool_call_arg`

### Walk

If audio is already available, required columns are:

- `example_id`
- `user_text`
- `audio_path`

Optional columns for tool-call grading:

- `gt_tool_call`
- `gt_tool_call_arg`

If audio is not available yet, start from the crawl-style columns above and generate `audio_path` entries with `walk_harness/generate_audio.py`.

### Run

Required index columns:

- `simulation_id`
- `simulation_path`

Each simulation JSON should define:

- assistant config
- simulator prompt
- audio config
- turn config
- tool mocks
- grader config

## README Expectations

The generated README should be useful without opening the harness source first. Include:

- a short explanation of why the chosen harness fits the request
- the files the user should edit first
- exact smoke and full commands from repo root
- the expected data shape
- troubleshooting notes for `OPENAI_API_KEY` and `ffmpeg` when relevant
