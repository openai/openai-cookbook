"""Restaurant application tools owned by the responses assistant."""

from __future__ import annotations

import copy
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


class RestaurantToolError(ValueError):
    """A requested restaurant operation is invalid or unauthorized."""


def _required_string(arguments: dict[str, Any], name: str, tool: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RestaurantToolError(f"{tool} requires a nonempty {name}")
    return value.strip()


def _reservation_arguments(arguments: dict[str, Any], tool: str, *, require_name: bool) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if require_name:
        normalized["guest_name"] = _required_string(arguments, "guest_name", tool)
    raw_date = _required_string(arguments, "date", tool)
    raw_time = _required_string(arguments, "time", tool)
    try:
        normalized["date"] = date.fromisoformat(raw_date).isoformat()
        normalized["time"] = datetime.strptime(raw_time, "%H:%M").strftime("%H:%M")
    except ValueError as exc:
        raise RestaurantToolError(f"{tool} requires an ISO date and HH:MM time") from exc
    party_size = arguments.get("party_size")
    if isinstance(party_size, bool) or not isinstance(party_size, int) or party_size < 1:
        raise RestaurantToolError(f"{tool} requires a positive party_size")
    normalized["party_size"] = party_size
    seating = arguments.get("seating")
    if seating is not None:
        if not isinstance(seating, str) or not seating.strip():
            raise RestaurantToolError(f"{tool} requires nonempty seating when provided")
        normalized["seating"] = seating.strip().casefold()
    return normalized


@dataclass(slots=True)
class RestaurantTools:
    """Execute verified restaurant actions against one example's private state."""

    initial_state: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    executions: list[dict[str, Any]] = field(default_factory=list)
    _state: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.initial_state, dict):
            raise RestaurantToolError("Restaurant initial state must be a JSON object")
        if not isinstance(self.facts, dict):
            raise RestaurantToolError("Restaurant business facts must be a JSON object")
        self._state = copy.deepcopy(self.initial_state)
        self.facts = copy.deepcopy(self.facts)

    def execute(self, name: str, arguments: dict[str, Any], *, call_id: str) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise RestaurantToolError("Restaurant tool arguments must be a JSON object")
        if name == "check_availability":
            output = self._check_availability(arguments)
        elif name == "create_reservation":
            output = self._create_reservation(arguments)
        elif name == "cancel_reservation":
            output = self._cancel_reservation(arguments)
        else:
            raise RestaurantToolError(f"Unauthorized restaurant tool: {name or '<missing>'}")
        self.executions.append(
            {
                "call_id": call_id,
                "name": name,
                "arguments": copy.deepcopy(arguments),
                "status": "completed",
                "output": copy.deepcopy(output),
            }
        )
        return output

    def snapshot(self) -> dict[str, Any]:
        """Return application state only; read-only execution does not change it."""
        return copy.deepcopy(self._state)

    def _check_availability(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested = _reservation_arguments(arguments, "check_availability", require_name=False)
        available = True
        for override in self.facts.get("availability_overrides", []):
            if not isinstance(override, dict):
                continue
            keys = ("date", "time", "party_size", "seating")
            if all(key not in override or override[key] == requested.get(key) for key in keys):
                available = bool(override.get("available", True))
                break
        return {"ok": True, **requested, "available": available}

    def _create_reservation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested = _reservation_arguments(arguments, "create_reservation", require_name=True)
        reservations = self._state.setdefault("reservations", [])
        if not isinstance(reservations, list):
            raise RestaurantToolError("Restaurant reservations state must be a list")
        reservation_id = f"R-{len(reservations) + 1:03}"
        reservation = {"reservation_id": reservation_id, **requested, "cancelled": False}
        reservations.append(copy.deepcopy(reservation))
        self._state.update({"reservation_created": True, **copy.deepcopy(requested)})
        return {"ok": True, "reservation_created": True, **reservation}

    def _cancel_reservation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        reservation_id = _required_string(arguments, "reservation_id", "cancel_reservation")
        authorized = self._state.get("authorized_reservation_ids", [])
        if not isinstance(authorized, list) or reservation_id not in authorized:
            raise RestaurantToolError(f"Not authorized to cancel reservation {reservation_id}")
        reservations = self._state.get("reservations", [])
        if not isinstance(reservations, list):
            raise RestaurantToolError("Restaurant reservations state must be a list")
        reservation = next(
            (item for item in reservations if isinstance(item, dict) and item.get("reservation_id") == reservation_id),
            None,
        )
        if reservation is None:
            raise RestaurantToolError(f"Reservation {reservation_id} does not exist")
        if reservation.get("cancelled") is True:
            raise RestaurantToolError(f"Reservation {reservation_id} is already cancelled")
        reservation["cancelled"] = True
        self._state.update({"reservation_id": reservation_id, "cancelled": True})
        return {"ok": True, "reservation_id": reservation_id, "cancelled": True}


_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


@dataclass(slots=True)
class RestaurantOfflineBehavior:
    """Derive protocol-fixture actions from legitimate visible inputs only."""

    conversation_context: str = ""
    initial_state: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)

    def infer_tool_call(self, user_text: str) -> tuple[str, dict[str, Any]] | None:
        lowered = user_text.casefold()
        if "cancel" in lowered:
            reservation_ids = re.findall(r"\b(R-\d+)\b", f"{self.conversation_context} {user_text}", re.IGNORECASE)
            if not reservation_ids:
                return None
            reservation_id = reservation_ids[-1].upper()
            authorized = self.initial_state.get("authorized_reservation_ids", [])
            if not isinstance(authorized, list) or reservation_id not in authorized:
                return None
            return "cancel_reservation", {"reservation_id": reservation_id}

        if "parking" in lowered or any(term in lowered for term in ("close", "hours", "open")):
            return None

        details = self._visible_details(user_text)
        is_availability = (
            "available" in lowered
            or "availability" in lowered
            or lowered.startswith(("do you have", "is there", "can you check"))
        )
        if is_availability:
            required = ("date", "time", "party_size")
            if not all(key in details for key in required):
                return None
            return "check_availability", {key: details[key] for key in (*required, "seating") if key in details}

        visible_intent = f"{self.conversation_context} {user_text}".casefold()
        booking_requested = any(word in visible_intent for word in ("book", "reserve", "reservation", "make it"))
        if not booking_requested:
            return None
        required = ("guest_name", "date", "time", "party_size")
        if not all(key in details for key in required):
            return None
        return "create_reservation", {key: details[key] for key in (*required, "seating") if key in details}

    def direct_answer(self, user_text: str) -> str:
        lowered = user_text.casefold()
        visible_context = f"{self.conversation_context} {user_text}"
        if "cancel" in visible_context.casefold():
            reservation_ids = re.findall(r"\b(R-\d+)\b", visible_context, re.IGNORECASE)
            if not reservation_ids:
                return "Which reservation ID would you like to cancel?"
            reservation_id = reservation_ids[-1].upper()
            authorized = self.initial_state.get("authorized_reservation_ids", [])
            if not isinstance(authorized, list) or reservation_id not in authorized:
                return "I can't cancel a reservation that you aren't authorized to manage."
            return f"Should I cancel reservation {reservation_id}?"
        if "parking" in lowered:
            return str(self.facts.get("parking", "Please contact the restaurant for parking information."))
        if any(term in lowered for term in ("close", "hours", "open")):
            return f"Our restaurant hours are {self.facts.get('hours', 'available from the restaurant')}."
        details = self._visible_details(user_text)
        missing = [key for key in ("guest_name", "time") if key not in details]
        if missing == ["guest_name", "time"]:
            return "What name and time would you like for the reservation?"
        if missing == ["guest_name"]:
            return "What name should I put on the reservation?"
        if missing == ["time"]:
            return "What time would you like the reservation?"
        return "How can I help with your restaurant reservation?"

    @staticmethod
    def final_answer(output: dict[str, Any]) -> str:
        if not output.get("ok"):
            return "I couldn't complete that restaurant request."
        if "available" in output:
            seating = f" {output['seating']}" if output.get("seating") else ""
            if output["available"]:
                return (
                    f"A{seating} table for {output['party_size']} is available on "
                    f"{output['date']} at {output['time']}. No reservation has been made."
                )
            return (
                f"A{seating} table for {output['party_size']} is not available on "
                f"{output['date']} at {output['time']}. No reservation has been made."
            )
        if output.get("cancelled"):
            return f"Reservation {output['reservation_id']} has been cancelled."
        seating = f" {output['seating']}" if output.get("seating") else ""
        return (
            f"Your{seating} reservation for {output['guest_name']} and "
            f"{output['party_size']} guests is confirmed on {output['date']} at {output['time']}."
        )

    def _visible_details(self, user_text: str) -> dict[str, Any]:
        context_details = self._extract_details(self.conversation_context)
        context_details.update(self._extract_details(user_text))
        return context_details

    def _extract_details(self, text: str) -> dict[str, Any]:
        details: dict[str, Any] = {}
        name_patterns = (
            r"\b(?i:under)\s+([A-Z][a-z]+)\b",
            r"\bfor\s+([A-Z][a-z]+)\s+on\b",
            r"\bcaller\s+is\s+([A-Z][a-z]+)\b",
            r"(?:^|[.!?]\s+)([A-Z][a-z]+)\s+requested\b",
        )
        for pattern in name_patterns:
            names = re.findall(pattern, text)
            if names:
                details["guest_name"] = names[-1]
                break

        dates = re.findall(r"\bAugust\s+(\d{1,2})\b", text, re.IGNORECASE)
        if dates:
            year = self.facts.get("reference_year", 2026)
            with suppress(TypeError, ValueError):
                details["date"] = date(int(year), 8, int(dates[-1])).isoformat()

        times = re.findall(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", text, re.IGNORECASE)
        if times:
            hour_text, minute_text, period = times[-1]
            hour = int(hour_text) % 12 + (12 if period.casefold() == "p" else 0)
            details["time"] = f"{hour:02}:{int(minute_text or '0'):02}"

        sizes = [
            match.group(1)
            for match in re.finditer(
                r"\b(?:for|actually)\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
                text,
                re.IGNORECASE,
            )
            if not re.match(r"\s*(?::\d{2})?\s*[ap]\.?m\.?", text[match.end() :], re.IGNORECASE)
        ]
        if sizes:
            size_text = sizes[-1].casefold()
            details["party_size"] = _NUMBER_WORDS.get(size_text, int(size_text) if size_text.isdigit() else 0)
        if re.search(r"\bpatio\b", text, re.IGNORECASE):
            details["seating"] = "patio"
        return details
