from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from app.domain.common import DomainModel, new_id, utc_now


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PolicyReason(DomainModel):
    code: str = Field(description="Machine-readable policy reason code.")
    message: str = Field(description="Human-readable policy reason.")
    rule_id: str = Field(description="Policy rule identifier that produced this reason.")

    @field_validator("code", "message", "rule_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Policy reason fields must not be empty.")
        return value.strip()


class PolicyEvaluationResult(DomainModel):
    evaluation_id: UUID = Field(default_factory=new_id, description="Unique policy evaluation id.")
    decision: PolicyDecision = Field(description="Final policy decision.")
    reasons: tuple[PolicyReason, ...] = Field(
        default_factory=tuple,
        description="Policy reasons that explain the decision.",
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether approval is required before execution.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether this policy result may be included in model context.",
    )
    evaluated_at: datetime = Field(
        default_factory=utc_now,
        description="Policy evaluation timestamp.",
    )
