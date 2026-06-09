from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.audit import InMemoryAuditLogger
from app.core.config import get_settings
from app.core.errors import RuntimeErrorBase
from app.data_qa import (
    DataQAFeedbackEvent,
    DataQAFeedbackRating,
    DataQAOrchestrator,
    DataQARunResult,
    DataQATaskRequest,
)
from app.domain.audit import AuditEventFilter
from app.domain.common import new_id
from app.domain.identity import UserContext, UserRole
from app.domain.policy import PolicyDecision
from app.domain.tasks import GovernanceTask
from app.domain.tools import ToolCallRequest, ToolRiskLevel
from app.runtime import GovernanceEngine, TaskRunResult
from app.security import SQLGateway
from app.tools import ToolExecutionContext


class CreateTaskRequest(BaseModel):
    user_prompt: str = Field(description="Governance task prompt.")


class TraceableResponse(BaseModel):
    trace_id: str = Field(description="Per-response trace id.")
    audit_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Audit event ids related to this response.",
    )


class HealthResponse(TraceableResponse):
    status: str = Field(description="Service status.")


class CreateSessionRequest(BaseModel):
    user_id: str = Field(default="runtime_user", description="Runtime user id.")
    display_name: str = Field(default="Data Steward", description="Runtime display name.")
    roles: tuple[UserRole, ...] = Field(
        default=(UserRole.DATA_STEWARD,),
        description="Runtime user roles.",
    )


class CreateSessionResponse(TraceableResponse):
    session_id: str = Field(description="Created runtime session id.")
    user_id: str = Field(description="Session user id.")


class CreateTaskResponse(BaseModel):
    trace_id: str = Field(description="Per-response trace id.")
    audit_refs: tuple[str, ...] = Field(description="Audit event ids related to task creation.")
    task_id: str = Field(description="Created task id.")
    status: str = Field(description="Task status.")
    task_type: str = Field(description="Classified task type.")
    task_level: str = Field(description="Classified task level.")


class SQLReviewRequest(BaseModel):
    sql: str = Field(description="SQL to review. It is never executed by this endpoint.")
    asset_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional governed SQL asset context.",
    )


class SQLReviewResponse(TraceableResponse):
    allowed: bool = Field(description="Whether SQL is allowed by SQL Gateway.")
    decision: PolicyDecision = Field(description="SQL Gateway decision.")
    risks: tuple[dict[str, Any], ...] = Field(description="Detected SQL risks.")
    rewritten_sql: str | None = Field(description="Safe rewritten SQL when applicable.")
    reason: str = Field(description="Decision reason.")
    required_approval: bool = Field(description="Whether approval is required.")


class ToolDryRunRequest(BaseModel):
    action: str | None = Field(default=None, description="Requested tool action.")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured tool input.",
    )
    asset_type: str | None = Field(default=None, description="Target asset type.")
    risk_level: ToolRiskLevel = Field(
        default=ToolRiskLevel.LOW,
        description="Tool call risk level.",
    )
    task_id: str | None = Field(default=None, description="Optional governance task id.")
    requires_approval: bool = Field(
        default=False,
        description="Whether the dry-run request needs approval.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether request payload may enter model context.",
    )


class ToolDryRunResponse(TraceableResponse):
    tool_name: str = Field(description="Executed tool name.")
    status: str = Field(description="Tool execution status.")
    result: dict[str, Any] = Field(description="Masked tool result.")


class PlanApprovalRequest(BaseModel):
    approver: str = Field(
        default="security_reviewer",
        description="Approver id.",
    )


class PlanRejectRequest(PlanApprovalRequest):
    reason: str = Field(default="Rejected in approval flow.", description="Reject reason.")


class PlanDecisionResponse(TraceableResponse):
    plan_id: str = Field(description="Governance plan id.")
    state: str = Field(description="Plan mode state.")
    plan: dict[str, Any] = Field(description="Safe governance plan summary.")


