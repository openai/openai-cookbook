"""Independent live and offline participants for RUN's default GPT Live caller."""

from __future__ import annotations

import base64
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from assistants import create_assistant
from assistants.config import LiveAgentSettings, ReasoningEffort
from assistants.frontend.events import EventQueue
from assistants.frontend.transport import build_context_append
from assistants.responses.assistant import ResponsesManagedAssistant
from assistants.runtime import ToolExecutor
from run_harness.simulation.gpt_live_prompts import caller_backend_instructions
from run_harness.simulation.models import DEFAULT_SIMULATOR_BACKEND_MODEL, DEFAULT_SIMULATOR_BACKEND_REASONING_EFFORT
from shared.audio.pcm import chunk_pcm, rms_pcm16, tone_for_text
from shared.scenarios import Scenario


@dataclass(frozen=True, slots=True)
class ParticipantSettings:
    """The participant-specific values consumed by shared assistant setup."""

    agent_endpoint: str
    agent_model: str
    agent_voice: str
    backend_model: str
    agent_instructions: str
    backend_instructions: str
    delegation_tools: list[dict[str, Any]]
    assistant_mode: str = "responses"
    assistant_endpoint: str = ""


class VoiceParticipant(Protocol):
    agent_id: str

    async def start(self) -> None: ...

    async def trigger_opening(self, text: str) -> dict[str, Any] | None: ...

    async def append_context(self, text: str) -> None: ...

    async def send_audio(self, pcm: bytes) -> None: ...

    def incoming(self) -> AsyncIterator[dict[str, Any]]: ...

    async def wait_for_tools(self) -> None: ...

    async def close(self) -> None: ...


class SimulatorControlTools:
    """Caller-owned state that cannot access restaurant application state."""

    def __init__(self) -> None:
        self.executions: list[dict[str, Any]] = []
        self.completed_objectives: set[str] = set()
        self._finished = False
        self._lock = threading.Lock()

    @property
    def finished(self) -> bool:
        with self._lock:
            return self._finished

    def execute(self, name: str, arguments: dict[str, Any], *, call_id: str) -> dict[str, Any]:
        with self._lock:
            if name == "report_objective_progress":
                objective_id = str(arguments.get("objective_id", "")).strip()
                if not objective_id:
                    raise ValueError("objective_id is required")
                self.completed_objectives.add(objective_id)
                output = {"ok": True, "completed_objectives": sorted(self.completed_objectives)}
            elif name == "finish_conversation":
                self._finished = True
                output = {"ok": True, "finished": True}
            else:
                raise ValueError(f"unknown simulator control tool: {name}")
            self.executions.append(
                {
                    "call_id": call_id,
                    "name": name,
                    "arguments": dict(arguments),
                    "status": "completed",
                    "output": output,
                }
            )
            return output

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "finished": self._finished,
                "completed_objectives": sorted(self.completed_objectives),
            }


OFFLINE_ASSISTANT_GREETING = "Hello, how can I help you today?"


class EvaluatedGptLiveParticipant:
    """One evaluated GPT Live assistant with its own delegated backend and tools."""

    def __init__(
        self,
        *,
        scenario: Scenario,
        settings: ParticipantSettings,
        api_key: str,
        tool_executor: ToolExecutor,
    ) -> None:
        config = LiveAgentSettings(
            endpoint=settings.agent_endpoint,
            model=settings.agent_model,
            voice=settings.agent_voice,
            backend_model=settings.backend_model,
            assistant_mode=settings.assistant_mode,
            client_endpoint=settings.assistant_endpoint,
        )
        self._agent = create_assistant(
            scenario=scenario,
            settings=settings,
            api_key=api_key,
            config=config,
            tool_executor=tool_executor,
        )
        self.agent_id = self._agent.agent_id

    async def start(self) -> None:
        await self._agent.start()

    async def trigger_opening(self, text: str) -> None:
        """Evaluated assistants wait for the caller to begin the conversation."""
        del text

    async def append_context(self, text: str) -> None:
        await self._agent.append_context(text)

    async def send_audio(self, pcm: bytes) -> None:
        await self._agent.send_audio(pcm)

    async def incoming(self) -> AsyncIterator[dict[str, Any]]:
        async for event in self._agent.incoming():
            yield event

    async def wait_for_tools(self) -> None:
        await self._agent.wait_for_tools()

    async def close(self) -> None:
        await self._agent.close()


