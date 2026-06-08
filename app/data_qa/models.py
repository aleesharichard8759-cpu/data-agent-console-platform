from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.domain.assets import DataDomain
from app.domain.common import DomainModel, new_id, utc_now
from app.domain.policy import PolicyDecision


class AudienceRole(StrEnum):
    MANAGER = "manager"
    DATA_TEAM = "data_team"
    OPERATIONS = "operations"


class DataQATaskType(StrEnum):
    QUERY_METRIC = "query_metric"
    EXPLAIN_METRIC = "explain_metric"
    KNOWLEDGE_QA = "knowledge_qa"
    MIXED = "mixed"
    ANOMALY_DIAGNOSIS = "anomaly_diagnosis"
    ATTRIBUTION_ANALYSIS = "attribution_analysis"
    BUSINESS_ADVICE = "business_advice"


class DataQATaskLevel(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class ClarificationStatus(StrEnum):
    COMPLETE = "complete"
    NEEDS_CLARIFICATION = "needs_clarification"
    ESCALATED = "escalated"
    DENIED = "denied"


class DataQAFeedbackRating(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class DataQATaskRequest(DomainModel):
    user_query: str = Field(description="Raw user question.")
    user_id: str = Field(default="demo_user", description="Stable requester id.")
    audience: AudienceRole = Field(
        default=AudienceRole.DATA_TEAM,
        description="Primary answer audience.",
    )
    source: str = Field(default="chat", description="Request source entrypoint.")
    business_domain: DataDomain = Field(
        default=DataDomain.UNKNOWN,
        description="Optional business domain hint.",
    )
    conversation_context: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Prior turns or business context snippets.",
    )

    @field_validator("user_query", "user_id", "source")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Data&QA request text fields must not be empty.")
        return value.strip()


class StructuredTask(DomainModel):
    task_id: UUID = Field(default_factory=new_id, description="Product task id.")
    task_type: DataQATaskType = Field(description="Data&QA task type.")
    task_level: DataQATaskLevel = Field(description="MVP task difficulty level.")
    raw_query: str = Field(description="Original user question.")
    metric: str | None = Field(default=None, description="Detected metric.")
    dimensions: tuple[str, ...] = Field(default_factory=tuple, description="Detected dimensions.")
    time_range_label: str | None = Field(default=None, description="Detected time range.")
    filters: tuple[str, ...] = Field(default_factory=tuple, description="Detected filters.")
    comparison: str | None = Field(default=None, description="Detected comparison intent.")
    clarification_status: ClarificationStatus = Field(description="Clarification state.")
    clarification_questions: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Required user clarifications before execution.",
    )
    requires_human_escalation: bool = Field(
        default=False,
        description="Whether this task should be routed to a human owner.",
    )
    escalation_reason: str | None = Field(default=None, description="Escalation reason.")


class SemanticIntent(DomainModel):
    task_id: UUID = Field(description="Product task id.")
    standard_metrics: tuple[str, ...] = Field(description="Mapped governed metrics.")
    standard_dimensions: tuple[str, ...] = Field(description="Mapped governed dimensions.")
    entities: tuple[str, ...] = Field(description="Mapped business entities.")
    knowledge_refs: tuple[str, ...] = Field(description="Mapped knowledge entries.")
    data_sources: tuple[str, ...] = Field(description="Allowed governed data sources.")
    permission_decision: PolicyDecision = Field(description="Product-level permission decision.")
    temporary_metric: bool = Field(
        default=False,
        description="Whether the answer uses a temporary non-standard metric definition.",
    )
    notes: tuple[str, ...] = Field(default_factory=tuple, description="Semantic mapping notes.")


class ExecutionPlan(DomainModel):
    plan_id: UUID = Field(default_factory=new_id, description="Product execution plan id.")
    task_id: UUID = Field(description="Product task id.")
    tool_sequence: tuple[str, ...] = Field(description="Planned governed tool calls.")
    sql: str | None = Field(default=None, description="Planned SQL reviewed by SQL Gateway.")
    knowledge_queries: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Knowledge lookup queries.",
    )
    risk_checkpoints: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Risk review checkpoints before answer delivery.",
    )


class AgentAnswer(DomainModel):
    task_id: UUID = Field(description="Product task id.")
    status: ClarificationStatus = Field(description="Final answer state.")
    summary: str = Field(description="User-facing answer summary.")
    evidence: tuple[dict[str, Any], ...] = Field(
        default_factory=tuple,
        description="Safe evidence returned by tools or knowledge references.",
    )
    metric_definition: str | None = Field(default=None, description="Metric definition used.")
    sources: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Data or knowledge sources.",
    )
    limitations: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Uncertainty, safety, or scope limitations.",
    )
    suggestions: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Safe next steps or action suggestions.",
    )
    follow_up_questions: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Questions needed before execution can continue.",
    )
    requires_human_escalation: bool = Field(
        default=False,
        description="Whether a human should take over.",
    )
    audit_refs: tuple[str, ...] = Field(default_factory=tuple, description="Audit references.")


class TraceRecord(DomainModel):
    trace_id: UUID = Field(default_factory=new_id, description="Product trace id.")
    task_id: UUID = Field(description="Product task id.")
    nodes: tuple[str, ...] = Field(description="Executed product workflow nodes.")
    tool_calls: tuple[str, ...] = Field(default_factory=tuple, description="Executed tools.")
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="Local deterministic quality scores.",
    )
    failure_node: str | None = Field(default=None, description="Failed or escalated node.")
    created_at: datetime = Field(default_factory=utc_now, description="Trace timestamp.")


class DataQARunResult(DomainModel):
    request: DataQATaskRequest = Field(description="Original request.")
    structured_task: StructuredTask = Field(description="Structured task definition.")
    semantic_intent: SemanticIntent = Field(description="Semantic mapping result.")
    execution_plan: ExecutionPlan = Field(description="Execution plan.")
    answer: AgentAnswer = Field(description="Final user-facing answer.")
    trace: TraceRecord = Field(description="Trace and quality signals.")


class DataQAFeedbackEvent(DomainModel):
    feedback_id: UUID = Field(default_factory=new_id, description="Feedback event id.")
    task_id: UUID = Field(description="Related product task id.")
    trace_id: UUID | None = Field(default=None, description="Related product trace id.")
    rating: DataQAFeedbackRating = Field(description="User feedback rating.")
    error_type: str | None = Field(
        default=None,
        description="Optional error category, such as value_error or metric_mismatch.",
    )
    comment: str | None = Field(default=None, description="User feedback comment.")
    enter_bad_case: bool = Field(
        default=False,
        description="Whether this should be routed into the Bad Case queue.",
    )
    created_at: datetime = Field(default_factory=utc_now, description="Feedback timestamp.")
