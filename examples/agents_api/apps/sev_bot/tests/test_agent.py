"""Regression tests for SRE bot incident cleanup."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

# Initialize the SDK beta package before the streaming import in agent.py.
import openai.lib.beta.agents  # noqa: F401
from fastapi import BackgroundTasks

from examples.agents_api.apps.sev_bot.agent import IncidentBot
from examples.agents_api.apps.sev_bot.alerts import queue_alerts


class RollbackRetryTests(IsolatedAsyncioTestCase):
    async def test_failed_investigation_discards_old_rollback_proposal(self) -> None:
        client = MagicMock()
        client.beta.agents.sessions.delete = AsyncMock()
        client.beta.agents.sessions.retrieve = AsyncMock()
        client.beta.agents.sessions.events.create = AsyncMock()
        slack = MagicMock()
        slack.post = AsyncMock(return_value={"ts": "new-approval"})
        bot = IncidentBot(client, slack=slack, history=[])
        alert = {
            "fingerprint": "retry-demo",
            "labels": {"service": "checkout-api"},
        }
        incident = bot.start_incident(alert)
        deployment = next(
            item
            for item in bot.service("checkout-api")["deployments"]
            if item["status"] == "previous_healthy"
        )
        incident.session_id = "old-session"
        incident.action = bot.propose_rollback(
            incident,
            {
                "service": "checkout-api",
                "version": deployment["version"],
                "reason": "old investigation",
            },
        )
        incident.action.update(call_id="old-call", turn_id="old-turn")
        incident.slack_approval_ts = "old-approval"

        with (
            patch.object(
                bot,
                "_investigate",
                new=AsyncMock(side_effect=RuntimeError("stream failed")),
            ),
            self.assertRaisesRegex(RuntimeError, "stream failed"),
        ):
            await bot.investigate(incident)

        self.assertEqual(incident.status, "failed")
        self.assertIsNone(incident.session_id)
        self.assertIsNone(incident.action)
        self.assertIsNone(incident.slack_approval_ts)
        client.beta.agents.sessions.delete.assert_awaited_once_with("old-session")

        retry_tasks = BackgroundTasks()
        self.assertEqual(
            queue_alerts(bot, {"alerts": [alert]}, retry_tasks)["status"], "accepted"
        )
        with patch.object(bot, "_investigate", new=AsyncMock(return_value="")):
            await retry_tasks()

        self.assertEqual(incident.status, "investigating")
        incident.session_id = "new-session"
        session = SimpleNamespace(
            id="new-session",
            required_actions=[
                SimpleNamespace(
                    type="function_call",
                    name="propose_rollback",
                    call_id="new-call",
                    turn_id="new-turn",
                    arguments=json.dumps(
                        {
                            "service": "checkout-api",
                            "version": deployment["version"],
                            "reason": "new investigation",
                        }
                    ),
                )
            ],
        )
        client.beta.agents.sessions.retrieve.return_value = session

        await bot.request_approval("new-session")

        self.assertEqual(incident.action["call_id"], "new-call")
        self.assertEqual(incident.slack_approval_ts, "new-approval")
        with self.assertRaisesRegex(ValueError, "No rollback is awaiting approval"):
            await bot.decide_rollback(incident.id, True, approval_ts="old-approval")
        client.beta.agents.sessions.events.create.assert_not_awaited()

        decision = await bot.decide_rollback(
            incident.id, True, approval_ts="new-approval"
        )

        self.assertEqual(decision["status"], "approved")
        event = client.beta.agents.sessions.events.create.await_args.kwargs["events"][0]
        self.assertEqual(event["turn_id"], "new-turn")
        self.assertEqual(event["call_id"], "new-call")
