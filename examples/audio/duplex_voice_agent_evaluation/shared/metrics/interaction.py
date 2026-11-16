"""Audio-aligned tick artifacts and τ-voice-style interaction metrics."""

from __future__ import annotations

import json
import math
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.observability.timeline import Timeline, Transcript
from shared.private_files import private_open

TickRecord = dict[str, Any]
METRICS_VERSION = "2.0"
# Evaluation policy, not a model SLA. Callers may choose a different predeclared deadline.
DEFAULT_RESPONSE_DEADLINE_MS = 5_000


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    role: str
    start_ms: int
    end_ms: int
    action: str = ""


@dataclass(frozen=True, slots=True)
class ResponseOpportunity:
    status: str
    reason: str
    deadline_at_ms: int | None = None
    observed_latency_ms: int | None = None


def _clip(intervals: tuple[tuple[int, int], ...], start_ms: int, end_ms: int) -> list[list[int]]:
    return [
        [max(start_ms, left), min(end_ms, right)]
        for left, right in _merge_intervals(intervals)
        if left < end_ms and start_ms < right
    ]


def _overlap(left: list[list[int]], right: list[list[int]]) -> int:
    return sum(max(0, min(b, d) - max(a, c)) for a, b in left for c, d in right)


def _merge_intervals(intervals: tuple[tuple[int, int], ...]) -> list[list[int]]:
    merged: list[list[int]] = []
    for start_ms, end_ms in sorted(intervals):
        if end_ms <= start_ms:
            continue
        if merged and start_ms <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end_ms)
        else:
            merged.append([start_ms, end_ms])
    return merged


def _speaking_duration(
    assistants: list[SpeechSegment],
    timeline: Timeline | None,
) -> dict[str, int]:
    raw_intervals = (
        timeline.speech_intervals("assistant")
        if timeline is not None
        else tuple((segment.start_ms, segment.end_ms) for segment in assistants)
    )
    intervals = _merge_intervals(raw_intervals)
    cumulative = sum(end_ms - start_ms for start_ms, end_ms in intervals)
    agent_turns = [turn for turn in timeline.turns if turn.role == "assistant"] if timeline is not None else []
    per_turn = [
        sum(max(0, min(end_ms, turn.end_ms) - max(start_ms, turn.start_ms)) for start_ms, end_ms in intervals)
        for turn in agent_turns
    ]
    return {
        "cumulative": cumulative,
        "maximum": max(per_turn or [end_ms - start_ms for start_ms, end_ms in intervals], default=0),
    }


