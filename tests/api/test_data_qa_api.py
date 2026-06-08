from fastapi import HTTPException

from app.data_qa import AudienceRole, DataQAFeedbackRating, DataQATaskRequest
from app.main import DataQAFeedbackRequest, create_app


def call_route(app, path: str, method: str, *args, **kwargs):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint(*args, **kwargs)
    raise AssertionError(f"Route not found: {method} {path}")


def test_data_qa_mvp_targets_expose_scope_and_thresholds() -> None:
    app = create_app()

    response = call_route(app, "/data-qa/mvp-targets", "GET")

    assert "L1 query_metric" in response["scope"]["stable"]
    assert response["targets"]["l1_sql_execution_success_rate"] == 0.80
    assert "default_deny" in response["safety_defaults"]


def test_data_qa_run_endpoint_stores_result() -> None:
    app = create_app()

    result = call_route(
        app,
        "/data-qa/run",
        "POST",
        DataQATaskRequest(
            user_query="上个月华东区的销售额是多少？",
            audience=AudienceRole.MANAGER,
        ),
    )
    task_id = result["structured_task"]["task_id"]
    stored = call_route(app, "/data-qa/tasks/{task_id}", "GET", task_id)

    assert result["answer"]["status"] == "complete"
    assert result["execution_plan"]["tool_sequence"] == ["search_metadata", "query_sql"]
    assert stored["result"]["structured_task"]["task_id"] == task_id


def test_data_qa_negative_feedback_enters_bad_case_queue() -> None:
    app = create_app()
    result = call_route(
        app,
        "/data-qa/run",
        "POST",
        DataQATaskRequest(user_query="上个月华东区的销售额是多少？"),
    )
    task_id = result["structured_task"]["task_id"]

    feedback = call_route(
        app,
        "/data-qa/feedback",
        "POST",
        DataQAFeedbackRequest(
            task_id=task_id,
            rating=DataQAFeedbackRating.NEGATIVE,
            error_type="metric_mismatch",
            comment="口径不对",
        ),
    )
    bad_cases = call_route(app, "/data-qa/bad-cases", "GET")

    assert feedback.feedback["enter_bad_case"]
    assert bad_cases["count"] == 1
    assert bad_cases["bad_cases"][0]["error_type"] == "metric_mismatch"


def test_data_qa_task_lookup_returns_404_for_unknown_task() -> None:
    app = create_app()

    try:
        call_route(app, "/data-qa/tasks/{task_id}", "GET", "missing")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("unknown Data&QA task should raise HTTP 404")
