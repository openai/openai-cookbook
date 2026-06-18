#!/usr/bin/env python3
"""Build speaker-aware meeting intelligence from recorded audio.

This sample does three things:
1. Uses the OpenAI Transcriptions API with gpt-4o-transcribe-diarize to
   produce speaker-labeled transcript segments.
2. Sends the speaker-labeled transcript to a text model for structured meeting
   intelligence: summary, action items, risks, decisions, and follow-up email.
3. Writes a guardrail report for evidence checks, PII checks, high-risk outputs,
   and optional content moderation.

Run without an API key:
    python meeting_intelligence.py --demo --output-dir /tmp/meeting-intelligence-demo

Run with real audio:
    export OPENAI_API_KEY="..."
    python meeting_intelligence.py \
      --audio-file meeting.wav \
      --known-speaker "Agent=agent_reference.wav" \
      --known-speaker "Customer=customer_reference.wav" \
      --redact \
      --output-dir /tmp/meeting-intelligence-real
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_SUMMARY_MODEL = os.getenv("OPENAI_MEETING_INTELLIGENCE_MODEL", "gpt-4.1-mini")
DEFAULT_MODERATION_MODEL = "omni-moderation-latest"
TIMESTAMP_PATTERN = re.compile(r"\b\d{2,}:\d{2}\.\d{3}\b")


@dataclass(frozen=True)
class Segment:
    speaker: str
    start: float
    end: float
    text: str


DEMO_SEGMENTS = [
    Segment(
        speaker="Solutions Engineer",
        start=0.0,
        end=9.2,
        text="Thanks for joining. I would like to understand where your support handoff breaks down today.",
    ),
    Segment(
        speaker="Customer",
        start=9.3,
        end=22.4,
        text="The biggest issue is that escalation notes are inconsistent. Managers spend Monday morning reconstructing what happened from call recordings.",
    ),
    Segment(
        speaker="Solutions Engineer",
        start=22.5,
        end=38.1,
        text="So the priority is reliable call summaries, who committed to what, and enough evidence that the team trusts the handoff.",
    ),
    Segment(
        speaker="Customer",
        start=38.2,
        end=55.0,
        text="Exactly. We also need risks called out, especially compliance-sensitive promises, and we need to push action items into our CRM.",
    ),
    Segment(
        speaker="Solutions Engineer",
        start=55.1,
        end=70.3,
        text="I will send a prototype that includes speaker-aware transcripts, action items with evidence, and a redaction pass before CRM sync.",
    ),
]


MEETING_INTELLIGENCE_SCHEMA: dict[str, Any] = {
    "name": "meeting_intelligence",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "participants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {"type": "string"},
                        "inferred_role": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["speaker", "inferred_role", "evidence"],
                },
            },
            "customer_context": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "fact": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["fact", "evidence"],
                },
            },
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "decision": {"type": "string"},
                        "speaker_or_group": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["decision", "speaker_or_group", "evidence"],
                },
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "owner_speaker": {"type": "string"},
                        "task": {"type": "string"},
                        "due_date_or_trigger": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["owner_speaker", "task", "due_date_or_trigger", "evidence"],
                },
            },
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "risk": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "evidence": {"type": "string"},
                        "mitigation": {"type": "string"},
                    },
                    "required": ["risk", "severity", "evidence", "mitigation"],
                },
            },
            "open_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question": {"type": "string"},
                        "owner_speaker": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["question", "owner_speaker", "evidence"],
                },
            },
            "notable_quotes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {"type": "string"},
                        "quote": {"type": "string"},
                        "timestamp": {"type": "string"},
                    },
                    "required": ["speaker", "quote", "timestamp"],
                },
            },
            "follow_up_email": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["subject", "body"],
            },
        },
        "required": [
            "summary",
            "participants",
            "customer_context",
            "decisions",
            "action_items",
            "risks",
            "open_questions",
            "notable_quotes",
            "follow_up_email",
        ],
    },
}


PII_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[email]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"), "[phone]"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create speaker-aware meeting intelligence from recorded audio."
    )
    parser.add_argument("--audio-file", type=Path, help="Path to the meeting recording.")
    parser.add_argument(
        "--known-speaker",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Optional speaker reference clip. Repeat up to 4 times, for example 'Agent=agent.wav'.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("meeting_intelligence_output"),
        help="Directory for generated artifacts.",
    )
    parser.add_argument(
        "--summary-model",
        default=DEFAULT_SUMMARY_MODEL,
        help=f"Text model for meeting intelligence extraction. Default: {DEFAULT_SUMMARY_MODEL}",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run without API calls using a synthetic diarized transcript.",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        help="Redact basic email and phone patterns from output artifacts before summarization.",
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Save the raw transcription API response. Off by default to reduce sensitive-data storage.",
    )
    parser.add_argument(
        "--moderate",
        action="store_true",
        help="Run optional text moderation on the transcript and generated brief.",
    )
    parser.add_argument(
        "--fail-on-guardrail",
        action="store_true",
        help="Exit non-zero when the guardrail report requires review.",
    )
    return parser.parse_args()


def parse_known_speakers(entries: list[str]) -> list[tuple[str, Path]]:
    if len(entries) > 4:
        raise ValueError("gpt-4o-transcribe-diarize accepts up to 4 known speaker references.")

    speakers: list[tuple[str, Path]] = []
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Expected --known-speaker NAME=PATH, got: {entry}")
        name, raw_path = entry.split("=", 1)
        name = name.strip()
        raw_path = raw_path.strip()
        if not name:
            raise ValueError(f"Known speaker name cannot be empty: {entry}")
        if not raw_path:
            raise ValueError(f"Known speaker reference path cannot be empty: {entry}")
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"Known speaker reference does not exist or is not a regular file: {path}"
            )
        speakers.append((name, path))
    return speakers


def to_data_url(path: Path | str) -> str:
    path = Path(path)
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type is None or not mime_type.startswith("audio/"):
        mime_type = "audio/wav"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def transcribe_with_diarization(
    audio_file: Path,
    known_speakers: list[tuple[str, Path]],
    model: str = DEFAULT_TRANSCRIPTION_MODEL,
) -> Any:
    if not audio_file.is_file():
        raise FileNotFoundError(f"Audio file does not exist or is not a regular file: {audio_file}")

    from openai import OpenAI

    client = OpenAI()
    params: dict[str, Any] = {
        "model": model,
        "response_format": "diarized_json",
        "chunking_strategy": "auto",
    }

    if known_speakers:
        params["extra_body"] = {
            "known_speaker_names": [name for name, _ in known_speakers],
            "known_speaker_references": [to_data_url(path) for _, path in known_speakers],
        }

    with audio_file.open("rb") as audio:
        return client.audio.transcriptions.create(file=audio, **params)


def to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: to_plain(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    return value


def normalize_segments(transcription: Any) -> list[Segment]:
    data = to_plain(transcription)
    raw_segments = data.get("segments", []) if isinstance(data, dict) else []
    segments: list[Segment] = []

    for index, item in enumerate(raw_segments):
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        segments.append(
            Segment(
                speaker=str(item.get("speaker") or f"Speaker {index + 1}"),
                start=float(item.get("start") or 0.0),
                end=float(item.get("end") or 0.0),
                text=text,
            )
        )

    if not segments and isinstance(data, dict) and data.get("text"):
        segments.append(Segment(speaker="Speaker 1", start=0.0, end=0.0, text=str(data["text"])))

    if not segments:
        raise ValueError("No transcript segments were found in the transcription response.")
    return segments


def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in PII_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_segments(segments: list[Segment]) -> list[Segment]:
    return [
        Segment(
            speaker=segment.speaker,
            start=segment.start,
            end=segment.end,
            text=redact_text(segment.text),
        )
        for segment in segments
    ]


def pii_matches(text: str) -> list[str]:
    matches: list[str] = []
    for pattern, replacement in PII_PATTERNS:
        if pattern.search(text):
            matches.append(replacement.strip("[]"))
    return sorted(set(matches))


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    minutes, remainder_ms = divmod(total_ms, 60_000)
    secs, millis = divmod(remainder_ms, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def transcript_as_markdown(segments: list[Segment]) -> str:
    lines = ["# Speaker-Labeled Transcript", ""]
    for segment in segments:
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        lines.append(f"**{segment.speaker} [{start}-{end}]**: {segment.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def transcript_for_model(segments: list[Segment]) -> str:
    return "\n".join(
        f"{segment.speaker} [{format_timestamp(segment.start)}-{format_timestamp(segment.end)}]: {segment.text}"
        for segment in segments
    )


def generate_meeting_intelligence(segments: list[Segment], model: str) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    transcript = transcript_for_model(segments)

    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": MEETING_INTELLIGENCE_SCHEMA},
        messages=[
            {
                "role": "system",
                "content": (
                    "You create meeting intelligence from speaker-labeled transcripts. "
                    "Use only the transcript as evidence. Do not invent names, dates, decisions, "
                    "or commitments. If evidence is missing, leave the relevant array empty. "
                    "Include timestamps in every evidence field. "
                    "If the follow-up email signer is unknown, end with [Your name]."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract a customer-safe meeting brief from this transcript.\n\n"
                    f"{transcript}"
                ),
            },
        ],
    )

    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("The model returned an empty response.")
    return json.loads(content)


def demo_meeting_intelligence() -> dict[str, Any]:
    return {
        "summary": (
            "The customer needs a dependable post-call handoff process. Their main pain point is "
            "inconsistent escalation notes, which forces managers to reconstruct calls manually. "
            "The proposed path is a speaker-aware transcript, evidence-backed action items, risk "
            "detection, redaction, and CRM sync."
        ),
        "participants": [
            {
                "speaker": "Solutions Engineer",
                "inferred_role": "OpenAI technical seller or solution owner",
                "evidence": "The speaker asks discovery questions and commits to sending a prototype at 00:55.100.",
            },
            {
                "speaker": "Customer",
                "inferred_role": "Customer stakeholder for support operations",
                "evidence": "The speaker describes escalation-note and CRM needs at 00:09.300 and 00:38.200.",
            },
        ],
        "customer_context": [
            {
                "fact": "Escalation notes are inconsistent today.",
                "evidence": "Customer [00:09.300-00:22.400]",
            },
            {
                "fact": "Managers spend time reconstructing calls from recordings.",
                "evidence": "Customer [00:09.300-00:22.400]",
            },
            {
                "fact": "The customer wants action items pushed into their CRM.",
                "evidence": "Customer [00:38.200-00:55.000]",
            },
        ],
        "decisions": [
            {
                "decision": "Prototype should include speaker-aware transcripts, evidence-backed actions, and redaction before CRM sync.",
                "speaker_or_group": "Solutions Engineer",
                "evidence": "Solutions Engineer [00:55.100-01:10.300]",
            }
        ],
        "action_items": [
            {
                "owner_speaker": "Solutions Engineer",
                "task": "Send a prototype of the speaker-aware meeting intelligence pipeline.",
                "due_date_or_trigger": "After the call",
                "evidence": "Solutions Engineer [00:55.100-01:10.300]",
            }
        ],
        "risks": [
            {
                "risk": "Compliance-sensitive promises could be missed or summarized without evidence.",
                "severity": "medium",
                "evidence": "Customer [00:38.200-00:55.000]",
                "mitigation": "Keep timestamps on action items and route high-risk claims to a review queue.",
            }
        ],
        "open_questions": [
            {
                "question": "Which CRM fields and workflow should receive action items?",
                "owner_speaker": "Customer",
                "evidence": "Customer asks for CRM push but does not specify schema at 00:38.200.",
            }
        ],
        "notable_quotes": [
            {
                "speaker": "Customer",
                "quote": "Managers spend Monday morning reconstructing what happened from call recordings.",
                "timestamp": "00:09.300",
            }
        ],
        "follow_up_email": {
            "subject": "Prototype for speaker-aware meeting handoffs",
            "body": (
                "Hi,\n\nThanks for the conversation. I heard that escalation-note quality, "
                "evidence-backed action items, compliance-sensitive risk detection, and CRM sync "
                "are the core requirements. I will send a prototype that uses speaker-aware "
                "transcripts, redaction, and structured outputs so your team can review the handoff "
                "before it enters downstream systems.\n\nBest,\n[Your name]"
            ),
        },
    }


def clean_markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_None identified._"

    header = "| " + " | ".join(title for title, _ in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(clean_markdown_cell(row.get(key, "")) for _, key in columns) + " |")
    return "\n".join([header, divider, *body])


def render_meeting_brief(intelligence: dict[str, Any]) -> str:
    follow_up = intelligence.get("follow_up_email", {})
    lines = [
        "# Meeting Brief",
        "",
        "## Summary",
        "",
        str(intelligence.get("summary", "")).strip() or "_No summary generated._",
        "",
        "## Participants",
        "",
        markdown_table(
            intelligence.get("participants", []),
            [("Speaker", "speaker"), ("Inferred role", "inferred_role"), ("Evidence", "evidence")],
        ),
        "",
        "## Customer Context",
        "",
        markdown_table(
            intelligence.get("customer_context", []),
            [("Fact", "fact"), ("Evidence", "evidence")],
        ),
        "",
        "## Decisions",
        "",
        markdown_table(
            intelligence.get("decisions", []),
            [("Decision", "decision"), ("Owner", "speaker_or_group"), ("Evidence", "evidence")],
        ),
        "",
        "## Action Items",
        "",
        markdown_table(
            intelligence.get("action_items", []),
            [
                ("Owner", "owner_speaker"),
                ("Task", "task"),
                ("Due date or trigger", "due_date_or_trigger"),
                ("Evidence", "evidence"),
            ],
        ),
        "",
        "## Risks",
        "",
        markdown_table(
            intelligence.get("risks", []),
            [
                ("Risk", "risk"),
                ("Severity", "severity"),
                ("Evidence", "evidence"),
                ("Mitigation", "mitigation"),
            ],
        ),
        "",
        "## Open Questions",
        "",
        markdown_table(
            intelligence.get("open_questions", []),
            [("Question", "question"), ("Owner", "owner_speaker"), ("Evidence", "evidence")],
        ),
        "",
        "## Notable Quotes",
        "",
        markdown_table(
            intelligence.get("notable_quotes", []),
            [("Speaker", "speaker"), ("Quote", "quote"), ("Timestamp", "timestamp")],
        ),
        "",
        "## Follow-up Email Draft",
        "",
        f"**Subject:** {follow_up.get('subject', '')}",
        "",
        str(follow_up.get("body", "")).strip(),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def summarize_moderation_response(response: Any) -> dict[str, Any]:
    data = to_plain(response)
    summaries: list[dict[str, Any]] = []

    for result in data.get("results", []) if isinstance(data, dict) else []:
        categories = result.get("categories", {}) if isinstance(result, dict) else {}
        category_scores = result.get("category_scores", {}) if isinstance(result, dict) else {}
        flagged_categories = sorted(
            key for key, value in categories.items() if bool(value)
        )
        top_scores = dict(
            sorted(
                category_scores.items(),
                key=lambda item: float(item[1] or 0.0),
                reverse=True,
            )[:5]
        )
        summaries.append(
            {
                "flagged": bool(result.get("flagged")) if isinstance(result, dict) else False,
                "flagged_categories": flagged_categories,
                "top_category_scores": top_scores,
            }
        )

    return {
        "id": data.get("id") if isinstance(data, dict) else None,
        "model": data.get("model") if isinstance(data, dict) else DEFAULT_MODERATION_MODEL,
        "flagged": any(item["flagged"] for item in summaries),
        "results": summaries,
    }


def moderate_text(text: str, model: str = DEFAULT_MODERATION_MODEL) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    response = client.moderations.create(model=model, input=text)
    return summarize_moderation_response(response)


def iter_evidence_fields(value: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            next_path = f"{path}.{key}"
            if key == "evidence":
                found.append((next_path, str(inner or "")))
            else:
                found.extend(iter_evidence_fields(inner, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(iter_evidence_fields(item, f"{path}[{index}]"))
    return found


def evidence_has_anchor(evidence: str) -> bool:
    return bool(TIMESTAMP_PATTERN.search(evidence))


def add_guardrail_check(
    checks: list[dict[str, Any]],
    name: str,
    status: str,
    detail: str,
    evidence: Any | None = None,
) -> None:
    check: dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if evidence is not None:
        check["evidence"] = evidence
    checks.append(check)


def build_guardrail_report(
    segments: list[Segment],
    intelligence: dict[str, Any],
    meeting_brief: str,
    redaction_enabled: bool,
    raw_saved: bool,
    moderation_results: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    transcript_text = transcript_for_model(segments)

    add_guardrail_check(
        checks,
        "transcript_segments_present",
        "pass" if segments else "fail",
        f"Found {len(segments)} normalized transcript segments.",
    )

    pii_found = pii_matches(transcript_text + "\n" + meeting_brief)
    add_guardrail_check(
        checks,
        "basic_pii_scan",
        "review" if pii_found else "pass",
        (
            "Basic PII patterns remain after redaction."
            if pii_found
            else "No basic email or phone patterns detected."
        ),
        {"matches": pii_found, "redaction_enabled": redaction_enabled},
    )

    evidence_fields = iter_evidence_fields(intelligence)
    weak_evidence = [
        {"path": path, "value": value}
        for path, value in evidence_fields
        if not evidence_has_anchor(value)
    ]
    add_guardrail_check(
        checks,
        "evidence_anchors",
        "review" if weak_evidence else "pass",
        (
            "Some evidence fields do not include a timestamp anchor."
            if weak_evidence
            else "All evidence fields include a timestamp anchor."
        ),
        {"weak_evidence_count": len(weak_evidence), "examples": weak_evidence[:5]},
    )

    risks = intelligence.get("risks", [])
    review_risks = [
        risk
        for risk in risks
        if str(risk.get("severity", "")).lower() in {"medium", "high"}
    ]
    severity_counts = {
        "low": sum(1 for risk in risks if str(risk.get("severity", "")).lower() == "low"),
        "medium": sum(1 for risk in risks if str(risk.get("severity", "")).lower() == "medium"),
        "high": sum(1 for risk in risks if str(risk.get("severity", "")).lower() == "high"),
    }
    add_guardrail_check(
        checks,
        "risk_outputs",
        "review" if review_risks else "pass",
        (
            "Medium or high risks should be reviewed before downstream writes."
            if review_risks
            else "No medium or high risks identified."
        ),
        {"severity_counts": severity_counts},
    )

    moderation_flagged = [
        name
        for name, result in moderation_results.items()
        if isinstance(result, dict) and result.get("flagged")
    ]
    if moderation_results:
        add_guardrail_check(
            checks,
            "moderation",
            "review" if moderation_flagged else "pass",
            (
                "Moderation flagged content that should be reviewed."
                if moderation_flagged
                else "Moderation did not flag transcript or brief content."
            ),
            {"flagged_artifacts": moderation_flagged},
        )
    else:
        add_guardrail_check(
            checks,
            "moderation",
            "not_run",
            "Moderation was not requested. Use --moderate for content safety classification.",
        )

    add_guardrail_check(
        checks,
        "raw_response_storage",
        "review" if raw_saved else "pass",
        (
            "Raw transcription response was saved; confirm retention and access controls."
            if raw_saved
            else "Raw transcription response was not saved."
        ),
    )

    review_statuses = {"review", "fail"}
    status = "review_required" if any(check["status"] in review_statuses for check in checks) else "pass"
    if any(check["status"] == "fail" for check in checks):
        status = "fail"

    return {
        "status": status,
        "recommended_next_step": (
            "Send artifacts to human review before downstream writes."
            if status != "pass"
            else "Artifacts passed local guardrail checks."
        ),
        "checks": checks,
        "moderation": moderation_results,
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    moderation_results: dict[str, Any] = {}

    if args.moderate and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("--moderate requires OPENAI_API_KEY.")

    if args.demo:
        segments = DEMO_SEGMENTS
        intelligence = demo_meeting_intelligence()
        raw_payload: Any | None = None
        if args.moderate:
            moderation_results["transcript"] = moderate_text(transcript_for_model(segments))
    else:
        if args.audio_file is None:
            raise SystemExit("Provide --audio-file, or use --demo to run with synthetic data.")
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("Set OPENAI_API_KEY before running on real audio.")

        known_speakers = parse_known_speakers(args.known_speaker)
        raw_payload = transcribe_with_diarization(args.audio_file, known_speakers)
        segments = normalize_segments(raw_payload)
        if args.redact:
            segments = redact_segments(segments)
        if args.moderate:
            moderation_results["transcript"] = moderate_text(transcript_for_model(segments))
        intelligence = generate_meeting_intelligence(segments, args.summary_model)

    meeting_brief = render_meeting_brief(intelligence)
    if args.moderate:
        moderation_results["meeting_brief"] = moderate_text(meeting_brief)

    raw_response_will_be_saved = args.save_raw and raw_payload is not None
    guardrail_report = build_guardrail_report(
        segments=segments,
        intelligence=intelligence,
        meeting_brief=meeting_brief,
        redaction_enabled=args.redact,
        raw_saved=raw_response_will_be_saved,
        moderation_results=moderation_results,
    )

    transcript_json = [asdict(segment) for segment in segments]
    write_json(args.output_dir / "transcript_segments.json", transcript_json)
    (args.output_dir / "speaker_labeled_transcript.md").write_text(
        transcript_as_markdown(segments),
        encoding="utf-8",
    )
    write_json(args.output_dir / "meeting_intelligence.json", intelligence)
    (args.output_dir / "meeting_brief.md").write_text(
        meeting_brief,
        encoding="utf-8",
    )
    write_json(args.output_dir / "guardrail_report.json", guardrail_report)

    if raw_response_will_be_saved:
        write_json(args.output_dir / "raw_transcription_response.json", to_plain(raw_payload))

    print(f"Wrote meeting intelligence artifacts to {args.output_dir}")
    print(f"- {args.output_dir / 'transcript_segments.json'}")
    print(f"- {args.output_dir / 'speaker_labeled_transcript.md'}")
    print(f"- {args.output_dir / 'meeting_intelligence.json'}")
    print(f"- {args.output_dir / 'meeting_brief.md'}")
    print(f"- {args.output_dir / 'guardrail_report.json'}")

    if args.fail_on_guardrail and guardrail_report["status"] != "pass":
        raise SystemExit(f"Guardrail status: {guardrail_report['status']}")


if __name__ == "__main__":
    main()