class DataQAFeedbackRequest(BaseModel):
    task_id: str = Field(description="Related Data&QA task id.")
    trace_id: str | None = Field(default=None, description="Related Data&QA trace id.")
    rating: DataQAFeedbackRating = Field(description="User feedback rating.")
    error_type: str | None = Field(
        default=None,
        description="Optional user-selected error type.",
    )
    comment: str | None = Field(default=None, description="Optional user feedback comment.")


class DataQAFeedbackResponse(TraceableResponse):
    feedback: dict[str, Any] = Field(description="Stored feedback event.")


DEFAULT_TOOL_REQUESTS: dict[str, tuple[str, str]] = {
    "search_metadata": ("metadata.query", "metadata"),
    "get_metric_definition": ("metric.definition.query", "metric_definition"),
    "generate_quality_rules": ("quality_rule.suggest", "quality_rule"),
    "query_sql": ("sql.query", "sql_query"),
}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    audit_logger = InMemoryAuditLogger()
    engine = GovernanceEngine(audit_logger=audit_logger)
    engine.start_session(
        UserContext(
                user_id="demo_user",
                display_name="Data Steward",
            roles=(UserRole.DATA_STEWARD,),
        )
    )
    task_results: dict[str, TaskRunResult] = {}
    data_qa_results: dict[str, DataQARunResult] = {}
    data_qa_feedback: list[DataQAFeedbackEvent] = []
    app.state.audit_logger = audit_logger
    app.state.governance_engine = engine
    app.state.task_results = task_results
    app.state.data_qa_orchestrator = DataQAOrchestrator(
        policy_engine=engine.policy_engine,
        tool_registry=engine.tool_registry,
        audit_logger=audit_logger,
    )
    app.state.data_qa_results = data_qa_results
    app.state.data_qa_feedback = data_qa_feedback
    app.state.sql_gateway = SQLGateway()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return HealthResponse(status="ok", trace_id=_trace_id()).model_dump(mode="json")

    @app.post("/sessions")
    def create_session(request: CreateSessionRequest | None = None) -> CreateSessionResponse:
        payload = request or CreateSessionRequest()
        start_index = _audit_index(app)
        session_id = app.state.governance_engine.start_session(
            UserContext(
                user_id=payload.user_id,
                display_name=payload.display_name,
                roles=payload.roles,
            )
        )
        return CreateSessionResponse(
            trace_id=_trace_id(),
            audit_refs=_audit_refs_since(app, start_index),
            session_id=session_id,
            user_id=payload.user_id,
        )

    @app.post("/tasks")
    def create_task(request: CreateTaskRequest) -> CreateTaskResponse:
        start_index = _audit_index(app)
        task = app.state.governance_engine.create_task(request.user_prompt)
        return CreateTaskResponse(
            trace_id=_trace_id(),
            audit_refs=_audit_refs_since(app, start_index),
            task_id=str(task.task_id),
            status=task.status.value,
            task_type=task.task_type.value,
            task_level=task.task_level.value,
        )

    @app.post("/tasks/{task_id}/run")
    def run_task(task_id: str) -> dict[str, Any]:
        task = app.state.governance_engine.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        result = app.state.governance_engine.run_task(task_id)
        app.state.task_results[task_id] = result
        payload = result.model_dump(mode="json")
        payload["trace_id"] = _trace_id()
        payload["audit_refs"] = result.audit_refs
        return payload

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        task = app.state.governance_engine.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        result = app.state.task_results.get(task_id)
        return {
            "trace_id": _trace_id(),
            "audit_refs": result.audit_refs if result is not None else tuple(),
            "task": task.model_dump(mode="json"),
            "result": result.model_dump(mode="json") if result is not None else None,
        }

    @app.get("/tasks/{task_id}/audit")
    def get_task_audit(task_id: str) -> dict[str, Any]:
        task = app.state.governance_engine.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        events = app.state.audit_logger.list_events(AuditEventFilter(task_id=task_id))
        audit_refs = tuple(str(event.event_id) for event in events)
        return {
            "trace_id": _trace_id(),
            "audit_refs": audit_refs,
            "events": [event.model_dump(mode="json") for event in events],
        }

    @app.get("/audit")
    def list_audit(task_id: str | None = None) -> dict[str, Any]:
        event_filter = AuditEventFilter(task_id=task_id) if task_id else None
        events = app.state.audit_logger.list_events(event_filter)
        audit_refs = tuple(str(event.event_id) for event in events)
        return {
            "trace_id": _trace_id(),
            "audit_refs": audit_refs,
            "events": [event.model_dump(mode="json") for event in events],
        }

    @app.post("/sql/review")
    def review_sql(request: SQLReviewRequest) -> SQLReviewResponse:
        start_index = _audit_index(app)
        review = app.state.sql_gateway.review_sql(
            request.sql,
            _current_user(app),
            request.asset_context,
            audit_logger=app.state.audit_logger,
            session_id=app.state.governance_engine.session_id,
            agent_name="rest_api",
            tool_name="sql_review",
        )
        return SQLReviewResponse(
            trace_id=_trace_id(),
            audit_refs=_audit_refs_since(app, start_index),
            allowed=review.allowed,
            decision=review.decision,
            risks=tuple(risk.model_dump(mode="json") for risk in review.risks),
            rewritten_sql=review.rewritten_sql,
            reason=review.reason,
            required_approval=review.required_approval,
        )

    @app.post("/tools/{tool_name}/dry-run")
    def dry_run_tool(tool_name: str, request: ToolDryRunRequest) -> ToolDryRunResponse:
        start_index = _audit_index(app)
        task = _task_or_none(app, request.task_id)
        action, asset_type = _resolve_tool_request(tool_name, request)
        tool_request = ToolCallRequest(
            tool_name=tool_name,
            action=action,
            parameters=request.parameters,
            asset_type=asset_type,
            risk_level=request.risk_level,
            requires_approval=request.requires_approval,
            requires_sql_gateway=action.startswith("sql."),
            allow_in_model_context=request.allow_in_model_context,
            task_level=task.task_level if task is not None else None,
        )
        try:
            result = app.state.governance_engine.tool_registry.execute_tool(
                tool_request,
                ToolExecutionContext(
                    user_context=_current_user(app),
                    task_context=task,
                    policy_engine=app.state.governance_engine.policy_engine,
                    audit_logger=app.state.audit_logger,
                    dry_run=True,
                    plan_mode=False,
                    session_id=app.state.governance_engine.session_id,
                    agent_name="rest_api",
                ),
            )
        except RuntimeErrorBase as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ToolDryRunResponse(
            trace_id=_trace_id(),
            audit_refs=_audit_refs_since(app, start_index),
            tool_name=tool_name,
            status=result.status.value,
            result=result.model_dump(mode="json"),
        )

    @app.post("/plans/{plan_id}/approve")
    def approve_plan(
        plan_id: str,
        request: PlanApprovalRequest | None = None,
    ) -> PlanDecisionResponse:
        payload = request or PlanApprovalRequest()
        start_index = _audit_index(app)
        try:
            plan, state = app.state.governance_engine.approve_plan(plan_id, payload.approver)
        except RuntimeErrorBase as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PlanDecisionResponse(
            trace_id=_trace_id(),
            audit_refs=_audit_refs_since(app, start_index),
            plan_id=str(plan.plan_id),
            state=state.value,
            plan=plan.model_dump(mode="json"),
        )

    @app.post("/plans/{plan_id}/reject")
    def reject_plan(plan_id: str, request: PlanRejectRequest | None = None) -> PlanDecisionResponse:
        payload = request or PlanRejectRequest()
        start_index = _audit_index(app)
        try:
            plan, state = app.state.governance_engine.reject_plan(
                plan_id,
                payload.approver,
                payload.reason,
            )
        except RuntimeErrorBase as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PlanDecisionResponse(
            trace_id=_trace_id(),
            audit_refs=_audit_refs_since(app, start_index),
            plan_id=str(plan.plan_id),
            state=state.value,
            plan=plan.model_dump(mode="json"),
        )

    @app.get("/data-qa/mvp-targets")
    def data_qa_mvp_targets() -> dict[str, Any]:
        return {
            "trace_id": _trace_id(),
            "audit_refs": tuple(),
            "scope": {
                "stable": ("L1 query_metric", "L1 explain_metric", "L1 knowledge_qa"),
                "escalated": (
                    "L2 anomaly_diagnosis",
                    "L3 attribution_analysis",
                    "L4 business_advice",
                ),
            },
            "targets": {
                "l1_sql_execution_success_rate": 0.80,
                "l1_task_completion_rate": 0.70,
                "l1_intent_identification_accuracy": 0.85,
                "l1_semantic_consistency": 0.85,
                "avg_clarification_rounds": 2.5,
            },
            "safety_defaults": (
                "default_deny",
                "least_privilege",
                "approval_when_needed",
                "full_audit",
                "no_direct_production_database_access",
            ),
        }

    @app.post("/data-qa/run")
    def run_data_qa(request: DataQATaskRequest) -> dict[str, Any]:
        result = app.state.data_qa_orchestrator.run(
            request,
            user_context=_current_user(app),
            session_id=app.state.governance_engine.session_id,
        )
        app.state.data_qa_results[str(result.structured_task.task_id)] = result
        return result.model_dump(mode="json")

    @app.get("/data-qa/tasks/{task_id}")
    def get_data_qa_task(task_id: str) -> dict[str, Any]:
        result = app.state.data_qa_results.get(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Data&QA task not found.")
        return {
            "trace_id": _trace_id(),
            "audit_refs": result.answer.audit_refs,
            "result": result.model_dump(mode="json"),
        }

    @app.post("/data-qa/feedback")
    def submit_data_qa_feedback(request: DataQAFeedbackRequest) -> DataQAFeedbackResponse:
        result = app.state.data_qa_results.get(request.task_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Data&QA task not found.")
        trace_id = request.trace_id or str(result.trace.trace_id)
        feedback = DataQAFeedbackEvent(
            task_id=request.task_id,
            trace_id=trace_id,
            rating=request.rating,
            error_type=request.error_type,
            comment=request.comment,
            enter_bad_case=request.rating == DataQAFeedbackRating.NEGATIVE,
        )
        app.state.data_qa_feedback.append(feedback)
        return DataQAFeedbackResponse(
            trace_id=_trace_id(),
            audit_refs=tuple(),
            feedback=feedback.model_dump(mode="json"),
        )

    @app.get("/data-qa/bad-cases")
    def list_data_qa_bad_cases() -> dict[str, Any]:
        bad_cases = [
            feedback.model_dump(mode="json")
            for feedback in app.state.data_qa_feedback
            if feedback.enter_bad_case
        ]
        return {
            "trace_id": _trace_id(),
            "audit_refs": tuple(),
            "bad_cases": bad_cases,
            "count": len(bad_cases),
        }

    return app


def _trace_id() -> str:
    return str(new_id())


def _audit_index(app: FastAPI) -> int:
    return len(app.state.audit_logger.list_events())


def _audit_refs_since(app: FastAPI, start_index: int) -> tuple[str, ...]:
    events = app.state.audit_logger.list_events()
    return tuple(str(event.event_id) for event in events[start_index:])


def _current_user(app: FastAPI) -> UserContext:
    user = app.state.governance_engine.user_context
    if user is None:
        raise HTTPException(status_code=500, detail="Runtime session has not started.")
    return user


def _task_or_none(app: FastAPI, task_id: str | None) -> GovernanceTask | None:
    if task_id is None:
        return None
    task = app.state.governance_engine.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


def _resolve_tool_request(tool_name: str, request: ToolDryRunRequest) -> tuple[str, str | None]:
    default_action, default_asset_type = DEFAULT_TOOL_REQUESTS.get(
        tool_name,
        ("metadata.query", None),
    )
    return request.action or default_action, request.asset_type or default_asset_type


app = create_app()
