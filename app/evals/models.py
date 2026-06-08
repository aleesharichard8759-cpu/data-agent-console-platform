from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from app.domain.common import DomainModel
from app.domain.policy import PolicyDecision
from app.domain.tasks import GovernanceTaskLevel, GovernanceTaskType


class EvalDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class EvalCase(DomainModel):
    case_id: str = Field(description="Stable evaluation case id.")
    name: str = Field(description="Evaluation case name.")
    task_type: GovernanceTaskType = Field(description="Expected task type.")
    task_level: GovernanceTaskLevel = Field(description="Expected task level.")
    user_query: str = Field(description="User query for the runtime.")
    expected_agents: tuple[str, ...] = Field(description="Expected selected agent names.")
    expected_tools: tuple[str, ...] = Field(description="Expected tool names.")
    expected_policy_decision: PolicyDecision = Field(description="Expected policy decision.")
    expected_key_points: tuple[str, ...] = Field(description="Expected structured key points.")
    must_not_include: tuple[str, ...] = Field(description="Strings that must not appear in output.")
    grading_rubric: str = Field(description="Human-readable grading rubric.")
    difficulty: EvalDifficulty = Field(description="Case difficulty.")
    tags: tuple[str, ...] = Field(description="Case tags.")
    expected_sql: str | None = Field(
        default=None,
        description="Optional reviewed SQL expected for Data&QA or SQL-focused cases.",
    )
    expected_result_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional expected result columns, row count, or output structure.",
    )
    expected_answer_key_points: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Answer-level key points required by product evaluations.",
    )
    reference_solution: str | None = Field(
        default=None,
        description="Known-good safe answer used to validate graders.",
    )
    last_verified_at: str | None = Field(
        default=None,
        description="Manual verification date or timestamp for the expected answer.",
    )


class EvalObservation(DomainModel):
    case_id: str = Field(description="Evaluation case id.")
    classified_task_type: GovernanceTaskType = Field(description="Observed task type.")
    classified_task_level: GovernanceTaskLevel = Field(description="Observed task level.")
    selected_agents: tuple[str, ...] = Field(description="Observed selected agents.")
    used_tools: tuple[str, ...] = Field(description="Observed tool names.")
    policy_decision: PolicyDecision = Field(description="Observed policy decision.")
    task_status: str = Field(description="Observed task run status.")
    output_text: str = Field(description="Safe serialized output for text safety checks.")
    structured: dict[str, Any] = Field(description="Additional structured observation.")


class GraderResult(DomainModel):
    grader_name: str = Field(description="Grader name.")
    passed: bool = Field(description="Whether this grader passed.")
    score: float = Field(ge=0.0, le=1.0, description="Grader score.")
    reason: str = Field(description="Grader explanation.")


class EvalCaseResult(DomainModel):
    case_id: str = Field(description="Evaluation case id.")
    name: str = Field(description="Case name.")
    passed: bool = Field(description="Whether all graders passed.")
    score: float = Field(ge=0.0, le=1.0, description="Average score.")
    grader_results: tuple[GraderResult, ...] = Field(description="Per-grader results.")
    observation: EvalObservation = Field(description="Observed runtime output.")


class EvalReport(DomainModel):
    total_cases: int = Field(description="Total number of cases.")
    passed_cases: int = Field(description="Number of passed cases.")
    failed_cases: int = Field(description="Number of failed cases.")
    pass_rate: float = Field(ge=0.0, le=1.0, description="Suite pass rate.")
    case_results: tuple[EvalCaseResult, ...] = Field(description="Case results.")
