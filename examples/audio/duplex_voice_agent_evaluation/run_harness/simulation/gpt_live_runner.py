"""Turnless dual-GPT Live runtime with frame-paced relay and post-hoc metrics."""

from __future__ import annotations

import asyncio
import copy
import json
import re
import time
import uuid
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from assistants.errors import LiveResponseError
from assistants.frontend.events import LimitedQueue
from assistants.frontend.transport import unwrap_response_event
from assistants.runtime import ToolExecutor
from run_harness.simulation.gpt_live_participants import SimulatorControlTools, VoiceParticipant
from run_harness.simulation.semantic_completion import SemanticCompletionDecision, SemanticCompletionObserver
from run_harness.simulation.validity import caller_simulation_validity
from shared.audio.conversation import ConversationRecorder, LiveMonitor, TimestampedAudioBuffer
from shared.audio.effects import AudioRealism, AudioRealismProcessor
from shared.audio.pacing import AudioPacer
from shared.audio.pcm import decode_audio, speech_intervals_pcm16
from shared.grading.scoring import EvalResult, build_result
from shared.metrics.interaction import (
    DEFAULT_RESPONSE_DEADLINE_MS,
    METRICS_VERSION,
    build_ticks,
    compute_interaction_metrics,
    compute_turn_interaction_metrics,
    extract_interaction_events,
    write_ticks,
)
from shared.observability.delegation import DelegationState, lifecycle_event
from shared.observability.timeline import Timeline, project_agent_event
from shared.observability.trace import record_event
from shared.private_files import private_open
from shared.reporting.results import write_json
from shared.scenarios import AudioCondition, Scenario

ASSISTANT_OPENING_TIMEOUT_SECONDS = 20.0
CALLER_OPENING_TIMEOUT_SECONDS = 20.0
COMPLETION_MIN_INTERVAL_MS = 500
COMPLETION_IDLE_RECHECK_MS = 5_000
LIVE_OUTPUT_BUFFER_MS = 400
LIVE_OUTPUT_SILENCE_MS = 100
QUIET_CAPTION_RMS_THRESHOLD = 110


