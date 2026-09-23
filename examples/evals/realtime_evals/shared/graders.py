"""Reusable default graders for realtime eval harnesses.

Design notes:
- Every grader returns the same shape: `(passed: bool, reason: str)`.
- Deterministic graders do not call a model.
- Model-based graders take an OpenAI client plus the smallest possible inputs.
- Audio-byte helpers are convenience wrappers for harnesses that only have raw
  PCM16 bytes and want this module to handle transcription first.
- `run_default_grader(...)` is the smallest shared integration surface for the
  core named graders in `DEFAULT_GRADER_FUNCTIONS`.
"""

import json
import re
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

from shared.result_types import ToolCallRecord

DEFAULT_GRADER_MODEL = "gpt-5.2"
DEFAULT_GRADER_REASONING_EFFORT = "none"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"

PASS_FAIL_REASON_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "pass": {"type": "boolean"},
    },
    "required": ["reason", "pass"],
    "additionalProperties": False,
}

INSTRUCTION_FOLLOWING_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "adheres_to_instructions": {"type": "boolean"},
    },
    "required": ["reason", "adheres_to_instructions"],
    "additionalProperties": False,
}

GENERAL_RUBRIC_GRADER_SYSTEM_PROMPT = """You are an expert evaluator.

You will receive:
1. InputContext: the information the model had available.
2. Output: the model response being graded.
3. Criteria: the single requirement being graded.

Task:
Determine whether the Output satisfies the Criteria using the InputContext only.

Guidelines:
- Grade exactly one thing: the provided Criteria.
- Use the InputContext only as context for the Output. Do not grade the
  InputContext itself.
- Ignore unrelated quality issues.
- Pass when the Output meets the Criteria within reasonably tight bounds.
- Fail when there is clear evidence that the Criteria is not met.
- If the evidence is ambiguous, prefer pass unless the Criteria explicitly says
  to be strict.

Return JSON matching the schema exactly.
""".strip()

INSTRUCTION_FOLLOWING_GRADER_SYSTEM_PROMPT = """You are an Instruction-Adherence Assessor.

Inputs:
1. instructions: the full set of rules the model had to follow.
2. response: the model's generated answer.

Task:
Determine whether the response clearly follows all mandatory rules in the
instructions.

Evaluation guidelines:
- Return true only when there are no obvious violations of mandatory rules.
- Treat guidance words like should or try as non-mandatory.
- Ignore minor style issues and subjective quality concerns if they do not
  break an explicit rule.
- If very uncertain, choose false.
- Focus on rule-breaking, not general usefulness or factual accuracy.
- Verify that the rule exists in the instructions before marking a violation.

Return JSON matching the schema exactly.
""".strip()

AUDIO_TEXT_MISMATCH_GRADER_SYSTEM_PROMPT = """You are grading AUDIO/TEXT MATCH, not general response quality.

Your only job is to decide whether the synthesized audio says the same thing as
the assistant text.

You will be shown:
- <assistant_text>: the intended assistant response text
- <audio_transcript>: an ASR transcript of the synthesized audio output

Decision policy:
1. Normalize harmless differences: casing, whitespace, punctuation,
   contractions, disfluencies, minor ASR substitutions, and light rephrasing.
2. Compare the semantic content of the two inputs.
3. Return pass = false only when there is a material mismatch.
4. Material mismatches include differences in names, order IDs, addresses,
   dates, quantities, prices, tool results, commitments, or the final user-facing
   action the assistant asks the user to take.
5. Return pass = true when differences are minor ASR noise and the meaning is
   preserved.

Reason requirements:
- Keep the reason short and specific.
- For failures, name the key mismatched detail.

Return JSON matching the schema exactly.
""".strip()

