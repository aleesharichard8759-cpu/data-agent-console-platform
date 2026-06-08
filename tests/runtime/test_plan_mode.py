from typing import Any

import pytest
from pydantic import BaseModel, Field, ValidationError

from app.audit import InMemoryAuditLogger
from app.core.errors import UnsafeOperationError
from app.domain import (
    AuditEventType,
    DataDomain,
    GovernanceTask,
    GovernanceTaskLevel,
    GovernanceTaskType,
    UserContext,
    UserRole,
)
from app.runtime import GovernancePlan, PlanModeError, PlanModeManager, PlanModeState
from app.tools import DataTool, ToolExecutionContext


class DemoInput(BaseModel):
    value: str = Field(description="Demo value.")


class DemoOutput(BaseModel):
    value: str = Field(description="Demo value.")


class ReadOnlyTool(DataTool):
    name = "read_only_tool"
    description = "Read-only plan mode test tool."
    input_model = DemoInput
    output_model = DemoOutput

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = DemoInput.model_validate(validated_input)
        return {"value": payload.value}


class WriteTool(ReadOnlyTool):
    name = "write_tool"
    description = "Write plan mode test tool."

    def is_read_only(self) -> bool:
        return False


class DestructiveTool(WriteTool):
    name = "destructive_tool"
    description = "Destructive plan mode test tool."

    def is_destructive(self) -> bool:
        return True


def make_user() -> UserContext:
    return UserContext(
        user_id="plan_user",
        display_name="Plan User",
        roles=(UserRole.DATA_STEWARD,),
    )


def make_task(level: GovernanceTaskLevel = GovernanceTaskLevel.G3) -> GovernanceTask:
    return GovernanceTask(
        title="订单域数据质量治理",
        task_type=GovernanceTaskType.DATA_QUALITY,
        task_level=level,
        domain=DataDomain.TRADE,
        objective="Plan governed quality rule changes for order assets.",
        created_by="plan_user",
        requires_approval=level in {GovernanceTaskLevel.G4, GovernanceTaskLevel.G5},
    )


def make_manager(audit_logger: InMemoryAuditLogger | None = None) -> PlanModeManager:
    return PlanModeManager(
        audit_logger=audit_logger or InMemoryAuditLogger(),
        user_context=make_user(),
        session_id="plan_session",
        agent_name="plan_agent",
    )


def create_valid_plan(
    manager: PlanModeManager,
    task: GovernanceTask,
    allowed_tools_after_approval: tuple[str, ...] = ("write_tool",),
) -> GovernancePlan:
    manager.enter_plan_mode(task)
    return manager.create_plan(
        title="订单域质量规则变更计划",
        summary="Create governed quality rules for approved order assets.",
        affected_assets=("ads_order_quality_1d",),
        proposed_actions=("quality_rule.create",),
        risk_level=task.task_level,
        required_approvers=("mock_approver",),
        rollback_plan="Disable newly created mock quality rules and restore previous config.",
        allowed_tools_after_approval=allowed_tools_after_approval,
    )


def test_plan_mode_allows_read_only_tools_while_planning() -> None:
    audit_logger = InMemoryAuditLogger()
    manager = make_manager(audit_logger)

    state = manager.enter_plan_mode(make_task())
    manager.assert_tool_allowed(ReadOnlyTool())

    assert state == PlanModeState.PLANNING
    assert audit_logger.list_events({"event_type": AuditEventType.PLAN_MODE_ENTERED})


def test_plan_mode_blocks_write_tools_while_planning() -> None:
    audit_logger = InMemoryAuditLogger()
    manager = make_manager(audit_logger)
    manager.enter_plan_mode(make_task())

    with pytest.raises(PlanModeError, match="read-only"):
        manager.assert_tool_allowed(WriteTool())

    denied_events = audit_logger.list_events({"event_type": AuditEventType.PERMISSION_DENIED})
    assert denied_events
    assert denied_events[-1].tool_name == "write_tool"


def test_plan_without_rollback_plan_cannot_be_submitted() -> None:
    manager = make_manager()
    task = make_task()
    manager.enter_plan_mode(task)

    with pytest.raises(ValidationError, match="rollback"):
        manager.create_plan(
            title="Missing rollback",
            summary="This plan is invalid.",
            affected_assets=("ads_order_quality_1d",),
            proposed_actions=("quality_rule.create",),
            risk_level=GovernanceTaskLevel.G3,
            required_approvers=("mock_approver",),
            rollback_plan=" ",
            allowed_tools_after_approval=("write_tool",),
        )


def test_high_risk_plan_cannot_disable_approval_requirement() -> None:
    manager = make_manager()
    task = make_task(GovernanceTaskLevel.G4)
    manager.enter_plan_mode(task)

    with pytest.raises(ValidationError, match="must require approval"):
        manager.create_plan(
            title="Unsafe approval bypass",
            summary="Attempt to bypass approval for a high-risk plan.",
            affected_assets=("dwd_trade_order_detail_d",),
            proposed_actions=("permission.change",),
            risk_level=GovernanceTaskLevel.G4,
            required_approvers=("mock_approver",),
            rollback_plan="Discard proposed permission change and keep current mock state.",
            approval_required=False,
            allowed_tools_after_approval=("write_tool",),
        )


def test_plan_mode_without_audit_logger_fails_closed() -> None:
    with pytest.raises(UnsafeOperationError, match="Audit Logger"):
        PlanModeManager(
            audit_logger=None,  # type: ignore[arg-type]
            user_context=make_user(),
            session_id="plan_session",
            agent_name="plan_agent",
        )


def test_unapproved_plan_cannot_execute() -> None:
    audit_logger = InMemoryAuditLogger()
    manager = make_manager(audit_logger)
    plan = create_valid_plan(manager, make_task())
    manager.request_approval(plan)

    with pytest.raises(PlanModeError, match="Unapproved"):
        manager.execute_approved_plan(plan.plan_id)

    assert manager.state == PlanModeState.WAITING_APPROVAL
    assert audit_logger.list_events({"event_type": AuditEventType.PERMISSION_DENIED})


def test_approved_plan_allows_only_plan_listed_tools() -> None:
    manager = make_manager()
    plan = create_valid_plan(
        manager,
        make_task(),
        allowed_tools_after_approval=("write_tool",),
    )
    manager.request_approval(plan)
    manager.approve_plan(plan.plan_id, "mock_approver")

    manager.assert_tool_allowed(WriteTool())
    with pytest.raises(PlanModeError, match="not listed"):
        manager.assert_tool_allowed(ReadOnlyTool())
    with pytest.raises(PlanModeError, match="Destructive"):
        manager.assert_tool_allowed(DestructiveTool())


def test_g5_task_cannot_be_approved() -> None:
    audit_logger = InMemoryAuditLogger()
    manager = make_manager(audit_logger)
    task = make_task(GovernanceTaskLevel.G5)
    plan = create_valid_plan(manager, task, allowed_tools_after_approval=("write_tool",))
    manager.request_approval(plan)

    with pytest.raises(Exception, match="G5"):
        manager.approve_plan(plan.plan_id, "mock_approver")

    assert manager.state == PlanModeState.REJECTED
    rejected_events = audit_logger.list_events({"event_type": AuditEventType.PLAN_REJECTED})
    assert rejected_events
