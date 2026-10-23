# Shared evaluation infrastructure

`shared/` provides common configuration, transport, audio, grading, metrics,
and utilities used by CRAWL, WALK, and RUN. It is not an evaluation module and
does not own a scenario dataset, runner, or application-specific tools.

## Shared architecture

```text
phase-owned caller
synthetic request | existing WAV | simulated conversation
                         │
                         ▼
                assistants/frontend GPT Live
                         │
              managed or client-owned backend
                         │
              assistant-owned application tools
                         │
             actual application execution and state
                         │
                         ▼
           shared timeline, artifacts, and metrics
```

Each evaluation session receives an isolated tool executor and application
state. The phase-specific runner and graders decide how to create the caller,
execute the scenario, and interpret the result. RUN keeps its two GPT Live
participant sessions, caller agenda, audio relay, completion observer, and
post-hoc event interpretation under `run_harness/simulation/`; shared code
does not own that simulator. The live caller has independent managed Responses
reasoning, but no application tools or local tool controller. RUN tracks caller
Responses work separately and blocks semantic completion while it is pending.
See RUN's [caller model settings](../run_harness/README.md#caller-models).
Interruption and backchannel intent are inferred from the recorded audio and
transcripts, not assigned by an active controller.

## Components

| Component | Responsibility |
| --- | --- |
| `config.py` | Standard-library TOML configuration and module-relative dataset paths. |
| `scenarios.py` | One versioned JSON scenario contract, including recordings, application state, tools, procedures, and personas. |
| `artifacts.py` | Portable scenario identifiers, checked artifact destinations, and exclusive run-directory creation. |
| `audio/pcm.py` | PCM chunks, validated WAV reading/writing, speech activity, and continuous ambience. |
| `audio/effects.py` | Deterministic acoustic presets, effect configuration, and audio-realism CLI options. |
| `audio/conversation.py` | Live stereo playback and saved timeline-aligned conversation audio. |
| `audio/pacing.py` | Absolute-deadline packet pacing without replay bursts. |
| `audio/assets/` | Bundled synthetic background-conversation audio. |
| `grading/outcomes.py` | Evidence-backed task-completion decisions. |
| `grading/scoring.py` and `metrics/evidence.py` | Task evidence and observed tool accuracy. |
| `grading/semantic.py` | Semantic-quality rubric and independent-judge contract. |
| `single_turn/runtime.py` | Low-level Live connection, audio streaming, receive-loop timeout, and session-close helpers; harnesses own orchestration. |
| `single_turn/response.py` | Per-response protocol evidence, tool/delegation correlation, and completion policy; no harness lifecycle or tool execution. |
| `single_turn/grading.py` | CRAWL/WALK deterministic grading plus severity-aware semantic judge scores. |
| `single_turn/observability.py` | CRAWL/WALK outcome diagnostics and evaluation traces. |
| `single_turn/console.py` | Readable streaming audio, transcript, delegation, and tool events. |
| `single_turn/types.py` | CRAWL/WALK result, artifact, latency, and run-configuration types. |
| `metrics/reporting.py` | Canonical comparable result columns. |
| `metrics/interaction.py` | Audio-derived response, interruption, yield, and backchannel observations. |
| `metrics/latency.py` | Actual speech and event timing. |
| `metrics/tokens.py` | Shared token-usage models and separate frontend/backend accounting. |
| `observability/timeline.py` | Timestamped speech, transcript, and application-event timelines. |
| `observability/trace.py` | Sanitized protocol traces with raw audio payloads removed. |
| `reporting/results.py` | Compact JSON reports, artifact writing, and timestamped run directories. |
| `reporting/schema.py` and `reporting/compat.py` | Current result schema version and narrow historical-result normalization. |
| `testing/live.py` | Explicit deterministic offline GPT Live protocol fixtures. |

Assistant settings and application resources live in `assistants/config.py` and
`assistants/resources.py`. Frontend transport belongs to
`assistants/frontend/transport.py`; generic tool contracts belong to
`assistants/runtime.py`. Each assistant backend owns its application-specific
tool schemas, implementations, offline behavior, and authorized business facts
under its own `tools/` directory.

## Artifact safety

Scenario IDs are portable filenames: 1–100 ASCII letters, digits, dots,
underscores, or hyphens, starting with a letter or digit. Trailing dots and
Windows device names are rejected. IDs must be unique ignoring case; use
`title` for a human-readable name. Every harness validates the complete dataset
before selecting examples, and each evaluation reserves a fresh run directory.
Checked destinations reject traversal, descendant symlinks, and hard-linked
files. Use output directories that other users cannot modify while a run is
active; these checks are not a sandbox against concurrent filesystem changes.