STT_THEN_TEXT_GRADER_SYSTEM_PROMPT = """You are grading a text response against a speech transcript.

You will be shown:
- <user_audio_transcript>: a speech-to-text transcript of what the user said
- <assistant_text>: the assistant response text
- <criteria>: the single requirement being graded

Task:
Use the user_audio_transcript as the source of truth for what the user said,
then decide whether the assistant_text satisfies the criteria.

Guidelines:
- Grade exactly one thing: the provided criteria.
- Ignore audio quality, pronunciation, and minor STT artifacts that do not
  change meaning.
- Ignore unrelated response quality issues.
- Pass when the criterion is satisfied within reasonably tight bounds.
- Fail only when there is clear evidence that the assistant_text misses the
  criterion.

Return JSON matching the schema exactly.
""".strip()


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
    return " ".join(substitutions.get(token, token) for token in tokens).strip()


def normalize_order_id(order_id: str) -> str:
    return normalize_text(order_id).replace(" ", "")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _serialize_for_grader(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, indent=2, ensure_ascii=True)
    except TypeError:
        return str(value)


def _parse_json_object(output_text: str) -> Dict[str, Any]:
    if not output_text:
        return {}
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _parse_bool_field(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    return None


def _run_json_schema_grader(
    client: Any,
    system_prompt: str,
    user_content: str,
    schema_name: str,
    schema: Dict[str, Any],
    *,
    model: str,
    reasoning_effort: str | None,
) -> Dict[str, Any]:
    request_kwargs: Dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }
    if reasoning_effort is not None:
        request_kwargs["reasoning"] = {"effort": reasoning_effort}

    completion = client.responses.create(**request_kwargs)
    return _parse_json_object(getattr(completion, "output_text", ""))


def _tool_call_name(tool_call: ToolCallRecord | Mapping[str, Any]) -> str:
    if isinstance(tool_call, ToolCallRecord):
        return tool_call.name
    return str(tool_call.get("name", ""))


def _tool_call_arguments(
    tool_call: ToolCallRecord | Mapping[str, Any],
) -> Dict[str, Any]:
    if isinstance(tool_call, ToolCallRecord):
        return tool_call.arguments
    arguments = tool_call.get("arguments", {})
    return arguments if isinstance(arguments, dict) else {}


def expected_args_subset(
    expected_args: Dict[str, Any], actual_args: Dict[str, Any]
) -> bool:
    def values_match(expected_value: Any, actual_value: Any) -> bool:
        if isinstance(expected_value, dict):
            if not isinstance(actual_value, dict):
                return False
            return expected_args_subset(expected_value, actual_value)

        if isinstance(expected_value, list):
            if not isinstance(actual_value, list):
                return False
            if len(expected_value) > len(actual_value):
                return False
            return all(
                values_match(expected_item, actual_item)
                for expected_item, actual_item in zip(expected_value, actual_value)
            )

        if isinstance(expected_value, bool) or isinstance(actual_value, bool):
            return expected_value is actual_value

        if isinstance(expected_value, (int, float)) and isinstance(
            actual_value, (int, float)
        ):
            return expected_value == actual_value

        expected_text = str(expected_value)
        actual_text = str(actual_value)
        return normalize_text(expected_text) == normalize_text(actual_text)

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
        elif not values_match(expected_value, actual_value):
            return False
    return True


def check_tool_call_names_correct(
    tool_calls: Sequence[ToolCallRecord | Mapping[str, Any]],
    expected_tool_names: Sequence[str],
) -> tuple[bool, str]:
    """Deterministically verify that the set of called tool names matches."""

    expected_names = [name.strip() for name in expected_tool_names if name.strip()]
    actual_names = [_tool_call_name(tool_call) for tool_call in tool_calls]

    if not actual_names and not expected_names:
        return True, ""
    if not actual_names:
        return False, f"No tool calls found. Expected {expected_names}."
    if set(actual_names) != set(expected_names):
        return (
            False,
            f"Tool calls do not match. Expected {expected_names}, got {actual_names}.",
        )
    return True, ""


def check_tool_args_correct(
    tool_calls: Sequence[ToolCallRecord | Mapping[str, Any]],
    expected_tool_name: str,
    expected_args: Mapping[str, Any],
) -> tuple[bool, str]:
    """Deterministically verify that a named tool call includes expected args."""

    for tool_call in tool_calls:
        if _tool_call_name(tool_call) != expected_tool_name:
            continue
        actual_args = _tool_call_arguments(tool_call)
        if expected_args_subset(dict(expected_args), actual_args):
            return True, ""
        return (
            False,
            f"Arguments for {expected_tool_name} did not match. "
            f"Expected subset {dict(expected_args)}, got {actual_args}.",
        )

    return False, f"Expected tool call {expected_tool_name} was not found."


