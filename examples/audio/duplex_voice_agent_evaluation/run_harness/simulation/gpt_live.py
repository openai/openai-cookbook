"""Default dual-GPT Live simulated caller for the common RUN harness."""

from __future__ import annotations

import os

from assistants.runtime import ToolExecutor
from run_harness.simulation.gpt_live_participants import (
    EvaluatedGptLiveParticipant,
    GptLiveCallerParticipant,
    OfflineCallerParticipant,
    OfflineRestaurantParticipant,
    ParticipantSettings,
    SimulatorControlTools,
)
from run_harness.simulation.gpt_live_prompts import caller_frontend_instructions
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner
from run_harness.simulation.models import Scenario, Settings
from run_harness.simulation.semantic_completion import SemanticCompletionObserver
from shared.grading.scoring import EvalResult


async def run_gpt_live_conversation(
    scenario: Scenario,
    settings: Settings,
    *,
    tool_executor: ToolExecutor,
    offline: bool,
    simulator_model: str,
    simulator_voice: str,
    drain_ms: int,
    completion_observer: SemanticCompletionObserver | None = None,
) -> EvalResult:
    """Run two independent Live participants while retaining RUN's scenario contract."""

    controls = SimulatorControlTools()
    assistant_first = settings.assistant_opening_prompt is not None
    caller_voice = simulator_voice or scenario.persona.voice
    if offline:
        caller = OfflineCallerParticipant(
            scenario,
            controls,
            sample_rate=settings.sample_rate,
            tick_ms=settings.tick_ms,
        )
        assistant = OfflineRestaurantParticipant(
            scenario,
            tool_executor,
            sample_rate=settings.sample_rate,
            tick_ms=settings.tick_ms,
        )
    else:
        api_key = os.environ["OPENAI_API_KEY"]
        caller = GptLiveCallerParticipant(
            scenario=scenario,
            endpoint=settings.agent_endpoint,
            model=simulator_model,
            voice=caller_voice,
            instructions=caller_frontend_instructions(scenario, assistant_first=assistant_first),
            api_key=api_key,
            backend_model=settings.simulator_backend_model,
            backend_reasoning_effort=settings.simulator_backend_reasoning_effort,
        )
        assistant = EvaluatedGptLiveParticipant(
            scenario=scenario,
            settings=ParticipantSettings(
                agent_endpoint=settings.agent_endpoint,
                agent_model=settings.agent_model,
                agent_voice=settings.agent_voice,
                backend_model=settings.backend_model,
                agent_instructions=settings.agent_instructions,
                backend_instructions=settings.backend_instructions,
                delegation_tools=settings.delegation_tools,
                assistant_mode=settings.assistant_mode,
                assistant_endpoint=settings.assistant_endpoint,
            ),
            api_key=api_key,
            tool_executor=tool_executor,
        )

    return await DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=tool_executor,
        tick_ms=settings.tick_ms,
        response_deadline_ms=settings.response_deadline_ms,
        sample_rate=settings.sample_rate,
        speech_rms_threshold=settings.speech_rms_threshold,
        max_duration_s=settings.max_duration_s,
        drain_ms=drain_ms,
        real_time=not offline,
        verbose=settings.verbose,
        save_conversations=settings.save_conversations,
        event_log_path=settings.event_log_path,
        debug_artifacts=settings.debug_artifacts,
        offline=offline,
        condition=settings.condition,
        audio_realism=settings.audio_realism,
        seed=settings.seed,
        listen=settings.listen,
        assistant_backend_model=settings.backend_model,
        simulator_backend_model=None if offline else settings.simulator_backend_model,
        simulator_backend_reasoning_effort=None if offline else settings.simulator_backend_reasoning_effort,
        caller_voice=None if offline else caller_voice,
        agent_voice=None if offline else settings.agent_voice,
        assistant_opening_prompt=settings.assistant_opening_prompt,
        completion_observer=completion_observer,
        final_audio_quiet_ms=settings.final_audio_quiet_ms,
    ).run()
