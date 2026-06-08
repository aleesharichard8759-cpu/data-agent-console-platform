import pytest

from data_governance_agent_runtime.core.enums import ActionRisk, Decision, Environment
from data_governance_agent_runtime.core.models import Actor, RuntimeContext, ToolRequest
from data_governance_agent_runtime.policy.engine import PolicyEngine


def make_context(environment: Environment = Environment.MOCK) -> RuntimeContext:
    return RuntimeContext(
        actor=Actor(actor_id="tester", roles=("data_steward",)),
        environment=environment,
        purpose="unit_test",
    )


def test_policy_denies_production_execution() -> None:
    request = ToolRequest(
        tool_name="asset_inventory",
        action="asset.inventory",
        risk=ActionRisk.LOW,
    )

    decision = PolicyEngine().evaluate(make_context(Environment.PRODUCTION), request)

    assert decision.decision == Decision.DENY
    assert decision.rule_id == "policy.no_production_agent_execution"


def test_policy_requires_sql_gateway_for_sql_actions() -> None:
    request = ToolRequest(tool_name="sql_query", action="sql.query", risk=ActionRisk.LOW)

    decision = PolicyEngine().evaluate(make_context(), request)

    assert decision.decision == Decision.DENY
    assert decision.rule_id == "policy.sql_gateway_required"


def test_policy_asks_for_high_risk_actions() -> None:
    request = ToolRequest(
        tool_name="permission_inspection",
        action="permission.revoke",
        risk=ActionRisk.HIGH,
        requires_approval=True,
    )

    decision = PolicyEngine().evaluate(make_context(), request)

    assert decision.decision == Decision.ASK
    assert decision.rule_id == "policy.plan_mode_required"


def test_policy_fail_closed_on_exception() -> None:
    def broken_rule(context: RuntimeContext, request: ToolRequest):  # type: ignore[no-untyped-def]
        del context, request
        raise RuntimeError("boom")

    request = ToolRequest(
        tool_name="asset_inventory",
        action="asset.inventory",
        risk=ActionRisk.LOW,
    )

    decision = PolicyEngine(rules=[broken_rule]).evaluate(make_context(), request)

    assert decision.decision == Decision.DENY
    assert decision.rule_id == "policy.fail_closed"


@pytest.mark.parametrize("risk", [ActionRisk.LOW, ActionRisk.MEDIUM])
def test_policy_allows_low_and_medium_mock_governance_actions(risk: ActionRisk) -> None:
    request = ToolRequest(tool_name="asset_inventory", action="asset.inventory", risk=risk)

    decision = PolicyEngine().evaluate(make_context(), request)

    assert decision.decision == Decision.ALLOW
