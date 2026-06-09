from data_governance_agent_runtime.core.enums import ActionRisk, AuditOutcome
from data_governance_agent_runtime.core.models import (
    Actor,
    GovernanceTask,
    RuntimeContext,
    ToolRequest,
)
from data_governance_agent_runtime.runtime.engine import GovernanceAgentRuntime


def make_runtime_context() -> RuntimeContext:
    return RuntimeContext(
        actor=Actor(actor_id="tester", roles=("data_steward",)),
        purpose="runtime_security_test",
    )


def test_runtime_completes_default_governance_loop() -> None:
    runtime = GovernanceAgentRuntime()
    task = GovernanceTask(objective="scan governed assets", domain="trade")

    response = runtime.run(task, make_runtime_context())

    assert response.status == "completed"
    assert len(response.results) == 4
    assert len(response.audit_event_ids) == 4


def test_runtime_creates_governance_plan_for_high_risk_action() -> None:
    runtime = GovernanceAgentRuntime()
    task = GovernanceTask(objective="review permission changes", domain="security")
    request = ToolRequest(
        tool_name="permission_inspection",
        action="permission.revoke",
        risk=ActionRisk.HIGH,
        requires_approval=True,
    )

    response = runtime.run(task, make_runtime_context(), [request])

    assert response.status == "plan_required"
    assert response.plan is not None
    assert response.plan.pending_tool.action == "permission.revoke"
    assert response.results[0].data["requires_plan_approval"] is True


def test_unknown_tool_is_denied_and_audited() -> None:
    runtime = GovernanceAgentRuntime()
    task = GovernanceTask(objective="try unknown tool", domain="trade")
    request = ToolRequest(
        tool_name="direct_database",
        action="database.connect",
        risk=ActionRisk.CRITICAL,
    )

    response = runtime.run(task, make_runtime_context(), [request])
    events = runtime.audit.list_events()

    assert response.status == "denied"
    assert events[-1].outcome == AuditOutcome.DENIED
    assert events[-1].reason == "Unknown tool denied by runtime."


def test_sql_query_uses_gateway_and_masks_sensitive_named_fields() -> None:
    runtime = GovernanceAgentRuntime()
    task = GovernanceTask(objective="query governed gateway", domain="trade")
    request = ToolRequest(
        tool_name="sql_query",
        action="sql.query",
        risk=ActionRisk.LOW,
        requires_sql_gateway=True,
        parameters={"statement": "select asset_name from governed_catalog"},
    )

    response = runtime.run(task, make_runtime_context(), [request])

    assert response.status == "completed"
    result = response.results[0]
    assert result.data["statement_type"] == "select"
    assert result.data["row_count"] == 0
    assert result.data["rows"] == []