class GptLiveCallerParticipant(EvaluatedGptLiveParticipant):
    """A caller-only GPT Live frontend with managed reasoning and no tools."""

    def __init__(
        self,
        *,
        scenario: Scenario,
        endpoint: str,
        model: str,
        voice: str,
        instructions: str,
        api_key: str,
        backend_model: str = DEFAULT_SIMULATOR_BACKEND_MODEL,
        backend_reasoning_effort: ReasoningEffort = DEFAULT_SIMULATOR_BACKEND_REASONING_EFFORT,
    ) -> None:
        settings = ParticipantSettings(
            agent_endpoint=endpoint,
            agent_model=model,
            agent_voice=voice,
            backend_model=backend_model,
            agent_instructions=instructions,
            backend_instructions=caller_backend_instructions(scenario),
            delegation_tools=[],
        )
        config = LiveAgentSettings(
            endpoint=endpoint,
            model=model,
            voice=voice,
            backend_model=backend_model,
            assistant_mode="responses",
            client_endpoint="",
            backend_reasoning_effort=backend_reasoning_effort,
            backend_max_output_tokens=1_024,
            backend_verbosity="low",
        )
        self._agent = ResponsesManagedAssistant(
            scenario=scenario,
            settings=settings,
            api_key=api_key,
            config=config,
            tool_executor=None,
        )
        self.agent_id = self._agent.agent_id

    async def trigger_opening(self, text: str) -> dict[str, Any]:
        """Ask the caller's own GPT Live session to speak the scenario opening."""
        event = build_context_append(
            "Immediately begin the call using the exact opening request below. "
            "Do not wait for the assistant to speak first. "
            "After the opening request, pause and listen.\n\n"
            f"{text}"
        )
        await self._agent._send_live(event)
        return event


