"""Compact task and interaction summaries suitable for eval ingestion."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, get_args

from shared.grading.matching import expected_arguments_match, unique_expected_matches
from shared.observability.timeline import AgentEvent, Timeline
from shared.reporting.schema import SCHEMA_VERSION
from shared.scenarios import ExpectedToolCall, Scenario

CallerMode = Literal["gpt-live", "offline_fixture", "tts", "recorded_audio"]
CallerAction = Literal["OPENING", "SPEAK", "BACKCHANNEL", "INTERRUPT", "STOP"]


@dataclass(slots=True)
class EvalResult:
    scenario_id: str
    caller_mode: CallerMode
    caller_model: str
    task_status: str
    task_metrics: dict[str, Any]
    criteria: list[dict[str, Any]]
    transcript: str
    agent_events: list[dict[str, Any]]
    delegation_count: int
    tool_event_count: int
    overlap_ms: int
    assistant_turns: int
    user_turns: int
    total_turns: int
    efficiency_metrics: dict[str, Any]
    caller_actions: dict[str, int]
    response_latencies_ms: list[int]
    yield_latencies_ms: list[int]
    interaction_metrics: dict[str, Any]
    turn_metrics: list[dict[str, Any]]
    caller_audio_ms: int
    usage: list[dict[str, Any]]
    termination_reason: str
    rubric_metrics: dict[str, Any] | None = None
    interaction_mode: str = "multi_turn"
    audio_source: str = "synthetic"
    audio_condition: str = "clean"
    run_id: str = ""
    transcripts: dict[str, Any] | None = None
    artifacts: dict[str, str] | None = None
    run_metadata: dict[str, Any] | None = None

    def model_dump(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}


def _matches_expected_tool(event: AgentEvent, expectation: ExpectedToolCall) -> bool:
    if event.name != expectation.name:
        return False
    if expectation.status != "any" and event.status != expectation.status:
        return False
    if not expectation.arguments:
        return True
    if not isinstance(event.arguments, dict):
        return False
    return expected_arguments_match(expectation.arguments, event.arguments)


def _evidence_progress(scenario: Scenario, text: str) -> tuple[list[str], list[str]]:
    def normalize(value: str) -> str:
        return re.sub(r"\b(\d+)\s+(st|nd|rd|th)\b", r"\1\2", value.casefold())

    searchable = normalize(text)
    matched: list[str] = []
    missing: list[str] = []
    for group in scenario.expected.diagnostic_terms:
        alternatives = [term.strip() for term in group.split("|") if term.strip()]
        found = next((term for term in alternatives if normalize(term) in searchable), None)
        if found is None:
            missing.append(group)
        else:
            matched.append(found)
    return matched, missing


def _coverage(matched: int, expected: int) -> float:
    return round(matched / expected, 4) if expected else 1.0


def unique_tool_invocations(events: list[AgentEvent]) -> list[AgentEvent]:
    """Collapse duplicate terminal tool projections emitted for the same invocation."""
    unique: dict[tuple[str, str, str | int], AgentEvent] = {}
    for event in events:
        if event.kind != "tool" or event.status not in {"completed", "failed"}:
            continue
        key = (event.name, event.status, event.call_id or event.timestamp_ms)
        current = unique.get(key)
        has_more_arguments = current is not None and (
            current.arguments in (None, "", {}, []) and event.arguments not in (None, "", {}, [])
        )
        has_execution_result = current is not None and (
            current.result in (None, "", {}, []) and event.result not in (None, "", {}, [])
        )
        if current is None or has_more_arguments or has_execution_result:
            unique[key] = event
    return sorted(unique.values(), key=lambda event: event.timestamp_ms)


def _task_progress(
    scenario: Scenario,
    timeline: Timeline,
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    prior_evidence: set[str] = set()
    prior_tools: set[int] = set()
    prior_assistant_text = ""
    prior_boundary_ms = -1

    for original in turns:
        record = dict(original)
        start_ms = int(record["start_ms"])
        end_ms = int(record["window_end_ms"])
        assistant_text = timeline.spoken_text("assistant", until_ms=end_ms)
        matched, missing = _evidence_progress(scenario, assistant_text)
        observed_events = [event for event in timeline.agent_events if event.timestamp_ms <= end_ms]
        observed_tools = [event for event in observed_events if event.kind == "tool"]
        matched_tools = {
            index
            for index, expected in enumerate(scenario.expected.tools.required)
            if any(_matches_expected_tool(event, expected) for event in observed_tools)
        }
        delegation_observed = any(event.kind == "delegation" for event in observed_events)
        requirements_satisfied = (
            not missing
            and len(matched_tools) == len(scenario.expected.tools.required)
            and (not scenario.expected.requires_delegation or delegation_observed)
            and not (scenario.expected.forbids_delegation and delegation_observed)
        )
        if assistant_text.startswith(prior_assistant_text):
            new_assistant_text = assistant_text[len(prior_assistant_text) :].strip()
        else:
            new_assistant_text = " ".join(
                fragment.text
                for fragment in timeline.fragments
                if fragment.role == "assistant"
                and fragment.end_ms > max(start_ms, prior_boundary_ms)
                and fragment.start_ms < end_ms
            )

        record["assistant_transcript"] = new_assistant_text
        record["task"] = {
            "new_evidence": [term for term in matched if term not in prior_evidence],
            "matched_evidence": matched,
            "missing_evidence": missing,
            "evidence_coverage": _coverage(len(matched), len(scenario.expected.diagnostic_terms)),
            "tool_calls": [
                event.model_dump() for event in observed_tools if prior_boundary_ms < event.timestamp_ms <= end_ms
            ],
            "new_matched_tool_calls": [
                scenario.expected.tools.required[index].name for index in sorted(matched_tools - prior_tools)
            ],
            "matched_tool_calls": [scenario.expected.tools.required[index].name for index in sorted(matched_tools)],
            "missing_tool_calls": [
                expected.name
                for index, expected in enumerate(scenario.expected.tools.required)
                if index not in matched_tools
            ],
            "tool_call_coverage": _coverage(len(matched_tools), len(scenario.expected.tools.required)),
            "delegation_required": scenario.expected.requires_delegation,
            "delegation_prohibited": scenario.expected.forbids_delegation,
            "delegation_observed": delegation_observed,
            "requirements_satisfied": requirements_satisfied,
            "task_completed": requirements_satisfied and record.get("action") == "STOP",
        }
        records.append(record)
        prior_evidence.update(matched)
        prior_tools.update(matched_tools)
        prior_assistant_text = assistant_text
        prior_boundary_ms = end_ms

    return records


def _efficiency_metrics(
    scenario: Scenario,
    timeline: Timeline,
    actions: dict[str, int],
    turns: list[dict[str, Any]],
    assistant_turns: int,
    user_turns: int,
) -> dict[str, Any]:
    ends = [
        *(item.end_ms for item in timeline.fragments),
        *(item.end_ms for item in timeline.user_utterances),
        *(item.end_ms for item in timeline.turns),
        *(item.timestamp_ms for item in timeline.agent_events),
    ]
    completion_index = next(
        (index for index, turn in enumerate(turns) if turn["task"]["requirements_satisfied"]),
        None,
    )
    completion_turn = turns[completion_index] if completion_index is not None else None
    observed_tools = [event for event in timeline.agent_events if event.kind == "tool"]
    unique_tools = unique_tool_invocations(observed_tools)
    completed_tools = [event for event in unique_tools if event.status == "completed"]
    unexpected_completed_tools = [
        event
        for event in completed_tools
        if not any(_matches_expected_tool(event, expected) for expected in scenario.expected.tools.required)
    ]
    matched_tools = unique_expected_matches(
        scenario.expected.tools.required,
        unique_tools,
        lambda expected, observed: _matches_expected_tool(observed, expected),
    )
    utterances = timeline.user_utterances
    substantive_utterances = [item for item in utterances if item.action not in {"BACKCHANNEL", "STOP"}]
    closing_turns = max(sum(item.action == "STOP" for item in utterances), int(actions.get("STOP", 0) > 0))
    response_episodes = 0
    for index, utterance in enumerate(substantive_utterances):
        next_start_ms = (
            substantive_utterances[index + 1].start_ms
            if index + 1 < len(substantive_utterances)
            else max(ends, default=0)
        )
        has_assistant_response = any(
            item.role == "assistant" and item.end_ms > utterance.start_ms and item.start_ms < next_start_ms
            for item in timeline.fragments
        ) or any(
            item.role == "assistant" and item.end_ms > utterance.start_ms and item.start_ms < next_start_ms
            for item in timeline.turns
        )
        response_episodes += int(has_assistant_response)
    substantive_turns = len(substantive_utterances)
    task_turns = substantive_turns + response_episodes + closing_turns
    post_requirement_turns = turns[completion_index + 1 :] if completion_index is not None else None

    delegation_ids = {
        str(item.get("delegation", item.get("item", {})).get("id") or item.get("id") or f"delegation-{index}")
        for index, item in enumerate(timeline.delegations)
    }

    return {
        "conversation_duration_s": round(max(ends, default=0) / 1_000, 3),
        "total_turns": task_turns,
        "projected_turns": assistant_turns + user_turns,
        "assistant_turns": assistant_turns,
        "user_turns": user_turns,
        "caller_utterances": len(utterances),
        "substantive_caller_turns": substantive_turns,
        "assistant_response_episodes": response_episodes,
        "closing_turns": closing_turns,
        "backchannel_count": sum(item.action == "BACKCHANNEL" for item in utterances),
        "delegation_count": len(delegation_ids),
        "turns_to_requirements": sum(
            turn.get("action") not in {"BACKCHANNEL", "STOP"} for turn in turns[: completion_index + 1]
        )
        if completion_index is not None
        else None,
        "seconds_to_requirements": round(int(completion_turn["window_end_ms"]) / 1_000, 3)
        if completion_turn is not None
        else None,
        "post_requirement_caller_turns": len(post_requirement_turns) if post_requirement_turns is not None else None,
        "post_requirement_substantive_caller_turns": sum(
            turn.get("action") not in {"BACKCHANNEL", "STOP"} for turn in post_requirement_turns
        )
        if post_requirement_turns is not None
        else None,
        "tool_event_count": len(observed_tools),
        "completed_tool_event_count": sum(event.status == "completed" for event in observed_tools),
        "failed_tool_event_count": sum(event.status == "failed" for event in observed_tools),
        "unique_tool_invocation_count": len(unique_tools),
        "unique_completed_tool_invocation_count": len(completed_tools),
        "unique_failed_tool_invocation_count": sum(event.status == "failed" for event in unique_tools),
        "expected_tool_call_count": len(scenario.expected.tools.required),
        "matched_tool_call_count": len(matched_tools),
        "unexpected_completed_tool_invocation_count": len(unexpected_completed_tools),
    }


def build_result(
    scenario: Scenario,
    timeline: Timeline,
    *,
    caller_mode: CallerMode,
    termination_reason: str,
    caller_actions: dict[str, int] | None = None,
    caller_model: str = "",
    caller_audio_ms: int = 0,
    caller_usage: list[dict[str, Any]] | None = None,
    interaction_metrics: dict[str, Any] | None = None,
    turn_metrics: list[dict[str, Any]] | None = None,
    interaction_mode: str = "multi_turn",
    audio_source: str = "synthetic",
    audio_condition: str = "clean",
    run_id: str = "",
    transcripts: dict[str, Any] | None = None,
    run_metadata: dict[str, Any] | None = None,
) -> EvalResult:
    actions = caller_actions or {}
    if caller_mode not in get_args(CallerMode):
        raise ValueError(f"Unsupported caller mode: {caller_mode!r}")
    if any(
        name not in get_args(CallerAction) or type(count) is not int or count < 0 for name, count in actions.items()
    ):
        raise ValueError("Caller actions must be nonnegative counts of observed speech behavior")
    interaction = interaction_metrics or {}
    transcript = timeline.evaluation_transcript()
    completed = termination_reason in {"user_stopped", "response_completed"}
    matched, missing = _evidence_progress(scenario, timeline.spoken_text("assistant"))
    delegation_observed = bool(timeline.delegations)
    delegation_ok = (not scenario.expected.requires_delegation or delegation_observed) and not (
        scenario.expected.forbids_delegation and delegation_observed
    )
    observed_tools = [event for event in timeline.agent_events if event.kind == "tool"]
    matched_tools = [
        expectation
        for expectation in scenario.expected.tools.required
        if any(_matches_expected_tool(event, expectation) for event in observed_tools)
    ]
    missing_tools = [
        expectation.name
        for expectation in scenario.expected.tools.required
        if not any(_matches_expected_tool(event, expectation) for event in observed_tools)
    ]
    prohibited_tools = [
        expectation.name
        for expectation in scenario.expected.tools.prohibited
        if any(_matches_expected_tool(event, expectation) for event in observed_tools)
    ]
    passed = completed and not missing and delegation_ok and not missing_tools and not prohibited_tools
    task_metrics = {
        "task_completed": passed,
        "conversation_completed": completed,
        "requirements_satisfied": not missing and delegation_ok and not missing_tools and not prohibited_tools,
        "evidence_coverage": _coverage(len(matched), len(scenario.expected.diagnostic_terms)),
        "matched_evidence_count": len(matched),
        "expected_evidence_count": len(scenario.expected.diagnostic_terms),
        "tool_call_coverage": _coverage(len(matched_tools), len(scenario.expected.tools.required)),
        "matched_tool_call_count": len(matched_tools),
        "expected_tool_call_count": len(scenario.expected.tools.required),
        "delegation_required": scenario.expected.requires_delegation,
        "delegation_prohibited": scenario.expected.forbids_delegation,
        "delegation_observed": delegation_observed,
        "prohibited_tool_call_count": len(prohibited_tools),
    }
    evidence = {
        "matched_terms": matched,
        "missing_terms": missing,
        "delegation_required": scenario.expected.requires_delegation,
        "delegation_prohibited": scenario.expected.forbids_delegation,
        "delegation_observed": delegation_observed,
        "expected_tool_calls": [item.model_dump() for item in scenario.expected.tools.required],
        "missing_tool_calls": missing_tools,
        "prohibited_tool_calls": prohibited_tools,
    }
    criteria = [
        {
            "criterion": criterion,
            "status": "passed" if passed else "not_verified",
            "evidence": evidence,
        }
        for criterion in scenario.expected.criteria
    ]
    turns = _task_progress(scenario, timeline, turn_metrics or [])
    assistant_turns = len([turn for turn in timeline.turns if turn.role == "assistant"])
    user_turns = len([turn for turn in timeline.turns if turn.role == "user"])
    efficiency_metrics = _efficiency_metrics(scenario, timeline, actions, turns, assistant_turns, user_turns)
    return EvalResult(
        scenario_id=scenario.id,
        caller_mode=caller_mode,
        caller_model=caller_model,
        task_status="passed" if passed else "incomplete",
        task_metrics=task_metrics,
        criteria=criteria,
        transcript=transcript,
        agent_events=[event.model_dump() for event in timeline.agent_events],
        delegation_count=efficiency_metrics["delegation_count"],
        tool_event_count=len(timeline.tool_events),
        overlap_ms=timeline.overlap_ms,
        assistant_turns=assistant_turns,
        user_turns=user_turns,
        total_turns=efficiency_metrics["total_turns"],
        efficiency_metrics=efficiency_metrics,
        caller_actions=actions,
        response_latencies_ms=interaction.get("response_latencies_ms", []),
        yield_latencies_ms=interaction.get("yield_latencies_ms", []),
        interaction_metrics=interaction,
        turn_metrics=turns,
        caller_audio_ms=caller_audio_ms,
        usage=[*timeline.usage, *(caller_usage or [])],
        termination_reason=termination_reason,
        interaction_mode=interaction_mode,
        audio_source=audio_source,
        audio_condition=audio_condition,
        run_id=run_id,
        transcripts=transcripts,
        run_metadata=run_metadata,
    )
