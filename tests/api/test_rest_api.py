from fastapi import HTTPException

from app.main import (
    CreateSessionRequest,
    CreateTaskRequest,
    PlanApprovalRequest,
    PlanRejectRequest,
    SQLReviewRequest,
    ToolDryRunRequest,
    create_app,
)


def call_route(app, path: str, method: str, *args, **kwargs):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint(*args, **kwargs)
    raise AssertionError(f"Route not found: {method} {path}")


def test_api_health_response_has_trace() -> None:
    app = create_app()

    response = call_route(app, "/health", "GET")

    assert response["status"] == "ok"
    assert response["trace_id"]
    assert "audit_refs" in response


def test_api_creates_session_and_task() -> None:
    app = create_app()

    session = call_route(app, "/sessions", "POST", CreateSessionRequest())
    task = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="帮我治理订单域数据"),
    )

    assert session.session_id
    assert session.audit_refs
    assert task.task_id
    assert task.trace_id
    assert task.audit_refs


def test_api_runs_order_domain_governance_task() -> None:
    app = create_app()
    task = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="请为订单域生成质量规则建议"),
    )

    result = call_route(app, "/tasks/{task_id}/run", "POST", task.task_id)
    task_view = call_route(app, "/tasks/{task_id}", "GET", task.task_id)
    audit = call_route(app, "/tasks/{task_id}/audit", "GET", task.task_id)

    assert result["status"] == "completed"
    assert result["trace_id"]
    assert result["audit_refs"]
    assert task_view["result"]["task_id"] == task.task_id
    assert audit["events"]
    assert audit["trace_id"]


def test_api_sql_review_denies_dangerous_sql() -> None:
    app = create_app()

    review = call_route(
        app,
        "/sql/review",
        "POST",
        SQLReviewRequest(sql="select * from dwd_customer_detail_d"),
    )

    assert review.decision == "deny"
    assert not review.allowed
    assert review.audit_refs
    assert any(risk["risk_type"] == "select_star" for risk in review.risks)


def test_api_tool_dry_run_uses_registry_and_audit() -> None:
    app = create_app()

    result = call_route(
        app,
        "/tools/{tool_name}/dry-run",
        "POST",
        "search_metadata",
        ToolDryRunRequest(parameters={"query": "order", "limit": 2}),
    )

    assert result.tool_name == "search_metadata"
    assert result.status == "succeeded"
    assert result.trace_id
    assert result.audit_refs


def test_api_tool_dry_run_unknown_tool_returns_404() -> None:
    app = create_app()

    try:
        call_route(
            app,
            "/tools/{tool_name}/dry-run",
            "POST",
            "unknown_tool",
            ToolDryRunRequest(parameters={}),
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("unknown tool should raise HTTP 404")


def test_api_mock_approval_flow() -> None:
    app = create_app()
    task = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="帮我识别订单域敏感字段"),
    )
    run_result = call_route(app, "/tasks/{task_id}/run", "POST", task.task_id)
    plan_id = run_result["required_approvals"][0]["plan_id"]

    approved = call_route(
        app,
        "/plans/{plan_id}/approve",
        "POST",
        plan_id,
        PlanApprovalRequest(),
    )

    assert approved.state == "approved"
    assert approved.trace_id
    assert approved.audit_refs


def test_api_mock_reject_flow() -> None:
    app = create_app()
    task = call_route(
        app,
        "/tasks",
        "POST",
        CreateTaskRequest(user_prompt="帮我识别订单域敏感字段"),
    )
    run_result = call_route(app, "/tasks/{task_id}/run", "POST", task.task_id)
    plan_id = run_result["required_approvals"][0]["plan_id"]

    rejected = call_route(
        app,
        "/plans/{plan_id}/reject",
        "POST",
        plan_id,
        PlanRejectRequest(reason="mock reject"),
    )

    assert rejected.state == "rejected"
    assert rejected.audit_refs