class _OfflineParticipant:
    """Speech/silence-reactive local protocol fixture for one participant."""

    silence_ms = 300

    def __init__(self, *, sample_rate: int, tick_ms: int, agent_id: str) -> None:
        self.sample_rate = sample_rate
        self.tick_ms = tick_ms
        self.agent_id = agent_id
        self.events = EventQueue()
        self.input_ms = 0
        self.peer_speaking = False
        self.peer_silence_ticks = 0
        self.response_index = 0
        self.closed = False
        self._speech_activity_hint: bool | None = None

    def set_speech_activity(self, speaking: bool) -> None:
        """Keep offline fixtures aware of primary speech beneath synthetic ambience."""
        self._speech_activity_hint = speaking

    async def start(self) -> None:
        await self.events.put({"type": "session.started", "session": {"mode": "offline", "id": self.agent_id}})

    async def trigger_opening(self, text: str) -> None:
        del text

    async def append_context(self, text: str) -> None:
        build_context_append(text)

    async def send_audio(self, pcm: bytes) -> None:
        start_ms = self.input_ms
        self.input_ms += self.tick_ms
        speaking = self._speech_activity_hint if self._speech_activity_hint is not None else rms_pcm16(pcm) > 220
        self._speech_activity_hint = None
        if speaking:
            self.peer_speaking = True
            self.peer_silence_ticks = 0
        elif self.peer_speaking:
            self.peer_silence_ticks += 1
            if self.peer_silence_ticks * self.tick_ms >= self.silence_ms:
                self.peer_speaking = False
                self.peer_silence_ticks = 0
                await self._respond(start_ms)

    async def _emit(self, text: str, *, action: str = "SPEAK") -> tuple[int, int]:
        pcm = tone_for_text(text, self.sample_rate)
        chunk_bytes = self.sample_rate * self.tick_ms // 1_000 * 2
        chunks = chunk_pcm(pcm, chunk_bytes)
        start_ms = self.input_ms + self.tick_ms
        for chunk in chunks:
            await self.events.put(
                {
                    "type": "session.output_audio.delta",
                    "delta": base64.b64encode(chunk).decode(),
                }
            )
        end_ms = start_ms + len(chunks) * self.tick_ms
        await self.events.put(
            {
                "type": "session.output_transcript.delta",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "delta": text,
                "action": action,
            }
        )
        return start_ms, end_ms

    async def _respond(self, start_ms: int) -> None:
        raise NotImplementedError

    async def incoming(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            event = await self.events.get()
            yield event
            if event.get("type") in {"session.closed", "error"}:
                return

    async def wait_for_tools(self) -> None:
        return None

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            await self.events.put(
                {"type": "session.closed", "reason": "client_request", "usage": {"seconds": self.input_ms / 1000}}
            )


class OfflineCallerParticipant(_OfflineParticipant):
    """Deterministic caller whose turns come from the RUN scenario agenda."""

    def __init__(
        self,
        scenario: Scenario,
        controls: SimulatorControlTools,
        *,
        sample_rate: int,
        tick_ms: int,
    ) -> None:
        super().__init__(sample_rate=sample_rate, tick_ms=tick_ms, agent_id="offline-caller-gpt-live")
        simulation = scenario.simulation_parameters
        if simulation is None:
            raise ValueError("offline caller requires simulation_parameters")
        self.objectives = [
            (item.id, item.response_hint)
            for item in simulation.agenda
            if item.action not in {"finish", "wait"} and item.response_hint
        ]
        self.turns = [scenario.input.text, *[hint for _, hint in self.objectives], "Thanks, goodbye."]
        self.controls = controls

    async def trigger_opening(self, text: str) -> None:
        if text != self.turns[0]:
            raise ValueError("offline opening must match the scenario input")
        await self._speak_next(action="OPENING")

    async def _respond(self, start_ms: int) -> None:
        del start_ms
        if self.response_index < len(self.turns):
            action = (
                "OPENING"
                if self.response_index == 0
                else "STOP"
                if self.response_index == len(self.turns) - 1
                else "SPEAK"
            )
            await self._speak_next(action=action)

    async def _speak_next(self, *, action: str) -> None:
        text = self.turns[self.response_index]
        objective_index = self.response_index - 1
        self.response_index += 1
        await self._emit(text, action=action)
        if action == "SPEAK" and 0 <= objective_index < len(self.objectives):
            objective_id, _ = self.objectives[objective_index]
            self.controls.execute(
                "report_objective_progress",
                {"objective_id": objective_id, "reason": "offline caller expressed the scenario objective"},
                call_id=f"offline-caller-objective-{objective_index + 1}",
            )
        if action == "STOP":
            self.controls.execute(
                "finish_conversation",
                {"reason": "offline fixture heard the verified booking and closed naturally"},
                call_id="offline-caller-finish",
            )


class OfflineRestaurantParticipant(_OfflineParticipant):
    """Deterministic assistant with real isolated restaurant tool execution."""

    def __init__(
        self,
        scenario: Scenario,
        tool_executor: ToolExecutor,
        *,
        sample_rate: int,
        tick_ms: int,
    ) -> None:
        super().__init__(sample_rate=sample_rate, tick_ms=tick_ms, agent_id="offline-assistant-gpt-live")
        self.scenario = scenario
        self.tool_executor = tool_executor

    async def append_context(self, text: str) -> None:
        build_context_append(text)
        await self._emit(OFFLINE_ASSISTANT_GREETING)

    async def _respond(self, start_ms: int) -> None:
        del start_ms
        index = self.response_index
        self.response_index += 1
        if self.scenario.expected.forbids_delegation and index < 3:
            await self._emit("I'm sorry, but I can't complete a request that you aren't authorized to make.")
            return
        if self.scenario.id == "restaurant_cancel_corrected_authorization" and index == 0:
            await self._emit("I can't cancel another customer's reservation without authorization.")
            return
        if index == 0:
            await self._emit("Certainly. What name should I use, and how many guests?")
            return
        if index == 1:
            await self._emit("Thanks. What time would you like on August 7?")
            return
        if index == 2:
            if self.scenario.expected.forbids_delegation:
                await self._emit("I'm sorry, but I can't complete a request that you aren't authorized to make.")
                return
            offset_ms = self.input_ms
            response_id = "offline-assistant-response"
            await self.events.put(
                {
                    "type": "session.delegation.created",
                    "delegation": {
                        "id": "offline-assistant-delegation",
                        "target": "responses",
                        "response_id": response_id,
                    },
                }
            )
            await self.events.put(
                {
                    "type": "response.event",
                    "delegation_id": "offline-assistant-delegation",
                    "event": {"type": "response.created", "response": {"id": response_id, "output": []}},
                }
            )
            for sequence, expected in enumerate(self.scenario.expected.tools.required, start=1):
                call_id = f"offline-assistant-tool-{sequence}"
                correlation = {
                    "name": expected.name,
                    "call_id": call_id,
                    "response_id": response_id,
                    "arguments": expected.arguments,
                    "offset_ms": offset_ms,
                }
                await self.events.put({"type": "tool.called", **correlation})
                output = self.tool_executor.execute(expected.name, expected.arguments, call_id=call_id)
                await self.events.put({"type": "tool.completed", **correlation, "result": output})
            await self.events.put(
                {
                    "type": "response.event",
                    "delegation_id": "offline-assistant-delegation",
                    "event": {
                        "type": "response.completed",
                        "response": {
                            "id": response_id,
                            "usage": {"input_tokens": 24, "output_tokens": 12},
                            "output": [],
                        },
                    },
                }
            )
            followup_response_id = f"{response_id}-followup"
            await self.events.put(
                {
                    "type": "response.event",
                    "delegation_id": "offline-assistant-delegation",
                    "event": {"type": "response.created", "response": {"id": followup_response_id, "output": []}},
                }
            )
            await self.events.put(
                {
                    "type": "response.event",
                    "delegation_id": "offline-assistant-delegation",
                    "event": {
                        "type": "response.completed",
                        "response": {
                            "id": followup_response_id,
                            "usage": {"input_tokens": 24, "output_tokens": 12},
                            "output": [],
                        },
                    },
                }
            )
            await self._emit("Your reservation is confirmed for Maya, for two guests on August 7 at 7 p.m.")
            return
        await self._emit("You're welcome. Goodbye.")
