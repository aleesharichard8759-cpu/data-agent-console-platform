import pytest

from app.agents import (
    AgentOrchestrator,
    AgentPermissionError,
    AgentTaskContext,
    MetadataAgent,
    build_agent_tool_registry,
    build_default_agent_registry,
    build_default_orchestrator,
)
from app.audit import InMemoryAuditLogger
from app.domain import (
    DataDomain,
    GovernanceTask,
    GovernanceTaskLevel,
    GovernanceTaskType,
    ToolCallRequest,
    ToolRiskLevel,
    UserContext,
    UserRole,
)
from app.policy import PolicyEngine


def make_user() -> UserContext:
    return UserContext(
        user_id="agent_user",
        display_name="Agent User",
        roles=(UserRole.DATA_STEWARD,),
    )


def make_task(task_type: GovernanceTaskType = GovernanceTaskType.DATA_QUALITY) -> GovernanceTask:
    return GovernanceTask(
        title="订单域治理任务",
        task_type=task_type,
        task_level=GovernanceTaskLevel.G2,
        domain=DataDomain.TRADE,
        objective="Run specialized governance subagents.",
        created_by="agent_user",
    )


def make_context(task: GovernanceTask) -> AgentTaskContext:
    return AgentTaskContext(task=task, user_context=make_user(), session_id="agent_session")


def make_agent_registry():
    return build_default_agent_registry(
        policy_engine=PolicyEngine(),
        audit_logger=InMemoryAuditLogger(),
        tool_registry=build_agent_tool_registry(),
    )


def test_agent_cannot_call_unauthorized_tool() -> None:
    registry = make_agent_registry()
    agent = registry.get_agent("metadata_agent")
    task = make_task(GovernanceTaskType.METADATA_COMPLETION)

    with pytest.raises(AgentPermissionError, match="not allowed"):
        agent.call_tool(
            make_context(task),
            ToolCallRequest(
                tool_name="generate_quality_rules",
                action="quality_rule.suggest",
                asset_type="quality_rule",
                parameters={"table_name": "ads_order_quality_1d"},
                risk_level=ToolRiskLevel.LOW,
            ),
        )


def test_agent_cannot_call_sql_tool() -> None:
    registry = make_agent_registry()
    agent = registry.get_agent("metadata_agent")
    task = make_task(GovernanceTaskType.METADATA_COMPLETION)

    with pytest.raises(AgentPermissionError, match="SQL"):
        agent.call_tool(
            make_context(task),
            ToolCallRequest(
                tool_name="query_sql",
                action="sql.query",
                asset_type="sql_query",
                parameters={"sql": "select order_count from ads_order_summary limit 10"},
                risk_level=ToolRiskLevel.LOW,
                requires_sql_gateway=True,
            ),
        )


def test_security_agent_identifies_sensitive_fields_and_vetoes_context() -> None:
    registry = make_agent_registry()
    agent = registry.get_agent("security_agent")

    result = agent.run(make_context(make_task(GovernanceTaskType.SENSITIVE_DATA_DISCOVERY)))

    assert result.veto is True
    assert result.findings["allow_in_model_context"] is False
    assert "L4" in result.findings["levels"]
    assert "L5" in result.findings["levels"]


def test_data_quality_agent_generates_rule_suggestions() -> None:
    registry = make_agent_registry()
    agent = registry.get_agent("data_quality_agent")

    result = agent.run(make_context(make_task(GovernanceTaskType.DATA_QUALITY)))

    assert result.status == "completed"
    assert result.findings["completeness_rules"]
    assert result.findings["strong_rules"]
    assert result.findings["weak_rules"]


def test_metadata_agent_outputs_metadata_issues() -> None:
    registry = make_agent_registry()
    agent = registry.get_agent("metadata_agent")

    result = agent.run(make_context(make_task(GovernanceTaskType.METADATA_COMPLETION)))

    assert result.findings["missing_owner_tables"]
    assert result.findings["missing_comment_fields"]
    assert result.findings["duplicate_table_candidates"]
    assert result.findings["completion_suggestions"]


def test_metric_agent_outputs_metric_card() -> None:
    registry = make_agent_registry()
    agent = registry.get_agent("metric_agent")

    result = agent.run(make_context(make_task(GovernanceTaskType.METRIC_GOVERNANCE)))

    assert result.findings["business_definition"]
    assert result.findings["technical_definition"]
    assert result.findings["dimensions"]
    assert result.findings["time_field"] == "metric_date"
    assert result.findings["open_questions"]


def test_orchestrator_dispatches_multiple_agents() -> None:
    task = make_task(GovernanceTaskType.DATA_QUALITY)
    orchestrator = AgentOrchestrator(make_agent_registry())

    result = orchestrator.run(task, make_context(task))

    assert result.status == "completed"
    assert {agent_result.agent_name for agent_result in result.agent_results} == {
        "metadata_agent",
        "data_quality_agent",
    }


def test_orchestrator_honors_security_agent_veto() -> None:
    task = make_task(GovernanceTaskType.GOVERNANCE_REPORT)
    orchestrator = build_default_orchestrator(
        policy_engine=PolicyEngine(),
        audit_logger=InMemoryAuditLogger(),
        tool_registry=build_agent_tool_registry(),
    )

    result = orchestrator.run(task, make_context(task))

    assert result.status == "vetoed"
    assert result.vetoed_by == ("security_agent",)
    assert result.summary["security_veto"] is True


def test_registry_selects_agent_for_task_type() -> None:
    registry = make_agent_registry()
    task = make_task(GovernanceTaskType.METADATA_COMPLETION)

    selected = registry.select_agents_for_task(task)

    assert len(selected) == 1
    assert isinstance(selected[0], MetadataAgent)
