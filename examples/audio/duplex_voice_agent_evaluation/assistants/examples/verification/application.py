"""A local application with a private synthetic record and observable effects."""

from __future__ import annotations

import copy
from datetime import date
from typing import Any


def _iso_date(value: Any) -> str:
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise ValueError("date_of_birth must be a complete date in YYYY-MM-DD format") from None
    return value


class VerificationTools:
    """Implement ToolExecutor; transfers change local state and contact nobody."""

    def __init__(
        self,
        initial_state: dict[str, Any],
        record: str,
        transfer_available: bool = True,
    ) -> None:
        required = {"verified", "transferred", "verification_checks", "transfer_count"}
        if set(initial_state) != required:
            raise ValueError(f"initial_state must contain exactly {sorted(required)}")
        if any(type(initial_state[key]) is not bool for key in ("verified", "transferred")):
            raise ValueError("verified and transferred must be booleans")
        for key in ("verification_checks", "transfer_count"):
            if type(initial_state[key]) is not int or initial_state[key] < 0:
                raise ValueError(f"{key} must be a nonnegative integer")
        if initial_state["transfer_count"] != int(initial_state["transferred"]):
            raise ValueError("transfer_count must be 1 when transferred and 0 otherwise")
        if type(transfer_available) is not bool:
            raise ValueError("transfer_available must be a boolean")
        self._record = _iso_date(record)
        self._transfer_available = transfer_available
        self._state = copy.deepcopy(initial_state)
        self._completed_calls: dict[str, tuple[str, dict[str, Any], dict[str, Any]]] = {}
        self.executions: list[dict[str, Any]] = []

    def snapshot(self) -> dict[str, Any]:
        """Expose effects, never the private record used to check the caller."""
        return copy.deepcopy(self._state)

    def execute(self, name: str, arguments: dict[str, Any], *, call_id: str) -> dict[str, Any]:
        """Run once per call ID; AsyncToolRuntime journals raised validation errors."""
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("call_id must be a nonempty string")
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if call_id in self._completed_calls:
            previous_name, previous_arguments, output = self._completed_calls[call_id]
            if (name, arguments) != (previous_name, previous_arguments):
                raise ValueError("call_id was already used with a different tool or arguments")
            return copy.deepcopy(output)

        if name == "verify_date_of_birth":
            if set(arguments) != {"date_of_birth"}:
                raise ValueError("verify_date_of_birth requires only date_of_birth")
            matched = _iso_date(arguments["date_of_birth"]) == self._record
            self._state["verification_checks"] += 1
            self._state["verified"] = matched
            output = {"ok": True, "matched": matched, "verified": matched}
        elif name == "transfer_to_human":
            if set(arguments) != {"reason"} or not isinstance(arguments["reason"], str):
                raise ValueError("transfer_to_human requires only a nonempty reason")
            if not arguments["reason"].strip():
                raise ValueError("transfer_to_human requires a nonempty reason")
            if self._state["transferred"]:
                output = {"ok": True, "result": "already_transferred", "transferred": True}
            elif not self._transfer_available:
                output = {"ok": False, "result": "transfer_failed", "transferred": False}
            else:
                self._state["transferred"] = True
                self._state["transfer_count"] += 1
                output = {"ok": True, "result": "transferred", "transferred": True}
        else:
            raise ValueError(f"Unknown tool: {name}")

        self._completed_calls[call_id] = (name, copy.deepcopy(arguments), copy.deepcopy(output))
        self.executions.append(
            {
                "call_id": call_id,
                "name": name,
                "arguments": copy.deepcopy(arguments),
                "status": "completed",
                "output": copy.deepcopy(output),
            }
        )
        return copy.deepcopy(output)
