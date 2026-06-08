from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.errors import UnsafeOperationError
from app.domain.audit import AuditEvent, AuditEventFilter
from app.domain.identity import UserContext
from app.domain.policy import PolicyDecision, PolicyEvaluationResult
from app.domain.tasks import GovernanceTask
from app.domain.tools import ToolCallRequest, ToolExecutionStatus
from app.policy import PolicyEngine


class AuditLogger(Protocol):
    def log_event(self, event: AuditEvent) -> AuditEvent:
        """Record one generic audit event."""

    def list_events(
        self,
        event_filter: AuditEventFilter | dict[str, object] | None = None,
    ) -> tuple[AuditEvent, ...]:
        """List events, optionally filtered."""

    def get_event(self, event_id: UUID | str) -> AuditEvent | None:
        """Get an event by id."""

    def record_tool_requested(
        self,
        request: ToolCallRequest,
        user: UserContext,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        """Record that a tool was requested."""

    def record_policy_evaluation(
        self,
        request: ToolCallRequest,
        user: UserContext,
        policy_result: PolicyEvaluationResult,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        """Record one policy evaluation event."""

    def record_result_masked(
        self,
        request: ToolCallRequest,
        user: UserContext,
        masked_fields: tuple[str, ...],
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        """Record that DLP masked tool output fields."""

    def record_sql_review(
        self,
        *,
        sql: str,
        user: UserContext,
        decision: PolicyDecision,
        reason: str,
        risks: tuple[object, ...],
        request: ToolCallRequest | None = None,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        """Record one SQL Gateway review event without raw SQL results."""

    def record_tool_event(
        self,
        request: ToolCallRequest,
        user: UserContext,
        status: ToolExecutionStatus,
        policy_result: PolicyEvaluationResult | None,
        metadata: dict[str, object] | None = None,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
    ) -> AuditEvent:
        """Record one tool execution event."""


@dataclass(frozen=True)
class ToolExecutionContext:
    user_context: UserContext
    task_context: GovernanceTask | None
    policy_engine: PolicyEngine
    audit_logger: AuditLogger
    dry_run: bool = False
    plan_mode: bool = False
    session_id: str | None = None
    agent_name: str | None = "governance_agent"

    def __post_init__(self) -> None:
        if self.policy_engine is None:
            raise UnsafeOperationError("Tool execution requires Policy Engine.")
        if self.audit_logger is None:
            raise UnsafeOperationError("Tool execution requires Audit Logger.")
