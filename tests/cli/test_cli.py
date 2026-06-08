import json

from app.cli import main


def run_cli(capsys, argv: list[str]) -> dict:
    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 0
    return json.loads(captured.out)


def test_cli_task_command_runs_order_governance(capsys) -> None:
    payload = run_cli(capsys, ["task", "帮我治理订单域数据"])

    assert payload["trace_id"]
    assert payload["audit_refs"]
    assert payload["task_id"]
    assert payload["status"] == "completed"


def test_cli_sql_review_denies_select_star(capsys) -> None:
    payload = run_cli(capsys, ["sql-review", "select * from dwd_customer_detail_d"])

    assert payload["trace_id"]
    assert payload["audit_refs"]
    assert payload["decision"] == "deny"
    assert any(risk["risk_type"] == "select_star" for risk in payload["risks"])


def test_cli_eval_run_generates_report(capsys) -> None:
    payload = run_cli(capsys, ["eval", "run"])

    assert payload["trace_id"]
    assert payload["total_cases"] == 30
    assert payload["passed_cases"] >= 1


def test_cli_audit_command_returns_traceable_empty_view(capsys) -> None:
    payload = run_cli(capsys, ["audit", "--task-id", "mock-task-id"])

    assert payload["trace_id"]
    assert "audit_refs" in payload
    assert payload["events"] == []
