from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from case_summary_service import summarize_case


class FakeChatCompletions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Summary: invoice correction requested; billing team owns follow-up."
                    )
                )
            ]
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeChatCompletions())


class SummarizeCaseTests(TestCase):
    def test_summarizes_case_notes(self) -> None:
        client = FakeOpenAIClient()

        summary = summarize_case(
            client,
            model="gpt-5.4-mini",
            case_notes=(
                "Customer says invoice INV-2026-0409 has the wrong billing address. "
                "Billing ops should regenerate and send the corrected PDF."
            ),
        )

        self.assertIn("invoice correction", summary)
        call = client.chat.completions.calls[0]
        self.assertEqual(call["model"], "gpt-5.4-mini")
        self.assertEqual(call["temperature"], 0)
        self.assertEqual(call["messages"][0]["role"], "system")
        self.assertEqual(call["messages"][1]["role"], "user")
        self.assertIn("INV-2026-0409", call["messages"][1]["content"])
