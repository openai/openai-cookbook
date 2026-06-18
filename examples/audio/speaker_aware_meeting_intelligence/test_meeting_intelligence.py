#!/usr/bin/env python3
"""Synthetic tests for the speaker-aware meeting intelligence example.

These tests avoid network calls and API credentials. They validate the local
pipeline pieces that should stay deterministic in Cookbook review:

- CLI demo end to end
- Markdown and JSON artifact creation
- PII redaction and PII guardrail detection
- evidence-anchor validation
- risk review routing
- synthetic guardrail fixtures
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EXAMPLE_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = EXAMPLE_DIR / "meeting_intelligence.py"
CASES_PATH = EXAMPLE_DIR / "synthetic_cases.json"


def load_module():
    spec = importlib.util.spec_from_file_location("meeting_intelligence", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["meeting_intelligence"] = module
    spec.loader.exec_module(module)
    return module


meeting_intelligence = load_module()


class EndToEndCliTests(unittest.TestCase):
    def test_demo_cli_writes_expected_artifacts_and_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--demo",
                    "--output-dir",
                    tmpdir,
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            self.assertIn("guardrail_report.json", result.stdout)
            output_dir = Path(tmpdir)
            expected_files = [
                "transcript_segments.json",
                "speaker_labeled_transcript.md",
                "meeting_intelligence.json",
                "meeting_brief.md",
                "guardrail_report.json",
            ]
            for filename in expected_files:
                self.assertTrue((output_dir / filename).exists(), filename)

            report = json.loads((output_dir / "guardrail_report.json").read_text())
            self.assertEqual(report["status"], "review_required")
            self.assertTrue(
                any(check["name"] == "risk_outputs" and check["status"] == "review" for check in report["checks"])
            )

    def test_demo_save_raw_does_not_report_missing_raw_artifact_as_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--demo",
                    "--save-raw",
                    "--output-dir",
                    tmpdir,
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            output_dir = Path(tmpdir)
            self.assertFalse((output_dir / "raw_transcription_response.json").exists())
            report = json.loads((output_dir / "guardrail_report.json").read_text())
            raw_check = next(check for check in report["checks"] if check["name"] == "raw_response_storage")
            self.assertEqual(raw_check["status"], "pass")


class GuardrailUnitTests(unittest.TestCase):
    def test_parse_known_speakers_trims_path_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference = Path(tmpdir) / "speaker.wav"
            reference.write_bytes(b"RIFF....WAVEfmt ")

            speakers = meeting_intelligence.parse_known_speakers([f" Agent = {reference} "])

            self.assertEqual(speakers, [("Agent", reference)])

    def test_to_data_url_accepts_path_or_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference = Path(tmpdir) / "speaker.wav"
            reference.write_bytes(b"RIFF....WAVEfmt ")

            self.assertEqual(
                meeting_intelligence.to_data_url(reference),
                meeting_intelligence.to_data_url(str(reference)),
            )
            self.assertTrue(meeting_intelligence.to_data_url(reference).startswith("data:audio/"))

    def test_redact_segments_removes_basic_email_and_phone(self) -> None:
        segments = [
            meeting_intelligence.Segment(
                speaker="Customer",
                start=0.0,
                end=4.0,
                text="Email me at alex@example.com or call 415-555-0100.",
            )
        ]
        redacted = meeting_intelligence.redact_segments(segments)
        self.assertEqual(redacted[0].text, "Email me at [email] or call [phone].")

    def test_fail_on_guardrail_exits_nonzero_for_demo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--demo",
                    "--fail-on-guardrail",
                    "--output-dir",
                    tmpdir,
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Guardrail status: review_required", result.stderr + result.stdout)

    def test_raw_storage_flag_requires_review(self) -> None:
        segments = [
            meeting_intelligence.Segment(
                speaker="Seller",
                start=0.0,
                end=3.0,
                text="I will send the notes.",
            )
        ]
        intelligence = minimal_intelligence("Seller [00:00.000-00:03.000]")
        brief = meeting_intelligence.render_meeting_brief(intelligence)
        report = meeting_intelligence.build_guardrail_report(
            segments=segments,
            intelligence=intelligence,
            meeting_brief=brief,
            redaction_enabled=False,
            raw_saved=True,
            moderation_results={},
        )
        self.assertEqual(report["status"], "review_required")
        self.assertTrue(
            any(check["name"] == "raw_response_storage" and check["status"] == "review" for check in report["checks"])
        )

    def test_evidence_anchor_requires_timestamp_not_speaker_name_only(self) -> None:
        self.assertFalse(meeting_intelligence.evidence_has_anchor("Customer described the escalation path."))
        self.assertTrue(meeting_intelligence.evidence_has_anchor("Customer [00:00.000-00:03.000]"))
        self.assertEqual(meeting_intelligence.format_timestamp(6000), "100:00.000")
        self.assertTrue(meeting_intelligence.evidence_has_anchor("Customer [100:00.000-100:03.000]"))


class SyntheticCaseTests(unittest.TestCase):
    def test_synthetic_guardrail_cases(self) -> None:
        cases = json.loads(CASES_PATH.read_text())
        self.assertGreaterEqual(len(cases), 4)

        for case in cases:
            with self.subTest(case=case["name"]):
                segments = [
                    meeting_intelligence.Segment(
                        speaker=item["speaker"],
                        start=float(item["start"]),
                        end=float(item["end"]),
                        text=item["text"],
                    )
                    for item in case["segments"]
                ]
                brief = meeting_intelligence.render_meeting_brief(case["intelligence"])
                report = meeting_intelligence.build_guardrail_report(
                    segments=segments,
                    intelligence=case["intelligence"],
                    meeting_brief=brief,
                    redaction_enabled=False,
                    raw_saved=False,
                    moderation_results={},
                )
                self.assertEqual(report["status"], case["expected_status"])

    def test_pii_case_passes_after_redaction(self) -> None:
        cases = {case["name"]: case for case in json.loads(CASES_PATH.read_text())}
        pii_case = cases["pii_requires_review"]
        segments = [
            meeting_intelligence.Segment(
                speaker=item["speaker"],
                start=float(item["start"]),
                end=float(item["end"]),
                text=item["text"],
            )
            for item in pii_case["segments"]
        ]
        redacted_segments = meeting_intelligence.redact_segments(segments)
        brief = meeting_intelligence.render_meeting_brief(pii_case["intelligence"])
        report = meeting_intelligence.build_guardrail_report(
            segments=redacted_segments,
            intelligence=pii_case["intelligence"],
            meeting_brief=brief,
            redaction_enabled=True,
            raw_saved=False,
            moderation_results={},
        )

        pii_check = next(check for check in report["checks"] if check["name"] == "basic_pii_scan")
        self.assertEqual(pii_check["status"], "pass")


def minimal_intelligence(evidence: str) -> dict:
    return {
        "summary": "A short meeting summary.",
        "participants": [
            {
                "speaker": "Seller",
                "inferred_role": "Vendor owner",
                "evidence": evidence,
            }
        ],
        "customer_context": [],
        "decisions": [],
        "action_items": [],
        "risks": [],
        "open_questions": [],
        "notable_quotes": [],
        "follow_up_email": {
            "subject": "Follow-up",
            "body": "Hi,\n\nThanks for the call.\n\nBest,\n[Your name]",
        },
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)
