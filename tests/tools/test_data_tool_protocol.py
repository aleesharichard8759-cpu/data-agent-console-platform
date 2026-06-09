from typing import Any

import pytest
from pydantic import BaseModel, Field

from app.audit import InMemoryAuditLogger
from app.domain import PolicyDecision, ToolCallRequest, ToolExecutionStatus, ToolRiskLevel
from app.domain.identity import UserContext, UserRole
from app.policy import PolicyEngine, PolicyRule
from app.tools import (
    DataTool,
    DataToolRegistry,
    SearchMetadataTool,
    ToolExecutionContext,
    ToolNotFoundError,
    build_real_tool_registry,
)


class SpyInput(BaseModel):
    value: str = Field(description="Spy input value.")


class SpyOutput(BaseModel):
    value: str = Field(description="Spy output value.")


class SensitiveSpyOutput(SpyOutput):
    customer_email: str = Field(description="Synthetic sensitive field.")


class SpyTool(DataTool):
    name = "spy_tool"
    description = "Spy tool for execution-flow tests."
    input_model = SpyInput
    output_model = SpyOutput

    execution_count: int = 0

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = SpyInput.model_validate(validated_input)
        self.execution_count += 1
        return {"value": payload.value}


class SensitiveSpyTool(SpyTool):
    output_model = SensitiveSpyOutput

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        output = super()._execute(validated_input, context)
        output["customer_email"] = "synthetic_email_value"
        return output


def make_user() -> UserContext:
    return UserContext(
        user_id="tool_user",
        display_name="Tool User",
        roles=(UserRole.DATA_STEWARD,),
    )


def make_context(policy_engine: PolicyEngine, plan_mode: bool = False) -> ToolExecutionContext:
    return ToolExecutionContext(
        user_context=make_user(),
        task_context=None,
        policy_engine=policy_engine,
        audit_logger=InMemoryAuditLogger(),
        dry_run=False,
        plan_mode=plan_mode,
    )


def make_request(action: str = "spy.execute", tool_name: str = "spy_tool") -> ToolCallRequest:
    return ToolCallRequest(
        tool_name=tool_name,
        action=action,
        parameters={"value": "ok"},
        risk_level=ToolRiskLevel.LOW,
    )


def make_rule(effect: PolicyDecision, action: str = "spy.execute") -> PolicyRule:
    return PolicyRule(
        rule_id=f"test.{effect.value}",
        name=f"Test {effect.value}",
        description="Test policy rule.",
        effect=effect,
        priority=1,
        match_operations=(action,),
        reason=f"Policy returned {effect.value}.",
    )


def test_register_and_list_tools() -> None:
    registry = build_real_tool_registry()

    names = [tool.name for tool in registry.list_tools()]

    assert names == [
        "generate_quality_rules",
        "get_metric_definition",
        "get_table_metadata",
        "query_sql",
        "search_metadata",
    ]
    assert registry.get_tool("search_metadata").description


def test_get_missing_tool_raises() -> None:
    registry = DataToolRegistry()

    with pytest.raises(ToolNotFoundError):
        registry.get_tool("missing_tool")


def test_deny_does_not_execute_tool() -> None:
    tool = SpyTool()
    registry = DataToolRegistry()
    registry.register(tool)
    context = make_context(PolicyEngine(rules=(make_rule(PolicyDecision.DENY),)))

    result = registry.execute_tool(make_request(), context)

    assert result.status == ToolExecutionStatus.DENIED
    assert tool.execution_count == 0
    assert result.error_message == "Policy returned deny."
    assert result.output["policy_decision"] == "deny"


def test_ask_does_not_execute_and_returns_approval_required() -> None:
    tool = SpyTool()
    registry = DataToolRegistry()
    registry.register(tool)
    context = make_context(PolicyEngine(rules=(make_rule(PolicyDecision.ASK),)))

    result = registry.execute_tool(make_request(), context)

    assert result.status == ToolExecutionStatus.ASKED
    assert tool.execution_count == 0
    assert result.output["approval_required"] is True
    assert result.output["policy_decision"] == "ask"


def test_allow_executes_tool() -> None:
    tool = SpyTool()
    registry = DataToolRegistry()
    registry.register(tool)
    context = make_context(PolicyEngine(rules=(make_rule(PolicyDecision.ALLOW),)))

    result = registry.execute_tool(make_request(), context)

    assert result.status == ToolExecutionStatus.SUCCEEDED
    assert tool.execution_count == 1
    assert result.output["data"] == {"value": "ok"}
    assert result.output["audit_event_id"]


def test_default_registry_hooks_mask_sensitive_tool_output() -> None:
    tool = SensitiveSpyTool()
    registry = DataToolRegistry()
    registry.register(tool)
    context = make_context(PolicyEngine(rules=(make_rule(PolicyDecision.ALLOW),)))

    result = registry.execute_tool(make_request(), context)

    assert result.status == ToolExecutionStatus.SUCCEEDED
    assert result.output["data"]["customer_email"] == "***MASKED***"
    assert "data.customer_email" in result.masked_fields


def test_read_only_tool_is_allowed_in_plan_mode_but_requires_real_connector() -> None:
    registry = DataToolRegistry()
    registry.register(SearchMetadataTool())
    context = make_context(PolicyEngine(), plan_mode=True)
    request = ToolCallRequest(
        tool_name="search_metadata",
        action="metadata.query",
        asset_type="metadata",
        parameters={"query": "order", "limit": 5},
        risk_level=ToolRiskLevel.LOW,
    )

    result = registry.execute_tool(request, context)

    assert result.status == ToolExecutionStatus.FAILED
    assert "No real metadata connector is configured" in (result.error_message or "")
