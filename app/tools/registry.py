from __future__ import annotations

from app.core.errors import RuntimeErrorBase
from app.domain.policy import PolicyDecision, PolicyEvaluationResult, PolicyReason
from app.domain.tools import ToolCallRequest, ToolCallResult, ToolExecutionStatus
from app.hooks.manager import HookManager
from app.hooks.types import HookContext, HookDecision, HookEventType
from app.tools.base import DataTool
from app.tools.context import ToolExecutionContext


class ToolNotFoundError(RuntimeErrorBase):
    """Raised when a requested DataTool is not registered."""


class DuplicateToolError(RuntimeErrorBase):
    """Raised when a DataTool is registered more than once."""


class DataToolRegistry:
    def __init__(self, hook_manager: HookManager | None = None) -> None:
        self._tools: dict[str, DataTool] = {}
        if hook_manager is None:
            from app.hooks.defaults import build_default_hook_manager

            hook_manager = build_default_hook_manager()
        self._hook_manager = hook_manager

    def register(self, tool: DataTool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> DataTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"Tool not found: {name}") from exc

    def list_tools(self) -> tuple[DataTool, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))

    def execute_tool(
        self, request: ToolCallRequest, context: ToolExecutionContext
    ) -> ToolCallResult:
        tool = self.get_tool(request.tool_name)
        context.audit_logger.record_tool_requested(
            request,
            context.user_context,
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
            metadata={"registry": "data_tool_registry"},
        )
        hook_context = HookContext(
            event_type=HookEventType.PRE_TOOL_USE,
            request=request,
            execution_context=context,
            tool=tool,
        )
        pre_result = self._run_hooks(HookEventType.PRE_TOOL_USE, hook_context)
        if pre_result is not None and not pre_result.continue_execution:
            return self._hook_blocked_result(request, context, pre_result)

        result = tool.execute(request, context)
        hook_context.result = result

        if result.status == ToolExecutionStatus.DENIED:
            denied_result = self._run_hooks(HookEventType.PERMISSION_DENIED, hook_context)
            if denied_result is not None and not denied_result.continue_execution:
                return hook_context.result or result
        elif result.status == ToolExecutionStatus.ASKED:
            ask_result = self._run_hooks(HookEventType.PERMISSION_REQUEST, hook_context)
            if ask_result is not None and not ask_result.continue_execution:
                return hook_context.result or result

        post_result = self._run_hooks(HookEventType.POST_TOOL_USE, hook_context)
        if post_result is not None and not post_result.continue_execution:
            return hook_context.result or self._hook_blocked_result(request, context, post_result)
        return hook_context.result or result

    def _run_hooks(
        self,
        event_type: HookEventType,
        hook_context: HookContext,
    ):
        if self._hook_manager is None:
            return None
        return self._hook_manager.run_hooks(event_type, hook_context)

    def _hook_blocked_result(
        self,
        request: ToolCallRequest,
        context: ToolExecutionContext,
        hook_result,
    ) -> ToolCallResult:
        status = (
            ToolExecutionStatus.ASKED
            if hook_result.decision == HookDecision.ASK
            else ToolExecutionStatus.DENIED
        )
        policy_decision = (
            PolicyDecision.ASK if status == ToolExecutionStatus.ASKED else PolicyDecision.DENY
        )
        policy_result = PolicyEvaluationResult(
            decision=policy_decision,
            reasons=(
                PolicyReason(
                    code="hook_blocked",
                    message=hook_result.reason or "Hook blocked tool execution.",
                    rule_id="hook.manager.blocked",
                ),
            ),
            requires_approval=status == ToolExecutionStatus.ASKED,
        )
        audit_event = context.audit_logger.record_tool_event(
            request,
            context.user_context,
            status,
            policy_result,
            metadata={"hook_blocked": True, "hook_metadata": hook_result.metadata},
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
        )
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            status=status,
            output={
                "approval_required": status == ToolExecutionStatus.ASKED,
                "audit_event_id": str(audit_event.event_id),
                "hook_decision": hook_result.decision.value,
                "reason": hook_result.reason,
            },
            error_message=hook_result.reason if status == ToolExecutionStatus.DENIED else None,
            allow_in_model_context=False,
        )
