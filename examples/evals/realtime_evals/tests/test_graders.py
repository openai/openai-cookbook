import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.graders import (
    AUDIO_TEXT_MISMATCH_GRADER_SYSTEM_PROMPT,
    DEFAULT_GRADER_FUNCTIONS,
    DEFAULT_GRADER_MODEL,
    DEFAULT_GRADER_SPECS,
    DEFAULT_TRANSCRIPTION_MODEL,
    INSTRUCTION_FOLLOWING_GRADER_SYSTEM_PROMPT,
    STT_THEN_TEXT_GRADER_SYSTEM_PROMPT,
    check_instruction_following_model_grader,
    check_tool_args_correct,
    check_tool_call_names_correct,
    compute_tool_call_grade,
    grade_audio_text_mismatch,
    grade_audio_text_mismatch_from_model_response,
    grade_stt_then_text,
    grade_stt_then_text_from_model_response,
    run_default_grader,
    transcribe_model_response_audio,
)


class FakeCompletion:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class FakeResponsesAPI:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeCompletion(self.output_text)


class FakeTranscriptionsAPI:
    def __init__(self, transcript_text: str) -> None:
        self.transcript_text = transcript_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        audio_file = kwargs["file"]
        audio_bytes = audio_file.read()
        self.calls.append(
            {
                "model": kwargs["model"],
                "filename": Path(audio_file.name).name,
                "audio_size": len(audio_bytes),
            }
        )
        audio_file.seek(0)
        return type("Transcription", (), {"text": self.transcript_text})()


class FakeAudioAPI:
    def __init__(self, transcript_text: str) -> None:
        self.transcriptions = FakeTranscriptionsAPI(transcript_text)


class FakeClient:
    def __init__(self, grader_output_text: str = "", transcript_text: str = "") -> None:
        self.responses = FakeResponsesAPI(grader_output_text)
        self.audio = FakeAudioAPI(transcript_text)


def test_check_tool_call_names_correct_matches_expected_set() -> None:
    passed, reason = check_tool_call_names_correct(
        [{"name": "lookup_order"}, {"name": "send_email"}],
        ["send_email", "lookup_order"],
    )

    assert passed is True
    assert reason == ""


def test_check_tool_args_correct_normalizes_addresses() -> None:
    passed, reason = check_tool_args_correct(
        [
            {
                "name": "update_shipping_address",
                "arguments": {
                    "order_id": "ord 3003",
                    "new_address": "12 Harbor Street Apt 4B Seattle Washington 98101",
                },
            }
        ],
        "update_shipping_address",
        {
            "order_id": "ORD-3003",
            "new_address": "12 Harbor St, Apt 4B, Seattle, WA 98101",
        },
    )

    assert passed is True
    assert reason == ""


def test_check_tool_args_correct_handles_nested_json_arguments() -> None:
    passed, reason = check_tool_args_correct(
        [
            {
                "name": "create_ticket",
                "arguments": {
                    "customer": {
                        "order_id": "ORD-4004",
                        "address": {"city": "Seattle", "state": "WA"},
                    },
                    "items": [
                        {"sku": "sku-1", "quantity": 2},
                        {"sku": "sku-2", "quantity": 1, "notes": "gift wrap"},
                    ],
                    "expedite": False,
                },
            }
        ],
        "create_ticket",
        {
            "customer": {
                "order_id": "ord 4004",
                "address": {"city": "Seattle"},
            },
            "items": [
                {"sku": "SKU-1", "quantity": 2},
                {"sku": "sku-2"},
            ],
            "expedite": False,
        },
    )

    assert passed is True
    assert reason == ""


def test_compute_tool_call_grade_uses_deterministic_graders() -> None:
    result = compute_tool_call_grade(
        "get_order_status",
        '{"order_id": "ORD-1001"}',
        [{"name": "get_order_status", "arguments": {"order_id": "ORD-1001"}}],
    )

    assert result["tool_call_correctness"] == 1
    assert result["tool_call_arg_correctness"] == 1
    assert result["pred_tool_call"] == "get_order_status"


def test_instruction_following_grader_uses_instruction_prompt_and_schema() -> None:
    client = FakeClient(
        grader_output_text='{"adheres_to_instructions": true, "reason": "All mandatory rules were followed."}'
    )

    passed, reason = check_instruction_following_model_grader(
        client,
        instructions="Use exactly three bullet points and do not mention pricing.",
        response_text="- A\\n- B\\n- C",
    )

    assert passed is True
    assert reason == "All mandatory rules were followed."
    request = client.responses.calls[0]
    assert request["input"][0]["content"] == INSTRUCTION_FOLLOWING_GRADER_SYSTEM_PROMPT
    assert request["text"]["format"]["schema"]["required"] == [
        "reason",
        "adheres_to_instructions",
    ]
    assert request["model"] == DEFAULT_GRADER_MODEL