def check_rubric_model_grader(
    client: Any,
    input_context: Any,
    response_text: str,
    criteria: str,
    *,
    model: str = DEFAULT_GRADER_MODEL,
    reasoning_effort: str | None = DEFAULT_GRADER_REASONING_EFFORT,
) -> tuple[bool, str]:
    """Grade a single criterion against a model response using strict JSON output."""

    grader_input = (
        f"<InputContext>\n{_serialize_for_grader(input_context)}\n</InputContext>\n\n"
        f"<Output>\n{response_text.strip()}\n</Output>\n\n"
        f"<Criteria>\n{criteria.strip()}\n</Criteria>"
    )
    response_data = _run_json_schema_grader(
        client,
        GENERAL_RUBRIC_GRADER_SYSTEM_PROMPT,
        grader_input,
        "rubric_grader_result",
        PASS_FAIL_REASON_SCHEMA,
        model=model,
        reasoning_effort=reasoning_effort,
    )

    reason = str(response_data.get("reason", "")).strip()
    final_answer = _parse_bool_field(response_data.get("pass"))
    if final_answer is None:
        return False, "Invalid grader response: missing boolean pass field."
    return final_answer, reason


def check_instruction_following_model_grader(
    client: Any,
    instructions: str,
    response_text: str,
    *,
    model: str = DEFAULT_GRADER_MODEL,
    reasoning_effort: str | None = DEFAULT_GRADER_REASONING_EFFORT,
) -> tuple[bool, str]:
    """Instruction-following (IF) grader for assistant text outputs."""

    grader_input = (
        f"<instructions>\n{instructions.strip()}\n</instructions>\n\n"
        f"<response>\n{response_text.strip()}\n</response>"
    )
    response_data = _run_json_schema_grader(
        client,
        INSTRUCTION_FOLLOWING_GRADER_SYSTEM_PROMPT,
        grader_input,
        "instruction_following_result",
        INSTRUCTION_FOLLOWING_SCHEMA,
        model=model,
        reasoning_effort=reasoning_effort,
    )

    reason = str(response_data.get("reason", "")).strip()
    final_answer = _parse_bool_field(response_data.get("adheres_to_instructions"))
    if final_answer is None:
        return (
            False,
            "Invalid grader response: missing boolean adheres_to_instructions field.",
        )
    return final_answer, reason


def grade_audio_text_mismatch(
    client: Any,
    assistant_text: str,
    audio_transcript: str,
    *,
    model: str = DEFAULT_GRADER_MODEL,
    reasoning_effort: str | None = DEFAULT_GRADER_REASONING_EFFORT,
) -> tuple[bool, str]:
    """Check whether synthesized audio matches the assistant text semantically."""

    grader_input = (
        f"<assistant_text>\n{assistant_text.strip()}\n</assistant_text>\n\n"
        f"<audio_transcript>\n{audio_transcript.strip()}\n</audio_transcript>"
    )
    response_data = _run_json_schema_grader(
        client,
        AUDIO_TEXT_MISMATCH_GRADER_SYSTEM_PROMPT,
        grader_input,
        "audio_text_mismatch_result",
        PASS_FAIL_REASON_SCHEMA,
        model=model,
        reasoning_effort=reasoning_effort,
    )

    reason = str(response_data.get("reason", "")).strip()
    final_answer = _parse_bool_field(response_data.get("pass"))
    if final_answer is None:
        return False, "Invalid grader response: missing boolean pass field."
    return final_answer, reason


