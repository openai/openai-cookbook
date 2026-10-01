from __future__ import annotations

from demo_date import demo_travel_date
from schemas import RuntimeRequest


def search_flights(request: RuntimeRequest) -> dict[str, object]:
    return {
        "flights": [
            {
                "flightNumber": "ELZ1234",
                "origin": request.origin,
                "destination": request.destination,
                "travelDate": request.travel_date,
                "departTime": "08:15",
                "arriveTime": "10:05",
                "fareUsd": 149,
            },
            {
                "flightNumber": "ELZ1458",
                "origin": request.origin,
                "destination": request.destination,
                "travelDate": request.travel_date,
                "departTime": "12:30",
                "arriveTime": "14:20",
                "fareUsd": 181,
            },
        ],
        "summary": "2 read-only sample options returned for the cookbook.",
    }


def upcoming_status() -> dict[str, object]:
    return {
        "flight": {
            "flightNumber": "ELZ4321",
            "origin": "DAL",
            "destination": "MDW",
            "travelDate": demo_travel_date(),
            "status": "ON_TIME",
            "summary": "Mock upcoming trip is on time.",
        }
    }


def live_status(request: RuntimeRequest) -> dict[str, object]:
    return {
        "flight": {
            "flightNumber": request.flight_number or "ELZ1628",
            "origin": request.origin or "DAL",
            "destination": request.destination or "MDW",
            "travelDate": request.travel_date or demo_travel_date(),
            "status": "ON_TIME",
            "summary": "Mock live status is on time.",
        }
    }
