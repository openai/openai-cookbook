import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.graders import (
    build_audio_text_mismatch_grader,
    build_if_grader,
    build_stt_then_text_grader,
    build_template_grader,
    build_tool_call_arg_grader,
    build_tool_call_grader,
    build_tool_call_argument_grader,
    expected_args_subset,
    list_template_graders,
)


def test_expected_args_subset_normalizes_address_and_order_id() -> None:
    assert expected_args_subset(
        {
            "order_id": "ORD-3003",
            "new_address": "12 Harbor St, Apt 4B, Seattle, WA 98101",
        },
        {
            "order_id": "ord 3003",
            "new_address": "12 Harbor Street Apt 4B Seattle Washington 98101",
            "extra_field": "ignored",
        },
    )


def test_build_tool_call_graders_return_expected_shapes() -> None:
    assert build_tool_call_grader("check_tool") == {
        "id": "check_tool",
        "type": "tool_call",
    }
    assert build_tool_call_arg_grader("check_args") == {
        "id": "check_args",
        "type": "tool_call_args",
    }
    assert build_tool_call_argument_grader("alias_args") == {
        "id": "alias_args",
        "type": "tool_call_args",
    }


def test_build_if_grader_contains_condition_logic() -> None:
    grader = build_if_grader(
        "needs_follow_up",
        "The assistant says it will send a confirmation email.",
        "The assistant also states when the email will arrive.",
        when_condition_false_grade=1,
    )

    assert grader["id"] == "needs_follow_up"
    assert grader["type"] == "llm_as_judge"
    assert "The assistant says it will send a confirmation email." in grader["criteria"]
    assert "The assistant also states when the email will arrive." in grader["criteria"]
    assert "If the condition is false, return grade 1" in grader["criteria"]


def test_build_audio_text_mismatch_grader_mentions_both_sources() -> None:
    grader = build_audio_text_mismatch_grader(
        "assistant_alignment",
        audio_source="assistant audio transcript",
        text_source="assistant text response",
    )

    assert grader["type"] == "llm_as_judge"
    assert "assistant audio transcript" in grader["criteria"]
    assert "assistant text response" in grader["criteria"]
    assert "names, order IDs, addresses, dates" in grader["criteria"]


def test_build_stt_then_text_grader_uses_transcript_as_source_of_truth() -> None:
    grader = build_stt_then_text_grader(
        "refund_request_understanding",
        "whether the assistant correctly understands and addresses the refund request",
    )

    assert grader["type"] == "llm_as_judge"
    assert "speech-to-text transcript as the source of truth" in grader["criteria"]
    assert "assistant text" in grader["criteria"]
    assert "refund request" in grader["criteria"]


def test_list_template_graders_and_dispatch_builder() -> None:
    templates = list_template_graders()

    assert "tool_call" in templates
    assert "audio_text_mismatch" in templates

    grader = build_template_grader(
        "stt_then_text",
        "status_request",
        evaluation_target="whether the assistant answers the order status question",
    )
    assert grader["id"] == "status_request"
    assert grader["type"] == "llm_as_judge"


def test_build_template_grader_rejects_unknown_template() -> None:
    try:
        build_template_grader("missing_template", "bad_grader")
    except ValueError as exc:
        assert "Unsupported grader template" in str(exc)
    else:
        raise AssertionError("Expected unsupported template lookup to fail")
