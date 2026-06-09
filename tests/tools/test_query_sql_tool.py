from app.audit import InMemoryAuditLogger
from app.domain import ToolCallRequest, ToolExecutionStatus, ToolRiskLevel
from app.domain.identity import UserContext, UserRole
from app.policy import PolicyEngine
from app.tools import DataToolRegistry, QuerySQLTool, ToolExecutionContext


class FakeWarehouseConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def query_preview(self, sql, context):
        self.calls.append(sql)
        return {
            "allowed": True,
            "decision": "allow",
            "columns": ["metric_date", "order_count"],
            "rows": [{"metric_date": "2026-06-09", "order_count": 7}],
            "row_count": 1,
            "reviewed_sql": sql,
            "source": "starrocks",
        }


def make_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_context=UserContext(
            user_id="sql_tool_user",
            display_name="SQL Tool User",
            roles=(UserRole.DATA_STEWARD,),
        ),
        task_context=None,
        policy_engine=PolicyEngine(),
        audit_logger=InMemoryAuditLogger(),
    )


def make_sql_request(sql: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_name="query_sql",
        action="sql.query",
        asset_type="aggregate_metric",
        parameters={"sql": sql},
        risk_level=ToolRiskLevel.LOW,
        requires_sql_gateway=True,
    )


def test_query_sql_tool_must_pass_sql_gateway_before_warehouse_execution() -> None:
    connector = FakeWarehouseConnector()
    tool = QuerySQLTool(warehouse_connector=connector)
    registry = DataToolRegistry()
    registry.register(tool)

    result = registry.execute_tool(
        make_sql_request("select order_count from ads_order_summary limit 10"),
        make_context(),
    )

    assert result.status == ToolExecutionStatus.SUCCEEDED
    assert tool.gateway_review_count == 1
    assert tool.warehouse_execution_count == 1
    assert connector.calls == ["select order_count from ads_order_summary limit 10"]
    assert result.output["sql_gateway_decision"] == "allow"
    assert result.output["data"]["source"] == "starrocks"
    assert result.allow_in_model_context is False


def test_query_sql_tool_denies_gateway_rejection_without_warehouse_execution() -> None:
    connector = FakeWarehouseConnector()
    tool = QuerySQLTool(warehouse_connector=connector)
    registry = DataToolRegistry()
    registry.register(tool)

    result = registry.execute_tool(
        make_sql_request("select customer_phone from ads_order_summary limit 10"),
        make_context(),
    )

    assert result.status == ToolExecutionStatus.DENIED
    assert tool.gateway_review_count == 1
    assert tool.warehouse_execution_count == 0
    assert connector.calls == []
    assert "customer_phone" in (result.error_message or "")


def test_query_sql_tool_returns_approval_required_for_gateway_ask() -> None:
    connector = FakeWarehouseConnector()
    tool = QuerySQLTool(warehouse_connector=connector)
    registry = DataToolRegistry()
    registry.register(tool)

    result = registry.execute_tool(
        make_sql_request("select order_id from ods_order_detail limit 10"),
        make_context(),
    )

    assert result.status == ToolExecutionStatus.ASKED
    assert result.output["approval_required"] is True
    assert tool.gateway_review_count == 1
    assert tool.warehouse_execution_count == 0
    assert connector.calls == []


def test_query_sql_tool_fails_closed_without_real_connector() -> None:
    tool = QuerySQLTool()
    registry = DataToolRegistry()
    registry.register(tool)

    result = registry.execute_tool(
        make_sql_request("select order_count from ads_order_summary limit 10"),
        make_context(),
    )

    assert result.status == ToolExecutionStatus.FAILED
    assert "No real warehouse connector is configured" in (result.error_message or "")
    assert tool.gateway_review_count == 1
    assert tool.warehouse_execution_count == 0
