from __future__ import annotations

from data_governance_agent_runtime.core.enums import AuditOutcome
from data_governance_agent_runtime.core.models import AuditEvent, RuntimeContext, ToolRequest


class AuditRecorder:
    """Append-only in-memory audit recorder for the mock runtime stage."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(
        self,
        context: RuntimeContext,
        request: ToolRequest,
        outcome: AuditOutcome,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            request_id=context.request_id,
            actor_id=context.actor.actor_id,
            tool_name=request.tool_name,
            action=request.action,
            outcome=outcome,
            reason=reason,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def list_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

