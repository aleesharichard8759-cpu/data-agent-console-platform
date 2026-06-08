from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.core.errors import RuntimeErrorBase, UnsafeOperationError
from app.domain.audit import AuditActor, AuditEvent, AuditEventType, AuditTarget
from app.domain.common import DomainModel, new_id
from app.domain.identity import UserContext
from app.domain.tasks import GovernanceTask, GovernanceTaskLevel
from app.tools.context import AuditLogger

if TYPE_CHECKING:
    from app.tools.base import DataTool


class PlanModeState(StrEnum):
    DISABLED = "disabled"
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"


class GovernancePlan(DomainModel):
    plan_id: UUID = Field(default_factory=new_id, description="Unique governance plan id.")
    task_id: UUID = Field(description="Governance task id covered by this plan.")
    title: str = Field(description="Plan title.")
    summary: str = Field(description="Safe plan summary.")
    affected_assets: tuple[str, ...] = Field(description="Assets affected by the plan.")
    proposed_actions: tuple[str, ...] = Field(description="Proposed governance actions.")
    risk_level: GovernanceTaskLevel = Field(description="Highest governance risk level.")
    required_approvers: tuple[str, ...] = Field(description="Mock approver ids required.")
    rollback_plan: str = Field(description="Rollback or recovery plan.")
    approval_required: bool = Field(description="Whether the plan requires approval.")
    allowed_tools_after_approval: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Tool names allowed after approval.",
    )

    @field_validator(
        "title",
        "summary",
        "rollback_plan",
    )
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Plan text fields must not be empty.")
        return value.strip()

    @field_validator("affected_assets", "proposed_actions", "required_approvers")
    @classmethod
    def tuple_items_not_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("Plan tuple fields must not be empty.")
        if any(not item.strip() for item in value):
            raise ValueError("Plan tuple items must not be empty.")
        return tuple(item.strip() for item in value)

    @field_validator("allowed_tools_after_approval")
    @classmethod
    def allowed_tools_not_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("Allowed tool names must not be empty.")
        return tuple(item.strip() for item in value)

    @model_validator(mode="after")
    def validate_rollback_plan(self) -> GovernancePlan:
        if not self.rollback_plan.strip():
            raise ValueError("Every governance plan must include rollback_plan.")
        if (
            self.risk_level in {GovernanceTaskLevel.G4, GovernanceTaskLevel.G5}
            and not self.approval_required
        ):
            raise ValueError("G4/G5 governance plans must require approval.")
        return self


class PlanModeError(RuntimeErrorBase):
    """Raised when plan mode state or approval rules are violated."""


