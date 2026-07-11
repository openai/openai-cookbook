from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from customer_support_bot import draft_reply


class FakeChatCompletions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Thanks for writing in. We are reviewing case CS-123."
                    )
                )
            ]
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeChatCompletions())


class DraftReplyTests(TestCase):
    def test_drafts_reply_with_case_context(self) -> None:
        client = FakeOpenAIClient()

        reply = draft_reply(
            client,
            model="gpt-5.4-mini",
            case_id="CS-123",
            customer_message="My shipment is late. Can someone check?",
        )

        self.assertIn("CS-123", reply)
        call = client.chat.completions.calls[0]
        self.assertEqual(call["model"], "gpt-5.4-mini")
        self.assertEqual(call["temperature"], 0)
        self.assertEqual(call["messages"][0]["role"], "system")
        self.assertEqual(call["messages"][1]["role"], "user")
        self.assertIn("CS-123", call["messages"][1]["content"])