## Configuration boundaries

Use the selected `.env` file or shell for OpenAI credentials and supported
assistant, endpoint, voice, backend, observer, and judge settings. Existing
shell values win; see [environment-file selection](../README.md#environment-file-selection).
RUN's caller backend model and effort are separate TOML settings. Its frontend
model and voice can be selected with `--simulator-model` and `--simulator-voice`.

Use a module-owned TOML for execution settings:

```text
crawl_harness/config.toml
walk_harness/config.toml
run_harness/config.toml
```

Command-line overrides apply to one run. Relative dataset paths resolve from
the selected configuration file.

WALK fixture generation and RUN use the same `clean`, `noisy`, `telephony`,
`background_speech`, `echo`, `packet_loss`, and `realistic` presets. WALK
applies effects before saving a reusable recording; RUN applies them to the
live caller stream. CRAWL remains a clean, synthetic single-turn baseline.

The `telephony` preset uses 300–3,400 Hz voice-band filtering, 8 kHz sampling,
and G.711 μ-law compression while preserving the continuous 24 kHz PCM
transport. The `realistic` preset includes the same telephone channel.
The `noisy` preset adds clearly audible deterministic background noise at
1,200 PCM16 RMS; override its intensity with `--noise-rms` when needed.
The `background_speech` preset mixes in a bundled synthetic conversation from
a second speaker; replace it with approved recorded speech using
`--background-speech` and adjust its level with `--background-gain`.
The `realistic` preset combines the telephone channel with 500-RMS noise,
background speech, moderate echo, and 4% single-frame packet loss.

## Evaluation boundaries

Keep these roles independent:

1. The caller provides synthetic, recorded, or simulated audio.
2. GPT Live receives the actual caller audio and authorized instructions.
3. The application executes explicitly permitted tools against isolated state.
4. Independent graders inspect observed responses, events, tools, and state.

Never send reference transcripts, expected answers, golden tool calls,
grading rubrics, final-state expectations, future simulated replies, or
judge-only evidence to the evaluated assistant.

## Shared metrics

All modules export the same task, observed-audio, and evaluated-assistant
token metric groups. Semantic quality is part of task evaluation. Task
completion remains a strict binary decision based on the achieved, authorized
application outcome; preferred procedures and partial-credit scores cannot
override required application state, tool contracts, safety checks, or
explicitly critical procedure requirements. Tool accuracy deterministically
matches unique executions, normalized nested arguments, and expected status;
delegation accuracy checks the binary decision to delegate or not against
the scenario policy. RUN scenarios explicitly set
`expected.golden_path.delegations`; the separate `delegations` metric reports
the observed and reference counts for the whole conversation. Neither action metric uses an LLM;
semantic quality is independently LLM-judged. Response latency is one
conversation-level measurement in
milliseconds; floor-hold silence reports cumulative and maximum uninterrupted
durations in milliseconds.

Independent semantic judges apply one shared rubric: `task_understanding`,
`context_fidelity`, `clarification_quality`, `grounded_communication`, and
`conversational_coherence`, as applicable. Each individual score is one of
`0`, `0.25`, `0.5`, `0.75`, or `1`; averages may fall between those values. Scores
are reported under `metrics.task.semantic_quality.dimensions` and averaged into
each scenario's `metrics.task.semantic_quality.score`. The run summary contains
only execution counts. Judges receive scenario-specific success criteria,
actual tool executions with returned outputs, and verified application state.
Only task understanding contributes to the semantic task-success verdict;
it is separate from the observer that decides when a RUN conversation can end.
Offline runs leave these scores `null` rather than inventing judge evidence.
Raw tool and turn counts remain separate from latency, yielding, interruption,
and backchannel measurements. Frontend usage supports audio duration and legacy
token shapes; cumulative session snapshots are not added together. Backend
usage preserves model attribution without double-counting Responses usage.
Metrics without an applicable opportunity are `null`; judge and caller usage
are never mixed into evaluated assistant consumption.

Event logs omit raw audio, but transcripts, tool arguments, and application
state remain visible. Treat generated artifacts as sensitive data.

See the root [results and metrics guide](../README.md#5-results-and-metrics)
for definitions and the individual phase READMEs for applicability.

## Installation paths

`shared.paths` resolves read-only package assets and writable result/cache defaults.
`shared.environment` owns explicit environment-file selection. See the
[installation guide](../README.md#installed-package-and-paths). Playback is an optional extra;
headless evaluation does not require an audio device.
