from __future__ import annotations

import json
import wave
from array import array
from pathlib import Path

import pytest

from run_harness.visualization.export_viewer import (
    _assign_event_lanes,
    _extract_waveforms,
    build_view_data,
    export_viewer,
    main,
)


def _write_stereo_audio(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = array("h")
    for tick in range(4):
        for _ in range(1_600):
            frames.extend((1_200 if tick in {0, 2} else 0, 1_800 if tick in {1, 2, 3} else 0))
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(2)
        recording.setsampwidth(2)
        recording.setframerate(8_000)
        recording.writeframes(frames.tobytes())


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _run_fixture(
    root: Path,
    *,
    scenario_ids: tuple[str, ...] = ("restaurant_booking_complete",),
    transcript: str = "I'd like a table.",
    scenario_title: str = "Book a restaurant table",
    tool_name: str = "check_availability",
    with_ticks: bool = True,
    with_turns: bool = True,
) -> Path:
    rows: list[dict[str, object]] = []
    for scenario_id in scenario_ids:
        audio_directory = root / "audio" / scenario_id
        audio_path = audio_directory / "conversation.wav"
        _write_stereo_audio(audio_path)

        ticks: list[dict[str, object]] = []
        for index in range(4):
            user_speaking = index in {0, 2}
            assistant_speaking = index in {1, 2, 3}
            ticks.append(
                {
                    "tick": index,
                    "start_ms": index * 200,
                    "end_ms": (index + 1) * 200,
                    "user": {
                        "speech": user_speaking,
                        "speech_intervals_ms": [[index * 200, (index + 1) * 200]] if user_speaking else [],
                        "rms": 1_200.0 if user_speaking else 0.0,
                        "action": "BACKCHANNEL" if index == 2 else "OPENING" if index == 0 else "",
                        "transcript": "Mm-hmm" if index == 2 else transcript if index == 0 else "",
                    },
                    "assistant": {
                        "speech": assistant_speaking,
                        "speech_intervals_ms": [[index * 200, (index + 1) * 200]] if assistant_speaking else [],
                        "rms": 1_800.0 if assistant_speaking else 0.0,
                        "transcript": "Sure" if index == 1 else "confirmed" if index == 3 else "please",
                    },
                    "interaction": {
                        "overlap_ms": 200 if index == 2 else 0,
                        "floor_owner": "both" if index == 2 else "user" if index == 0 else "assistant",
                        "delegation_active": index == 2,
                    },
                    "events": [],
                }
            )
        if with_ticks:
            _write_jsonl(audio_directory / "conversation.ticks.jsonl", ticks)

        turns = [
            {
                "turn_index": 0,
                "start_ms": 0,
                "end_ms": 180,
                "window_end_ms": 400,
                "action": "OPENING",
                "user_transcript": transcript,
                "assistant_transcript": "Sure, what time?",
                "audio": {"overlap_ms": 0, "response_latency_ms": 20},
                "task": {"tool_calls": []},
            },
            {
                "turn_index": 1,
                "start_ms": 400,
                "end_ms": 520,
                "window_end_ms": 800,
                "action": "BACKCHANNEL",
                "user_transcript": "Mm-hmm",
                "assistant_transcript": "Confirmed.",
                "audio": {"overlap_ms": 120, "response_latency_ms": None},
                "task": {
                    "tool_calls": [
                        {
                            "timestamp_ms": 500,
                            "event_type": "tool.called",
                            "kind": "tool",
                            "name": tool_name,
                            "status": "called",
                            "arguments": {"party_size": 2},
                        },
                        {
                            "timestamp_ms": 650,
                            "event_type": "tool.completed",
                            "kind": "tool",
                            "name": tool_name,
                            "status": "completed",
                            "result": {"available": True},
                        },
                    ]
                },
            },
        ]
        if with_turns:
            _write_jsonl(audio_directory / "conversation.turns.jsonl", turns)

        details = {
            "task_status": "passed",
            "turn_metrics": turns,
            "run_metadata": {
                "metric_derivation": "post_hoc_audio_and_events",
                "caller_action_attribution": "inferred_from_audio_and_transcript",
                "voice_metrics_limitations": ["Caller intent is inferred."],
                "tool_executions": [{"name": tool_name, "status": "completed"}],
            },
            "interaction_metrics": {
                "events": [{"type": "response", "caller_end_ms": 180, "assistant_start_ms": 200, "latency_ms": 20}]
            },
        }
        (audio_directory / "conversation.result.json").write_text(json.dumps(details), encoding="utf-8")

        events = [
            {
                "type": "session.started",
                "event_time_ms": 1,
                "event": {"instructions": "DO_NOT_EMBED_PRIVATE_SESSION_INSTRUCTIONS"},
            },
            {
                "type": "tool.called",
                "event_time_ms": 510,
                "event": {"type": "tool.called", "offset_ms": 500, "name": tool_name},
            },
        ]
        _write_jsonl(root / "events" / f"{scenario_id}.jsonl", events)

        rows.append(
            {
                "scenario_id": scenario_id,
                "title": scenario_title,
                "status": "passed",
                "metrics": {
                    "task": {
                        "task_completed": True,
                        "semantic_quality": {"score": 0.85, "dimensions": {"task_understanding": 0.85}},
                        "tool_accuracy": 0.5,
                        "delegation_accuracy": 1.0,
                    },
                    "audio": {
                        "response_latency_ms": 20,
                        "response_rate": 1.0,
                        "interruption_rate": 0.0,
                        "speaking_duration_ms": {"cumulative": 500, "maximum": 300},
                        "floor_hold_silence_ms": {"cumulative": 100, "maximum": 70},
                    },
                },
                "artifacts": {
                    "conversation_audio": f"audio/{scenario_id}/conversation.wav",
                    "details": f"audio/{scenario_id}/conversation.result.json",
                    "events": f"events/{scenario_id}.jsonl",
                },
                "observability": {
                    "floor": {
                        "controller": "none",
                        "attribution": "post_hoc_audio_and_transcript",
                        "decisions": None,
                    },
                    "tools": {"executed": [{"name": tool_name, "status": "completed"}]},
                    "completion": {"passed": True, "rationale": "Reservation verified."},
                },
            }
        )

    report = {
        "run": {
            "id": "viewer-test-run",
            "module": "run",
            "execution_mode": "offline_fixture",
            "configuration": {
                "model": "gpt-live-test",
                "backend_model": "gpt-test",
                "simulator_model": "gpt-live-test",
                "tick_ms": 200,
            },
        },
        "summary": {"total": len(rows), "passed": len(rows), "failed": 0},
        "results": rows,
    }
    destination = root / "results.json"
    destination.write_text(json.dumps(report), encoding="utf-8")
    return destination


def test_extract_waveforms_keeps_caller_and_assistant_channels_separate(tmp_path: Path) -> None:
    audio_path = tmp_path / "conversation.wav"
    _write_stereo_audio(audio_path)

    waveform = _extract_waveforms(audio_path, points=4)

    assert waveform["durationMs"] == 800
    assert waveform["sampleRate"] == 8_000
    assert waveform["caller"][0] > 0
    assert waveform["assistant"][0] == 0
    assert waveform["caller"][1] == 0
    assert waveform["assistant"][1] > 0


def test_extract_waveforms_rejects_an_empty_recording(tmp_path: Path) -> None:
    audio_path = tmp_path / "conversation.wav"
    with wave.open(str(audio_path), "wb") as recording:
        recording.setnchannels(2)
        recording.setsampwidth(2)
        recording.setframerate(8_000)
        recording.writeframes(b"")

    with pytest.raises(ValueError, match="must contain at least one audio frame"):
        _extract_waveforms(audio_path)


def test_build_view_data_extracts_segments_overlap_and_inferred_attribution(tmp_path: Path) -> None:
    result_path = _run_fixture(tmp_path)

    scenario = build_view_data(result_path)["scenarios"][0]

    assert "floor" not in scenario
    assert scenario["interaction"]["attribution"] == "post_hoc_audio_and_transcript"
    assert scenario["tracks"]["caller"] == [
        {"startMs": 0, "endMs": 200, "text": "I'd like a table.", "action": "OPENING"},
        {"startMs": 400, "endMs": 600, "text": "Mm-hmm", "action": "BACKCHANNEL"},
    ]
    assert scenario["tracks"]["assistant"][0]["startMs"] == 200
    assert scenario["overlaps"] == [{"startMs": 400, "endMs": 600}]
    assert scenario["metrics"]["response_latency_ms"] == 20
    assert scenario["metrics"]["speaking_duration_ms"] == {"cumulative": 500, "maximum": 300}
    assert scenario["metrics"]["floor_hold_silence_ms"] == {"cumulative": 100, "maximum": 70}
    assert scenario["task"]["semantic_quality"]["score"] == 0.85


def test_build_view_data_attaches_measured_latency_to_the_matching_assistant_turn(tmp_path: Path) -> None:
    scenario = build_view_data(_run_fixture(tmp_path))["scenarios"][0]

    assistants = [turn for turn in scenario["turns"] if turn["role"] == "assistant"]

    assert assistants[0]["responseLatencyMs"] == 20
    assert "responseLatencyMs" not in assistants[1]
    assert all("responseLatencyMs" not in turn for turn in scenario["turns"] if turn["role"] == "caller")


def test_build_view_data_projects_safe_interaction_opportunity_counts(tmp_path: Path) -> None:
    result_path = _run_fixture(tmp_path)
    details_path = tmp_path / "audio" / "restaurant_booking_complete" / "conversation.result.json"
    details = json.loads(details_path.read_text(encoding="utf-8"))
    details["interaction_metrics"]["counts"] = {
        "response_total": 2,
        "response_count": 1,
        "yield_total": 0,
        "yield_count": 0,
        "backchannel_total": 1,
        "backchannel_correct_count": 1,
        "backchannel_error_count": 0,
        "agent_interrupts_count": 0,
        "private_diagnostic": "DO_NOT_EMBED_PRIVATE_DIAGNOSTIC",
    }
    details_path.write_text(json.dumps(details), encoding="utf-8")

    scenario = build_view_data(result_path)["scenarios"][0]

    assert scenario["interactionCounts"] == {
        "response_total": 2,
        "response_count": 1,
        "yield_total": 0,
        "yield_count": 0,
        "backchannel_total": 1,
        "backchannel_correct_count": 1,
        "backchannel_error_count": 0,
        "agent_interrupts_count": 0,
    }
    assert "DO_NOT_EMBED_PRIVATE_DIAGNOSTIC" not in export_viewer(result_path).read_text(encoding="utf-8")


def test_build_view_data_keeps_historical_results_without_interaction_counts_compatible(tmp_path: Path) -> None:
    scenario = build_view_data(_run_fixture(tmp_path, with_ticks=False, with_turns=False))["scenarios"][0]

    assert scenario["interactionCounts"] == {}
    assert next(turn for turn in scenario["turns"] if turn["role"] == "assistant")["responseLatencyMs"] == 20


def test_exported_viewer_explains_primary_audio_and_delegation_metrics(tmp_path: Path) -> None:
    html = export_viewer(_run_fixture(tmp_path)).read_text(encoding="utf-8")

    assert "Average response latency" in html
    assert "Cumulative floor-hold silence" in html
    assert "Maximum floor-hold silence" in html
    assert "Delegation accuracy" in html
    assert "eligible requests" in html
    assert "expected tools" in html
    assert "Yield latency" not in html
    assert "Backchannel handling" not in html


def test_viewer_uses_customer_owned_scenarios_and_tools_without_restaurant_assumptions(tmp_path: Path) -> None:
    results = _run_fixture(
        tmp_path,
        scenario_ids=("insurance_claim_status",),
        transcript="What is the status of claim C-204?",
        scenario_title="Check an insurance claim",
        tool_name="lookup_claim",
        with_ticks=False,
        with_turns=False,
    )

    html = export_viewer(results).read_text(encoding="utf-8")
    scenario = build_view_data(results)["scenarios"][0]

    assert scenario["id"] == "insurance_claim_status"
    assert scenario["title"] == "Check an insurance claim"
    assert scenario["toolEvents"][0]["name"] == "lookup_claim"
    assert "What is the status of claim C-204?" in html
    assert "restaurant" not in html.lower()


def test_offline_fixture_view_data_identifies_synthetic_tone_audio(tmp_path: Path) -> None:
    data = build_view_data(_run_fixture(tmp_path))

    assert data["run"]["executionMode"] == "offline_fixture"
    assert data["run"]["audioProvenance"] == "synthetic_tone_fixture"


def test_viewer_omits_floor_decisions(tmp_path: Path) -> None:
    scenario = build_view_data(_run_fixture(tmp_path))["scenarios"][0]

    assert "floor" not in scenario
    assert "floorDecisions" not in scenario
    assert all(event["kind"] in {"delegation", "tool"} for event in scenario["eventAnnotations"])
    assert all(event.get("label") != "respond" for event in scenario["eventAnnotations"])


def test_clustered_event_labels_use_separate_lanes_without_changing_timestamps() -> None:
    markers = [
        {"timeMs": 10_000, "label": "Delegation · client", "kind": "delegation"},
        {"timeMs": 10_150, "label": "check_availability", "kind": "tool"},
        {"timeMs": 24_000, "label": "create_reservation", "kind": "tool"},
    ]

    positioned = _assign_event_lanes(markers, duration_ms=30_000, track_width_px=420)

    assert [item["timeMs"] for item in positioned] == [10_000, 10_150, 24_000]
    assert positioned[0]["lane"] != positioned[1]["lane"]
    assert positioned[0]["lane"] == positioned[2]["lane"]


def test_build_view_data_preserves_distinct_tool_lifecycle_events(tmp_path: Path) -> None:
    scenario = build_view_data(_run_fixture(tmp_path))["scenarios"][0]

    assert scenario["toolEvents"] == [
        {"timeMs": 500, "name": "check_availability", "status": "called"},
        {"timeMs": 650, "name": "check_availability", "status": "completed"},
    ]
    backchannel = next(turn for turn in scenario["turns"] if turn["role"] == "caller" and turn["startMs"] == 400)
    assert backchannel["action"] == "BACKCHANNEL"


def test_build_view_data_shows_delegations_without_tool_calls_alongside_tool_markers(tmp_path: Path) -> None:
    result_path = _run_fixture(tmp_path)
    ticks_path = tmp_path / "audio" / "restaurant_booking_complete" / "conversation.ticks.jsonl"
    ticks = [json.loads(line) for line in ticks_path.read_text(encoding="utf-8").splitlines()]
    ticks[1]["events"].append(
        {
            "type": "session.delegation.created",
            "timestamp_ms": 240,
            "kind": "delegation",
            "name": "client",
            "arguments": "PRIVATE_DELEGATED_REQUEST_DO_NOT_EMBED",
        }
    )
    ticks[2]["events"].append(
        {
            "type": "session.delegation.created",
            "timestamp_ms": 440,
            "kind": "delegation",
            "name": "client",
        }
    )
    _write_jsonl(ticks_path, ticks)

    scenario = build_view_data(result_path)["scenarios"][0]

    assert scenario["delegationEvents"] == [
        {"timeMs": 240, "target": "client"},
        {"timeMs": 440, "target": "client"},
    ]
    assert [
        {"timeMs": event["timeMs"], "label": event["label"], "kind": event["kind"]}
        for event in scenario["eventAnnotations"]
    ] == [
        {"timeMs": 240, "label": "Delegation · client", "kind": "delegation"},
        {"timeMs": 440, "label": "Delegation · client", "kind": "delegation"},
        {"timeMs": 500, "label": "check_availability", "kind": "tool"},
    ]
    html = export_viewer(result_path).read_text(encoding="utf-8")
    assert "PRIVATE_DELEGATED_REQUEST_DO_NOT_EMBED" not in html
    assert "is-delegation" in html
    assert "Delegations · tools" in html
    assert "transform: translateX(-3.5px);" in html
    assert "var left = center - 3.5 - 7;" in html
    assert "var right = center - 3.5 + width + 7;" in html


def test_viewer_deduplicates_repeated_delegations_in_tick_traces(tmp_path: Path) -> None:
    result_path = _run_fixture(tmp_path)
    ticks_path = tmp_path / "audio" / "restaurant_booking_complete" / "conversation.ticks.jsonl"
    ticks = [json.loads(line) for line in ticks_path.read_text(encoding="utf-8").splitlines()]
    ticks[1]["events"].extend(
        [
            {"type": "session.delegation.created", "timestamp_ms": 240, "name": "client"},
            {"type": "session.delegation.created", "timestamp_ms": 240, "name": "client"},
        ]
    )
    _write_jsonl(ticks_path, ticks)

    assert build_view_data(result_path)["scenarios"][0]["delegationEvents"] == [{"timeMs": 240, "target": "client"}]


@pytest.mark.parametrize(("with_ticks", "with_turns"), [(False, False), (False, True), (True, False)])
def test_historical_results_reconstruct_timeline_without_optional_debug_artifacts(
    tmp_path: Path,
    with_ticks: bool,
    with_turns: bool,
) -> None:
    result_path = _run_fixture(tmp_path, with_ticks=with_ticks, with_turns=with_turns)

    scenario = build_view_data(result_path)["scenarios"][0]

    assert scenario["timelineProvenance"] == "reconstructed_audio"
    assert [(item["startMs"], item["endMs"]) for item in scenario["tracks"]["caller"]] == [
        (0, 200),
        (400, 600),
    ]
    assert scenario["tracks"]["assistant"][0]["startMs"] == 200
    assert scenario["overlaps"] == [{"startMs": 400, "endMs": 600}]
    assert scenario["turns"][0]["text"] == "I'd like a table."
    assert scenario["toolEvents"][0]["name"] == "check_availability"


def test_complete_debug_artifacts_are_labeled_as_original_trace(tmp_path: Path) -> None:
    scenario = build_view_data(_run_fixture(tmp_path))["scenarios"][0]

    assert scenario["timelineProvenance"] == "debug_trace"


@pytest.mark.parametrize("artifact_name", ["conversation_audio", "details", "events"])
@pytest.mark.parametrize("escape_kind", ["absolute", "parent", "symlink"])
def test_build_view_data_rejects_artifacts_outside_the_run_directory(
    tmp_path: Path,
    artifact_name: str,
    escape_kind: str,
) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    results_path = _run_fixture(run_directory)
    report = json.loads(results_path.read_text(encoding="utf-8"))
    artifacts = report["results"][0]["artifacts"]
    original_path = run_directory / artifacts[artifact_name]
    external_directory = tmp_path / "external"
    external_directory.mkdir()
    external_path = external_directory / original_path.name
    external_path.write_bytes(original_path.read_bytes())

    if escape_kind == "absolute":
        escaped_path = str(external_path)
    elif escape_kind == "parent":
        escaped_path = str(Path("..") / "external" / original_path.name)
    else:
        (run_directory / "linked").symlink_to(external_directory, target_is_directory=True)
        escaped_path = str(Path("linked") / original_path.name)
    artifacts[artifact_name] = escaped_path
    results_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="must stay within the run directory"):
        build_view_data(results_path)


