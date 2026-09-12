"""Export RUN evaluation artifacts to an interactive, self-contained HTML viewer."""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
import wave
from array import array
from pathlib import Path
from typing import Any

from run_harness.visualization.activity import build_backend_activity
from shared.audio.pcm import speech_intervals_pcm16
from shared.paths import package_path, require_external_output
from shared.private_files import private_write_text
from shared.reporting.compat import normalize_run_configuration, normalize_run_observability

TEMPLATE_DIR = package_path("run_harness", "visualization", "templates")
WAVEFORM_POINTS = 480
SPEECH_GAP_MS = 80
INTERACTION_COUNT_KEYS = (
    "response_total",
    "response_count",
    "yield_total",
    "yield_count",
    "backchannel_total",
    "backchannel_correct_count",
    "backchannel_error_count",
    "agent_interrupts_count",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _run_artifact(run_directory: Path, value: object, *, label: str) -> Path:
    """Reject absolute, relative, or symlink escapes from the results directory."""
    path = Path(str(value))
    candidate = (path if path.is_absolute() else run_directory / path).resolve()
    try:
        candidate.relative_to(run_directory.resolve())
    except ValueError as exc:
        raise ValueError(f"RUN {label} artifact must stay within the run directory: {value}") from exc
    return candidate


def _read_jsonl(path: Path, *, explain_debug_artifacts: bool = False) -> list[dict[str, Any]]:
    if not path.exists():
        hint = " Re-run the evaluation with --debug-artifacts." if explain_debug_artifacts else ""
        raise FileNotFoundError(f"Required conversation artifact does not exist: {path}.{hint}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _extract_waveforms(audio_path: Path, points: int = WAVEFORM_POINTS) -> dict[str, Any]:
    """Extract independent caller/assistant amplitude envelopes from PCM16 WAV."""
    if points <= 0:
        raise ValueError("waveform points must be greater than zero")
    with wave.open(str(audio_path), "rb") as recording:
        channels = recording.getnchannels()
        if channels not in {1, 2}:
            raise ValueError("conversation audio must contain one or two channels")
        if recording.getsampwidth() != 2:
            raise ValueError("conversation audio must use PCM16 samples")
        sample_rate = recording.getframerate()
        frame_count = recording.getnframes()
        if frame_count <= 0:
            raise ValueError("conversation audio must contain at least one audio frame")
        samples = array("h")
        samples.frombytes(recording.readframes(frame_count))
    if sys.byteorder != "little":
        samples.byteswap()

    caller = samples[::channels]
    assistant = samples[1::channels] if channels == 2 else array("h", [0]) * len(caller)
    window = max(1, math.ceil(frame_count / points))

    def envelope(track: array[int]) -> list[float]:
        return [
            round(max((abs(sample) for sample in track[index : index + window]), default=0) / 32_768, 4)
            for index in range(0, len(track), window)
        ]

    return {
        "durationMs": round(frame_count * 1_000 / sample_rate),
        "sampleRate": sample_rate,
        "caller": envelope(caller),
        "assistant": envelope(assistant),
    }


def _reconstruct_ticks(audio_path: Path, tick_ms: int) -> list[dict[str, Any]]:
    """Recover speaker timing from an older run's ordinary stereo recording."""
    if tick_ms <= 0:
        raise ValueError("conversation tick duration must be greater than zero")
    with wave.open(str(audio_path), "rb") as recording:
        channels = recording.getnchannels()
        if channels not in {1, 2}:
            raise ValueError("conversation audio must contain one or two channels")
        if recording.getsampwidth() != 2:
            raise ValueError("conversation audio must use PCM16 samples")
        sample_rate = recording.getframerate()
        samples = array("h")
        samples.frombytes(recording.readframes(recording.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()

    caller = samples[::channels]
    assistant = samples[1::channels] if channels == 2 else array("h", [0]) * len(caller)
    frames_per_tick = max(1, sample_rate * tick_ms // 1_000)
    ticks: list[dict[str, Any]] = []
    for start_frame in range(0, len(caller), frames_per_tick):
        end_frame = min(start_frame + frames_per_tick, len(caller))
        start_ms = start_frame * 1_000 // sample_rate
        end_ms = end_frame * 1_000 // sample_rate
        tick: dict[str, Any] = {"start_ms": start_ms, "end_ms": end_ms}
        for role, track in (("user", caller), ("assistant", assistant)):
            intervals = speech_intervals_pcm16(track[start_frame:end_frame].tobytes(), start_ms, sample_rate, 220.0)
            tick[role] = {"speech": bool(intervals), "speech_intervals_ms": [list(item) for item in intervals]}
        ticks.append(tick)
    return ticks


def _speech_segments(ticks: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for tick in ticks:
        participant = tick.get(role, {})
        intervals = participant.get("speech_intervals_ms", [])
        if not participant.get("speech") or not intervals:
            continue
        start_ms = min(int(interval[0]) for interval in intervals)
        end_ms = max(int(interval[1]) for interval in intervals)
        text = str(participant.get("transcript", "")).strip()
        action = str(participant.get("action", "")).strip() if role == "user" else ""

        if segments and start_ms - int(segments[-1]["endMs"]) <= SPEECH_GAP_MS:
            previous = segments[-1]
            previous["endMs"] = max(int(previous["endMs"]), end_ms)
            if text and text != previous.get("_lastText"):
                previous["text"] = " ".join(part for part in (str(previous["text"]), text) if part)
                previous["_lastText"] = text
            if action and not previous.get("action"):
                previous["action"] = action
            continue

        segment: dict[str, Any] = {"startMs": start_ms, "endMs": end_ms, "text": text, "_lastText": text}
        if role == "user":
            segment["action"] = action
        segments.append(segment)

    for segment in segments:
        segment.pop("_lastText", None)
    return segments


def _overlap_segments(ticks: list[dict[str, Any]]) -> list[dict[str, int]]:
    overlaps: list[dict[str, int]] = []
    for tick in ticks:
        caller_intervals = tick.get("user", {}).get("speech_intervals_ms", [])
        assistant_intervals = tick.get("assistant", {}).get("speech_intervals_ms", [])
        for left_start, left_end in caller_intervals:
            for right_start, right_end in assistant_intervals:
                start_ms, end_ms = max(int(left_start), int(right_start)), min(int(left_end), int(right_end))
                if start_ms >= end_ms:
                    continue
                if overlaps and start_ms <= overlaps[-1]["endMs"] + SPEECH_GAP_MS:
                    overlaps[-1]["endMs"] = max(overlaps[-1]["endMs"], end_ms)
                else:
                    overlaps.append({"startMs": start_ms, "endMs": end_ms})
    return overlaps


def _tool_events(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for turn in turns:
        for event in turn.get("task", {}).get("tool_calls", []):
            name = str(event.get("name", "")).strip()
            status = str(event.get("status", "")).strip()
            event_type = str(event.get("event_type", ""))
            if not name or name == "unknown" or event_type not in {"tool.called", "tool.completed"}:
                continue
            timestamp_ms = int(event.get("timestamp_ms", turn.get("start_ms", 0)))
            marker = (timestamp_ms, name, status)
            if marker in seen:
                continue
            seen.add(marker)
            events.append({"timeMs": timestamp_ms, "name": name, "status": status})
    return sorted(events, key=lambda item: (item["timeMs"], item["status"]))


def _delegation_events(ticks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract assistant delegations without exporting private request contents."""
    delegations: dict[tuple[int, str], dict[str, Any]] = {}

    for tick in ticks:
        for event in tick.get("events", []):
            if not isinstance(event, dict) or event.get("type") not in {
                "session.delegation.created",
                "delegation.created",
            }:
                continue
            timestamp = event.get("timestamp_ms", tick.get("start_ms"))
            if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0:
                continue
            item = event.get("delegation", event.get("item", {}))
            item = item if isinstance(item, dict) else {}
            target = str(event.get("name") or item.get("target") or "responses")
            delegations[timestamp, target] = {"timeMs": timestamp, "target": target}

    return sorted(delegations.values(), key=lambda event: (event["timeMs"], event["target"]))


def _assign_event_lanes(
    events: list[dict[str, Any]],
    *,
    duration_ms: int,
    track_width_px: int = 960,
) -> list[dict[str, Any]]:
    """Keep event markers anchored at their dots while right-aligned labels avoid collisions."""
    if duration_ms <= 0 or track_width_px <= 0:
        raise ValueError("event timeline duration and track width must be greater than zero")

    occupied_until: dict[int, float] = {}
    positioned: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: int(item["timeMs"])):
        center = int(event["timeMs"]) * track_width_px / duration_ms
        label_width = min(172, max(35, len(str(event.get("label", ""))) * 5.7 + 16))
        left = center - 3.5 - 8
        right = center - 3.5 + label_width + 8
        lane = 0
        while occupied_until.get(lane, float("-inf")) > left:
            lane += 1
        occupied_until[lane] = right
        positioned.append({**event, "lane": lane})
    return positioned


def _turn_rows(turns: list[dict[str, Any]], tracks: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for turn in turns:
        start_ms = int(turn.get("start_ms", 0))
        end_ms = int(turn.get("end_ms", start_ms))
        window_end_ms = int(turn.get("window_end_ms", end_ms))
        user_text = str(turn.get("user_transcript", "")).strip()
        assistant_text = str(turn.get("assistant_transcript", "")).strip()

        if user_text:
            output.append(
                {
                    "role": "caller",
                    "startMs": start_ms,
                    "endMs": end_ms,
                    "text": user_text,
                    "action": str(turn.get("action", "")),
                    "overlapMs": int(turn.get("audio", {}).get("overlap_ms", 0)),
                }
            )
        if assistant_text:
            matches = [
                segment
                for segment in tracks["assistant"]
                if segment["endMs"] > start_ms and segment["startMs"] < window_end_ms
            ]
            assistant_start = max(start_ms, int(matches[0]["startMs"])) if matches else end_ms
            assistant_end = min(window_end_ms, int(matches[-1]["endMs"])) if matches else window_end_ms
            assistant_row = {
                "role": "assistant",
                "startMs": assistant_start,
                "endMs": max(assistant_start, assistant_end),
                "text": assistant_text,
                "action": "",
                "overlapMs": int(turn.get("audio", {}).get("overlap_ms", 0)),
            }
            response_latency = turn.get("audio", {}).get("response_latency_ms")
            if (
                isinstance(response_latency, int | float)
                and not isinstance(response_latency, bool)
                and response_latency >= 0
            ):
                assistant_row["responseLatencyMs"] = response_latency
            output.append(assistant_row)
    return sorted(output, key=lambda item: (item["startMs"], item["role"] != "caller"))


def _transcript_rows(
    transcript: object, turns: list[dict[str, Any]], tracks: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Keep timestamped speech separate from caller-centered scoring windows."""
    legacy_rows = _turn_rows(turns, tracks)
    if not isinstance(transcript, str):
        return legacy_rows
    entries: list[list[str]] = []
    for line in transcript.splitlines():
        # Agent event headers also end speech, so their continuations cannot become spoken text.
        if re.match(
            r"(?:(?:USER|ASSISTANT) \d+\.\.\d+ms(?: \[OVERLAP\])?|(?:TOOL|BACKEND|DELEGATION) \d+ms): ",
            line,
        ):
            entries.append([line])
        elif entries:
            entries[-1].append(line)
    rows: list[dict[str, Any]] = []
    for entry in entries:
        match = re.fullmatch(r"(USER|ASSISTANT) (\d+)\.\.(\d+)ms(?: \[OVERLAP\])?: (.*)", "\n".join(entry), re.DOTALL)
        if not match:
            continue
        role, start, end, text = match.groups()
        start_ms, end_ms = int(start), int(end)
        if end_ms < start_ms or not text.strip():
            continue
        rows.append(
            {
                "role": "caller" if role == "USER" else "assistant",
                "startMs": start_ms,
                "endMs": end_ms,
                "text": text,
                "action": "",
                "overlapMs": 0,
            }
        )
    if not rows:
        return legacy_rows
    rows.sort(key=lambda item: (item["startMs"], item["role"] != "caller"))
    for row in rows:
        # Scoring windows supply annotations only, never transcript text/timing.
        annotations = [
            item
            for item in legacy_rows
            if item["role"] == row["role"] and row["startMs"] <= item["startMs"] < row["endMs"]
        ]
        if row["role"] == "caller" and annotations:
            row["action"] = annotations[0]["action"]
        elif row["role"] == "assistant":
            latencies = [item["responseLatencyMs"] for item in annotations if "responseLatencyMs" in item]
            if len(latencies) == 1:
                row["responseLatencyMs"] = latencies[0]
        # Measure overlap using acoustic intervals rather than an entire turn window.
        opposite = tracks["assistant" if row["role"] == "caller" else "caller"]
        own = tracks[row["role"]]
        row["overlapMs"] = sum(
            max(0, min(row["endMs"], a["endMs"], b["endMs"]) - max(row["startMs"], a["startMs"], b["startMs"]))
            for a in own
            for b in opposite
        )
    return rows


def _scenario_view(run_directory: Path, row: dict[str, Any]) -> dict[str, Any]:
    artifacts = row.get("artifacts", {})
    if not artifacts.get("conversation_audio") or not artifacts.get("details"):
        raise ValueError(f"RUN scenario {row.get('scenario_id', '<unknown>')} does not include audio and details")

    audio_path = _run_artifact(run_directory, artifacts["conversation_audio"], label="conversation audio")
    details_path = _run_artifact(run_directory, artifacts["details"], label="scenario details")
    details = _read_json(details_path)
    interaction_metrics = details.get("interaction_metrics", {})
    raw_interaction_counts = interaction_metrics.get("counts", {})
    if not isinstance(raw_interaction_counts, dict):
        raw_interaction_counts = {}
    interaction_counts = {
        key: value
        for key in INTERACTION_COUNT_KEYS
        if isinstance(value := raw_interaction_counts.get(key), int) and not isinstance(value, bool) and value >= 0
    }
    metadata = details.get("run_metadata", {})
    ticks_path = _run_artifact(run_directory, audio_path.with_suffix(".ticks.jsonl"), label="tick trace")
    turns_path = _run_artifact(run_directory, audio_path.with_suffix(".turns.jsonl"), label="turn trace")
    tick_ms = int(metadata.get("synchronized_tick_ms", metadata.get("frame_ms", 200)))
    ticks = _read_jsonl(ticks_path) if ticks_path.exists() else _reconstruct_ticks(audio_path, tick_ms)
    turns = _read_jsonl(turns_path) if turns_path.exists() else details.get("turn_metrics", [])
    if not isinstance(turns, list) or not all(isinstance(turn, dict) for turn in turns):
        raise ValueError(f"RUN scenario {row.get('scenario_id', '<unknown>')} does not include usable turn records")
    provenance = "debug_trace" if ticks_path.exists() and turns_path.exists() else "reconstructed_audio"
    observations = normalize_run_observability(row.get("observability", {}))
    interaction = observations["interaction"]
    observed_tools = observations.get("tools", {})
    executions = observed_tools.get("executed", [])
    tools = {
        "executed": [
            {"name": str(execution.get("name", "")), "status": str(execution.get("status", ""))}
            for execution in executions
            if isinstance(execution, dict)
        ],
        **{
            key: observed_tools[key]
            for key in ("expected_count", "matched_count", "unexpected_completed_count", "failed_count")
            if key in observed_tools
        },
    }
    tracks = {"caller": _speech_segments(ticks, "user"), "assistant": _speech_segments(ticks, "assistant")}
    event_path = _run_artifact(
        run_directory,
        artifacts.get("events") or "__missing_events__.jsonl",
        label="event log",
    )
    waveform = _extract_waveforms(audio_path)
    tool_events = _tool_events(turns)
    timeline_events = [
        *ticks,
        {
            "events": [
                {**event, "type": event.get("event_type")}
                for event in details.get("agent_events", [])
                if isinstance(event, dict)
            ]
        },
    ]
    delegations, tool_calls = build_backend_activity(event_path, _delegation_events(timeline_events), turns, executions)
    delegation_events = [
        {"timeMs": event["timeMs"], "target": event["target"]} for event in delegations if event["timeMs"] is not None
    ]
    annotations = [
        {
            "timeMs": event["timeMs"],
            "label": event["name"],
            "kind": "tool",
            "status": event["status"],
            "toolIndex": index,
        }
        for index, event in enumerate(tool_calls)
        if event["timeMs"] is not None
    ]
    annotations.extend(
        {
            "timeMs": event["timeMs"],
            "label": f"Delegation · {event['target']}",
            "kind": "delegation",
            "delegationIndex": index,
        }
        for index, event in enumerate(delegations)
        if event["timeMs"] is not None
    )
    return {
        "id": str(row["scenario_id"]),
        "title": str(row.get("title", row["scenario_id"])),
        "status": str(row.get("status", "unknown")),
        "timelineProvenance": provenance,
        "audioData": "data:audio/wav;base64," + base64.b64encode(audio_path.read_bytes()).decode("ascii"),
        "waveform": waveform,
        "tracks": tracks,
        "overlaps": _overlap_segments(ticks),
        "turns": _transcript_rows(details.get("transcript"), turns, tracks),
        "toolEvents": tool_events,
        "toolCalls": tool_calls,
        "delegationEvents": delegation_events,
        "delegations": delegations,
        "eventAnnotations": _assign_event_lanes(annotations, duration_ms=waveform["durationMs"]),
        "interaction": {
            "attribution": interaction["attribution"],
            "callerActions": interaction["caller_actions"],
        },
        "metrics": row.get("metrics", {}).get("audio", {}),
        "finalMetrics": row.get("metrics", {}),
        "task": row.get("metrics", {}).get("task", {}),
        "tools": tools,
        "completion": observations.get("completion", {}),
        "interactionEvents": interaction_metrics.get("events", []),
        "interactionCounts": interaction_counts,
    }


def build_view_data(results_path: Path, scenario_id: str | None = None) -> dict[str, Any]:
    """Build a minimal, browser-safe view model from existing RUN artifacts."""
    results_path = results_path.expanduser().resolve()
    report = _read_json(results_path)
    raw_run = report.get("run", {})
    if not isinstance(raw_run, dict) or str(raw_run.get("module", "run")).lower() != "run":
        raise ValueError("The conversation viewer only supports RUN evaluation results")

    source_rows = report.get("results", [])
    if not isinstance(source_rows, list) or not all(isinstance(row, dict) for row in source_rows):
        raise ValueError("RUN evaluation results must contain a list of scenario result objects")
    matching_rows = [row for row in source_rows if scenario_id is None or row.get("scenario_id") == scenario_id]
    if not matching_rows:
        if scenario_id is not None:
            raise ValueError(f"No RUN scenario matched {scenario_id!r}")
        raise ValueError("No visualizable RUN conversations are available")
    rows = [row for row in matching_rows if row.get("status") != "infrastructure_error"]
    if not rows:
        raise ValueError("No visualizable RUN conversations are available; matching scenarios failed to run")

    raw_configuration = normalize_run_configuration(raw_run.get("configuration", {}))
    execution_mode = str(raw_run.get("execution_mode", "unknown"))
    audio_provenance = (
        "synthetic_tone_fixture"
        if execution_mode == "offline_fixture"
        else "live_model_speech"
        if execution_mode == "live"
        else "unknown"
    )
    configuration = {
        key: raw_configuration.get(key)
        for key in ("model", "backend_model", "simulator_model", "simulator_voice", "tick_ms", "audio_condition")
        if key in raw_configuration
    }
    return {
        "run": {
            "id": raw_run.get("id", results_path.parent.name),
            "module": raw_run.get("module", "run"),
            "executionMode": execution_mode,
            "audioProvenance": audio_provenance,
            "configuration": configuration,
        },
        "summary": report.get("summary", {}),
        "scenarios": [_scenario_view(results_path.parent, row) for row in rows],
    }


def _render_html(data: dict[str, Any]) -> str:
    css = (TEMPLATE_DIR / "viewer.css").read_text(encoding="utf-8")
    javascript = (TEMPLATE_DIR / "viewer.js").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Voice Evals · RUN conversation</title>
  <style>{css}</style>
</head>
<body>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="#timeline" aria-label="Voice Evals conversation viewer">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>
        <span>VOICE EVALS</span>
      </a>
      <div class="topbar-context"><span class="context-label">EVALUATION</span><span>RUN</span></div>
      <span class="run-state" id="run-state">READY</span>
    </header>

    <main>
      <section class="overview" aria-labelledby="scenario-heading">
        <div class="overview-copy">
          <h1 id="scenario-heading">Conversation timeline</h1>
          <p class="scenario-id" id="scenario-id"></p>
        </div>
        <div class="overview-controls">
          <label class="scenario-picker">SCENARIO
            <select id="scenario-select" aria-label="Select scenario"></select>
          </label>
          <span class="result-pill" id="scenario-status"></span>
        </div>
      </section>

      <section class="timeline-panel" id="timeline" data-timeline aria-label="Conversation audio timeline">
        <div class="timeline-toolbar">
          <div class="transport">
            <button class="play-button" id="play-button" type="button" aria-label="Play conversation">
              <svg class="play-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10-6.5z"/></svg>
              <svg class="pause-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg>
            </button>
            <span class="time-readout">
              <span id="current-time">0:00</span><span>/</span><span id="duration">0:00</span>
            </span>
          </div>
          <div class="timeline-legend">
            <span><i class="legend-dot caller"></i>Caller</span>
            <span><i class="legend-dot assistant"></i>Agent</span>
            <span><i class="legend-dot overlap"></i>Overlap</span>
          </div>
          <button class="speed-button" id="speed-button" type="button" aria-label="Playback speed">1×</button>
        </div>

        <div class="timeline-stage" id="timeline-stage" tabindex="0" aria-label="Seek conversation timeline">
          <div class="time-ruler" id="time-ruler"></div>
          <div class="track" data-track="caller">
            <div class="track-label"><span>CALLER</span><small>Left channel</small></div>
            <div class="track-canvas" id="caller-track"></div>
          </div>
          <div class="track events-track" data-track="events">
            <div class="track-label"><span>EVENTS</span><small>Delegations · tools</small></div>
            <div class="track-canvas" id="events-track"></div>
          </div>
          <div class="track" data-track="assistant">
            <div class="track-label"><span>AGENT</span><small>Right channel</small></div>
            <div class="track-canvas" id="assistant-track"></div>
          </div>
          <div class="playhead" id="playhead" aria-hidden="true"><span></span></div>
        </div>

        <div class="timeline-footer"><span id="timeline-caption"></span><span id="tick-caption"></span></div>
      </section>

      <section class="analysis-layout">
        <section class="transcript-panel" aria-labelledby="transcript-heading">
          <div class="section-heading">
            <div><h2 id="transcript-heading">Conversation</h2></div>
            <span id="turn-count"></span>
          </div>
          <p class="activity-note">Backend activity grouped by speech timing; event timestamps are unchanged.</p>
          <ol class="transcript-list" id="transcript-list"></ol>
        </section>

        <aside class="evidence-panel" aria-labelledby="evidence-heading">
          <div class="section-heading">
            <div><h2 id="evidence-heading">Signals</h2></div>
          </div>
          <div class="architecture-block"><span id="interaction-mode"></span><p id="interaction-explanation"></p></div>
          <div id="metric-list"></div>
          <div class="tool-block"><h3>Tool activity</h3><div id="tool-list"></div></div>
          <div class="outcome-block"><h3>Outcome</h3><p id="outcome-message"></p></div>
        </aside>
      </section>
    </main>
  </div>
  <audio id="conversation-audio" preload="metadata"></audio>
  <script id="viewer-data" type="application/json">{payload}</script>
  <script>{javascript}</script>
</body>
</html>
"""


def export_viewer(
    results_path: Path,
    output_path: Path | None = None,
    scenario_id: str | None = None,
) -> Path:
    """Write one standalone HTML viewer with embedded conversation audio."""
    results_path = results_path.expanduser().resolve()
    destination = require_external_output(output_path if output_path else results_path.parent / "viewer.html")
    private_write_text(destination, _render_html(build_view_data(results_path, scenario_id)), encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse export options without reading or writing artifacts."""
    parser = argparse.ArgumentParser(description="Export RUN conversations to a standalone interactive HTML viewer.")
    parser.add_argument("--results", required=True, type=Path, help="Path to an existing RUN results.json file.")
    parser.add_argument("--scenario", default=None, help="Export one scenario; defaults to every scenario in the run.")
    parser.add_argument("--output", type=Path, default=None, help="HTML output path; defaults to <run>/viewer.html.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the public `run-view` standalone conversation-export command."""
    args = parse_args(argv)
    output = export_viewer(args.results, args.output, args.scenario)
    print(f"Viewer: {output}")


if __name__ == "__main__":
    main()
