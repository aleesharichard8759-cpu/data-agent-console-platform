from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.assets import DataDomain
from app.domain.classification import SensitivityLevel
from app.domain.common import DomainModel, new_id, utc_now
from app.domain.tasks import GovernanceTaskLevel


class ToolRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolExecutionStatus(StrEnum):
    CREATED = "created"
    ALLOWED = "allowed"
    ASKED = "asked"
    DENIED = "denied"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MASKED = "masked"


class ToolCallRequest(DomainModel):
    tool_call_id: UUID = Field(default_factory=new_id, description="Unique tool call identifier.")
    tool_name: str = Field(description="DataTool name.")
    action: str = Field(description="Requested tool action.")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured tool parameters. Must not contain raw secrets.",
    )
    asset_type: str | None = Field(
        default=None,
        description="Target asset type, such as metadata, metric, table, column, or policy.",
    )
    data_domain: DataDomain | None = Field(
        default=None,
        description="Target business data domain for the tool call.",
    )
    sensitivity_level: SensitivityLevel | None = Field(
        default=None,
        description="Sensitivity level of the target data, if known.",
    )
    task_level: GovernanceTaskLevel | None = Field(
        default=None,
        description="Governance task level associated with this tool call, if any.",
    )
    risk_level: ToolRiskLevel = Field(description="Risk level of this tool call.")
    requires_approval: bool = Field(
        default=False,
        description="Whether the tool call requires approval before execution.",
    )
    requires_sql_gateway: bool = Field(
        default=False,
        description="Whether the tool call must be routed through SQL Gateway.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether the request payload may be placed in model context.",
    )
    requested_at: datetime = Field(default_factory=utc_now, description="Tool request timestamp.")

    @field_validator("tool_name", "action")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Tool request text fields must not be empty.")
        return value.strip()

    @model_validator(mode="after")
    def validate_security_boundary(self) -> ToolCallRequest:
        if self.risk_level in {ToolRiskLevel.HIGH, ToolRiskLevel.CRITICAL}:
            if not self.requires_approval:
                raise ValueError("High and critical risk tool calls must require approval.")
            if self.allow_in_model_context:
                raise ValueError("High and critical risk tool calls cannot enter model context.")
        if self.action.startswith("sql.") and not self.requires_sql_gateway:
            raise ValueError("SQL tool calls must require SQL Gateway.")
        return self


class ToolCallResult(DomainModel):
    tool_call_id: UUID = Field(description="Tool call identifier this result belongs to.")
    status: ToolExecutionStatus = Field(description="Tool execution status.")
    output: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured masked tool output.",
    )
    error_message: str | None = Field(
        default=None,
        description="Safe error message if execution failed.",
    )
    masked_fields: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Output fields masked by DLP.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether this result may be included in model context.",
    )
    executed_at: datetime = Field(default_factory=utc_now, description="Tool result timestamp.")
