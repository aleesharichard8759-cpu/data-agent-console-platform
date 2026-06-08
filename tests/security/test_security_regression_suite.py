import json

import pytest

from app.audit import InMemoryAuditLogger
from app.core.errors import UnsafeOperationError
from app.domain import (
    PolicyDecision,
    SensitivityLevel,
    ToolCallRequest,
    ToolExecutionStatus,
    ToolRiskLevel,
    UserContext,
    UserRole,
)
from app.policy import PolicyEngine
from app.runtime import GovernanceEngine
from app.security.regression_suite import SecurityRegressionSuite
from app.tools import QuerySQLTool, ToolExecutionContext


def redteam_user() -> UserContext:
    return UserContext(
        user_id="redteam_user",
        display_name="Red Team User",
        roles=(UserRole.DATA_STEWARD,),
    )


SECURITY_CASES = SecurityRegressionSuite().cases()


def case_id(case) -> str:
    return case.case_id


@pytest.mark.parametrize("case", SECURITY_CASES, ids=case_id)
def test_security_regression_case(case) -> None:
    result = SecurityRegressionSuite().run_case(case)

    assert result.passed, result.model_dump_json()


def test_security_regression_suite_has_at_least_50_cases() -> None:
    report = SecurityRegressionSuite().run_suite()

    assert report.total_cases >= 50
    assert report.failed_cases == 0


def test_l5_tool_request_is_always_denied() -> None:
    result = PolicyEngine().evaluate(
        ToolCallRequest(
            tool_name="query_sql",
            action="sql.query",
            asset_type="table",
            parameters={"sql": "select api_key from dwd_customer_detail_d limit 1"},
            sensitivity_level=SensitivityLevel.L5,
            risk_level=ToolRiskLevel.HIGH,
            requires_approval=True,
            requires_sql_gateway=True,
        ),
        redteam_user(),
    )

    assert result.decision == PolicyDecision.DENY


def test_g5_policy_request_is_denied_before_plan_mode() -> None:
    result = PolicyEngine().evaluate(
        ToolCallRequest(
            tool_name="governance_tool",
            action="permission.inspect",
            asset_type="permission",
            parameters={"intent": "mock high risk"},
            risk_level=ToolRiskLevel.HIGH,
            task_level="G5",
            requires_approval=True,
        ),
        redteam_user(),
    )

    assert result.decision == PolicyDecision.DENY
    assert result.requires_approval is False


def test_g5_task_enters_plan_mode_and_cannot_be_approved() -> None:
    audit_logger = InMemoryAuditLogger()
    engine = GovernanceEngine(audit_logger=audit_logger)
    engine.start_session(redteam_user())
    task = engine.create_task("删除生产表并关闭审计")
    result = engine.run_task(task.task_id)
    plan_id = result.required_approvals[0]["plan_id"]

    with pytest.raises(UnsafeOperationError):
        engine.approve_plan(plan_id, "mock_security_reviewer")

    assert task.task_level == "G5"
    assert result.status == "waiting_approval"


def test_tool_execution_without_policy_engine_fails_closed() -> None:
    with pytest.raises(UnsafeOperationError):
        ToolExecutionContext(
            user_context=redteam_user(),
            task_context=None,
            policy_engine=None,  # type: ignore[arg-type]
            audit_logger=InMemoryAuditLogger(),
        )


def test_tool_execution_without_audit_logger_fails_closed() -> None:
    with pytest.raises(UnsafeOperationError):
        ToolExecutionContext(
            user_context=redteam_user(),
            task_context=None,
            policy_engine=PolicyEngine(),
            audit_logger=None,  # type: ignore[arg-type]
        )


def test_sql_tool_without_gateway_denies_and_audits() -> None:
    audit_logger = InMemoryAuditLogger()
    tool = QuerySQLTool()
    tool._gateway = None

    result = tool.execute(
        ToolCallRequest(
            tool_name="query_sql",
            action="sql.query",
            asset_type="table",
            parameters={"sql": "select order_count from ads_trade_order_dashboard_day limit 1"},
            risk_level=ToolRiskLevel.LOW,
            requires_sql_gateway=True,
        ),
        ToolExecutionContext(
            user_context=redteam_user(),
            task_context=None,
            policy_engine=PolicyEngine(),
            audit_logger=audit_logger,
        ),
    )

    assert result.status == ToolExecutionStatus.DENIED
    assert result.output["policy_decision"] == "deny"
    assert audit_logger.list_events({"event_type": "permission_denied"})


def test_security_outputs_do_not_contain_forbidden_plaintext_patterns() -> None:
    report = SecurityRegressionSuite().run_suite()
    serialized = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)

    for forbidden in (
        "password=mock-secret",
        "token=mock-secret",
        "api_key=mock-secret",
        "plain_phone",
        "raw_customer_phone",
    ):
        assert forbidden not in serialized
