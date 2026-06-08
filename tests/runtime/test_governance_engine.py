from typing import Any

from pydantic import BaseModel, Field

from app.audit import InMemoryAuditLogger
from app.domain import (
    AuditEventType,
    GovernanceTaskLevel,
    GovernanceTaskType,
    PolicyDecision,
    ToolCallRequest,
    ToolExecutionStatus,
    ToolRiskLevel,
    UserContext,
    UserRole,
)
from app.policy import PolicyEngine, PolicyRule
from app.runtime import (
    GovernanceEngine,
    GovernanceStep,
    GovernanceStepNode,
    GovernanceStepStatus,
    TaskRunStatus,
)
from app.tools import DataTool, DataToolRegistry, ToolExecutionContext


class SpyInput(BaseModel):
    value: str = Field(description="Spy value.")


class SpyOutput(BaseModel):
    value: str = Field(description="Spy value.")


class SpyTool(DataTool):
    name = "spy_tool"
    description = "Spy tool for deny tests."
    input_model = SpyInput
    output_model = SpyOutput
    execution_count: int = 0

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = SpyInput.model_validate(validated_input)
        self.execution_count += 1
        return {"value": payload.value}


def make_user() -> UserContext:
    return UserContext(
        user_id="engine_user",
        display_name="Engine User",
        roles=(UserRole.DATA_STEWARD,),
    )


def make_engine(audit_logger: InMemoryAuditLogger | None = None) -> GovernanceEngine:
    engine = GovernanceEngine(audit_logger=audit_logger or InMemoryAuditLogger())
    engine.start_session(make_user())
    return engine


def test_engine_can_create_task() -> None:
    engine = make_engine()

    task = engine.create_task("请为订单域生成质量规则建议")

    assert task.task_id
    assert task.task_type == GovernanceTaskType.DATA_QUALITY
    assert engine.get_task(task.task_id) == task


def test_engine_classifies_data_quality_task() -> None:
    engine = make_engine()

    task = engine.classify_task("订单表需要质量规则")

    assert task.task_type == GovernanceTaskType.DATA_QUALITY
    assert task.task_level == GovernanceTaskLevel.G2


def test_engine_classifies_metadata_task() -> None:
    engine = make_engine()

    task = engine.classify_task("帮我补全字段注释和数据字典")

    assert task.task_type == GovernanceTaskType.METADATA_COMPLETION


def test_g1_g2_task_can_generate_recommendations_directly() -> None:
    engine = make_engine()
    task = engine.create_task("请为订单域生成质量规则建议")

    result = engine.run_task(task.task_id)

    assert result.status == TaskRunStatus.COMPLETED
    assert len(result.steps) == 9
    assert result.evidence
    assert result.recommendations
    assert not result.required_approvals
    assert {step.node for step in result.steps} == set(GovernanceEngine.workflow_nodes)


def test_g4_task_enters_plan_mode() -> None:
    audit_logger = InMemoryAuditLogger()
    engine = make_engine(audit_logger)
    task = engine.create_task("请检查订单域敏感字段脱敏和权限策略")

    result = engine.run_task(task.task_id)

    assert task.task_level == GovernanceTaskLevel.G4
    assert result.status == TaskRunStatus.WAITING_APPROVAL
    assert result.required_approvals
    assert result.steps[-1].node == GovernanceStepNode.GOVERNANCE_PLANNING
    assert result.steps[-1].status == GovernanceStepStatus.WAITING_APPROVAL
    assert audit_logger.list_events({"event_type": AuditEventType.PLAN_MODE_ENTERED})


def test_task_completion_writes_audit_event() -> None:
    audit_logger = InMemoryAuditLogger()
    engine = make_engine(audit_logger)
    task = engine.create_task("生成订单域治理报告")

    result = engine.run_task(task.task_id)

    assert result.status == TaskRunStatus.COMPLETED
    completed_events = audit_logger.list_events({"event_type": AuditEventType.TASK_COMPLETED})
    assert len(completed_events) == 1
    assert completed_events[0].task_id == str(task.task_id)


def test_denied_request_does_not_execute_tool() -> None:
    spy_tool = SpyTool()
    registry = DataToolRegistry()
    registry.register(spy_tool)
    engine = GovernanceEngine(
        tool_registry=registry,
        policy_engine=PolicyEngine(
            rules=(
                PolicyRule(
                    rule_id="test.deny_spy",
                    name="Deny spy",
                    description="Deny spy tool.",
                    effect=PolicyDecision.DENY,
                    priority=1,
                    match_operations=("spy.execute",),
                    reason="Spy execution denied.",
                ),
            )
        ),
    )
    engine.start_session(make_user())
    task = engine.create_task("盘点资产")
    step = GovernanceStep(
        task_id=task.task_id,
        node=GovernanceStepNode.EVIDENCE_COLLECTION,
        tool_request=ToolCallRequest(
            tool_name="spy_tool",
            action="spy.execute",
            parameters={"value": "blocked"},
            risk_level=ToolRiskLevel.LOW,
        ),
    )

    executed_step, result = engine.execute_step(step)

    assert result is not None
    assert result.status == ToolExecutionStatus.DENIED
    assert executed_step.status == GovernanceStepStatus.DENIED
    assert spy_tool.execution_count == 0
