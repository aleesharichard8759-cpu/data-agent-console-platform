from typing import Any

from pydantic import BaseModel, Field

from app.audit import InMemoryAuditLogger
from app.domain import (
    PolicyDecision,
    SensitivityLevel,
    ToolCallRequest,
    ToolExecutionStatus,
    ToolRiskLevel,
)
from app.domain.identity import UserContext, UserRole
from app.hooks import (
    Hook,
    HookContext,
    HookDecision,
    HookEventType,
    HookManager,
    HookResult,
    build_default_hook_manager,
)
from app.policy import PolicyEngine, PolicyRule
from app.tools import DataTool, DataToolRegistry, ToolExecutionContext


class DemoInput(BaseModel):
    value: str = Field(description="Demo input value.")


class DemoOutput(BaseModel):
    value: str = Field(description="Demo output value.")
    customer_phone: str | None = Field(default=None, description="Synthetic sensitive field.")


class DemoTool(DataTool):
    name = "demo_tool"
    description = "Demo hook test tool."
    input_model = DemoInput
    output_model = DemoOutput

    execution_count: int = 0
    include_sensitive_output: bool = False
    model_context_allowed: bool = False

    def allow_in_model_context(self) -> bool:
        return self.model_context_allowed

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = DemoInput.model_validate(validated_input)
        self.execution_count += 1
        output = {"value": payload.value}
        if self.include_sensitive_output:
            output["customer_phone"] = "synthetic_phone_value"
        return output


class BlockingPreHook(Hook):
    name = "blocking_pre_hook"
    event_type = HookEventType.PRE_TOOL_USE

    def run(self, context: HookContext) -> HookResult:
        del context
        return HookResult(
            continue_execution=False,
            decision=HookDecision.DENY,
            reason="Blocked by pre hook.",
        )


class AllowingPreHook(Hook):
    name = "allowing_pre_hook"
    event_type = HookEventType.PRE_TOOL_USE

    def run(self, context: HookContext) -> HookResult:
        del context
        return HookResult(continue_execution=True, decision=HookDecision.ALLOW)


class ModifyingPostHook(Hook):
    name = "modifying_post_hook"
    event_type = HookEventType.POST_TOOL_USE

    def run(self, context: HookContext) -> HookResult:
        if context.result is not None:
            output = {**context.result.output, "post_hook_modified": True}
            context.result = context.result.model_copy(update={"output": output})
        return HookResult(continue_execution=True)


class CountingHook(Hook):
    def __init__(self, event_type: HookEventType) -> None:
        self.event_type = event_type
        self.name = f"counting_{event_type.value}"
        self.call_count = 0

    def run(self, context: HookContext) -> HookResult:
        del context
        self.call_count += 1
        return HookResult(continue_execution=True)


def make_user() -> UserContext:
    return UserContext(
        user_id="hook_user",
        display_name="Hook User",
        roles=(UserRole.DATA_STEWARD,),
    )


def make_context(policy_engine: PolicyEngine) -> ToolExecutionContext:
    return ToolExecutionContext(
        user_context=make_user(),
        task_context=None,
        policy_engine=policy_engine,
        audit_logger=InMemoryAuditLogger(),
    )


def make_policy(effect: PolicyDecision) -> PolicyEngine:
    return PolicyEngine(
        rules=(
            PolicyRule(
                rule_id=f"test.{effect.value}",
                name=f"Test {effect.value}",
                description="Hook test policy.",
                effect=effect,
                priority=1,
                match_operations=("demo.execute",),
                reason=f"Policy returned {effect.value}.",
            ),
        )
    )


def make_request(**overrides: Any) -> ToolCallRequest:
    payload = {
        "tool_name": "demo_tool",
        "action": "demo.execute",
        "parameters": {"value": "ok"},
        "risk_level": ToolRiskLevel.LOW,
    }
    payload.update(overrides)
    return ToolCallRequest(**payload)


def execute_with_hooks(
    hook_manager: HookManager,
    policy_engine: PolicyEngine,
    tool: DemoTool | None = None,
    request: ToolCallRequest | None = None,
):
    registry = DataToolRegistry(hook_manager=hook_manager)
    demo_tool = tool or DemoTool()
    registry.register(demo_tool)
    result = registry.execute_tool(request or make_request(), make_context(policy_engine))
    return result, demo_tool


def test_pre_hook_can_block_tool_execution_and_is_audited() -> None:
    result, tool = execute_with_hooks(
        HookManager((BlockingPreHook(),)), make_policy(PolicyDecision.ALLOW)
    )

    assert result.status == ToolExecutionStatus.DENIED
    assert result.error_message == "Blocked by pre hook."
    assert tool.execution_count == 0
    assert result.output["audit_event_id"]


def test_pre_hook_allow_cannot_bypass_policy_engine_deny() -> None:
    result, tool = execute_with_hooks(
        HookManager((AllowingPreHook(),)), make_policy(PolicyDecision.DENY)
    )

    assert result.status == ToolExecutionStatus.DENIED
    assert tool.execution_count == 0
    assert result.output["policy_decision"] == "deny"


def test_post_hook_can_modify_result() -> None:
    result, tool = execute_with_hooks(
        HookManager((ModifyingPostHook(),)),
        make_policy(PolicyDecision.ALLOW),
    )

    assert result.status == ToolExecutionStatus.SUCCEEDED
    assert tool.execution_count == 1
    assert result.output["post_hook_modified"] is True


def test_denied_hook_is_called() -> None:
    denied_hook = CountingHook(HookEventType.PERMISSION_DENIED)
    result, tool = execute_with_hooks(HookManager((denied_hook,)), make_policy(PolicyDecision.DENY))

    assert result.status == ToolExecutionStatus.DENIED
    assert tool.execution_count == 0
    assert denied_hook.call_count == 1


def test_approval_hook_is_called() -> None:
    result, tool = execute_with_hooks(build_default_hook_manager(), make_policy(PolicyDecision.ASK))

    assert result.status == ToolExecutionStatus.ASKED
    assert tool.execution_count == 0
    assert result.output["approval_required"] is True
    assert result.output["approval_placeholder"]["status"] == "pending"


def test_l4_l5_result_cannot_enter_model_context() -> None:
    result, tool = execute_with_hooks(
        build_default_hook_manager(),
        make_policy(PolicyDecision.ALLOW),
        tool=DemoTool(model_context_allowed=True),
        request=make_request(sensitivity_level=SensitivityLevel.L5),
    )

    assert result.status == ToolExecutionStatus.SUCCEEDED
    assert tool.execution_count == 1
    assert result.allow_in_model_context is False


def test_masking_post_tool_use_hook_masks_sensitive_fields() -> None:
    result, tool = execute_with_hooks(
        build_default_hook_manager(),
        make_policy(PolicyDecision.ALLOW),
        tool=DemoTool(include_sensitive_output=True),
    )

    assert result.status == ToolExecutionStatus.SUCCEEDED
    assert tool.execution_count == 1
    assert result.output["data"]["customer_phone"] == "***MASKED***"
    assert "data.customer_phone" in result.masked_fields