def test_build_view_data_skips_infrastructure_failures_when_a_conversation_exists(tmp_path: Path) -> None:
    results_path = _run_fixture(tmp_path)
    report = json.loads(results_path.read_text(encoding="utf-8"))
    report["summary"] = {"total": 2, "passed": 1, "failed": 0, "infrastructure_errors": 1}
    report["results"].append({"scenario_id": "unavailable_provider", "status": "infrastructure_error", "artifacts": {}})
    results_path.write_text(json.dumps(report), encoding="utf-8")

    data = build_view_data(results_path)

    assert [scenario["id"] for scenario in data["scenarios"]] == ["restaurant_booking_complete"]
    assert data["summary"]["infrastructure_errors"] == 1


def test_build_view_data_reports_when_no_conversation_can_be_visualized(tmp_path: Path) -> None:
    results_path = _run_fixture(tmp_path)
    report = json.loads(results_path.read_text(encoding="utf-8"))
    report["results"][0].update({"status": "infrastructure_error", "artifacts": {}})
    results_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="No visualizable RUN conversations"):
        build_view_data(results_path)


@pytest.mark.parametrize("module", ["crawl", "walk"])
def test_build_view_data_rejects_other_harness_modules(tmp_path: Path, module: str) -> None:
    results_path = _run_fixture(tmp_path)
    report = json.loads(results_path.read_text(encoding="utf-8"))
    report["run"]["module"] = module
    results_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="only supports RUN evaluation results"):
        build_view_data(results_path)