class DualGptLiveRunner:
    """Continuously cross-feed two independently speaking GPT Live participants."""

    def __init__(
        self,
        scenario: Scenario,
        *,
        caller: VoiceParticipant,
        assistant: VoiceParticipant,
        caller_tools: SimulatorControlTools,
        application_tools: ToolExecutor,
        tick_ms: int = 200,
        response_deadline_ms: int = DEFAULT_RESPONSE_DEADLINE_MS,
        sample_rate: int = 24_000,
        speech_rms_threshold: float = 220,
        max_duration_s: float = 90,
        drain_ms: int = 1_500,
        real_time: bool = True,
        verbose: bool = False,
        save_conversations: Path | None = None,
        event_log_path: Path | None = None,
        debug_artifacts: bool = False,
        offline: bool = False,
        condition: AudioCondition = "clean",
        audio_realism: AudioRealism | None = None,
        seed: int = 7,
        listen: bool = False,
        assistant_backend_model: str | None = None,
        simulator_backend_model: str | None = None,
        simulator_backend_reasoning_effort: str | None = None,
        caller_voice: str | None = None,
        agent_voice: str | None = None,
        assistant_opening_prompt: str | None = None,
        completion_observer: SemanticCompletionObserver | None = None,
        final_audio_quiet_ms: int = 600,
    ) -> None:
        if tick_ms <= 0 or sample_rate <= 0:
            raise ValueError("tick_ms and sample_rate must be positive")
        if (
            isinstance(response_deadline_ms, bool)
            or not isinstance(response_deadline_ms, int)
            or response_deadline_ms <= 0
        ):
            raise ValueError("response_deadline_ms must be a positive integer")
        self.scenario = scenario
        self.caller = caller
        self.assistant = assistant
        self.caller_tools = caller_tools
        self.application_tools = application_tools
        self.initial_application_state = application_tools.snapshot()
        self.tick_ms = tick_ms
        self.response_deadline_ms = response_deadline_ms
        self.sample_rate = sample_rate
        self.speech_rms_threshold = speech_rms_threshold
        self.max_duration_s = max_duration_s
        self.drain_ms = drain_ms
        self.real_time = real_time
        self.verbose = verbose
        self.save_conversations = save_conversations
        self.event_log_path = event_log_path
        self.debug_artifacts = debug_artifacts
        self.offline = offline
        self.condition = condition
        self.seed = seed
        self.assistant_backend_model = assistant_backend_model
        self.simulator_backend_model = simulator_backend_model
        self.simulator_backend_reasoning_effort = simulator_backend_reasoning_effort
        self.caller_voice = caller_voice
        self.agent_voice = agent_voice
        self.assistant_opening_prompt = assistant_opening_prompt
        self.completion_observer = completion_observer
        self.final_audio_quiet_ms = final_audio_quiet_ms
        self.audio_processor = AudioRealismProcessor(condition, seed, audio_realism)
        self.monitor = LiveMonitor(sample_rate) if listen else None
        self.timeline = Timeline()
        self._quiet_caption_intervals: dict[str, list[tuple[int, int]]] = {"caller": [], "assistant": []}
        self.recorder = ConversationRecorder(sample_rate)
        self.events: LimitedQueue[tuple[str, dict[str, Any]]] = LimitedQueue()
        self.audio = {"caller": bytearray(), "assistant": bytearray()}
        self.output_audio_clocks = {
            "caller": TimestampedAudioBuffer(sample_rate),
            "assistant": TimestampedAudioBuffer(sample_rate),
        }
        self._output_timestamp_origins: dict[str, tuple[int, int] | None] = {"caller": None, "assistant": None}
        self.received_audio_bytes = {"caller": 0, "assistant": 0}
        self.consumed_audio_bytes = {"caller": 0, "assistant": 0}
        self.relayed_silence_samples = {"caller": 0, "assistant": 0}
        self._relay_underflow_samples = {"caller": 0, "assistant": 0}
        self._audio_buffer_deadline: dict[str, int | None] = {"caller": None, "assistant": None}
        self._receipt_audio_frontier = {"caller": 0, "assistant": 0}
        self._pending_audio_captions: dict[str, deque[tuple[int, dict[str, Any], int, int]]] = {
            "caller": deque(),
            "assistant": deque(),
        }
        self._relay_max_buffered_bytes = {"caller": 0, "assistant": 0}
        self._relay_max_send_ms = {"caller": 0.0, "assistant": 0.0}
        self._relay_packets = 0
        self._relay_max_queue_delay_ms = 0.0
        self.caller_actions: Counter[str] = Counter()
        self.caller_usage: list[dict[str, Any]] = []
        self.participant_events: list[dict[str, Any]] = []
        self._caller_work_state = DelegationState()
        self.failure: LiveResponseError | None = None
        self.started = 0.0
        self.input_ms = 0
        self.run_id = uuid.uuid4().hex
        self.event_log: TextIO | None = None
        self.event_index = {"value": 0}
        self._pumps: list[asyncio.Task[None]] = []
        self._completion_task: asyncio.Task[SemanticCompletionDecision] | None = None
        self._completion_signature = ""
        self._completion_revision = 0
        self._completion_work_revision = 0
        self._completion_requested_revision = 0
        self._completion_requested_speech_ms = -1
        self._completion_requested_assistant_speech_ms = -1
        self._completion_next_allowed_ms = 0.0
        self._completion_idle_recheck_ms = 0.0
        self._completion_fallback_reason = ""
        self._finish_observed_ms: int | None = None
        self._conversation_finished = False
        self._drain_revision = 0
        self._drain_caller_speech_ms = -1
        self._consumed_finish_executions = 0
        self.completion_signal = ""
        self.started_at = ""
        self._shutting_down = False
        self._finalized: set[str] = set()
        self._caller_usage_response_ids: set[str] = set()
        self._projected_caller_actions: dict[str, str] = {}

    def log(self, text: str) -> None:
        if self.verbose:
            print(f"{(time.monotonic() - self.started):7.3f}s  {text}", flush=True)

    def trace(self, event: dict[str, Any], *, source: str, direction: str) -> None:
        if self.event_log is not None:
            record_event(
                self.event_log,
                event,
                started_at=self.started,
                event_index_state=self.event_index,
                source=source,
                direction=direction,
            )

    async def _pump(self, label: str, participant: VoiceParticipant) -> None:
        try:
            async for event in participant.incoming():
                event = unwrap_response_event(event)
                # Receipt and media position are different clocks. In particular,
                # startup and a stalled send advance wall time without advancing PCM.
                received = {
                    **event,
                    "_relay_receipt": {
                        "monotonic_elapsed_ms": round((time.monotonic() - self.started) * 1_000, 3),
                        "media_ms": self.input_ms,
                    },
                }
                await self.events.put((label, received))
        except asyncio.CancelledError:
            raise
        except asyncio.QueueFull:
            self.failure = LiveResponseError(
                f"{label} GPT Live event buffer capacity exceeded (event_queue_overflow)",
                failure_stage=f"{label}_connection",
            )
        except Exception as exc:  # noqa: BLE001 - convert participant failures at the runtime boundary.
            self.failure = LiveResponseError(
                f"{label} GPT Live connection failed: {type(exc).__name__}: {exc}",
                failure_stage=f"{label}_connection",
            )

    async def _start_participants(self) -> None:
        """Start both sessions and retain the participant responsible for startup failures."""
        outcomes = await asyncio.gather(self.caller.start(), self.assistant.start(), return_exceptions=True)
        for label, outcome in zip(("caller", "assistant"), outcomes, strict=True):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if isinstance(outcome, Exception):
                raise LiveResponseError(
                    f"{label} GPT Live connection failed to start: {type(outcome).__name__}: {outcome}",
                    failure_stage=f"{label}_connection",
                ) from outcome

    async def _send_participant_audio(self, label: str, participant: VoiceParticipant, pcm: bytes) -> None:
        """Attribute a broken relay stream to the participant that rejected audio."""
        started = time.monotonic()
        try:
            await participant.send_audio(pcm)
        except Exception as exc:  # noqa: BLE001 - expose participant-specific transport failures.
            raise LiveResponseError(
                f"{label} GPT Live audio stream failed: {type(exc).__name__}: {exc}",
                failure_stage=f"{label}_connection",
            ) from exc
        finally:
            elapsed_ms = (time.monotonic() - started) * 1_000
            self._relay_max_send_ms[label] = max(self._relay_max_send_ms[label], round(elapsed_ms, 3))

    def _record_usage(self, label: str, event: dict[str, Any]) -> None:
        usage: dict[str, Any] | None = None
        if event.get("type") == "response.completed":
            identifier = str(event.get("response", {}).get("id") or "")
            if label == "caller" and identifier in self._caller_usage_response_ids:
                return
            self._caller_usage_response_ids.add(identifier)
            candidate = event.get("response", {}).get("usage")
            usage = candidate if isinstance(candidate, dict) else None
        elif event.get("type") in {"session.usage.updated", "session.closed"}:
            candidate = event.get("usage")
            usage = candidate if isinstance(candidate, dict) else None
        if usage and label == "caller":
            self.caller_usage.append({"source": "caller_gpt_live", **usage})

    def _project_assistant_event(self, event: dict[str, Any]) -> None:
        receipt = event.get("_relay_receipt", {})
        self.timeline.apply_event(project_agent_event(event, int(receipt.get("media_ms", self.input_ms))))
        if event.get("type") in {
            "session.delegation.created",
            "client_delegation.completed",
            "client_delegation.failed",
            "response.created",
            "response.completed",
            "response.failed",
            "tool.called",
            "tool.completed",
            "tool.failed",
        }:
            self._completion_work_revision += 1

    def _project_caller_event(self, event: dict[str, Any]) -> None:
        """Retain caller reasoning without treating it as target-assistant work."""
        receipt = event.get("_relay_receipt", {})
        media_ms = int(receipt.get("media_ms", self.input_ms))
        self.participant_events.append({"timeline_ms": media_ms, "participant": "caller", **event})
        if not self.simulator_backend_model:
            return
        # The tool-free caller cannot continue an incomplete backend response.
        # Close its pending state, while retaining the original event for validity.
        terminal = {**event, "type": "response.failed"} if event.get("type") == "response.incomplete" else event
        normalized = lifecycle_event(terminal, media_ms)
        if normalized is not None:
            self._caller_work_state.apply(normalized)
            self._completion_work_revision += 1

    def _output_audio_layout(self, label: str, sample_count: int, start_ms: int | None) -> tuple[int, int]:
        """Preflight novel PCM and padding without allocating provider-sized gaps."""
        clock = self.output_audio_clocks[label]
        origin = self._output_timestamp_origins[label]
        target_sample = clock.sample_count
        if start_ms is not None and origin is not None:
            origin_ms, origin_sample = origin
            target_sample = max(0, origin_sample + (start_ms - origin_ms) * self.sample_rate // 1_000)
        gap_samples = max(0, target_sample - clock.sample_count)
        overlapping_samples = min(sample_count, max(0, clock.sample_count - target_sample))
        already_relayed_samples = min(gap_samples, self.relayed_silence_samples[label])
        required_bytes = (gap_samples - already_relayed_samples + sample_count - overlapping_samples) * 2
        return required_bytes, already_relayed_samples

    def _buffer_output_audio(self, label: str, event: dict[str, Any]) -> bool:
        pcm = decode_audio(event)
        clock = self.output_audio_clocks[label]
        if len(pcm) % 2:
            raise ValueError("timestamped audio must contain complete PCM16 samples")
        if not pcm:
            clock.gap_samples = 0
            return True
        raw_start_ms = event.get("start_ms", event.get("offset_ms"))
        start_ms = raw_start_ms if isinstance(raw_start_ms, int) else None
        required_bytes, already_relayed_samples = self._output_audio_layout(label, len(pcm) // 2, start_ms)
        if len(self.audio[label]) + required_bytes > self.events.max_bytes:
            # Emptying the bounded event queue must not transfer an unbounded
            # backlog into decoded PCM. Check before append allocates gap padding.
            self.failure = LiveResponseError(
                f"{label} GPT Live decoded audio buffer capacity exceeded (audio_queue_overflow)",
                failure_stage=f"{label}_connection",
            )
            return False
        if start_ms is not None and self._output_timestamp_origins[label] is None:
            self._output_timestamp_origins[label] = (start_ms, clock.sample_count)
        # The receiver's source clock still advances over silence already sent
        # during underflow, but allocating and then slicing that padding is wasteful
        # and could exceed the budget even when the remaining queue fits.
        clock.sample_count += already_relayed_samples
        aligned_pcm = clock.append(pcm, start_ms=start_ms)
        clock.gap_samples += already_relayed_samples
        if aligned_pcm:
            self.relayed_silence_samples[label] = 0
        self.audio[label].extend(aligned_pcm)
        self.received_audio_bytes[label] += len(aligned_pcm)
        self._relay_max_buffered_bytes[label] = max(self._relay_max_buffered_bytes[label], len(self.audio[label]))
        return True

    async def _drain_events(self) -> None:
        while True:
            try:
                label, event = self.events.get_nowait()
            except asyncio.QueueEmpty:
                break
            kind = str(event.get("type", "unknown"))
            receipt = event.get("_relay_receipt", {})
            trace_event = dict(event)
            if "monotonic_elapsed_ms" in receipt:
                trace_event["_relay_queue_delay_ms"] = round(
                    (time.monotonic() - self.started) * 1_000 - receipt["monotonic_elapsed_ms"], 3
                )
                self._relay_max_queue_delay_ms = max(
                    self._relay_max_queue_delay_ms, trace_event["_relay_queue_delay_ms"]
                )
            self.trace(trace_event, source=f"{label}_gpt_live", direction="server_to_relay")
            self._record_usage(label, event)
            if kind == "session.closed" and not event.get("_synthetic"):
                seconds = event.get("usage", {}).get("seconds")
                if isinstance(seconds, (int, float)) and seconds >= 0:
                    self._finalized.add(label)
            if kind == "session.output_audio.delta":
                if not self._buffer_output_audio(label, event):
                    return
            elif kind == "session.output_transcript.delta":
                self._record_output_transcript(label, event)
            elif kind == "session.input_transcript.delta":
                continue  # The peer's own output transcript is the shared conversation source.
            elif label == "assistant":
                self._project_assistant_event(event)
            else:
                self._project_caller_event(event)
            if kind == "error":
                details = event.get("error", {})
                message = details.get("message", "unknown provider error") if isinstance(details, dict) else details
                self.failure = LiveResponseError(
                    f"{label} GPT Live returned an error: {message}", failure_stage=f"{label}_connection"
                )
            elif kind == "session.closed" and not self._conversation_finished and not self._shutting_down:
                self.failure = LiveResponseError(
                    f"{label} GPT Live session closed before the conversation completed",
                    failure_stage=f"{label}_connection",
                )

    def _record_output_transcript(self, label: str, event: dict[str, Any]) -> None:
        role = "user" if label == "caller" else "assistant"
        self.timeline.add_transcript(role, event["start_ms"], event["end_ms"], event["delta"], event["type"])
        frontier = self._receipt_audio_frontier[label]
        boundary = self.received_audio_bytes[label]
        if (
            not self.offline
            and self._output_timestamp_origins[label] is None
            and frontier > self.consumed_audio_bytes[label]
        ):
            # Retain receipt provenance above; move only the projector's local
            # observation cutoff to when this same source position is played.
            self._pending_audio_captions[label].append((frontier, event, self.input_ms, boundary))
        else:
            self.timeline.transcript_projection.record(role, event, received_ms=self.input_ms, boundary=boundary)

    def _pop_audio(self, label: str, size: int) -> bytes:
        # Source position the immediate relay would have reached at receipt.
        # A counter suffices: no second PCM queue or provider timestamp is needed.
        self._receipt_audio_frontier[label] += min(
            size, self.received_audio_bytes[label] - self._receipt_audio_frontier[label]
        )
        before = self.consumed_audio_bytes[label]
        self._relay_max_buffered_bytes[label] = max(self._relay_max_buffered_bytes[label], len(self.audio[label]))
        available = min(size, len(self.audio[label]))
        if not self.offline and self._output_timestamp_origins[label] is None:
            # Each hold is bounded; repeated refills can add more total latency.
            reserve = self.sample_rate * LIVE_OUTPUT_BUFFER_MS // 1_000 * 2
            quiet = max(size, self.sample_rate * LIVE_OUTPUT_SILENCE_MS // 1_000 * 2)
            may_wait = self.consumed_audio_bytes[label] == 0 or (
                len(self.audio[label]) >= quiet and not any(self.audio[label][:quiet])
            )
            if self.audio[label] and may_wait and len(self.audio[label]) < reserve + size:
                if self._audio_buffer_deadline[label] is None:
                    self._audio_buffer_deadline[label] = self.input_ms + LIVE_OUTPUT_BUFFER_MS
                if self.input_ms < self._audio_buffer_deadline[label]:
                    available = 0
                # Do not rearm an expired wait until this quiet stretch ends:
                # finite tails must drain so captions reach their byte boundary.
            else:
                self._audio_buffer_deadline[label] = None
        pcm = bytes(self.audio[label][:available])
        del self.audio[label][:available]
        self.consumed_audio_bytes[label] += available
        self.relayed_silence_samples[label] += (size - available) // 2
        self._relay_underflow_samples[label] += (size - available) // 2
        pending = self._pending_audio_captions[label]
        while pending and pending[0][0] <= self.consumed_audio_bytes[label]:
            frontier, event, received_ms, boundary = pending.popleft()
            playout_ms = self.input_ms + max(0, frontier - before) * 1_000 // (self.sample_rate * 2)
            self.timeline.transcript_projection.record(
                "user" if label == "caller" else "assistant",
                event,
                received_ms=max(received_ms, playout_ms),
                boundary=boundary,
            )
        return pcm + bytes(size - available)

    @staticmethod
    def _contains_expected(actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(
                key in actual and DualGptLiveRunner._contains_expected(actual[key], value)
                for key, value in expected.items()
            )
        if isinstance(expected, list):
            return isinstance(actual, list) and all(
                any(DualGptLiveRunner._contains_expected(item, value) for item in actual) for value in expected
            )
        return actual == expected

    def _verified_outcome(self) -> bool:
        expected = self.scenario.expected.state
        observed = self.application_tools.snapshot()
        if expected == {"unchanged": True}:
            return observed == self.initial_application_state
        return bool(expected) and self._contains_expected(observed, expected)

    @staticmethod
    def _looks_like_closing(text: str) -> bool:
        lowered = text.casefold()
        return any(term in lowered for term in ("bye", "goodbye", "thank you", "thanks"))

    def _caller_closed(self) -> bool:
        return bool(
            self.timeline.user_utterances
            and self._looks_like_closing(self.timeline.user_utterances[-1].text)
            and self._verified_outcome()
        )

    @staticmethod
    def _normalized_utterance(text: str) -> str:
        return re.sub(r"[^\w\s]", "", text.casefold()).strip()

    def _caller_action(self, text: str, start_ms: int, end_ms: int, explicit: str = "") -> str:
        """Infer caller intent only when an uncontrolled Live participant overlaps speech."""

        if explicit in {"OPENING", "STOP", "BACKCHANNEL", "INTERRUPT"}:
            return explicit
        if self.caller_actions["OPENING"] == 0:
            return "OPENING"
        if self.completion_observer is None and self._verified_outcome() and self._looks_like_closing(text):
            return "STOP"
        overlaps_assistant = any(
            max(start_ms, assistant_start) < min(end_ms, assistant_end)
            for assistant_start, assistant_end in self.timeline.speech_intervals("assistant")
        )
        if not overlaps_assistant:
            return "SPEAK"
        acknowledgements = {
            self._normalized_utterance(item)
            for item in (*self.scenario.persona.backchannels, "mm-hmm", "mhm", "uh-huh", "right", "okay", "got it")
        }
        return "BACKCHANNEL" if self._normalized_utterance(text) in acknowledgements else "INTERRUPT"

    def _record_quiet_caption_audio(self, label: str, pcm: bytes, start_ms: int) -> None:
        intervals = self._quiet_caption_intervals[label]
        for left, right in speech_intervals_pcm16(pcm, start_ms, self.sample_rate, QUIET_CAPTION_RMS_THRESHOLD):
            if intervals and intervals[-1][1] == left:
                intervals[-1] = (intervals[-1][0], right)
            else:
                intervals.append((left, right))

    def _project_completed_turns(self, label: str) -> None:
        role = "user" if label == "caller" else "assistant"
        turns = self.timeline.transcript_projection.project(
            role,
            self.timeline.speech_intervals(role),
            now_ms=self.input_ms,
            consumed=self.consumed_audio_bytes[label],
            quiet_ms=self.final_audio_quiet_ms,
            quiet_intervals=tuple(self._quiet_caption_intervals[label]),
        )
        for turn in turns:
            if not self.timeline.add_turn(turn):
                continue
            if role == "user":
                action = self._caller_action(turn.transcript, turn.start_ms, turn.end_ms)
                old_action = self._projected_caller_actions.get(turn.turn_id)
                if old_action:
                    self.caller_actions[old_action] -= 1
                self._projected_caller_actions[turn.turn_id] = action
                self.caller_actions[action] += 1
                self.timeline.add_user_utterance(
                    turn.start_ms,
                    turn.end_ms,
                    turn.transcript,
                    source="caller_gpt_live",
                    action=action,
                    turn_id=turn.turn_id,
                )
            self.trace(
                {
                    "type": "evaluation.turn.projected",
                    "role": role,
                    "id": turn.turn_id,
                    "start_ms": turn.start_ms,
                    "end_ms": turn.end_ms,
                    "text": turn.transcript,
                    "attribution": "local_audio_and_transcript",
                },
                source=f"{label}_gpt_live",
                direction="internal",
            )
            self.log(f"{role.upper()} {turn.start_ms}..{turn.end_ms}ms: {turn.transcript}")

    def _completion_evidence(self) -> tuple[int, dict[str, Any]]:
        evidence = {
            "turns": list(self.timeline.turns),
            "initial_state": copy.deepcopy(self.initial_application_state),
            "observed_state": self.application_tools.snapshot(),
            "state_verified": self._verified_outcome(),
            "tool_executions": copy.deepcopy(self.application_tools.executions),
            "assistant_work_pending": self.timeline.delegation_active,
        }
        # Timeline.version includes streaming response deltas. Only evidence the
        # observer can use (plus work transitions) should invalidate an assessment.
        signature = json.dumps(
            {
                **evidence,
                "turns": [
                    (turn.role, turn.start_ms, turn.end_ms, turn.transcript, turn.turn_id) for turn in evidence["turns"]
                ],
                "work_revision": self._completion_work_revision,
                "caller_work_pending": self._caller_work_state.active,
            },
            sort_keys=True,
            default=str,
        )
        if signature != self._completion_signature:
            self._completion_signature = signature
            self._completion_revision += 1
        return self._completion_revision, evidence

    def _buffered_speech(self, label: str) -> bool:
        return bool(
            speech_intervals_pcm16(bytes(self.audio[label]), self.input_ms, self.sample_rate, self.speech_rms_threshold)
        )

    def _caller_evidence_current(self) -> bool:
        # New audio can precede its transcript by seconds. An old goodbye is not a
        # current decision while that untranscribed caller speech is outstanding.
        return (
            self.timeline.last_user_speech_ms <= self.timeline.last_user_text_ms
            and not self.timeline.transcript_projection.pending("user")
            and not self._pending_audio_captions["caller"]
            and not self._buffered_speech("caller")
            and not self._caller_work_state.active
        )

    def _conversation_evidence_current(self) -> bool:
        latest_assistant = self.timeline.latest_turn("assistant")
        finalized_assistant_ms = latest_assistant.end_ms if latest_assistant is not None else -1
        # Quiet audio is not finalized semantic evidence: either participant's
        # correction can finish speaking long before its transcript arrives.
        return (
            self._caller_evidence_current()
            and self.timeline.last_assistant_speech_ms <= finalized_assistant_ms
            and not self.timeline.transcript_projection.pending("assistant")
            and not self._pending_audio_captions["assistant"]
            and not self._buffered_speech("assistant")
        )

    def _completed_semantic_decision(
        self, observer: SemanticCompletionObserver, revision: int, evidence: dict[str, Any]
    ) -> SemanticCompletionDecision | None:
        if self._completion_task is None or not self._completion_task.done():
            return None
        task = self._completion_task
        self._completion_task = None
        try:
            decision = task.result()
        except Exception as exc:  # noqa: BLE001 - observer outages must not kill a valid voice session.
            self._completion_fallback_reason = f"{type(exc).__name__}: {exc}"
            self.trace(
                {
                    "type": "simulator.completion.observer_failed",
                    "timeline_ms": self.input_ms,
                    "model": observer.model,
                    "reason": self._completion_fallback_reason,
                    "fallback": "verified_outcome_and_natural_closing",
                },
                source="semantic_completion_observer",
                direction="internal",
            )
            return None
        if (
            revision != self._completion_requested_revision
            or self.timeline.last_user_speech_ms != self._completion_requested_speech_ms
            or self.timeline.last_assistant_speech_ms != self._completion_requested_assistant_speech_ms
        ):
            self.trace(
                {
                    "type": "simulator.completion.stale",
                    "timeline_ms": self.input_ms,
                    "requested_revision": self._completion_requested_revision,
                    "current_revision": revision,
                    "should_drain": decision.should_drain,
                },
                source="semantic_completion_observer",
                direction="internal",
            )
            return None
        if decision.should_drain and (
            self.timeline.delegation_active
            or not self._conversation_evidence_current()
            or (decision.outcome == "resolved" and self.scenario.expected.state and not evidence["state_verified"])
        ):
            decision = decision.model_copy(
                update={
                    "should_drain": False,
                    "outcome": "unresolved",
                    "reason": "Caller evidence, pending work, or expected state is unresolved.",
                }
            )
        self.trace(
            {
                "type": "simulator.completion.assessed",
                "timeline_ms": self.input_ms,
                "model": observer.model,
                "revision": revision,
                **decision.model_dump(),
            },
            source="semantic_completion_observer",
            direction="internal",
        )
        return decision

    def _advance_semantic_completion(self) -> SemanticCompletionDecision | None:
        """Advance background observation without pausing the live relay."""
        observer = self.completion_observer
        if observer is None or self._completion_fallback_reason:
            return None
        revision, evidence = self._completion_evidence()
        decision = self._completed_semantic_decision(observer, revision, evidence)
        if decision is not None and decision.should_drain and decision.outcome != "unresolved":
            return decision
        if (
            self._completion_fallback_reason
            or self._completion_task is not None
            or len(self.timeline.user_utterances) < 2
        ):
            return None
        if self._finish_observed_ms is not None or not self._conversation_evidence_current():
            return None
        if not any(turn.role == "assistant" for turn in self.timeline.turns):
            return None
        now_ms = self.input_ms if self.offline else time.monotonic() * 1_000
        if now_ms < self._completion_next_allowed_ms:
            return None
        if revision == self._completion_requested_revision and now_ms < self._completion_idle_recheck_ms:
            return None
        self._completion_requested_revision = revision
        self._completion_requested_speech_ms = self.timeline.last_user_speech_ms
        self._completion_requested_assistant_speech_ms = self.timeline.last_assistant_speech_ms
        self._completion_next_allowed_ms = now_ms + COMPLETION_MIN_INTERVAL_MS
        self._completion_idle_recheck_ms = now_ms + COMPLETION_IDLE_RECHECK_MS
        self._completion_task = asyncio.create_task(
            observer.assess(self.scenario, **evidence),
            name=f"semantic-completion-{self.scenario.id}-{revision}",
        )
        return None

    def _assistant_drain_complete(self, finish_observed_ms: int) -> bool:
        """Retain both audio tails, late caller transcripts, and delegated work."""
        if self.input_ms < finish_observed_ms + self.drain_ms:
            return False
        if (
            any(self._buffered_speech(label) for label in ("caller", "assistant"))
            or self.timeline.delegation_active
            or self.timeline.last_user_speech_ms > finish_observed_ms
            or self.timeline.last_user_text_ms > finish_observed_ms
            or not self._conversation_evidence_current()
        ):
            return False
        return (
            self.input_ms
            >= max(self.timeline.last_assistant_speech_ms, self.timeline.last_user_speech_ms)
            + self.final_audio_quiet_ms
        )

    def _advance_completion_lifecycle(self) -> bool:
        revision, _ = self._completion_evidence()
        if self._finish_observed_ms is not None and (
            revision != self._drain_revision
            or self.timeline.last_user_speech_ms > self._drain_caller_speech_ms
            or not self._conversation_evidence_current()
        ):
            self.trace(
                {
                    "type": "simulator.completion.drain_revoked",
                    "timeline_ms": self.input_ms,
                    "previous_signal": self.completion_signal,
                    "previous_revision": self._drain_revision,
                    "current_revision": revision,
                },
                source="semantic_completion_observer",
                direction="internal",
            )
            self._finish_observed_ms = None
            self.completion_signal = ""
        decision = self._advance_semantic_completion()
        if self._finish_observed_ms is None:
            # finished is sticky. Consume an execution once, so a revoked drain
            # cannot immediately restart from the same now-obsolete finish call.
            finish_executions = sum(
                item.get("name") == "finish_conversation" and item.get("status") == "completed"
                for item in self.caller_tools.executions
            )
            if (
                finish_executions > self._consumed_finish_executions
                and self.caller_tools.finished
                and self._conversation_evidence_current()
            ):
                self._consumed_finish_executions = finish_executions
                self.completion_signal = "caller_finish_tool"
            elif decision is not None:
                self.completion_signal = f"semantic_conversation_{decision.outcome}"
            elif (
                (self.completion_observer is None or self._completion_fallback_reason)
                and self._caller_closed()
                and self._conversation_evidence_current()
            ):
                self.completion_signal = "verified_outcome_and_natural_closing"
            if self.completion_signal:
                self._finish_observed_ms = self.input_ms
                self._drain_revision = revision
                self._drain_caller_speech_ms = self.timeline.last_user_speech_ms
        if self._finish_observed_ms is None or not self._assistant_drain_complete(self._finish_observed_ms):
            return False
        # Completion is session-level evidence, not proof that the last caller
        # utterance needed no response. Preserve its original metric eligibility.
        self._conversation_finished = True
        return True

    def _trace_analysis_tick(self, start_ms: int, end_ms: int) -> None:
        intervals = {
            role: [
                (max(start_ms, start), min(end_ms, end))
                for start, end in self.timeline.speech_intervals(role)
                if start < end_ms and end > start_ms
            ]
            for role in ("user", "assistant")
        }
        self.trace(
            {
                "type": "dual_gpt_live.tick",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "caller_speech": bool(intervals["user"]),
                "assistant_speech": bool(intervals["assistant"]),
                "overlap_ms": sum(
                    max(0, min(a_end, b_end) - max(a_start, b_start))
                    for a_start, a_end in intervals["user"]
                    for b_start, b_end in intervals["assistant"]
                ),
            },
            source="dual_gpt_live_relay",
            direction="bidirectional",
        )

    async def run(self) -> EvalResult:
        self.started = time.monotonic()
        self.started_at = datetime.now(UTC).isoformat()
        initial_state = self.initial_application_state
        if self.event_log_path is not None:
            self.event_log = private_open(self.event_log_path)
        # Offline peers advance their fixture clock once per send. Live peers do
        # not: select their next PCM at each wire boundary, never a whole tick ahead.
        transport_frame_ms = self.tick_ms if self.offline else 20
        chunk_bytes = self.sample_rate * transport_frame_ms // 1_000 * 2
        analysis_start_ms = 0
        termination_reason = "duration_limit"
        caller_work_pending_at_end = False
        assistant_first = self.assistant_opening_prompt is not None
        assistant_opening_speech_observed = False
        caller_opening_speech_observed = False
        opening_deadline: float | None = None
        conversation_start_ms: int | None = None if assistant_first else 0
        try:
            if self.monitor is not None:
                self.monitor.start()
                self.log("LISTEN live stereo enabled: user=left, GPT Live=right")
            await self._start_participants()
            self._pumps = [
                asyncio.create_task(self._pump("caller", self.caller), name="dual-gpt-live-caller-receiver"),
                asyncio.create_task(self._pump("assistant", self.assistant), name="dual-gpt-live-assistant-receiver"),
            ]
            if assistant_first:
                try:
                    await self.assistant.append_context(self.assistant_opening_prompt or "")
                except Exception as exc:
                    raise LiveResponseError(
                        f"Assistant opening request failed: {type(exc).__name__}: {exc}",
                        failure_stage="assistant_opening",
                    ) from exc
                opening_deadline = time.monotonic() + ASSISTANT_OPENING_TIMEOUT_SECONDS
            else:
                try:
                    opening_event = await self.caller.trigger_opening(self.scenario.input.text)
                except Exception as exc:
                    raise LiveResponseError(
                        f"Caller opening request failed: {type(exc).__name__}: {exc}",
                        failure_stage="caller_opening",
                    ) from exc
                if opening_event:
                    self.trace(opening_event, source="caller_gpt_live", direction="relay_to_server")
                opening_deadline = time.monotonic() + CALLER_OPENING_TIMEOUT_SECONDS
            pacer = AudioPacer(transport_frame_ms) if self.real_time else None
            while conversation_start_ms is None or self.input_ms - conversation_start_ms < int(
                self.max_duration_s * 1_000
            ):
                opening_speech_observed = (
                    assistant_opening_speech_observed if assistant_first else caller_opening_speech_observed
                )
                if (
                    not opening_speech_observed
                    and opening_deadline is not None
                    and time.monotonic() >= opening_deadline
                ):
                    opening_speaker = "Assistant" if assistant_first else "Caller"
                    raise LiveResponseError(
                        f"{opening_speaker} opening timed out before speech was observed",
                        failure_stage=f"{opening_speaker.lower()}_opening",
                    )
                await asyncio.sleep(0)
                await self._drain_events()
                if self.failure is not None:
                    if assistant_first and not assistant_opening_speech_observed:
                        raise LiveResponseError(str(self.failure), failure_stage="assistant_opening")
                    raise self.failure
                raw_caller_pcm = self._pop_audio("caller", chunk_bytes)
                assistant_pcm = self._pop_audio("assistant", chunk_bytes)
                start_ms = self.input_ms
                end_ms = start_ms + transport_frame_ms
                source_intervals = speech_intervals_pcm16(
                    raw_caller_pcm, start_ms, self.sample_rate, self.speech_rms_threshold
                )
                caller_pcm = self.audio_processor.process(raw_caller_pcm, speech_active=bool(source_intervals))
                caller_intervals = speech_intervals_pcm16(
                    self.audio_processor.last_source_pcm,
                    start_ms,
                    self.sample_rate,
                    self.speech_rms_threshold,
                )
                assistant_intervals = speech_intervals_pcm16(
                    assistant_pcm, start_ms, self.sample_rate, self.speech_rms_threshold
                )
                # Caption recovery uses source audio, excluding the mixed noise
                # bed. These intervals never enter the acoustic metric detector.
                # last_source_pcm is already gated by the main speech threshold.
                if not self.audio_processor.last_packet_lost:
                    self._record_quiet_caption_audio("caller", raw_caller_pcm, start_ms)
                self._record_quiet_caption_audio("assistant", assistant_pcm, start_ms)
                if assistant_first and caller_intervals and not assistant_opening_speech_observed:
                    raise LiveResponseError(
                        "GPT Live caller spoke before the assistant opening",
                        failure_stage="assistant_opening",
                    )
                if assistant_first and assistant_intervals and not assistant_opening_speech_observed:
                    assistant_opening_speech_observed = True
                    conversation_start_ms = start_ms
                if not assistant_first and caller_intervals:
                    caller_opening_speech_observed = True
                self.timeline.add_audio(
                    "user", start_ms, end_ms, bool(caller_intervals), speech_intervals=caller_intervals
                )
                self.timeline.add_audio(
                    "assistant", start_ms, end_ms, bool(assistant_intervals), speech_intervals=assistant_intervals
                )
                self.recorder.add("user", start_ms, caller_pcm)
                self.recorder.add("assistant", start_ms, assistant_pcm)
                if self.monitor is not None:
                    self.monitor.push("user", caller_pcm, start_ms=start_ms)
                    self.monitor.push("assistant", assistant_pcm, start_ms=start_ms)
                if self.offline and (set_speech_activity := getattr(self.assistant, "set_speech_activity", None)):
                    set_speech_activity(bool(caller_intervals))
                await asyncio.gather(
                    self._send_participant_audio("assistant", self.assistant, caller_pcm),
                    self._send_participant_audio("caller", self.caller, assistant_pcm),
                )
                self._relay_packets += 1
                self.input_ms = end_ms
                if pacer is not None:
                    delay, lag_ms = pacer.next_delay()
                    if lag_ms is not None:
                        self.trace(
                            {
                                "type": "audio.pacing_lag",
                                "lag_ms": lag_ms,
                                "chunk_ms": transport_frame_ms,
                                "stream": "dual_gpt_live_relay",
                            },
                            source="dual_gpt_live_relay",
                            direction="internal",
                        )
                    await asyncio.sleep(delay)
                while analysis_start_ms + self.tick_ms <= end_ms:
                    self._trace_analysis_tick(analysis_start_ms, analysis_start_ms + self.tick_ms)
                    analysis_start_ms += self.tick_ms
                if self.audio_processor.last_packet_lost:
                    self.trace(
                        {"type": "audio.packet_loss", "start_ms": start_ms, "end_ms": end_ms},
                        source="caller_audio_realism",
                        direction="to_assistant",
                    )
                for acoustic in self.audio_processor.last_acoustic_events:
                    self.trace(
                        {
                            "type": "audio.distraction",
                            "kind": acoustic.kind,
                            "start_ms": acoustic.start_ms,
                            "end_ms": acoustic.end_ms,
                            "provenance": acoustic.provenance,
                        },
                        source="caller_audio_realism",
                        direction="to_assistant",
                    )
                await asyncio.sleep(0)
                await self._drain_events()
                if self.failure is not None:
                    raise self.failure
                self._project_completed_turns("caller")
                self._project_completed_turns("assistant")
                if self._advance_completion_lifecycle():
                    termination_reason = "response_completed"
                    break
            # A reply received during cleanup cannot rescue reasoning that did
            # not finish within the captured conversation.
            caller_work_pending_at_end = self._caller_work_state.active
            if not assistant_first and not caller_opening_speech_observed:
                raise LiveResponseError(
                    "Caller opening finished without producing speech",
                    failure_stage="caller_opening",
                )
            await asyncio.gather(self.caller.wait_for_tools(), self.assistant.wait_for_tools())
            await self._drain_events()
            self._project_completed_turns("caller")
            self._project_completed_turns("assistant")
            if analysis_start_ms < self.input_ms:
                self._trace_analysis_tick(analysis_start_ms, self.input_ms)
        finally:
            if self._completion_task is not None:
                self._completion_task.cancel()
                await asyncio.gather(self._completion_task, return_exceptions=True)
            self._shutting_down = True
            close_results = await asyncio.gather(self.caller.close(), self.assistant.close(), return_exceptions=True)
            if self._pumps:
                _, pending = await asyncio.wait(self._pumps, timeout=1.0)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*self._pumps, return_exceptions=True)
            await self._drain_events()
            if self.event_log is not None:
                self.event_log.close()
            if self.monitor is not None:
                self.monitor.close()

        ticks = build_ticks(
            self.timeline,
            self.tick_ms,
            self.sample_rate,
            duration_ms=self.input_ms,
            user_track=self.recorder.user,
            assistant_track=self.recorder.assistant,
        )
        turn_metrics = compute_turn_interaction_metrics(
            ticks,
            self.timeline,
            response_deadline_ms=self.response_deadline_ms,
        )
        interaction_metrics = compute_interaction_metrics(
            ticks,
            tick_ms=self.tick_ms,
            timeline=self.timeline,
            response_deadline_ms=self.response_deadline_ms,
        )
        interaction_metrics["events"] = extract_interaction_events(turn_metrics)
        user_audio_ms = sum(end - start for start, end in self.timeline.speech_intervals("user"))
        result = build_result(
            self.scenario,
            self.timeline,
            caller_mode="offline_fixture" if self.offline else "gpt-live",
            caller_model=self.caller.agent_id,
            caller_actions=dict(self.caller_actions),
            caller_audio_ms=user_audio_ms,
            caller_usage=self.caller_usage,
            termination_reason=termination_reason,
            interaction_metrics=interaction_metrics,
            turn_metrics=turn_metrics,
            interaction_mode="multi_turn",
            audio_source="dual_gpt_live",
            audio_condition=self.condition,
            run_id=self.run_id,
            run_metadata={
                "run_id": self.run_id,
                "started_at": self.started_at,
                "scenario_id": self.scenario.id,
                "interaction": "multi_turn",
                "audio_source": "dual_gpt_live",
                "audio_condition": self.condition,
                "audio_realism": self.audio_processor.metadata,
                "sample_rate_hz": self.sample_rate,
                "audio_format": "pcm16",
                "frame_ms": self.tick_ms,
                "real_time": self.real_time,
                "seed": self.seed,
                "metric_derivation": "post_hoc_audio_and_events",
                "metrics_version": METRICS_VERSION,
                "api_version": "v3",
                "turn_derivation": "local_audio_and_transcript",
                "audio_timing_source": "local_relay_playout",
                "response_deadline_ms": self.response_deadline_ms,
                "caller_action_attribution": "inferred_from_audio_and_transcript",
                "voice_metrics_limitations": [
                    "Caller interruption and backchannel intent are inferred after the conversation.",
                ],
                "synchronized_tick_ms": self.tick_ms,
                "transport_frame_ms": transport_frame_ms,
                "analysis_tick_ms": self.tick_ms,
                "audio_realism_processing_frame_ms": transport_frame_ms,
                "relay_media_clock": "cumulative_pcm_samples",
                "event_receipt_clock": "monotonic_since_run_start",
                "untimed_event_clock": "relay_media_position_at_receipt",
                "untimed_event_resolution_ms": transport_frame_ms,
                "relay_transport": {
                    "synchronization": "paired_send",
                    "playout_buffer_max_hold_ms": 0 if self.offline else LIVE_OUTPUT_BUFFER_MS,
                    "playout_buffer_refill_silence_ms": LIVE_OUTPUT_SILENCE_MS,
                    "packets_per_direction": self._relay_packets,
                    "underflow_samples": dict(self._relay_underflow_samples),
                    "max_buffered_audio_bytes": dict(self._relay_max_buffered_bytes),
                    "audio_buffer_limit_bytes_per_direction": self.events.max_bytes,
                    "max_send_ms": dict(self._relay_max_send_ms),
                    "max_event_queue_delay_ms": self._relay_max_queue_delay_ms,
                    "delivery_evidence": "participant_send_completed_not_physical_playback",
                },
                "caller_frontend_model": self.caller.agent_id,
                "simulator_backend_model": self.simulator_backend_model,
                "simulator_backend_reasoning_effort": self.simulator_backend_reasoning_effort,
                "caller_voice": self.caller_voice,
                "agent_model": self.assistant.agent_id,
                "agent_voice": self.agent_voice,
                "delegation_backend_model": self.assistant_backend_model,
                "first_speaker": "assistant" if assistant_first else "caller",
                "initial_application_state": initial_state,
                "final_application_state": self.application_tools.snapshot(),
                "tool_executions": self.application_tools.executions,
                "caller_control_state": self.caller_tools.snapshot(),
                "caller_control_executions": self.caller_tools.executions,
                "caller_agenda_completed": sorted(self.caller_tools.completed_objectives),
                "caller_completion_policy": (
                    "caller_finish_tool_or_verified_outcome"
                    if self.offline
                    else "semantic_conversation_observer"
                    if self.completion_observer is not None and not self._completion_fallback_reason
                    else "verified_outcome_and_natural_closing"
                ),
                "semantic_completion": {
                    "enabled": self.completion_observer is not None,
                    "model": self.completion_observer.model if self.completion_observer is not None else None,
                    "assessments": (
                        list(self.completion_observer.assessments) if self.completion_observer is not None else []
                    ),
                    "usage": list(self.completion_observer.usage) if self.completion_observer is not None else [],
                    "fallback_reason": self._completion_fallback_reason or None,
                    "quiet_tail_ms": self.final_audio_quiet_ms,
                },
                "caller_participant_events": self.participant_events,
                "simulator_validity": caller_simulation_validity(
                    self.participant_events,
                    backend_enabled=bool(self.simulator_backend_model),
                    work_pending=caller_work_pending_at_end or self._caller_work_state.active,
                ),
                "delegation_lifecycle_events": self.timeline.delegation_events(),
                "completion_signal": self.completion_signal,
                "offline": self.offline,
            },
        )
        if any(isinstance(outcome, Exception) for outcome in close_results) or self._finalized != {
            "caller",
            "assistant",
        }:
            result.task_status = "error"
            result.task_metrics["task_completed"] = False
            result.termination_reason = "session_close_failed"
        if self.save_conversations is not None:
            audio_path, transcript_path = self.recorder.save(
                self.save_conversations / "conversation.wav", result.transcript
            )
            result.artifacts = {
                "audio": str(audio_path),
                "transcript": str(transcript_path),
                "result": str(audio_path.with_suffix(".result.json")),
            }
            if self.event_log_path is not None:
                result.artifacts["events"] = str(self.event_log_path)
            if self.debug_artifacts:
                result.artifacts["ticks"] = str(write_ticks(audio_path.with_suffix(".ticks.jsonl"), ticks))
                result.artifacts["turns"] = str(
                    write_ticks(audio_path.with_suffix(".turns.jsonl"), result.turn_metrics)
                )
            write_json(Path(result.artifacts["result"]), result.model_dump())
        if any(isinstance(outcome, Exception) for outcome in close_results) or self._finalized != {
            "caller",
            "assistant",
        }:
            raise LiveResponseError(
                "GPT Live session finalization failed; captured artifacts were retained", failure_stage="session_close"
            )
        return result


__all__ = ["DualGptLiveRunner"]
