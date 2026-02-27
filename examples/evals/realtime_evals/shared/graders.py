import json
import re
import textwrap
from typing import Any, Callable, Dict, Mapping, Sequence

from shared.result_types import ToolCallRecord


TemplateGraderBuilder = Callable[..., Dict[str, Any]]


def parse_json_dict(json_text: str) -> Dict[str, Any]:
    if not json_text:
        return {}
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower().strip()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_address(address: str) -> str:
    normalized = normalize_text(address)
    tokens = normalized.split()
    substitutions = {
        "st": "street",
        "ave": "avenue",
        "blvd": "boulevard",
        "rd": "road",
        "dr": "drive",
        "ln": "lane",
        "ct": "court",
        "tx": "texas",
        "ca": "california",
        "ny": "new york",
        "wa": "washington",
    }
    expanded_tokens = []
    for token in tokens:
        expanded_tokens.append(substitutions.get(token, token))
    return " ".join(expanded_tokens).strip()


def normalize_order_id(order_id: str) -> str:
    return normalize_text(order_id).replace(" ", "")


def _normalize_criteria_text(text: str) -> str:
    return textwrap.dedent(text).strip()


def build_llm_as_judge_grader(
    grader_id: str,
    criteria: str,
    *,
    model: str = "",
) -> Dict[str, Any]:
    grader = {
        "id": grader_id.strip(),
        "type": "llm_as_judge",
        "criteria": _normalize_criteria_text(criteria),
    }
    if model.strip():
        grader["model"] = model.strip()
    return grader


def build_tool_call_grader(grader_id: str = "tool_call") -> Dict[str, Any]:
    return {"id": grader_id.strip(), "type": "tool_call"}


def build_tool_call_arg_grader(grader_id: str = "tool_call_args") -> Dict[str, Any]:
    return {"id": grader_id.strip(), "type": "tool_call_args"}


def build_if_grader(
    grader_id: str,
    condition: str,
    requirement: str,
    *,
    model: str = "",
    when_condition_false_grade: int = 1,
    out_of_scope: str = "",
) -> Dict[str, Any]:
    if when_condition_false_grade not in (0, 1):
        raise ValueError("when_condition_false_grade must be 0 or 1")

    condition_false_rule = (
        "If the condition is false, return grade 1 because this check does not apply."
        if when_condition_false_grade == 1
        else "If the condition is false, return grade 0 because the required "
        "condition never happened."
    )
    out_of_scope_text = (
        out_of_scope.strip()
        or "Everything unrelated to this conditional requirement."
    )

    criteria = f"""
    Grade exactly one thing: whether a conditional requirement is satisfied.

    Inputs:
    - The provided conversation context only.

    Source of truth:
    - Use only the provided context. Do not invent missing turns or hidden state.

    Condition:
    - {condition.strip()}

    Requirement when the condition is true:
    - {requirement.strip()}

    Out of scope:
    - {out_of_scope_text}

    Decision process:
    1. Determine whether the condition is true.
    2. If the condition is true, pass only if the requirement is satisfied.
    3. {condition_false_rule}
    4. Ignore minor wording differences that do not change meaning.

    Tie-breaker:
    - Pass unless failure evidence is clear.
    """
    return build_llm_as_judge_grader(grader_id, criteria, model=model)


def build_audio_text_mismatch_grader(
    grader_id: str = "audio_text_mismatch",
    *,
    model: str = "",
    audio_source: str = "assistant audio transcript",
    text_source: str = "assistant text",
) -> Dict[str, Any]:
    criteria = f"""
    Grade exactly one thing: whether the spoken content and text content match.

    Inputs:
    - {audio_source.strip()}
    - {text_source.strip()}

    Source of truth:
    - Compare the two inputs against each other. Neither input has priority.

    Fail if:
    - The two inputs differ in meaning.
    - They disagree on names, order IDs, addresses, dates, quantities, prices,
      tool results, commitments, or any safety-relevant content.

    Ignore:
    - Casing, punctuation, filler words, disfluencies, small STT artifacts,
      and harmless paraphrases that preserve the same meaning.

    Decision process:
    1. Normalize obvious transcription noise.
    2. Compare the semantic content of the audio transcript and the text.
    3. Fail on any material mismatch.
    4. Pass otherwise.

    Tie-breaker:
    - Pass unless mismatch evidence is clear.
    """
    return build_llm_as_judge_grader(grader_id, criteria, model=model)