class PlanModeManager:
    """Governance Plan Mode state machine with audit for every state transition."""

    def __init__(
        self,
        audit_logger: AuditLogger,
        user_context: UserContext,
        session_id: str | None = None,
        agent_name: str = "governance_agent",
    ) -> None:
        if audit_logger is None:
            raise UnsafeOperationError("Plan Mode requires Audit Logger.")
        self._audit_logger = audit_logger
        self._user_context = user_context
        self._session_id = session_id
        self._agent_name = agent_name
        self._state = PlanModeState.DISABLED
        self._task: GovernanceTask | None = None
        self._plans: dict[UUID, GovernancePlan] = {}
        self._approved_plans: set[UUID] = set()
        self._active_plan_id: UUID | None = None

    @property
    def state(self) -> PlanModeState:
        return self._state

    def enter_plan_mode(self, task: GovernanceTask) -> PlanModeState:
        self._task = task
        self._transition(
            PlanModeState.PLANNING,
            AuditEventType.PLAN_MODE_ENTERED,
            "plan_mode.enter",
            "Governance task entered plan mode.",
            task=task,
        )
        return self._state

    def assert_tool_allowed(self, tool: DataTool) -> None:
        if self._state == PlanModeState.DISABLED:
            return
        if tool.is_destructive():
            self._deny_tool(tool, "Destructive tools cannot execute directly in plan mode.")
        if self._state == PlanModeState.PLANNING:
            if not tool.is_read_only():
                self._deny_tool(tool, "Planning state allows read-only tools only.")
            return
        if self._state == PlanModeState.APPROVED:
            plan = self._active_plan()
            if tool.name not in plan.allowed_tools_after_approval:
                self._deny_tool(tool, "Tool is not listed in the approved governance plan.")
            return
        if self._state == PlanModeState.EXECUTING:
            plan = self._active_plan()
            if tool.name not in plan.allowed_tools_after_approval:
                self._deny_tool(tool, "Tool is not listed in the executing governance plan.")
            return
        self._deny_tool(tool, f"Plan mode state {self._state.value} does not allow tool use.")

    def create_plan(
        self,
        *,
        title: str,
        summary: str,
        affected_assets: tuple[str, ...],
        proposed_actions: tuple[str, ...],
        risk_level: GovernanceTaskLevel | None = None,
        required_approvers: tuple[str, ...],
        rollback_plan: str,
        approval_required: bool = True,
        allowed_tools_after_approval: tuple[str, ...] = tuple(),
        task: GovernanceTask | None = None,
    ) -> GovernancePlan:
        resolved_task = task or self._task
        if resolved_task is None:
            raise PlanModeError("Plan mode requires a governance task before creating a plan.")
        plan = GovernancePlan(
            task_id=resolved_task.task_id,
            title=title,
            summary=summary,
            affected_assets=affected_assets,
            proposed_actions=proposed_actions,
            risk_level=risk_level or resolved_task.task_level,
            required_approvers=required_approvers,
            rollback_plan=rollback_plan,
            approval_required=approval_required,
            allowed_tools_after_approval=allowed_tools_after_approval,
        )
        self._plans[plan.plan_id] = plan
        self._active_plan_id = plan.plan_id
        self._log_state_event(
            AuditEventType.PLAN_CREATED,
            "plan.create",
            "created",
            "Governance plan created.",
            plan=plan,
            task=resolved_task,
        )
        return plan

    def request_approval(self, plan: GovernancePlan) -> GovernancePlan:
        if plan.plan_id not in self._plans:
            self._plans[plan.plan_id] = plan
        self._active_plan_id = plan.plan_id
        self._transition(
            PlanModeState.WAITING_APPROVAL,
            AuditEventType.APPROVAL_REQUIRED,
            "plan.approval.request",
            "Mock approval requested for governance plan.",
            plan=plan,
        )
        return plan

    def approve_plan(self, plan_id: UUID | str, approver: str) -> GovernancePlan:
        plan = self._get_plan(plan_id)
        if plan.risk_level == GovernanceTaskLevel.G5:
            self._transition(
                PlanModeState.REJECTED,
                AuditEventType.PLAN_REJECTED,
                "plan.approval.reject",
                "G5 governance plans cannot be approved in mock plan mode.",
                plan=plan,
                approver=approver,
            )
            raise UnsafeOperationError("G5 governance tasks cannot be approved through Plan Mode.")
        if approver not in plan.required_approvers:
            self._log_state_event(
                AuditEventType.PERMISSION_DENIED,
                "plan.approval.deny",
                "denied",
                "Approver is not listed on the governance plan.",
                plan=plan,
                approver=approver,
            )
            raise PlanModeError("Approver is not listed on the governance plan.")
        self._approved_plans.add(plan.plan_id)
        self._active_plan_id = plan.plan_id
        self._transition(
            PlanModeState.APPROVED,
            AuditEventType.PLAN_APPROVED,
            "plan.approval.approve",
            "Governance plan approved by mock approver.",
            plan=plan,
            approver=approver,
        )
        return plan

    def reject_plan(self, plan_id: UUID | str, approver: str, reason: str) -> GovernancePlan:
        plan = self._get_plan(plan_id)
        self._approved_plans.discard(plan.plan_id)
        self._transition(
            PlanModeState.REJECTED,
            AuditEventType.PLAN_REJECTED,
            "plan.approval.reject",
            reason,
            plan=plan,
            approver=approver,
        )
        return plan

    def execute_approved_plan(self, plan_id: UUID | str) -> GovernancePlan:
        plan = self._get_plan(plan_id)
        if plan.plan_id not in self._approved_plans:
            self._log_state_event(
                AuditEventType.PERMISSION_DENIED,
                "plan.execute.deny",
                "denied",
                "Governance plan must be approved before execution.",
                plan=plan,
            )
            raise PlanModeError("Unapproved governance plans cannot execute.")
        self._active_plan_id = plan.plan_id
        self._transition(
            PlanModeState.EXECUTING,
            AuditEventType.PLAN_EXECUTION_STARTED,
            "plan.execute",
            "Approved governance plan entered execution state.",
            plan=plan,
        )
        return plan

    def get_plan(self, plan_id: UUID | str) -> GovernancePlan | None:
        return self._plans.get(UUID(str(plan_id)))

    def _active_plan(self) -> GovernancePlan:
        if self._active_plan_id is None:
            raise PlanModeError("No active governance plan.")
        return self._get_plan(self._active_plan_id)

    def _get_plan(self, plan_id: UUID | str) -> GovernancePlan:
        try:
            plan_uuid = UUID(str(plan_id))
        except ValueError as exc:
            raise PlanModeError(f"Invalid plan id: {plan_id}") from exc
        try:
            return self._plans[plan_uuid]
        except KeyError as exc:
            raise PlanModeError(f"Governance plan not found: {plan_id}") from exc

    def _deny_tool(self, tool: DataTool, reason: str) -> None:
        self._log_state_event(
            AuditEventType.PERMISSION_DENIED,
            "plan_mode.tool.deny",
            "denied",
            reason,
            tool_name=tool.name,
        )
        raise PlanModeError(reason)

    def _transition(
        self,
        state: PlanModeState,
        event_type: AuditEventType,
        action: str,
        reason: str,
        *,
        plan: GovernancePlan | None = None,
        task: GovernanceTask | None = None,
        approver: str | None = None,
    ) -> None:
        self._state = state
        self._log_state_event(
            event_type,
            action,
            state.value,
            reason,
            plan=plan,
            task=task,
            approver=approver,
        )

    def _log_state_event(
        self,
        event_type: AuditEventType,
        action: str,
        outcome: str,
        reason: str,
        *,
        plan: GovernancePlan | None = None,
        task: GovernanceTask | None = None,
        approver: str | None = None,
        tool_name: str | None = None,
    ) -> AuditEvent:
        resolved_task = task or self._task
        target_id = (
            str(plan.plan_id)
            if plan is not None
            else str(resolved_task.task_id)
            if resolved_task is not None
            else "plan_mode"
        )
        target_type = "governance_plan" if plan is not None else "governance_task"
        metadata: dict[str, object] = {"plan_mode_state": self._state.value}
        if approver is not None:
            metadata["approver"] = approver
        if plan is not None:
            metadata["allowed_tools_after_approval"] = plan.allowed_tools_after_approval
        event = AuditEvent(
            event_type=event_type,
            actor=AuditActor(
                actor_id=self._user_context.user_id,
                actor_type="service" if self._user_context.is_service_account else "user",
                display_name=self._user_context.display_name,
                department=self._user_context.department.name
                if self._user_context.department
                else None,
            ),
            target=AuditTarget(
                target_id=target_id,
                target_type=target_type,
                qualified_name=plan.title
                if plan is not None
                else resolved_task.title
                if resolved_task is not None
                else None,
            ),
            user_id=self._user_context.user_id,
            role=self._user_context.roles[0].value if self._user_context.roles else None,
            session_id=self._session_id,
            task_id=str(resolved_task.task_id) if resolved_task is not None else None,
            agent_name=self._agent_name,
            tool_name=tool_name,
            asset_refs=plan.affected_assets if plan is not None else tuple(),
            action=action,
            outcome=outcome,
            reason=reason,
            request_summary=self._plan_summary(plan)
            if plan is not None
            else resolved_task.title
            if resolved_task is not None
            else "plan_mode",
            result_summary=f"state={self._state.value}",
            raw_payload_allowed=False,
            metadata=metadata,
        )
        return self._audit_logger.log_event(event)

    @staticmethod
    def _plan_summary(plan: GovernancePlan) -> str:
        return (
            f"plan={plan.title} risk_level={plan.risk_level.value} "
            f"affected_assets={len(plan.affected_assets)} "
            f"proposed_actions={len(plan.proposed_actions)}"
        )