def test_viewer_excludes_unused_sensitive_tool_arguments_and_results(tmp_path: Path) -> None:
    results_path = _run_fixture(tmp_path)
    report = json.loads(results_path.read_text(encoding="utf-8"))
    report["results"][0]["observability"]["tools"]["executed"][0].update(
        {
            "arguments": {"access_token": "PRIVATE_OBSERVABILITY_ARGUMENT_DO_NOT_EMBED"},
            "result": "PRIVATE_OBSERVABILITY_RESULT_DO_NOT_EMBED",
            "call_id": "PRIVATE_CALL_IDENTIFIER_DO_NOT_EMBED",
        }
    )
    results_path.write_text(json.dumps(report), encoding="utf-8")
    turns_path = tmp_path / "audio" / "restaurant_booking_complete" / "conversation.turns.jsonl"
    turns = [json.loads(line) for line in turns_path.read_text(encoding="utf-8").splitlines()]
    turns[1]["task"]["tool_calls"][0]["arguments"] = {"token": "PRIVATE_TRACE_ARGUMENT_DO_NOT_EMBED"}
    turns[1]["task"]["tool_calls"][1]["result"] = {"secret": "PRIVATE_TRACE_RESULT_DO_NOT_EMBED"}
    _write_jsonl(turns_path, turns)

    html = export_viewer(results_path).read_text(encoding="utf-8")

    assert "PRIVATE_OBSERVABILITY_ARGUMENT_DO_NOT_EMBED" not in html
    assert "PRIVATE_OBSERVABILITY_RESULT_DO_NOT_EMBED" not in html
    assert "PRIVATE_CALL_IDENTIFIER_DO_NOT_EMBED" not in html
    assert "PRIVATE_TRACE_ARGUMENT_DO_NOT_EMBED" not in html
    assert "PRIVATE_TRACE_RESULT_DO_NOT_EMBED" not in html
    assert "check_availability" in html


