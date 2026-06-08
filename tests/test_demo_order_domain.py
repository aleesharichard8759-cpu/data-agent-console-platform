from app.audit import InMemoryAuditLogger
from app.domain import ToolCallRequest, ToolRiskLevel, UserContext, UserRole
from app.main import CreateTaskRequest, create_app
from app.policy import PolicyEngine
from app.tools import QuerySQLTool, ToolExecutionContext


def call_route(app, path: str, method: str, *args, **kwargs):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint(*args, **kwargs)
    raise AssertionError(f"Route not found: {method} {path}")


def test_order_domain_governance_demo_runs() -> None:
    app = create_app()

    created = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="请为订单域生成质量规则建议"),
    )
    task_id = created.task_id
    run_result = call_route(app, "/tasks/{task_id}/run", "POST", task_id)
    task_response = call_route(app, "/tasks/{task_id}", "GET", task_id)

    assert run_result["status"] == "completed"
    assert run_result["recommendations"]
    assert task_response["result"]["task_id"] == task_id


def test_customer_phone_detail_query_is_denied() -> None:
    tool = QuerySQLTool()
    audit_logger = InMemoryAuditLogger()
    request = ToolCallRequest(
        tool_name="query_sql",
        action="sql.query",
        asset_type="table",
        parameters={"sql": "select customer_phone from dwd_customer_detail_d limit 10"},
        risk_level=ToolRiskLevel.LOW,
        requires_sql_gateway=True,
    )

    result = tool.execute(
        request,
        ToolExecutionContext(
            user_context=UserContext(
                user_id="demo_user",
                display_name="Demo User",
                roles=(UserRole.DATA_STEWARD,),
            ),
            task_context=None,
            policy_engine=PolicyEngine(),
            audit_logger=audit_logger,
        ),
    )

    assert result.status == "denied"
    assert "Sensitive column is denied" in result.error_message
    assert audit_logger.list_events({"event_type": "sql_reviewed"})


def test_quality_rule_suggestions_are_generated() -> None:
    app = create_app()
    task_id = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="订单域质量规则治理"),
    ).task_id

    result = call_route(app, "/tasks/{task_id}/run", "POST", task_id)

    subagent_evidence = [item for item in result["evidence"] if item.get("node") == "subagents"]
    assert subagent_evidence
    assert "data_quality_agent" in subagent_evidence[0]["agents"]
    assert any(
        "strong rules" in recommendation.lower() for recommendation in result["recommendations"]
    )


def test_metadata_issues_are_identified() -> None:
    app = create_app()
    task_id = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="请补全订单域字段注释和数据字典"),
    ).task_id

    result = call_route(app, "/tasks/{task_id}/run", "POST", task_id)

    assert result["status"] == "completed"
    assert any("Assign owner" in recommendation for recommendation in result["recommendations"])


def test_demo_audit_events_are_complete_for_task() -> None:
    app = create_app()
    task_id = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="请为订单域生成质量规则建议"),
    ).task_id
    call_route(app, "/tasks/{task_id}/run", "POST", task_id)

    events = call_route(app, "/audit", "GET", task_id)["events"]
    event_types = {event["event_type"] for event in events}

    assert "task_created" in event_types
    assert "tool_requested" in event_types
    assert "policy_evaluated" in event_types
    assert "tool_executed" in event_types
    assert "task_completed" in event_types
