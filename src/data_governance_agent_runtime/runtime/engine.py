from __future__ import annotations

from data_governance_agent_runtime.audit.recorder import AuditRecorder
from data_governance_agent_runtime.core.enums import AuditOutcome
from data_governance_agent_runtime.core.models import (
    GovernancePlan,
    GovernanceTask,
    RuntimeContext,
    RuntimeResponse,
    ToolRequest,
    ToolResult,
)
from data_governance_agent_runtime.dlp.masking import DlpMasker
from data_governance_agent_runtime.policy.engine import PolicyEngine
from data_governance_agent_runtime.tools.governance import default_tool_requests
from data_governance_agent_runtime.tools.registry import ToolRegistry, build_default_registry


class GovernanceAgentRuntime:
    """Minimal agentic loop with policy-gated DataTool execution."""

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        audit: AuditRecorder | None = None,
        dlp: DlpMasker | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.policy = policy or PolicyEngine()
        self.audit = audit or AuditRecorder()
        self.dlp = dlp or DlpMasker()
        self.registry = registry or build_default_registry(self.policy, self.audit, self.dlp)

    def run(
        self,
        task: GovernanceTask,
        context: RuntimeContext,
        tool_requests: list[ToolRequest] | None = None,
    ) -> RuntimeResponse:
        requests = tool_requests or default_tool_requests(task.domain)
        results: list[ToolResult] = []

        for index, request in enumerate(requests[: task.max_steps]):
            if not self.registry.has(request.tool_name):
                self.audit.record(
                    context,
                    request,
                    AuditOutcome.DENIED,
                    "Unknown tool denied by runtime.",
                    {"step": index},
                )
                return RuntimeResponse(
                    request_id=context.request_id,
                    task_id=task.task_id,
                    status="denied",
                    results=tuple(results),
                    audit_event_ids=tuple(event.event_id for event in self.audit.list_events()),
                )

            result = self.registry.get(request.tool_name).invoke(context, request)
            results.append(result)
            if result.data.get("requires_plan_approval") is True:
                plan = GovernancePlan(
                    task_id=task.task_id,
                    objective=task.objective,
                    pending_tool=request,
                    reason=str(result.data["reason"]),
                )
                return RuntimeResponse(
                    request_id=context.request_id,
                    task_id=task.task_id,
                    status="plan_required",
                    results=tuple(results),
                    plan=plan,
                    audit_event_ids=tuple(event.event_id for event in self.audit.list_events()),
                )
            if "error" in result.data:
                return RuntimeResponse(
                    request_id=context.request_id,
                    task_id=task.task_id,
                    status="denied",
                    results=tuple(results),
                    audit_event_ids=tuple(event.event_id for event in self.audit.list_events()),
                )

        return RuntimeResponse(
            request_id=context.request_id,
            task_id=task.task_id,
            status="completed",
            results=tuple(results),
            audit_event_ids=tuple(event.event_id for event in self.audit.list_events()),
        )
