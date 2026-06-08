from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from app.domain.classification import SensitivityLevel
from app.domain.policy import PolicyDecision, PolicyEvaluationResult, PolicyReason
from app.domain.tools import ToolCallRequest, ToolCallResult, ToolExecutionStatus
from app.tools.context import ToolExecutionContext


class DataTool(BaseModel, ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]
    max_rows: ClassVar[int] = 100
    max_bytes: ClassVar[int] = 1024 * 1024

    def validate_input(self, request: ToolCallRequest) -> BaseModel:
        return self.input_model.model_validate(request.parameters)

    def check_permission(
        self, request: ToolCallRequest, context: ToolExecutionContext
    ) -> PolicyEvaluationResult:
        return context.policy_engine.evaluate(
            request,
            context.user_context,
            audit_logger=context.audit_logger,
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
        )

    def execute(self, request: ToolCallRequest, context: ToolExecutionContext) -> ToolCallResult:
        try:
            validated_input = self.validate_input(request)
        except ValidationError as exc:
            return self._failed_result(request, context, f"Invalid tool input: {exc.errors()}")

        policy_result = self.check_permission(request, context)
        if policy_result.decision == PolicyDecision.DENY:
            return self._policy_result(request, context, policy_result, ToolExecutionStatus.DENIED)
        if policy_result.decision == PolicyDecision.ASK:
            return self._policy_result(request, context, policy_result, ToolExecutionStatus.ASKED)

        if context.plan_mode and not self.is_read_only():
            plan_result = PolicyEvaluationResult(
                decision=PolicyDecision.ASK,
                reasons=(
                    PolicyReason(
                        code="plan_mode_approval_required",
                        message="Non-read-only tools require approval in plan mode.",
                        rule_id="tools.plan_mode_non_read_only",
                    ),
                ),
                requires_approval=True,
            )
            return self._policy_result(request, context, plan_result, ToolExecutionStatus.ASKED)

        try:
            output = self._execute(validated_input, context)
            validated_output = self.output_model.model_validate(output)
        except Exception as exc:
            return self._failed_result(request, context, f"Tool execution failed: {exc}")

        audit_event = context.audit_logger.record_tool_event(
            request,
            context.user_context,
            ToolExecutionStatus.SUCCEEDED,
            policy_result,
            metadata={"tool_name": self.name, "dry_run": context.dry_run},
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
        )
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            status=ToolExecutionStatus.SUCCEEDED,
            output={
                "data": validated_output.model_dump(mode="json"),
                "audit_event_id": str(audit_event.event_id),
                "policy_decision": policy_result.decision.value,
            },
            allow_in_model_context=self.allow_in_model_context(),
        )

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    def is_concurrency_safe(self) -> bool:
        return True

    def get_sensitivity_level(self) -> SensitivityLevel:
        return SensitivityLevel.L1

    def requires_approval(self) -> bool:
        return False

    def allow_in_model_context(self) -> bool:
        return False

    @abstractmethod
    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        raise NotImplementedError

    def _policy_result(
        self,
        request: ToolCallRequest,
        context: ToolExecutionContext,
        policy_result: PolicyEvaluationResult,
        status: ToolExecutionStatus,
    ) -> ToolCallResult:
        audit_event = context.audit_logger.record_tool_event(
            request,
            context.user_context,
            status,
            policy_result,
            metadata={"tool_name": self.name},
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
        )
        reason = policy_result.reasons[0].message if policy_result.reasons else "Policy decision."
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            status=status,
            output={
                "approval_required": status == ToolExecutionStatus.ASKED,
                "audit_event_id": str(audit_event.event_id),
                "policy_decision": policy_result.decision.value,
                "reasons": [reason.model_dump(mode="json") for reason in policy_result.reasons],
            },
            error_message=reason if status == ToolExecutionStatus.DENIED else None,
            allow_in_model_context=False,
        )

    def _failed_result(
        self, request: ToolCallRequest, context: ToolExecutionContext, message: str
    ) -> ToolCallResult:
        audit_event = context.audit_logger.record_tool_event(
            request,
            context.user_context,
            ToolExecutionStatus.FAILED,
            None,
            metadata={"tool_name": self.name, "error": message},
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
        )
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            status=ToolExecutionStatus.FAILED,
            output={"audit_event_id": str(audit_event.event_id)},
            error_message=message,
            allow_in_model_context=False,
        )
