"""Request bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Decision(BaseModel):
    key: str
    verdict: Literal["keep", "pass"]
    # When the verdict was given on the device, not when it reached the Pi.
    decided_at: str
    # What the device was shown. Used only if the Pi has already forgotten the candidate.
    meta: dict = Field(default_factory=dict)
    wall_colour: str | None = None
    width: int | None = None
    height: int | None = None

    @field_validator("decided_at")
    @classmethod
    def must_be_a_time(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class DecisionBatch(BaseModel):
    decisions: list[Decision]


class Rooms(BaseModel):
    enabled: list[int]
