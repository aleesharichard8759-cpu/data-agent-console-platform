from __future__ import annotations

from typing import Any

from app.domain.classification import SensitivityLevel
from app.domain.tools import ToolExecutionStatus
from app.hooks.base import Hook
from app.hooks.manager import HookManager
from app.hooks.types import HookContext, HookDecision, HookEventType, HookResult

SENSITIVE_FIELD_TOKENS = (
    "address",
    "customer_phone",
    "email",
    "id_card",
    "phone",
    "secret",
    "token",
)


class AuditPreToolUseHook(Hook):
    name = "audit_pre_tool_use"
    event_type = HookEventType.PRE_TOOL_USE

    def run(self, context: HookContext) -> HookResult:
        context.execution_context.audit_logger.record_tool_event(
            context.request,
            context.execution_context.user_context,
            ToolExecutionStatus.CREATED,
            None,
            metadata={"hook": self.name, "event_type": self.event_type.value},
            task=context.execution_context.task_context,
            session_id=context.execution_context.session_id,
            agent_name=context.execution_context.agent_name,
        )
        return HookResult(continue_execution=True)


class AuditPostToolUseHook(Hook):
    name = "audit_post_tool_use"
    event_type = HookEventType.POST_TOOL_USE

    def run(self, context: HookContext) -> HookResult:
        status = context.result.status if context.result is not None else ToolExecutionStatus.FAILED
        context.execution_context.audit_logger.record_tool_event(
            context.request,
            context.execution_context.user_context,
            status,
            None,
            metadata={"hook": self.name, "event_type": self.event_type.value},
            task=context.execution_context.task_context,
            session_id=context.execution_context.session_id,
            agent_name=context.execution_context.agent_name,
        )
        return HookResult(continue_execution=True)


class DenySensitiveModelContextHook(Hook):
    name = "deny_sensitive_model_context"
    event_type = HookEventType.POST_TOOL_USE

    def run(self, context: HookContext) -> HookResult:
        if context.result is None:
            return HookResult(continue_execution=True)
        if (
            context.request.sensitivity_level in {SensitivityLevel.L4, SensitivityLevel.L5}
            and context.result.allow_in_model_context
        ):
            context.result = context.result.model_copy(update={"allow_in_model_context": False})
            return HookResult(
                continue_execution=True,
                decision=HookDecision.DENY,
                reason="L4/L5 tool results cannot enter model context.",
                system_message="Sensitive result was removed from model context eligibility.",
            )
        return HookResult(continue_execution=True)


class RequireApprovalHook(Hook):
    name = "require_approval"
    event_type = HookEventType.PERMISSION_REQUEST

    def run(self, context: HookContext) -> HookResult:
        if context.result is None:
            return HookResult(continue_execution=True)
        reason = context.result.error_message or context.result.output.get("reasons", [{}])[0].get(
            "message", "Approval required."
        )
        output = {
            **context.result.output,
            "approval_required": True,
            "approval_placeholder": {
                "status": "pending",
                "reason": reason,
            },
        }
        context.result = context.result.model_copy(update={"output": output})
        return HookResult(
            continue_execution=True,
            decision=HookDecision.ASK,
            reason="Approval placeholder generated.",
            metadata={"approval_required": True},
        )


class MaskingPostToolUseHook(Hook):
    name = "masking_post_tool_use"
    event_type = HookEventType.POST_TOOL_USE

    def run(self, context: HookContext) -> HookResult:
        if context.result is None or not context.result.output:
            return HookResult(continue_execution=True)
        masked_fields: list[str] = list(context.result.masked_fields)
        masked_output = self._mask_value(context.result.output, "", masked_fields)
        context.result = context.result.model_copy(
            update={"output": masked_output, "masked_fields": tuple(masked_fields)}
        )
        if masked_fields:
            context.execution_context.audit_logger.record_result_masked(
                context.request,
                context.execution_context.user_context,
                tuple(masked_fields),
                task=context.execution_context.task_context,
                session_id=context.execution_context.session_id,
                agent_name=context.execution_context.agent_name,
                metadata={"hook": self.name},
            )
        return HookResult(
            continue_execution=True,
            metadata={"masked_fields": tuple(masked_fields)},
        )

    def _mask_value(self, value: Any, path: str, masked_fields: list[str]) -> Any:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else key
                if self._is_sensitive_key(key):
                    output[key] = "***MASKED***"
                    masked_fields.append(child_path)
                else:
                    output[key] = self._mask_value(item, child_path, masked_fields)
            return output
        if isinstance(value, list):
            return [
                self._mask_value(item, f"{path}[{index}]", masked_fields)
                for index, item in enumerate(value)
            ]
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in SENSITIVE_FIELD_TOKENS)


def build_default_hook_manager() -> HookManager:
    return HookManager(
        hooks=(
            AuditPreToolUseHook(),
            AuditPostToolUseHook(),
            DenySensitiveModelContextHook(),
            RequireApprovalHook(),
            MaskingPostToolUseHook(),
        )
    )