def grade_stt_then_text(
    client: Any,
    user_audio_transcript: str,
    assistant_text: str,
    criteria: str,
    *,
    model: str = DEFAULT_GRADER_MODEL,
    reasoning_effort: str | None = DEFAULT_GRADER_REASONING_EFFORT,
) -> tuple[bool, str]:
    """Grade assistant text against an STT transcript treated as source of truth."""

    grader_input = (
        f"<user_audio_transcript>\n{user_audio_transcript.strip()}\n"
        f"</user_audio_transcript>\n\n"
        f"<assistant_text>\n{assistant_text.strip()}\n</assistant_text>\n\n"
        f"<criteria>\n{criteria.strip()}\n</criteria>"
    )
    response_data = _run_json_schema_grader(
        client,
        STT_THEN_TEXT_GRADER_SYSTEM_PROMPT,
        grader_input,
        "stt_then_text_result",
        PASS_FAIL_REASON_SCHEMA,
        model=model,
        reasoning_effort=reasoning_effort,
    )

    reason = str(response_data.get("reason", "")).strip()
    final_answer = _parse_bool_field(response_data.get("pass"))
    if final_answer is None:
        return False, "Invalid grader response: missing boolean pass field."
    return final_answer, reason


def _write_pcm16_audio_bytes_to_temp_wav(
    audio_bytes: bytes,
    sample_rate_hz: int,
) -> Path:
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = Path(temp_file.name)
    temp_file.close()

    with wave.open(str(temp_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(audio_bytes)

    return temp_path


def transcribe_model_response_audio(
    client: Any,
    audio_bytes: bytes | None,
    sample_rate_hz: int,
    *,
    transcription_model: str = DEFAULT_TRANSCRIPTION_MODEL,
) -> tuple[bool, str]:
    """Transcribe PCM16 mono audio bytes from a realtime model response."""

    if not audio_bytes:
        return False, "No audio returned by the model response."

    wav_path = _write_pcm16_audio_bytes_to_temp_wav(audio_bytes, sample_rate_hz)
    try:
        with wav_path.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=transcription_model,
                file=audio_file,
            )
        transcript_text = _normalize_whitespace(getattr(transcription, "text", ""))
        if not transcript_text:
            return False, "Transcription returned empty text."
        return True, transcript_text
    except (
        APIConnectionError,
        APITimeoutError,
        RateLimitError,
        APIError,
        OSError,
    ) as error:
        return False, f"Unable to transcribe audio: {error}"
    finally:
        wav_path.unlink(missing_ok=True)


def grade_audio_text_mismatch_from_model_response(
    client: Any,
    assistant_text: str,
    audio_bytes: bytes | None,
    sample_rate_hz: int,
    *,
    grade_model: str = DEFAULT_GRADER_MODEL,
    grade_reasoning_effort: str | None = DEFAULT_GRADER_REASONING_EFFORT,
    transcription_model: str = DEFAULT_TRANSCRIPTION_MODEL,
) -> tuple[bool, str]:
    """Transcribe assistant audio bytes, then grade transcript/text alignment."""

    transcribed, transcript_or_reason = transcribe_model_response_audio(
        client,
        audio_bytes,
        sample_rate_hz,
        transcription_model=transcription_model,
    )
    if not transcribed:
        return False, transcript_or_reason
    return grade_audio_text_mismatch(
        client,
        assistant_text,
        transcript_or_reason,
        model=grade_model,
        reasoning_effort=grade_reasoning_effort,
    )


def grade_stt_then_text_from_model_response(
    client: Any,
    user_audio_bytes: bytes | None,
    sample_rate_hz: int,
    assistant_text: str,
    criteria: str,
    *,
    grade_model: str = DEFAULT_GRADER_MODEL,
    grade_reasoning_effort: str | None = DEFAULT_GRADER_REASONING_EFFORT,
    transcription_model: str = DEFAULT_TRANSCRIPTION_MODEL,
) -> tuple[bool, str]:
    """Transcribe user audio bytes, then grade assistant text against that STT."""

    transcribed, transcript_or_reason = transcribe_model_response_audio(
        client,
        user_audio_bytes,
        sample_rate_hz,
        transcription_model=transcription_model,
    )
    if not transcribed:
        return False, transcript_or_reason
    return grade_stt_then_text(
        client,
        transcript_or_reason,
        assistant_text,
        criteria,
        model=grade_model,
        reasoning_effort=grade_reasoning_effort,
    )


DEFAULT_GRADER_FUNCTIONS: Dict[str, Any] = {
    "tool_call": check_tool_call_names_correct,
    "tool_call_args": check_tool_args_correct,
    "rubric": check_rubric_model_grader,
    "instruction_following": check_instruction_following_model_grader,
    "audio_text_mismatch": grade_audio_text_mismatch,
    "stt_then_text": grade_stt_then_text,
}

DEFAULT_GRADER_SPECS: Dict[str, Dict[str, Any]] = {
    "tool_call": {
        "summary": "Deterministic grader for whether the expected tool names were called.",
        "required_kwargs": ("tool_calls", "expected_tool_names"),
    },
    "tool_call_args": {
        "summary": "Deterministic grader for whether a named tool call includes the expected argument subset.",
        "required_kwargs": ("tool_calls", "expected_tool_name", "expected_args"),
    },
    "rubric": {
        "summary": "Generic LLM-as-judge grader for one explicit criterion.",
        "required_kwargs": ("client", "input_context", "response_text", "criteria"),
    },
    "instruction_following": {
        "summary": "LLM-as-judge grader for whether a response obeys instructions.",
        "required_kwargs": ("client", "instructions", "response_text"),
    },
    "audio_text_mismatch": {
        "summary": "LLM-as-judge grader that compares assistant text to an existing audio transcript.",
        "required_kwargs": ("client", "assistant_text", "audio_transcript"),
    },
    "stt_then_text": {
        "summary": "LLM-as-judge grader that treats a provided STT transcript as source of truth.",
        "required_kwargs": ("client", "user_audio_transcript", "assistant_text", "criteria"),
    },
}


def run_default_grader(grader_name: str, /, **kwargs: Any) -> tuple[bool, str]:
    """Run a named default grader through a shared registry.

    Intended usage:
    1. Pick one of the names in DEFAULT_GRADER_FUNCTIONS.
    2. Look up the expected kwargs in DEFAULT_GRADER_SPECS.
    3. Forward only those kwargs from the harness.

    If a harness only has raw audio bytes rather than a transcript, call
    `grade_audio_text_mismatch_from_model_response(...)` or
    `grade_stt_then_text_from_model_response(...)` directly instead of routing
    through this registry.
    """

    grader = DEFAULT_GRADER_FUNCTIONS.get(grader_name.strip())
    if grader is None:
        supported = ", ".join(sorted(DEFAULT_GRADER_FUNCTIONS))
        return False, f"Unsupported grader '{grader_name}'. Supported: {supported}"
    return grader(**kwargs)


def compute_tool_call_grade(
    expected_tool_name: str,
    expected_tool_args_text: str,
    tool_calls: Sequence[ToolCallRecord | Mapping[str, Any]],
) -> Dict[str, Any]:
    """Compatibility helper used by the existing realtime harness scripts."""

    expected_tool_name = expected_tool_name.strip()
    expected_args = parse_json_dict(expected_tool_args_text.strip())

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
            "pred_tool_call": _tool_call_name(first_call),
            "pred_tool_call_arg": json.dumps(_tool_call_arguments(first_call)),
        }

    tool_name_correct, _ = check_tool_call_names_correct(
        tool_calls, [expected_tool_name]
    )
    tool_args_correct, _ = check_tool_args_correct(
        tool_calls, expected_tool_name, expected_args
    )

    matching_call = None
    for tool_call in tool_calls:
        if _tool_call_name(tool_call) == expected_tool_name:
            matching_call = tool_call
            break

    if matching_call is None:
        first_call = tool_calls[0] if tool_calls else {}
        return {
            "tool_call_correctness": int(tool_name_correct),
            "tool_call_arg_correctness": int(tool_args_correct),
            "pred_tool_call": _tool_call_name(first_call),
            "pred_tool_call_arg": json.dumps(_tool_call_arguments(first_call)),
        }

    actual_args = _tool_call_arguments(matching_call)
    return {
        "tool_call_correctness": int(tool_name_correct),
        "tool_call_arg_correctness": int(tool_args_correct),
        "pred_tool_call": _tool_call_name(matching_call),
        "pred_tool_call_arg": json.dumps(actual_args),
    }
