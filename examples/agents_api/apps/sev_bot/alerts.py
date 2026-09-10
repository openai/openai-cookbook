"""Normalize incident-provider alerts and schedule independent investigations."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import BackgroundTasks, HTTPException

from .agent import IncidentBot

logger = logging.getLogger(__name__)


def normalize_alerts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = payload.get("alerts")
    if isinstance(alerts, list):
        if not all(isinstance(alert, dict) for alert in alerts):
            raise HTTPException(status_code=400, detail="Each alert must be an object.")
        return [
            {
                **alert,
                "status": alert.get("status", payload.get("status", "firing")),
                "fingerprint": alert.get("fingerprint")
                or f"{alert.get('labels', {}).get('service', '')}:"
                f"{alert.get('labels', {}).get('alertname', '')}",
            }
            for alert in alerts
        ]

    event = payload.get("event")
    if isinstance(event, dict) and isinstance(event.get("data"), dict):
        event_type = str(event.get("event_type", ""))
        if event_type not in {"incident.triggered", "incident.resolved"}:
            return []
        data = event["data"]
        service = data.get("service", {})
        details = data.get("custom_details", {})
        service_name = (
            details.get("service") or service.get("name") or service.get("summary")
        )
        return [
            {
                "fingerprint": f"pagerduty:{data['id']}",
                "status": "resolved" if event_type.endswith(".resolved") else "firing",
                "labels": {
                    "service": service_name,
                    "severity": "critical"
                    if data.get("urgency") == "high"
                    else "warning",
                    "alertname": event_type,
                },
                "annotations": {
                    "summary": str(data.get("title") or data.get("summary", ""))
                },
            }
        ]

    incident_event_type = payload.get("event_type")
    if isinstance(incident_event_type, str):
        if incident_event_type not in {
            "public_incident.incident_created_v2",
            "public_incident.incident_status_updated_v2",
        }:
            return []
        data = payload[incident_event_type]
        data = data.get("incident", data)
        service_name = os.environ.get("INCIDENT_SERVICE")
        if not service_name:
            raise HTTPException(
                status_code=400,
                detail="Set INCIDENT_SERVICE for this incident.io subscription.",
            )
        category = data.get("incident_status", {}).get("category", "live")
        return [
            {
                "fingerprint": f"incidentio:{data['id']}",
                "status": (
                    "resolved"
                    if category
                    in {"learning", "closed", "declined", "merged", "canceled"}
                    else "firing"
                ),
                "labels": {
                    "service": service_name,
                    "severity": (
                        "critical"
                        if (data.get("severity") or {}).get("name", "").lower()
                        in {"critical", "sev-1"}
                        else "warning"
                    ),
                    "alertname": incident_event_type,
                },
                "annotations": {"summary": str(data.get("name", ""))},
            }
        ]

    raise HTTPException(
        status_code=400,
        detail="Expected an Alertmanager, PagerDuty, or incident.io incident webhook.",
    )


async def run_incident_tasks(tasks: BackgroundTasks) -> None:
    # One incident waiting for approval must not hold up the rest of an alert batch.
    results = await asyncio.gather(
        *(task() for task in tasks.tasks), return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            logger.error("Incident background task failed", exc_info=result)


def queue_alerts(
    bot: IncidentBot, payload: dict[str, Any], tasks: BackgroundTasks
) -> dict[str, Any]:
    alerts = normalize_alerts(payload)
    incident_tasks = BackgroundTasks()

    accepted: list[str] = []
    duplicates: list[str] = []
    for alert in alerts:
        fingerprint = str(alert.get("fingerprint", ""))
        existing = bot.fingerprints.get(fingerprint)
        if alert.get("status") == "resolved":
            if existing is not None:
                incident_tasks.add_task(bot.resolve, existing)
                accepted.append(existing)
            continue

        if existing is not None:
            incident = bot.incident(existing)
            if incident.status == "failed":
                incident.status = "investigating"
                incident_tasks.add_task(bot.investigate, incident)
                accepted.append(existing)
            else:
                duplicates.append(existing)
            continue

        try:
            incident = bot.start_incident(alert)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        accepted.append(incident.id)
        incident_tasks.add_task(bot.investigate, incident)

    if incident_tasks.tasks:
        tasks.add_task(run_incident_tasks, incident_tasks)

    return {
        "status": "accepted"
        if accepted
        else "already_tracking"
        if duplicates
        else "ignored",
        "incidents": accepted or duplicates,
    }
