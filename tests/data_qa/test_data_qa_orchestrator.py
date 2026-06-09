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
from app.tools import DataToolRegistry, QuerySQLTool, SearchMetadataTool, build_real_tool_registry


def build_orchestrator():
    audit_logger = InMemoryAuditLogger()
    return (
        DataQAOrchestrator(
            policy_engine=PolicyEngine(),
            tool_registry=build_real_tool_registry(),
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


class FakeMetadataConnector:
    def search_assets(self, query, context):
        return {
            "results": [
                {
                    "name": "ads_afs_rma_multi_dim_metric_1d",
                    "qualified_name": "rma_ads.ads_afs_rma_multi_dim_metric_1d",
                    "database": "rma_ads",
                    "type": "BASE TABLE",
                    "source": "starrocks_information_schema",
                    "column_count": "12",
                    "comment": "RMA ADS metric table",
                }
            ]
        }


class FakeWarehouseConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def query_preview(self, sql, context):
        self.calls.append(sql)
        return {
            "allowed": True,
            "decision": "allow",
            "columns": ["complaint_rate"],
            "rows": [{"complaint_rate": 0.0234}],
            "row_count": 1,
            "reviewed_sql": sql,
            "source": "starrocks",
        }


def build_rma_orchestrator():
    audit_logger = InMemoryAuditLogger()
    warehouse = FakeWarehouseConnector()
    registry = DataToolRegistry()
    registry.register(SearchMetadataTool(metadata_connector=FakeMetadataConnector()))
    registry.register(QuerySQLTool(warehouse_connector=warehouse))
    return (
        DataQAOrchestrator(
            policy_engine=PolicyEngine(),
            tool_registry=registry,
            audit_logger=audit_logger,
        ),
        warehouse,
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


def test_rma_complaint_rate_maps_to_real_ads_table_and_formula() -> None:
    orchestrator, warehouse = build_rma_orchestrator()

    result = orchestrator.run(
        DataQATaskRequest(user_query="本月 RMA 客诉率是多少？", audience=AudienceRole.MANAGER),
        user_context=user(),
        session_id="test_session",
    )

    assert result.semantic_intent.standard_metrics == ("complaint_rate",)
    assert result.semantic_intent.data_sources[0] == "ads_afs_rma_multi_dim_metric_1d"
    assert "ads_afs_rma_multi_dim_metric_1d" in result.execution_plan.sql
    assert "sum(problem_qty) / nullif(sum(sale_qty), 0)" in result.execution_plan.sql
    assert "stat_date" in result.execution_plan.sql
    assert "ads_trade_order_dashboard_day" not in result.execution_plan.sql
    assert warehouse.calls == [result.execution_plan.sql]
    assert "2.34%" in result.answer.summary
    assert "SUM(problem_qty)" in (result.answer.metric_definition or "")


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
