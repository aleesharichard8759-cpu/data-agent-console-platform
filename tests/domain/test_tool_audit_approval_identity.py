import pytest
from pydantic import ValidationError

from app.domain import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    AuditActor,
    AuditEvent,
    AuditEventType,
    AuditTarget,
    AuthContext,
    Department,
    ToolCallRequest,
    ToolCallResult,
    ToolExecutionStatus,
    ToolRiskLevel,
    UserContext,
    UserRole,
)


def test_identity_and_auth_context_round_trip() -> None:
    user = UserContext(
        user_id="user_001",
        display_name="Data Steward",
        roles=(UserRole.DATA_STEWARD,),
        department=Department(department_id="dept_data", name="Data Department"),
    )
    auth = AuthContext(user=user, session_id="session_001", auth_method="sso")

    restored = AuthContext.model_validate_json(auth.model_dump_json())

    assert restored.user.roles == (UserRole.DATA_STEWARD,)
    assert restored.user.department is not None
    assert restored.user.department.name == "Data Department"


def test_sql_tool_call_requires_sql_gateway() -> None:
    with pytest.raises(ValidationError):
        ToolCallRequest(
            tool_name="sql_query",
            action="sql.query",
            risk_level=ToolRiskLevel.LOW,
        )


def test_high_risk_tool_call_requires_approval() -> None:
    with pytest.raises(ValidationError):
        ToolCallRequest(
            tool_name="permission_inspection",
            action="permission.revoke",
            risk_level=ToolRiskLevel.HIGH,
        )


def test_tool_result_round_trip() -> None:
    request = ToolCallRequest(
        tool_name="sql_query",
        action="sql.query",
        risk_level=ToolRiskLevel.LOW,
        requires_sql_gateway=True,
    )
    result = ToolCallResult(
        tool_call_id=request.tool_call_id,
        status=ToolExecutionStatus.MASKED,
        output={"rows": []},
        masked_fields=("rows[0].email_hash",),
    )

    restored = ToolCallResult.model_validate_json(result.model_dump_json())

    assert restored.status == ToolExecutionStatus.MASKED
    assert restored.masked_fields == ("rows[0].email_hash",)


def test_audit_event_round_trip() -> None:
    event = AuditEvent(
        event_type=AuditEventType.POLICY_EVALUATED,
        actor=AuditActor(actor_id="agent_001", actor_type="agent"),
        target=AuditTarget(target_id="asset_001", target_type="table", sensitivity_level="L3"),
        action="policy.evaluate",
        outcome="ask",
        reason="approval required",
    )

    restored = AuditEvent.model_validate_json(event.model_dump_json())

    assert restored.event_type == AuditEventType.POLICY_EVALUATED
    assert restored.target is not None
    assert restored.target.sensitivity_level == "L3"


def test_approval_request_decision_consistency() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest(
            requester_id="data_steward",
            approver_ids=("security_reviewer",),
            status=ApprovalStatus.PENDING,
            decision=ApprovalDecision.APPROVE,
            reason="Review high risk action.",
            target_type="tool_call",
            target_id=ToolCallRequest(
                tool_name="mock_tool",
                action="mock.inspect",
                risk_level=ToolRiskLevel.LOW,
            ).tool_call_id,
        )