def test_viewer_does_not_export_retired_floor_decisions_from_protocol_log(tmp_path: Path) -> None:
    results_path = _run_fixture(tmp_path)
    events_path = tmp_path / "events" / "restaurant_booking_complete.jsonl"
    _write_jsonl(
        events_path,
        [
            {
                "source": "assistant_gpt_live",
                "event": {"type": "floor.decision", "private": "PRIVATE_FLOOR_DECISION"},
            }
        ],
    )

    scenario = build_view_data(results_path)["scenarios"][0]
    assert "floorDecisions" not in scenario
    assert all(event["kind"] != "floor" for event in scenario["eventAnnotations"])
    assert "PRIVATE_FLOOR_DECISION" not in export_viewer(results_path).read_text(encoding="utf-8")


def test_viewer_rejects_legacy_caller_results(tmp_path: Path) -> None:
    results_path = _run_fixture(tmp_path)
    report = json.loads(results_path.read_text(encoding="utf-8"))
    report["run"]["configuration"]["user_backend"] = "realtime"
    results_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="legacy RUN caller backends"):
        build_view_data(results_path)


def test_unknown_scenario_reports_the_requested_identifier(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not-a-real-scenario"):
        build_view_data(_run_fixture(tmp_path), scenario_id="not-a-real-scenario")


def test_export_viewer_embeds_audio_and_excludes_private_session_events(tmp_path: Path) -> None:
    output = export_viewer(_run_fixture(tmp_path))
    html = output.read_text(encoding="utf-8")

    assert output == tmp_path / "viewer.html"
    assert "data:audio/wav;base64," in html
    assert "DO_NOT_EMBED_PRIVATE_SESSION_INSTRUCTIONS" not in html
    assert "https://" not in html


def test_export_viewer_escapes_script_terminators_inside_transcripts(tmp_path: Path) -> None:
    output = export_viewer(_run_fixture(tmp_path, transcript="</script><img src=x onerror=alert(1)>"))

    assert "</script><img" not in output.read_text(encoding="utf-8")


def test_export_viewer_keeps_multiple_scenarios_available_for_selection(tmp_path: Path) -> None:
    result_path = _run_fixture(tmp_path, scenario_ids=("restaurant_booking_complete", "restaurant_cancel_authorized"))

    data = build_view_data(result_path)

    assert [scenario["id"] for scenario in data["scenarios"]] == [
        "restaurant_booking_complete",
        "restaurant_cancel_authorized",
    ]


def test_exported_viewer_exposes_accessible_transport_and_evidence_labels(tmp_path: Path) -> None:
    html = export_viewer(_run_fixture(tmp_path)).read_text(encoding="utf-8")

    assert "<title>Voice Evals · RUN conversation</title>" in html
    assert 'aria-label="Voice Evals conversation viewer"' in html
    assert "VOICE EVALS" in html
    assert "voice lab" not in html.casefold()
    assert 'aria-label="Play conversation"' in html
    assert "data-timeline" in html
    assert "Post-hoc inference" in html
    assert "Floor controlled" not in html


def test_exported_viewer_defaults_to_a_light_color_scheme(tmp_path: Path) -> None:
    html = export_viewer(_run_fixture(tmp_path)).read_text(encoding="utf-8")

    assert '<meta name="color-scheme" content="light">' in html
    assert "color-scheme: light;" in html


def test_main_writes_requested_scenario_and_custom_destination(tmp_path: Path) -> None:
    result_path = _run_fixture(tmp_path, scenario_ids=("restaurant_booking_complete", "restaurant_cancel_authorized"))
    destination = tmp_path / "custom" / "conversation.html"

    main(["--results", str(result_path), "--scenario", "restaurant_cancel_authorized", "--output", str(destination)])

    html = destination.read_text(encoding="utf-8")
    assert "restaurant_cancel_authorized" in html
    assert "restaurant_booking_complete" not in html


@pytest.mark.parametrize(
    "boundary",
    [
        "TOOL 320ms: name=check_availability status=completed",
        "BACKEND 320ms: target=responses status=completed",
        "DELEGATION 320ms: target=responses status=completed",
        "ASSISTANT 320..310ms: Invalid timing.",
    ],
)
def test_timestamped_transcript_preserves_assistant_first_and_multiline_responses(
    tmp_path: Path, boundary: str
) -> None:
    results = _run_fixture(tmp_path)
    details_path = tmp_path / "audio/restaurant_booking_complete/conversation.result.json"
    details = json.loads(details_path.read_text())
    details["transcript"] = (
        "ASSISTANT 10..80ms: Hello, I'm John.\n"
        "I'll help with your reservation.\n"
        "USER 100..180ms: I'd like a table.\n"
        "\nFor two, please.\n"
        "ASSISTANT 200..300ms: Let me check.\n"
        f"{boundary}\n"
        "This continuation is not speech.\n"
        "ASSISTANT 330..390ms: What time?\n"
        "USER 400..520ms [OVERLAP]: Mm-hmm\n"
        "ASSISTANT 520..800ms: \n"
        "Confirmed.\nYour reservation number is R-001."
    )
    details_path.write_text(json.dumps(details))
    rows = build_view_data(results)["scenarios"][0]["turns"]
    assert [(row["role"], row["startMs"]) for row in rows] == [
        ("assistant", 10),
        ("caller", 100),
        ("assistant", 200),
        ("assistant", 330),
        ("caller", 400),
        ("assistant", 520),
    ]
    assert rows[0]["text"] == "Hello, I'm John.\nI'll help with your reservation."
    assert "responseLatencyMs" not in rows[0]
    assert rows[1]["text"] == "I'd like a table.\n\nFor two, please."
    assert rows[2]["text"] == "Let me check."
    assert rows[2]["responseLatencyMs"] == 20
    assert rows[3]["text"] == "What time?"
    assert "responseLatencyMs" not in rows[3]
    assert rows[4]["action"] == "BACKCHANNEL"
    assert rows[5]["text"] == "\nConfirmed.\nYour reservation number is R-001."
