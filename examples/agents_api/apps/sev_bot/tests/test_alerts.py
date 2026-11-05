"""Offline alert-batch regression tests.

Run from the repository root:
    python -m unittest discover -s examples/agents_api/apps/sev_bot/tests -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock

from fastapi import BackgroundTasks, HTTPException

from examples.agents_api.apps.sev_bot.agent import IncidentBot
from examples.agents_api.apps.sev_bot.alerts import queue_alerts


def alert(
    service: str = "checkout-api",
    fingerprint: str = "checkout-alert",
    status: str = "firing",
) -> dict:
    return {
        "fingerprint": fingerprint,
        "status": status,
        "labels": {"service": service, "alertname": "HighErrorRate"},
    }


class AlertBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bot = IncidentBot(
            AsyncMock(),
            operations={"checkout-api": {"team": "Payments SRE"}},
            slack=AsyncMock(),
            history=[],
        )
        self.bot.investigate = AsyncMock()
        self.bot.resolve = AsyncMock()

    def queue(self, alerts: list[dict]) -> tuple[dict, BackgroundTasks]:
        tasks = BackgroundTasks()
        result = queue_alerts(self.bot, {"alerts": alerts}, tasks)
        return result, tasks

    def test_rejected_batch_leaves_no_incident_and_valid_alert_can_retry(self) -> None:
        tasks = BackgroundTasks()
        next_incident_number = self.bot.next_incident_number

        with self.assertRaises(HTTPException) as raised:
            queue_alerts(
                self.bot,
                {"alerts": [alert(), alert("unknown-service", "unknown-alert")]},
                tasks,
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "Unknown service: unknown-service")
        self.assertEqual(self.bot.incidents, {})
        self.assertEqual(self.bot.fingerprints, {})
        self.assertEqual(self.bot.next_incident_number, next_incident_number)
        self.assertEqual(tasks.tasks, [])

        result, retry_tasks = self.queue([alert()])
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(result["incidents"]), 1)
        asyncio.run(retry_tasks())
        self.bot.investigate.assert_awaited_once_with(
            self.bot.incident(result["incidents"][0])
        )

    def test_rejected_batch_does_not_change_failed_incident_retry_state(self) -> None:
        incident = self.bot.start_incident(alert())
        incident.status = "failed"
        tasks = BackgroundTasks()

        with self.assertRaises(HTTPException):
            queue_alerts(
                self.bot,
                {"alerts": [alert(), alert("unknown-service", "unknown-alert")]},
                tasks,
            )

        self.assertEqual(incident.status, "failed")
        self.assertEqual(list(self.bot.incidents), [incident.id])
        self.assertEqual(tasks.tasks, [])
        result, retry_tasks = self.queue([alert()])
        self.assertEqual(result, {"status": "accepted", "incidents": [incident.id]})
        self.assertEqual(incident.status, "investigating")
        asyncio.run(retry_tasks())
        self.bot.investigate.assert_awaited_once_with(incident)

    def test_valid_batch_investigates_each_distinct_incident(self) -> None:
        result, tasks = self.queue([alert(), alert(fingerprint="second-alert")])

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(result["incidents"]), 2)
        asyncio.run(tasks())
        self.assertEqual(self.bot.investigate.await_count, 2)
        self.assertEqual(self.bot.resolve.await_count, 0)

    def test_duplicate_in_same_batch_does_not_validate_or_create_again(self) -> None:
        result, tasks = self.queue([alert(), alert("unknown-service")])

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(self.bot.incidents), 1)
        asyncio.run(tasks())
        self.bot.investigate.assert_awaited_once()

    def test_existing_fingerprint_is_still_deduplicated(self) -> None:
        incident = self.bot.start_incident(alert())
        result, tasks = self.queue([alert("unknown-service")])

        self.assertEqual(
            result, {"status": "already_tracking", "incidents": [incident.id]}
        )
        self.assertEqual(tasks.tasks, [])
        self.bot.investigate.assert_not_awaited()

    def test_resolution_does_not_require_service_lookup(self) -> None:
        incident = self.bot.start_incident(alert())
        result, tasks = self.queue([alert("unknown-service", status="resolved")])

        self.assertEqual(result, {"status": "accepted", "incidents": [incident.id]})
        asyncio.run(tasks())
        self.bot.resolve.assert_awaited_once_with(incident.id)
        self.bot.investigate.assert_not_awaited()

    def test_unknown_resolution_is_ignored(self) -> None:
        result, tasks = self.queue([alert("unknown-service", status="resolved")])

        self.assertEqual(result, {"status": "ignored", "incidents": []})
        self.assertEqual(self.bot.incidents, {})
        self.assertEqual(tasks.tasks, [])


if __name__ == "__main__":
    unittest.main()