def _rms(track: array[int] | None, start_ms: int, end_ms: int, sample_rate: int) -> float | None:
    if track is None:
        return None
    samples = track[start_ms * sample_rate // 1_000 : end_ms * sample_rate // 1_000]
    if not samples:
        return 0.0
    return round(math.sqrt(sum(sample * sample for sample in samples) / len(samples)), 2)


def _project_text(item: Transcript, start_ms: int, end_ms: int) -> str:
    overlap_start = max(start_ms, item.start_ms)
    overlap_end = min(end_ms, item.end_ms)
    if overlap_end <= overlap_start:
        return ""
    words = item.text.split()
    if not words:
        return ""
    duration_ms = max(1, item.end_ms - item.start_ms)
    first = (overlap_start - item.start_ms) * len(words) // duration_ms
    last = (overlap_end - item.start_ms) * len(words) // duration_ms
    if overlap_end == item.end_ms:
        last = len(words)
    return " ".join(words[first:last])


def _events(timeline: Timeline) -> list[tuple[int, dict[str, Any]]]:
    events: list[tuple[int, dict[str, Any]]] = []
    for fragment in timeline.fragments:
        events.append(
            (
                fragment.start_ms,
                {
                    "type": fragment.source,
                    "role": fragment.role,
                    "start_ms": fragment.start_ms,
                    "end_ms": fragment.end_ms,
                    "text": fragment.text,
                },
            )
        )
    for utterance in timeline.user_utterances:
        events.append(
            (
                utterance.start_ms,
                {"type": "caller.action.observed", "role": "user", "action": utterance.action, "text": utterance.text},
            )
        )
    for turn in timeline.turns:
        events.append(
            (
                turn.end_ms,
                {
                    "type": "evaluation.turn.projected" if turn.turn_id.startswith("local-") else "turn.done",
                    "role": turn.role,
                    "start_ms": turn.start_ms,
                    "end_ms": turn.end_ms,
                    "transcript": turn.transcript,
                },
            )
        )
    for event in timeline.agent_events:
        payload = event.model_dump()
        payload["type"] = payload.pop("event_type")
        events.append((event.timestamp_ms, payload))
    for event in timeline.tool_events:
        if event.get("type") != "response.created":
            continue
        response = event.get("response", {})
        response_id = response.get("id") if isinstance(response, dict) else None
        if isinstance(response_id, str) and response_id:
            events.append((int(event.get("offset_ms", 0)), {"type": "response.created", "response_id": response_id}))
    return sorted(events, key=lambda item: item[0])


def build_ticks(
    timeline: Timeline,
    tick_ms: int,
    sample_rate: int,
    *,
    duration_ms: int = 0,
    user_track: array[int] | None = None,
    assistant_track: array[int] | None = None,
) -> list[TickRecord]:
    """Project asynchronously received speech, transcripts, and tools onto one audio clock."""
    if tick_ms <= 0:
        raise ValueError("tick_ms must be positive")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    events = _events(timeline)
    audio_end_ms = max(
        duration_ms,
        timeline.last_assistant_audio_ms,
        timeline.last_user_speech_ms,
        timeline.last_assistant_speech_ms,
        max((turn.end_ms for turn in timeline.turns), default=0),
        max((timestamp for timestamp, _ in events), default=0),
        len(user_track) * 1_000 // sample_rate if user_track is not None else 0,
        len(assistant_track) * 1_000 // sample_rate if assistant_track is not None else 0,
    )
    if audio_end_ms <= 0:
        return []

    user_intervals = timeline.speech_intervals("user")
    assistant_intervals = timeline.speech_intervals("assistant")
    delegation_intervals = timeline.delegation_intervals(audio_end_ms)
    event_index = 0
    records: list[TickRecord] = []

    for tick in range(math.ceil(audio_end_ms / tick_ms)):
        start_ms = tick * tick_ms
        end_ms = min(start_ms + tick_ms, audio_end_ms)
        user_speech = _clip(user_intervals, start_ms, end_ms)
        assistant_speech = _clip(assistant_intervals, start_ms, end_ms)
        delegated_work = _clip(delegation_intervals, start_ms, end_ms)
        utterances = [item for item in timeline.user_utterances if item.start_ms < end_ms and start_ms < item.end_ms]
        fragments = [
            item
            for item in timeline.fragments
            if item.role == "assistant" and item.start_ms < end_ms and start_ms < item.end_ms
        ]
        tick_events: list[dict[str, Any]] = []
        while event_index < len(events) and events[event_index][0] < end_ms:
            _, event = events[event_index]
            tick_events.append(event)
            event_index += 1
        user_active = bool(user_speech)
        assistant_active = bool(assistant_speech)
        records.append(
            {
                "tick": tick,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "user": {
                    "speech": user_active,
                    "speech_intervals_ms": user_speech,
                    "rms": _rms(user_track, start_ms, end_ms, sample_rate),
                    "action": utterances[0].action if utterances else "",
                    "transcript": " ".join(
                        piece for item in utterances if (piece := _project_text(item, start_ms, end_ms))
                    ),
                },
                "assistant": {
                    "speech": assistant_active,
                    "speech_intervals_ms": assistant_speech,
                    "rms": _rms(assistant_track, start_ms, end_ms, sample_rate),
                    "transcript": " ".join(
                        piece for item in fragments if (piece := _project_text(item, start_ms, end_ms))
                    ),
                },
                "interaction": {
                    "overlap_ms": _overlap(user_speech, assistant_speech),
                    # Presence anywhere in this bin, not the bin's final lifecycle state.
                    "delegation_active": bool(delegated_work),
                    "delegation_intervals_ms": delegated_work,
                    "delegation_active_ms": sum(right - left for left, right in delegated_work),
                },
                "events": tick_events,
            }
        )

    # Events exactly at the final boundary still belong to the last observed tick.
    if event_index < len(events):
        records[-1]["events"].extend(event for _, event in events[event_index:])
    return records


def write_ticks(path: Path, ticks: list[TickRecord]) -> Path:
    with private_open(path) as output:
        for tick in ticks:
            output.write(json.dumps(tick, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def _segments(ticks: list[TickRecord], role: str) -> list[SpeechSegment]:
    """Union actual voiced intervals; a nonempty reporting bin is not continuous speech."""
    segments: list[SpeechSegment] = []
    intervals = sorted(
        (int(left), int(right), str(tick[role].get("action", "")) if role == "user" else "")
        for tick in ticks
        for left, right in tick[role]["speech_intervals_ms"]
        if right > left
    )
    for start_ms, end_ms, action in intervals:
        if segments and start_ms <= segments[-1].end_ms:
            previous = segments[-1]
            segments[-1] = SpeechSegment(
                role, previous.start_ms, max(previous.end_ms, end_ms), previous.action or action
            )
        else:
            segments.append(SpeechSegment(role, start_ms, end_ms, action))
    return segments


def _caller_segments(ticks: list[TickRecord], timeline: Timeline | None = None) -> list[SpeechSegment]:
    """Merge acoustic gaps within one simulated utterance so pauses do not become extra user turns."""
    segments = _segments(ticks, "user")
    if timeline is None or not timeline.user_utterances:
        return segments
    merged: list[SpeechSegment] = []
    voiced = tuple((segment.start_ms, segment.end_ms) for segment in segments)
    for utterance in sorted(timeline.user_utterances, key=lambda item: (item.start_ms, item.end_ms)):
        matching = _clip(voiced, utterance.start_ms, utterance.end_ms)
        if not matching:
            # Simulator text labels classify observed audio; they must never invent speech.
            continue
        # Adjacent semantic requests may share one continuous acoustic segment.
        # Attribute only the voiced support inside this annotation, not both requests.
        start_ms = matching[0][0]
        end_ms = matching[-1][1]
        merged.append(SpeechSegment("user", start_ms, end_ms, utterance.action))
    return merged


def _expects_assistant_response(segment: SpeechSegment) -> bool:
    """Acknowledgements and explicit caller closings are not assistant requests."""
    return segment.action not in {"BACKCHANNEL", "STOP"}


def _response_exclusion(user: SpeechSegment, assistants: list[SpeechSegment]) -> str:
    """Keep the acoustic first-post-request-response population explicit."""
    if user.action == "BACKCHANNEL":
        return "backchannel"
    if user.action == "STOP":
        return "caller_closing"
    if any(agent.start_ms < user.end_ms <= agent.end_ms for agent in assistants):
        return "assistant_active_at_request_end"
    return ""


def _response_opportunities(
    users: list[SpeechSegment],
    assistants: list[SpeechSegment],
    *,
    conversation_end_ms: int,
    response_deadline_ms: int,
) -> list[ResponseOpportunity]:
    """Classify once for both views, preserving censored tails and late observations.

    A deadline-qualified response arrives no later than the declared deadline or
    the next eligible request. A later answer remains evidence of a missed deadline.
    """
    if type(response_deadline_ms) is not int or response_deadline_ms <= 0:
        raise ValueError("response_deadline_ms must be a positive integer")

    exclusions = [_response_exclusion(user, assistants) for user in users]
    opportunities: list[ResponseOpportunity] = []
    for index, user in enumerate(users):
        if exclusions[index]:
            opportunities.append(ResponseOpportunity("excluded", exclusions[index]))
            continue
        deadline_at_ms = user.end_ms + response_deadline_ms
        next_user = next(
            (
                following
                for following, reason in zip(users[index + 1 :], exclusions[index + 1 :], strict=True)
                if not reason and following.start_ms >= user.end_ms
            ),
            None,
        )
        next_response = next(
            (
                agent
                for agent in assistants
                if agent.start_ms >= user.end_ms and (next_user is None or agent.start_ms <= next_user.start_ms)
            ),
            None,
        )
        observed_latency_ms = next_response.start_ms - user.end_ms if next_response is not None else None
        if observed_latency_ms is not None and observed_latency_ms <= response_deadline_ms:
            status, reason = "answered", "response_received"
        elif next_user is not None and next_user.start_ms < deadline_at_ms:
            status, reason = "missed", "next_eligible_request"
        elif conversation_end_ms >= deadline_at_ms:
            status, reason = "missed", "deadline_expired"
        else:
            status, reason = "censored", "observation_ended_before_deadline"
        opportunities.append(ResponseOpportunity(status, reason, deadline_at_ms, observed_latency_ms))
    return opportunities


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _mean_seconds(samples_ms: list[int]) -> float | None:
    return round(sum(samples_ms) / len(samples_ms) / 1_000, 4) if samples_ms else None


def _duration_within(
    intervals: tuple[tuple[int, int], ...],
    start_ms: int,
    end_ms: int,
) -> int:
    return sum(right - left for left, right in _clip(intervals, start_ms, end_ms))


def _interrupted_assistant(user: SpeechSegment, assistants: list[SpeechSegment]) -> SpeechSegment | None:
    """Require pre-cue speech, retaining an explicit cue's immediate zero-overlap yield."""
    return next(
        (
            segment
            for segment in assistants
            if segment.start_ms < user.start_ms
            and (user.start_ms < segment.end_ms or (user.action == "INTERRUPT" and user.start_ms == segment.end_ms))
        ),
        None,
    )


def _agent_interruptions(
    user: SpeechSegment,
    assistants: list[SpeechSegment],
    caller_audio: tuple[tuple[int, int], ...],
) -> list[int]:
    if not _expects_assistant_response(user):
        return []
    voiced = _clip(caller_audio, user.start_ms, user.end_ms)
    return [
        assistant.start_ms
        for assistant in assistants
        if any(left <= assistant.start_ms < right for left, right in voiced)
    ]


def _backchannel_outcome(
    user: SpeechSegment,
    interrupted: SpeechSegment,
    *,
    backchannel_window_ms: int,
) -> str:
    """Accept continued speech or natural completion after a short acknowledgement."""

    continued_until_ms = interrupted.end_ms
    deadline_ms = user.start_ms + backchannel_window_ms

    # An assistant that talks beyond the acknowledgement did not yield to it,
    # even if it naturally finishes its sentence before the full τ-Voice window.
    # Exact segments already join touching audio; reporting ticks must not bridge silence.
    if continued_until_ms > user.end_ms or continued_until_ms >= deadline_ms:
        return "continued"
    return "false_yield"


def compute_turn_interaction_metrics(
    ticks: list[TickRecord],
    timeline: Timeline,
    *,
    yield_window_ms: int = 2_000,
    backchannel_window_ms: int = 1_000,
    response_deadline_ms: int = DEFAULT_RESPONSE_DEADLINE_MS,
    simulator_timings: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attribute versioned acoustic outcomes to each actual caller speech turn."""
    users = _caller_segments(ticks, timeline)
    assistants = _segments(ticks, "assistant")
    conversation_end_ms = ticks[-1]["end_ms"] if ticks else 0
    opportunities = _response_opportunities(
        users, assistants, conversation_end_ms=conversation_end_ms, response_deadline_ms=response_deadline_ms
    )
    caller_audio = timeline.speech_intervals("user")
    agent_audio = timeline.speech_intervals("assistant")
    records: list[dict[str, Any]] = []

    for index, user in enumerate(users):
        next_user = users[index + 1] if index + 1 < len(users) else None
        window_end_ms = next_user.start_ms if next_user is not None else conversation_end_ms
        utterance = next(
            (item for item in timeline.user_utterances if item.start_ms < user.end_ms and user.start_ms < item.end_ms),
            None,
        )
        interrupted = _interrupted_assistant(user, assistants)
        opportunity = opportunities[index]
        response_eligible = opportunity.status != "excluded"
        response_latency_ms = opportunity.observed_latency_ms if opportunity.status == "answered" else None
        response_outcome = {
            "answered": "responded",
            "missed": "no_response",
            "censored": "unobserved",
            "excluded": "not_applicable",
        }[opportunity.status]

        yield_latency_ms: int | None = None
        yield_outcome = "not_applicable"
        backchannel_outcome = "not_applicable"
        if interrupted is not None and user.action != "STOP":
            delay_ms = interrupted.end_ms - user.start_ms
            if user.action == "BACKCHANNEL":
                backchannel_outcome = _backchannel_outcome(
                    user,
                    interrupted,
                    backchannel_window_ms=backchannel_window_ms,
                )
            elif delay_ms <= yield_window_ms:
                yield_outcome = "yielded"
                yield_latency_ms = delay_ms
            else:
                yield_outcome = "no_yield"

        agent_interruptions = _agent_interruptions(user, assistants, caller_audio)
        user_intervals = _clip(caller_audio, user.start_ms, user.end_ms)
        assistant_intervals = _clip(agent_audio, user.start_ms, user.end_ms)
        timing_key = utterance.start_ms if utterance is not None else user.start_ms
        records.append(
            {
                "metrics_version": METRICS_VERSION,
                "turn_index": index,
                "start_ms": user.start_ms,
                "end_ms": user.end_ms,
                "window_end_ms": max(user.end_ms, window_end_ms),
                "action": user.action,
                "user_transcript": utterance.text if utterance is not None else "",
                "audio": {
                    "user_speech_ms": _duration_within(caller_audio, user.start_ms, user.end_ms),
                    "assistant_speech_ms": _duration_within(
                        agent_audio,
                        user.start_ms,
                        max(user.end_ms, window_end_ms),
                    ),
                    "overlap_ms": _overlap(user_intervals, assistant_intervals),
                    "response_expected": response_eligible,
                    "response_outcome": response_outcome,
                    "response_latency_ms": response_latency_ms,
                    "response_status": opportunity.status,
                    "response_reason": opportunity.reason,
                    "response_deadline_at_ms": opportunity.deadline_at_ms,
                    "response_observed_latency_ms": opportunity.observed_latency_ms,
                    "user_interrupted_assistant": interrupted is not None and _expects_assistant_response(user),
                    "yield_outcome": yield_outcome,
                    "yield_latency_ms": yield_latency_ms,
                    "agent_interrupted_user": bool(agent_interruptions),
                    "agent_interruption_count": len(agent_interruptions),
                    "agent_interruption_starts_ms": agent_interruptions,
                    "backchannel_outcome": backchannel_outcome,
                },
                "simulator": dict((simulator_timings or {}).get(timing_key, {})),
            }
        )
    return records


def extract_interaction_events(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Explain aggregate voice metrics using observed speech boundaries only."""

    events: list[dict[str, Any]] = []
    for turn in turns:
        audio = turn.get("audio", {})
        start_ms = int(turn["start_ms"])
        end_ms = int(turn["end_ms"])
        if audio.get("response_outcome") == "responded":
            latency_ms = int(audio["response_latency_ms"])
            events.append(
                {
                    "type": "response",
                    "caller_end_ms": end_ms,
                    "assistant_start_ms": end_ms + latency_ms,
                    "latency_ms": latency_ms,
                }
            )
        elif audio.get("response_outcome") == "no_response":
            events.append({"type": "no_response", "caller_end_ms": end_ms})
            if audio.get("response_observed_latency_ms") is not None:
                latency_ms = int(audio["response_observed_latency_ms"])
                events.append(
                    {
                        "type": "late_response",
                        "caller_end_ms": end_ms,
                        "assistant_start_ms": end_ms + latency_ms,
                        "latency_ms": latency_ms,
                        "deadline_at_ms": int(audio["response_deadline_at_ms"]),
                    }
                )

        if audio.get("yield_outcome") == "yielded":
            latency_ms = int(audio["yield_latency_ms"])
            events.append(
                {
                    "type": "yield",
                    "caller_interruption_ms": start_ms,
                    "assistant_stop_ms": start_ms + latency_ms,
                    "latency_ms": latency_ms,
                }
            )
        elif audio.get("yield_outcome") == "no_yield":
            events.append({"type": "no_yield", "caller_interruption_ms": start_ms})

        if audio.get("backchannel_outcome") in {"continued", "false_yield"}:
            events.append(
                {
                    "type": "backchannel_correct"
                    if audio["backchannel_outcome"] == "continued"
                    else "backchannel_error",
                    "caller_start_ms": start_ms,
                    "caller_end_ms": end_ms,
                }
            )

        for assistant_start_ms in audio.get("agent_interruption_starts_ms", []):
            events.append(
                {
                    "type": "agent_interruption",
                    "caller_start_ms": start_ms,
                    "caller_end_ms": end_ms,
                    "assistant_start_ms": assistant_start_ms,
                }
            )

    return events


def _floor_hold_intervals(ticks: list[TickRecord], timeline: Timeline | None) -> tuple[list[list[int]], str]:
    """Intersect exact delegated work with the complement of both voiced tracks."""
    duration_ms = int(ticks[-1]["end_ms"]) if ticks else 0
    if timeline is not None and (timeline.agent_events or timeline.tool_events or timeline.delegations):
        active = timeline.delegation_intervals(duration_ms)
        source = "lifecycle_events"
    elif all("delegation_intervals_ms" in tick.get("interaction", {}) for tick in ticks):
        active = tuple(
            (int(left), int(right)) for tick in ticks for left, right in tick["interaction"]["delegation_intervals_ms"]
        )
        source = "exact_tick_intervals"
    else:
        # Historical artifacts only have a boolean. Preserve that approximation
        # visibly; missing lifecycle timestamps cannot be recovered from a bin.
        active = tuple(
            (int(tick["start_ms"]), int(tick["end_ms"]))
            for tick in ticks
            if tick.get("interaction", {}).get("delegation_active")
        )
        source = "legacy_tick_projection"

    speech = tuple(
        (int(left), int(right))
        for tick in ticks
        for role in ("user", "assistant")
        for left, right in tick[role]["speech_intervals_ms"]
    )
    silent: list[tuple[int, int]] = []
    for start_ms, end_ms in _clip(active, 0, duration_ms):
        cursor_ms = start_ms
        for left, right in _clip(speech, start_ms, end_ms):
            if cursor_ms < left:
                silent.append((cursor_ms, left))
            cursor_ms = max(cursor_ms, right)
        if cursor_ms < end_ms:
            silent.append((cursor_ms, end_ms))
    return _merge_intervals(tuple(silent)), source


def compute_interaction_metrics(
    ticks: list[TickRecord],
    *,
    tick_ms: int,
    timeline: Timeline | None = None,
    yield_window_ms: int = 2_000,
    backchannel_window_ms: int = 1_000,
    response_deadline_ms: int = DEFAULT_RESPONSE_DEADLINE_MS,
) -> dict[str, Any]:
    """Compute versioned interaction metrics from actual shared-timeline speech."""
    users = _caller_segments(ticks, timeline)
    assistants = _segments(ticks, "assistant")
    opportunities = _response_opportunities(
        users,
        assistants,
        conversation_end_ms=int(ticks[-1]["end_ms"]) if ticks else 0,
        response_deadline_ms=response_deadline_ms,
    )
    response_latencies_ms = [
        item.observed_latency_ms
        for item in opportunities
        if item.status == "answered" and item.observed_latency_ms is not None
    ]
    late_response_latencies_ms = [
        item.observed_latency_ms
        for item in opportunities
        if item.status == "missed" and item.observed_latency_ms is not None
    ]
    no_response_count = sum(item.status == "missed" for item in opportunities)
    censored_count = sum(item.status == "censored" for item in opportunities)
    exclusion_reasons: dict[str, int] = {}
    for item in opportunities:
        if item.status == "excluded":
            exclusion_reasons[item.reason] = exclusion_reasons.get(item.reason, 0) + 1
    excluded_count = sum(exclusion_reasons.values())

    yield_latencies_ms: list[int] = []
    no_yield_count = 0
    backchannel_correct = 0
    backchannel_error = 0
    for user in users:
        if user.action == "STOP":
            continue
        interrupted = _interrupted_assistant(user, assistants)
        if interrupted is None:
            continue
        stop_delay_ms = interrupted.end_ms - user.start_ms
        if user.action == "BACKCHANNEL":
            outcome = _backchannel_outcome(
                user,
                interrupted,
                backchannel_window_ms=backchannel_window_ms,
            )
            if outcome == "false_yield":
                backchannel_error += 1
            else:
                backchannel_correct += 1
        elif stop_delay_ms <= yield_window_ms:
            yield_latencies_ms.append(stop_delay_ms)
        else:
            no_yield_count += 1

    response_count = len(response_latencies_ms)
    response_total = response_count + no_response_count
    yield_count = len(yield_latencies_ms)
    yield_total = yield_count + no_yield_count
    caller_audio = tuple((segment.start_ms, segment.end_ms) for segment in _segments(ticks, "user"))
    agent_interrupts_count = len(
        {start_ms for user in users for start_ms in _agent_interruptions(user, assistants, caller_audio)}
    )
    backchannel_total = backchannel_correct + backchannel_error

    floor_hold_episodes_ms, delegation_timing_source = _floor_hold_intervals(ticks, timeline)

    return {
        "metrics_version": METRICS_VERSION,
        "response_rate": _rate(response_count, response_total),
        "response_latency_ms": round(sum(response_latencies_ms) / response_count, 3) if response_count else None,
        "response_latency_mean": _mean_seconds(response_latencies_ms),
        "yield_latency_mean": _mean_seconds(yield_latencies_ms),
        "yield_rate": _rate(yield_count, yield_total),
        "interruption_rate": _rate(agent_interrupts_count, response_total),
        "speaking_duration_ms": _speaking_duration(assistants, timeline),
        "floor_hold_silence_ms": {
            "cumulative": sum(end_ms - start_ms for start_ms, end_ms in floor_hold_episodes_ms),
            "maximum": max((end_ms - start_ms for start_ms, end_ms in floor_hold_episodes_ms), default=0),
        },
        "floor_hold_intervals_ms": floor_hold_episodes_ms,
        "delegation_timing_source": delegation_timing_source,
        "selectivity_backchannel": _rate(backchannel_correct, backchannel_total),
        "selectivity_vocal_tic": None,
        "selectivity_non_directed": None,
        "response_latencies_ms": response_latencies_ms,
        "late_response_latencies_ms": late_response_latencies_ms,
        "response_exclusion_reasons": exclusion_reasons,
        "yield_latencies_ms": yield_latencies_ms,
        "counts": {
            "caller_turn_count": len(opportunities),
            "response_eligible_count": len(opportunities) - excluded_count,
            "response_censored_count": censored_count,
            "response_excluded_count": excluded_count,
            "response_late_count": len(late_response_latencies_ms),
            "response_total": response_total,
            "response_count": response_count,
            "no_response_count": no_response_count,
            "yield_total": yield_total,
            "yield_count": yield_count,
            "no_yield_count": no_yield_count,
            "backchannel_total": backchannel_total,
            "backchannel_correct_count": backchannel_correct,
            "backchannel_error_count": backchannel_error,
            "agent_interrupts_count": agent_interrupts_count,
            "vocal_tic_total": 0,
            "non_directed_total": 0,
        },
        "config": {
            "tick_ms": tick_ms,
            "yield_window_ms": yield_window_ms,
            "backchannel_window_ms": backchannel_window_ms,
            "response_deadline_ms": response_deadline_ms,
        },
    }
