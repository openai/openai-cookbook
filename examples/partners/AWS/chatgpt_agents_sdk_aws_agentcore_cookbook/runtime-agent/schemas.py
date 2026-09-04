from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ActionName = Literal["search_flights", "get_upcoming_status", "get_live_status"]
ExecutionMode = Literal["local", "deployed"]
ProviderName = Literal["agentcore-runtime"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeRequest(StrictModel):
    action: ActionName
    origin: str | None = Field(default=None, min_length=3, max_length=3)
    destination: str | None = Field(default=None, min_length=3, max_length=3)
    travel_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    flight_number: str | None = None

    @model_validator(mode="after")
    def require_action_fields(self) -> RuntimeRequest:
        if self.action == "search_flights":
            missing = [
                name
                for name in ("origin", "destination", "travel_date")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"search_flights is missing: {', '.join(missing)}")

        if self.action == "get_live_status" and not any(
            [self.flight_number, self.origin, self.destination]
        ):
            raise ValueError("get_live_status needs a flight number or route hint")

        return self


class Flight(StrictModel):
    flightNumber: str
    origin: str
    destination: str
    travelDate: str
    departTime: str
    arriveTime: str
    fareUsd: int


class TripStatus(StrictModel):
    flightNumber: str
    origin: str
    destination: str
    travelDate: str
    status: str
    summary: str


class RuntimeResponse(StrictModel):
    provider: ProviderName = Field(
        default="agentcore-runtime",
        description="Deprecated compatibility field; use executionMode.",
        json_schema_extra={"deprecated": True},
    )
    executionMode: ExecutionMode
    action: ActionName
    data: dict[str, Any]
