from app.audit import InMemoryAuditLogger
from app.data_qa import (
    AudienceRole,
    ClarificationStatus,
    DataQAOrchestrator,
    DataQATaskRequest,
    DataQATaskType,
)
from app.domain.identity import UserContext, UserRole
from app.policy import PolicyEngine
from app.tools.mock_tools import build_mock_tool_registry


def build_orchestrator():
    audit_logger = InMemoryAuditLogger()
    return (
        DataQAOrchestrator(
            policy_engine=PolicyEngine(),
            tool_registry=build_mock_tool_registry(),
            audit_logger=audit_logger,
        ),
        audit_logger,
    )


def user() -> UserContext:
    return UserContext(
        user_id="data_qa_tester",
        display_name="Data QA Tester",
        roles=(UserRole.DATA_ANALYST,),
    )


def test_l1_metric_query_runs_through_governed_tools() -> None:
    orchestrator, audit_logger = build_orchestrator()

    result = orchestrator.run(
        DataQATaskRequest(
            user_query="上个月华东区的销售额是多少？",
            audience=AudienceRole.MANAGER,
        ),
        user_context=user(),
        session_id="test_session",
    )

    assert result.structured_task.task_type == DataQATaskType.QUERY_METRIC
    assert result.structured_task.clarification_status == ClarificationStatus.COMPLETE
    assert result.semantic_intent.standard_metrics == ("order_amount",)
    assert result.execution_plan.tool_sequence == ("search_metadata", "query_sql")
    assert "limit 100" in result.execution_plan.sql.lower()
    assert result.answer.status == ClarificationStatus.COMPLETE
    assert result.answer.audit_refs
    assert any(event.action == "sql.query" for event in audit_logger.list_events())


def test_metric_explanation_uses_definition_and_sources() -> None:
    orchestrator, _audit_logger = build_orchestrator()

    result = orchestrator.run(
        DataQATaskRequest(user_query="其他收入是什么？"),
        user_context=user(),
        session_id="test_session",
    )

    assert result.structured_task.task_type == DataQATaskType.EXPLAIN_METRIC
    assert result.execution_plan.tool_sequence == ("get_metric_definition",)
    assert result.answer.metric_definition
    assert "metric_platform" in result.answer.sources


def test_ambiguous_recent_query_requires_clarification_before_sql() -> None:
    orchestrator, audit_logger = build_orchestrator()

    result = orchestrator.run(
        DataQATaskRequest(user_query="最近转化差在哪里？"),
        user_context=user(),
        session_id="test_session",
    )

    assert result.structured_task.clarification_status == ClarificationStatus.NEEDS_CLARIFICATION
    assert result.answer.follow_up_questions
    assert result.execution_plan.tool_sequence == tuple()
    assert not audit_logger.list_events()


def test_sensitive_detail_request_is_denied_without_tool_execution() -> None:
    orchestrator, audit_logger = build_orchestrator()

    result = orchestrator.run(
        DataQATaskRequest(user_query="导出客户手机号明细"),
        user_context=user(),
        session_id="test_session",
    )

    assert result.semantic_intent.permission_decision == "deny"
    assert result.answer.status == ClarificationStatus.DENIED
    assert result.answer.requires_human_escalation
    assert result.execution_plan.tool_sequence == tuple()
    assert not audit_logger.list_events()


def test_business_advice_is_escalated_in_mvp() -> None:
    orchestrator, _audit_logger = build_orchestrator()

    result = orchestrator.run(
        DataQATaskRequest(user_query="哪些客户的报价不合理，需要调整？"),
        user_context=user(),
        session_id="test_session",
    )

    assert result.structured_task.task_type == DataQATaskType.BUSINESS_ADVICE
    assert result.structured_task.requires_human_escalation
    assert result.answer.status == ClarificationStatus.ESCALATED
    assert result.trace.failure_node == "risk_review"
