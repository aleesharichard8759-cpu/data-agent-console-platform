from __future__ import annotations

from uuid import UUID

from pydantic import Field, field_validator

from app.domain.classification import SensitivityLevel
from app.domain.common import DomainModel, new_id
from app.domain.identity import UserRole
from app.domain.policy import PolicyDecision


class PolicyRule(DomainModel):
    rule_uid: UUID = Field(default_factory=new_id, description="Unique policy rule identifier.")
    rule_id: str = Field(description="Stable machine-readable policy rule id.")
    name: str = Field(description="Human-readable policy rule name.")
    description: str = Field(description="Detailed rule description.")
    effect: PolicyDecision = Field(description="Rule effect: allow, ask, or deny.")
    priority: int = Field(
        default=100,
        ge=0,
        description="Rule priority. Lower values are evaluated first within the same effect.",
    )
    match_tool_names: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Tool names matched by this rule. Empty means any tool.",
    )
    match_operations: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Tool operations matched by this rule. Empty means any operation.",
    )
    match_asset_types: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Asset types matched by this rule. Empty means any asset type.",
    )
    match_sensitivity_levels: tuple[SensitivityLevel, ...] = Field(
        default_factory=tuple,
        description="Sensitivity levels matched by this rule. Empty means any level.",
    )
    match_roles: tuple[UserRole, ...] = Field(
        default_factory=tuple,
        description="User roles matched by this rule. Empty means any role.",
    )
    reason: str = Field(description="Reason returned when this rule decides a request.")

    @field_validator("rule_id", "name", "description", "reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Policy rule text fields must not be empty.")
        return value.strip()