def build_stt_then_text_grader(
    grader_id: str,
    evaluation_target: str,
    *,
    model: str = "",
    transcript_source: str = "speech-to-text transcript of the user audio",
    assistant_text_source: str = "assistant text",
    out_of_scope: str = "",
) -> Dict[str, Any]:
    out_of_scope_text = (
        out_of_scope.strip()
        or "Audio quality, pronunciation, speaking style, and anything unrelated to "
        "the evaluation target."
    )
    criteria = f"""
    Grade exactly one thing: {evaluation_target.strip()}

    Inputs:
    - {transcript_source.strip()}
    - {assistant_text_source.strip()}

    Source of truth:
    - Use the speech-to-text transcript as the source of truth for what the user said.
    - Grade the assistant text against that transcript.

    Ignore:
    - STT filler artifacts, repeated words, hesitations, and minor punctuation issues
      that do not change meaning.

    Out of scope:
    - {out_of_scope_text}

    Decision process:
    1. Read the transcript to determine the user's actual request.
    2. Check whether the assistant text satisfies the evaluation target.
    3. Ignore harmless STT noise and wording differences.
    4. Fail only when the assistant text clearly misses the target.

    Tie-breaker:
    - Pass unless failure evidence is clear.
    """
    return build_llm_as_judge_grader(grader_id, criteria, model=model)


def list_template_graders() -> Dict[str, str]:
    return {
        "tool_call": "Deterministic check for whether the expected tool was called.",
        "tool_call_args": "Deterministic check for whether expected tool arguments match.",
        "if": "LLM-as-judge template for conditional 'if X, then Y' requirements.",
        "audio_text_mismatch": "LLM-as-judge template that compares audio transcript and text output.",
        "stt_then_text": "LLM-as-judge template that treats STT transcript as source of truth for grading text behavior.",
    }


def build_template_grader(
    template_name: str,
    grader_id: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    builders: Dict[str, TemplateGraderBuilder] = {
        "tool_call": build_tool_call_grader,
        "tool_call_args": build_tool_call_arg_grader,
        "if": build_if_grader,
        "audio_text_mismatch": build_audio_text_mismatch_grader,
        "stt_then_text": build_stt_then_text_grader,
    }
    builder = builders.get(template_name.strip())
    if builder is None:
        supported = ", ".join(sorted(builders))
        raise ValueError(
            f"Unsupported grader template '{template_name}'. "
            f"Supported templates: {supported}"
        )
    if template_name in {"tool_call", "tool_call_args"}:
        return builder(grader_id=grader_id)
    return builder(grader_id=grader_id, **kwargs)


build_tool_call_argument_grader = build_tool_call_arg_grader


def expected_args_subset(
    expected_args: Dict[str, Any], actual_args: Dict[str, Any]
) -> bool:
    for key, expected_value in expected_args.items():
        if key not in actual_args:
            return False
        actual_value = actual_args.get(key)
        if key == "new_address":
            if normalize_address(str(expected_value)) != normalize_address(
                str(actual_value)
            ):
                return False
        elif key == "order_id":
            if normalize_order_id(str(expected_value)) != normalize_order_id(
                str(actual_value)
            ):
                return False
        else:
            if normalize_text(str(expected_value)) != normalize_text(str(actual_value)):
                return False
    return True


def compute_tool_call_grade(
    expected_tool_name: str,
    expected_tool_args_text: str,
    tool_calls: Sequence[ToolCallRecord | Mapping[str, Any]],
) -> Dict[str, Any]:
    expected_tool_name = expected_tool_name.strip()
    expected_args = parse_json_dict(expected_tool_args_text.strip())

    def get_tool_name(tool_call: ToolCallRecord | Mapping[str, Any]) -> str:
        if isinstance(tool_call, ToolCallRecord):
            return tool_call.name
        return str(tool_call.get("name", ""))

    def get_tool_arguments(
        tool_call: ToolCallRecord | Mapping[str, Any],
    ) -> Dict[str, Any]:
        if isinstance(tool_call, ToolCallRecord):
            return tool_call.arguments
        arguments = tool_call.get("arguments", {})
        return arguments if isinstance(arguments, dict) else {}

    if not expected_tool_name:
        if not tool_calls:
            return {
                "tool_call_correctness": 1,
                "tool_call_arg_correctness": 1,
                "pred_tool_call": "",
                "pred_tool_call_arg": "",
            }
        first_call = tool_calls[0]
        return {
            "tool_call_correctness": 0,
            "tool_call_arg_correctness": 0,
            "pred_tool_call": get_tool_name(first_call),
            "pred_tool_call_arg": json.dumps(get_tool_arguments(first_call)),
        }

    matching_call = None
    for call in tool_calls:
        if get_tool_name(call) == expected_tool_name:
            matching_call = call
            break

    if not matching_call:
        first_call = tool_calls[0] if tool_calls else {}
        return {
            "tool_call_correctness": 0,
            "tool_call_arg_correctness": 0,
            "pred_tool_call": get_tool_name(first_call),
            "pred_tool_call_arg": json.dumps(get_tool_arguments(first_call)),
        }

    actual_args = get_tool_arguments(matching_call)
    if expected_args:
        args_match = 1 if expected_args_subset(expected_args, actual_args) else 0
    else:
        args_match = 1

    return {
        "tool_call_correctness": 1,
        "tool_call_arg_correctness": args_match,
        "pred_tool_call": get_tool_name(matching_call),
        "pred_tool_call_arg": json.dumps(actual_args),
    }
