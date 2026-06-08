from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Base model for immutable domain objects."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        use_enum_values=False,
    )


def new_id() -> UUID:
    return uuid4()


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimeRange(DomainModel):
    start_at: datetime | None = Field(default=None, description="Start timestamp for the range.")
    end_at: datetime | None = Field(default=None, description="End timestamp for the range.")

