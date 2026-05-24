from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from case_summary_service.client import complete_summary_prompt


class FakeChatCompletions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Legacy summary from chat wrapper")
                )
            ]
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeChatCompletions())


class CompleteSummaryPromptTests(TestCase):
    def test_calls_chat_completions_with_summary_messages(self) -> None:
        client = FakeOpenAIClient()
        messages = [
            {"role": "system", "content": "Summarize case notes."},
            {"role": "user", "content": "Customer asked for an invoice correction."},
        ]

        text = complete_summary_prompt(
            client,
            model="gpt-5.4-mini",
            messages=messages,
        )

        self.assertEqual(text, "Legacy summary from chat wrapper")
        call = client.chat.completions.calls[0]
        self.assertEqual(call["model"], "gpt-5.4-mini")
        self.assertEqual(call["messages"], messages)
        self.assertEqual(call["temperature"], 0)
