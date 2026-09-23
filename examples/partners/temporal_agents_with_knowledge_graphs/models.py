"""Models used when interacting with the database interface."""
import json
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

class RawEntity(BaseModel):
    """Model representing an entity (for entity resolution)."""

    entity_idx: int
    name: str
    type: str = ""
    description: str = ""


class Entity(BaseModel):
    """
    Model representing an entity (for entity resolution).
    'id' is the canonical entity id if this is a canonical entity.
    'resolved_id' is set to the canonical id if this is an alias.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_id: uuid.UUID | None = None
    name: str
    type: str
    description: str
    resolved_id: uuid.UUID | None = None

    @classmethod
    def from_raw(
        cls, raw_entity: "RawEntity", event_id: uuid.UUID | None = None
    ) -> "Entity":
        """Create an Entity instance from a RawEntity, optionally associating it with an event_id."""
        return cls(
            id=uuid.uuid4(),
            event_id=event_id,
            name=raw_entity.name,
            type=raw_entity.type,
            description=raw_entity.description,
            resolved_id=None,
        )

class TemporalType(StrEnum):
    """Enumeration of temporal types for statements."""

    ATEMPORAL = "ATEMPORAL"
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"

class StatementType(StrEnum):
    """Enumeration of statement types for statements."""

    FACT = "FACT"
    OPINION = "OPINION"
    PREDICTION = "PREDICTION"

class TemporalEvent(BaseModel):
    """Model representing a temporal event with statement, triplet, and validity information."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    chunk_id: uuid.UUID
    statement: str
    embedding: list[float] = Field(default_factory=lambda: [0.0] * 256)
    triplets: list[uuid.UUID]
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    temporal_type: TemporalType
    statement_type: StatementType
    created_at: datetime = Field(default_factory=datetime.now)
    expired_at: datetime | None = None
    invalidated_by: uuid.UUID | None = None

    @property
    def triplets_json(self) -> str:
        """Convert triplets list to JSON string."""
        return json.dumps([str(t) for t in self.triplets]) if self.triplets else "[]"

    @classmethod
    def parse_triplets_json(cls, triplets_str: str) -> list[uuid.UUID]:
        """Parse JSON string back into list of UUIDs."""
        if not triplets_str or triplets_str == "[]":
            return []
        return [uuid.UUID(t) for t in json.loads(triplets_str)]

    @model_validator(mode="after")
    def set_expired_at(self) -> "TemporalEvent":
        """Set expired_at if invalid_at is set and temporal_type is DYNAMIC."""
        self.expired_at = (
            self.created_at
            if (self.invalid_at is not None)
            and (self.temporal_type == TemporalType.DYNAMIC)
            else None
        )
        return self
