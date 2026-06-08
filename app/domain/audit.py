from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.classification import SensitivityLevel
from app.domain.common import DomainModel, new_id, utc_now
from app.domain.policy import PolicyDecision


class AuditEventType(StrEnum):
    SESSION_STARTED = "session_started"
    TASK_CREATED = "task_created"
    PLAN_MODE_ENTERED = "plan_mode_entered"
    PLAN_CREATED = "plan_created"
    TOOL_REQUESTED = "tool_requested"
    POLICY_EVALUATED = "policy_evaluated"
    PERMISSION_DENIED = "permission_denied"
    APPROVAL_REQUIRED = "approval_required"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    PLAN_EXECUTION_STARTED = "plan_execution_started"
    CONNECTOR_CALLED = "connector_called"
    CONNECTOR_FAILED = "connector_failed"
    SQL_REVIEWED = "sql_reviewed"
    TOOL_EXECUTED = "tool_executed"
    RESULT_MASKED = "result_masked"
    TASK_COMPLETED = "task_completed"
    APPROVAL_DECIDED = "approval_decided"
    ERROR_RAISED = "error_raised"
    TOOL_COMPLETED = "tool_executed"
    APPROVAL_REQUESTED = "approval_required"
    SECURITY_MASKED = "result_masked"


class AuditActor(DomainModel):
    actor_id: str = Field(description="Actor identifier.")
    actor_type: str = Field(description="Actor type, such as user, service, or agent.")
    display_name: str | None = Field(default=None, description="Actor display name.")
    department: str | None = Field(default=None, description="Actor department.")


class AuditTarget(DomainModel):
    target_id: str = Field(description="Target object identifier.")
    target_type: str = Field(description="Target object type.")
    qualified_name: str | None = Field(default=None, description="Target qualified name.")
    sensitivity_level: str | None = Field(default=None, description="Target sensitivity level.")


class AuditEvent(DomainModel):
    event_id: UUID = Field(default_factory=new_id, description="Unique audit event identifier.")
    timestamp: datetime = Field(default_factory=utc_now, description="Audit event timestamp.")
    event_type: AuditEventType = Field(description="Audit event type.")
    user_id: str | None = Field(default=None, description="User identifier for filtering.")
    role: str | None = Field(default=None, description="Primary actor role for filtering.")
    session_id: str | None = Field(default=None, description="Runtime session identifier.")
    task_id: str | None = Field(default=None, description="Governance task identifier.")
    agent_name: str | None = Field(default=None, description="Agent or subagent name.")
    tool_name: str | None = Field(default=None, description="DataTool name.")
    asset_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Safe asset references touched by the event.",
    )
    sensitivity_level: SensitivityLevel | None = Field(
        default=None,
        description="Highest sensitivity level involved in the event.",
    )
    policy_decision: PolicyDecision | None = Field(
        default=None,
        description="Policy decision associated with the event, if any.",
    )
    request_summary: str | None = Field(
        default=None,
        description="Safe request summary without raw sensitive payload.",
    )
    result_summary: str | None = Field(
        default=None,
        description="Safe result summary without raw result rows.",
    )
    request_hash: str | None = Field(
        default=None,
        description="Hash of request payload when raw payload is not retained.",
    )
    result_hash: str | None = Field(
        default=None,
        description="Hash of result payload when raw payload is not retained.",
    )
    raw_payload_allowed: bool = Field(
        default=False,
        description="Whether raw payload retention is explicitly allowed. Defaults to false.",
    )
    actor: AuditActor = Field(description="Actor that caused the event.")
    target: AuditTarget | None = Field(default=None, description="Object affected by the event.")
    action: str = Field(description="Action being audited.")
    outcome: str = Field(description="Action outcome.")
    reason: str | None = Field(default=None, description="Optional reason or explanation.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional safe metadata.")
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether this audit event may be included in model context.",
    )
    occurred_at: datetime = Field(default_factory=utc_now, description="Event timestamp.")

    @model_validator(mode="before")
    @classmethod
    def fill_filter_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        actor = value.get("actor")
        if isinstance(actor, dict):
            value.setdefault("user_id", actor.get("actor_id"))
            value.setdefault("role", actor.get("actor_type"))
        target = value.get("target")
        if isinstance(target, dict):
            sensitivity = target.get("sensitivity_level")
            if sensitivity is not None:
                value.setdefault("sensitivity_level", sensitivity)
            qualified_name = target.get("qualified_name")
            if qualified_name is not None and "asset_refs" not in value:
                value["asset_refs"] = (qualified_name,)
        if "timestamp" not in value and "occurred_at" in value:
            value["timestamp"] = value["occurred_at"]
        if "occurred_at" not in value and "timestamp" in value:
            value["occurred_at"] = value["timestamp"]
        return value


class AuditEventFilter(DomainModel):
    event_type: AuditEventType | None = Field(
        default=None,
        description="Optional event type filter.",
    )
    user_id: str | None = Field(default=None, description="Optional user id filter.")
    session_id: str | None = Field(default=None, description="Optional session id filter.")
    task_id: str | None = Field(default=None, description="Optional task id filter.")
    tool_name: str | None = Field(default=None, description="Optional tool name filter.")
    policy_decision: PolicyDecision | None = Field(
        default=None,
        description="Optional policy decision filter.",
    )
