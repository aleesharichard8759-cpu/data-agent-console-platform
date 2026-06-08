from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from data_governance_agent_runtime.core.enums import (
    ActionRisk,
    AuditOutcome,
    Decision,
    Environment,
    SqlStatementType,
)


class Actor(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor_id: str
    roles: tuple[str, ...] = Field(default_factory=tuple)
    department: str | None = None


class RuntimeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID = Field(default_factory=uuid4)
    actor: Actor
    environment: Environment = Environment.MOCK
    purpose: str
    approved_plan_id: UUID | None = None


class GovernanceTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: UUID = Field(default_factory=uuid4)
    objective: str
    domain: str
    max_steps: int = Field(default=8, ge=1, le=30)


class ToolRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    action: str
    risk: ActionRisk
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_sql_gateway: bool = False
    requires_approval: bool = False


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: Decision
    reason: str
    rule_id: str

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    data: dict[str, Any]
    masked_fields: tuple[str, ...] = Field(default_factory=tuple)
    policy: PolicyDecision
    audit_event_id: UUID


class SqlRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    statement: str
    purpose: str
    max_rows: int = Field(default=100, ge=1, le=1000)


class SqlGatewayResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    statement_type: SqlStatementType
    rows: list[dict[str, Any]]
    row_count: int
    masked_fields: tuple[str, ...] = Field(default_factory=tuple)


class DlpResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: dict[str, Any]
    masked_fields: tuple[str, ...] = Field(default_factory=tuple)


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_id: str
    tool_name: str
    action: str
    outcome: AuditOutcome
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernancePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    objective: str
    pending_tool: ToolRequest
    reason: str
    required_approvers: tuple[str, ...] = ("data_owner", "security_reviewer")


class RuntimeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    task_id: UUID
    status: str
    results: tuple[ToolResult, ...] = Field(default_factory=tuple)
    plan: GovernancePlan | None = None
    audit_event_ids: tuple[UUID, ...] = Field(default_factory=tuple)

