from __future__ import annotations

from abc import ABC, abstractmethod

from data_governance_agent_runtime.audit.recorder import AuditRecorder
from data_governance_agent_runtime.core.enums import AuditOutcome, Decision
from data_governance_agent_runtime.core.models import RuntimeContext, ToolRequest, ToolResult
from data_governance_agent_runtime.dlp.masking import DlpMasker
from data_governance_agent_runtime.policy.engine import PolicyEngine


class DataTool(ABC):
    name: str

    def __init__(
        self,
        policy: PolicyEngine,
        audit: AuditRecorder,
        dlp: DlpMasker | None = None,
    ) -> None:
        self._policy = policy
        self._audit = audit
        self._dlp = dlp or DlpMasker()

    def invoke(self, context: RuntimeContext, request: ToolRequest) -> ToolResult:
        decision = self._policy.evaluate(context, request)
        if decision.decision == Decision.DENY:
            event = self._audit.record(
                context,
                request,
                AuditOutcome.DENIED,
                decision.reason,
                {"rule_id": decision.rule_id},
            )
            return ToolResult(
                tool_name=self.name,
                data={"error": decision.reason},
                policy=decision,
                audit_event_id=event.event_id,
            )

        if decision.decision == Decision.ASK:
            event = self._audit.record(
                context,
                request,
                AuditOutcome.ASKED,
                decision.reason,
                {"rule_id": decision.rule_id},
            )
            return ToolResult(
                tool_name=self.name,
                data={"requires_plan_approval": True, "reason": decision.reason},
                policy=decision,
                audit_event_id=event.event_id,
            )

        raw = self._execute(context, request)
        masked = self._dlp.mask(raw)
        event = self._audit.record(
            context,
            request,
            AuditOutcome.ALLOWED,
            decision.reason,
            {"rule_id": decision.rule_id, "masked_fields": list(masked.masked_fields)},
        )
        return ToolResult(
            tool_name=self.name,
            data=masked.data,
            masked_fields=masked.masked_fields,
            policy=decision,
            audit_event_id=event.event_id,
        )

    @abstractmethod
    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        raise NotImplementedError