def test_audio_text_mismatch_grader_uses_specialized_prompt() -> None:
    client = FakeClient(
        grader_output_text='{"pass": false, "reason": "Audio says ORD-1002 while text says ORD-1001."}'
    )

    passed, reason = grade_audio_text_mismatch(
        client,
        assistant_text="Your order ORD-1001 will arrive tomorrow.",
        audio_transcript="Your order ORD-1002 will arrive tomorrow.",
    )

    assert passed is False
    assert "ORD-1002" in reason
    request = client.responses.calls[0]
    assert request["input"][0]["content"] == AUDIO_TEXT_MISMATCH_GRADER_SYSTEM_PROMPT


def test_stt_then_text_grader_uses_transcript_as_grounding() -> None:
    client = FakeClient(
        grader_output_text='{"pass": true, "reason": "Assistant answered the refund request directly."}'
    )

    passed, reason = grade_stt_then_text(
        client,
        user_audio_transcript="I want a refund for my damaged order.",
        assistant_text="I can help with that refund request.",
        criteria="Assistant acknowledges the refund request and responds directly.",
    )

    assert passed is True
    assert "refund request" in reason
    request = client.responses.calls[0]
    assert request["input"][0]["content"] == STT_THEN_TEXT_GRADER_SYSTEM_PROMPT


def test_transcribe_model_response_audio_writes_valid_wav() -> None:
    client = FakeClient(transcript_text="Thanks for calling support.")
    audio_bytes = b"\x00\x00" * 200

    passed, transcript = transcribe_model_response_audio(
        client,
        audio_bytes,
        sample_rate_hz=24000,
    )

    assert passed is True
    assert transcript == "Thanks for calling support."
    transcription_call = client.audio.transcriptions.calls[0]
    assert transcription_call["model"] == DEFAULT_TRANSCRIPTION_MODEL
    assert transcription_call["filename"].endswith(".wav")
    assert transcription_call["audio_size"] > 0


def test_transcribe_model_response_audio_rejects_missing_audio() -> None:
    client = FakeClient(transcript_text="unused")

    passed, reason = transcribe_model_response_audio(
        client,
        None,
        sample_rate_hz=24000,
    )

    assert passed is False
    assert "No audio returned" in reason


def test_audio_text_mismatch_from_model_response_transcribes_then_grades() -> None:
    client = FakeClient(
        grader_output_text='{"pass": true, "reason": "Audio matches the text."}',
        transcript_text="Your order ORD-1001 will arrive tomorrow.",
    )

    passed, reason = grade_audio_text_mismatch_from_model_response(
        client,
        assistant_text="Your order ORD-1001 will arrive tomorrow.",
        audio_bytes=b"\x00\x00" * 200,
        sample_rate_hz=24000,
    )

    assert passed is True
    assert reason == "Audio matches the text."
    assert len(client.audio.transcriptions.calls) == 1
    assert len(client.responses.calls) == 1


def test_stt_then_text_from_model_response_transcribes_then_grades() -> None:
    client = FakeClient(
        grader_output_text='{"pass": true, "reason": "Assistant addressed the request."}',
        transcript_text="Please refund my damaged order.",
    )

    passed, reason = grade_stt_then_text_from_model_response(
        client,
        user_audio_bytes=b"\x00\x00" * 200,
        sample_rate_hz=24000,
        assistant_text="I can help with that refund.",
        criteria="Assistant acknowledges the refund request and responds directly.",
    )

    assert passed is True
    assert reason == "Assistant addressed the request."
    assert len(client.audio.transcriptions.calls) == 1
    assert len(client.responses.calls) == 1


def test_run_default_grader_dispatches_named_graders() -> None:
    client = FakeClient(
        grader_output_text='{"adheres_to_instructions": true, "reason": "All rules followed."}'
    )

    passed, reason = run_default_grader(
        "instruction_following",
        client=client,
        instructions="Do not mention pricing.",
        response_text="I can help with your order.",
    )

    assert "instruction_following" in DEFAULT_GRADER_FUNCTIONS
    assert DEFAULT_GRADER_SPECS["instruction_following"]["required_kwargs"] == (
        "client",
        "instructions",
        "response_text",
    )
    assert passed is True
    assert reason == "All rules followed."
