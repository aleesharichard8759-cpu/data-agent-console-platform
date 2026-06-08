from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from app.domain.policy import PolicyDecision, PolicyEvaluationResult, PolicyReason
from app.domain.tools import ToolCallRequest, ToolCallResult, ToolExecutionStatus
from app.security import SQLAssetContext, SQLGateway
from app.tools.base import DataTool
from app.tools.context import ToolExecutionContext


class QuerySQLInput(BaseModel):
    sql: str = Field(description="SQL statement to review and mock-execute.")
    asset_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional mock asset context for table and column safety review.",
    )


class QuerySQLOutput(BaseModel):
    columns: list[str] = Field(description="Mock result columns.")
    rows: list[dict[str, Any]] = Field(description="Mock result rows.")
    reviewed_sql: str = Field(description="SQL approved by SQL Gateway.")
    review_reason: str = Field(description="SQL Gateway review reason.")


class QuerySQLTool(DataTool):
    name = "query_sql"
    description = "Review SQL through SQL Gateway and return mock results."
    input_model = QuerySQLInput
    output_model = QuerySQLOutput
    max_rows = 100
    max_bytes = 256 * 1024

    gateway_review_count: int = 0
    mock_execution_count: int = 0
    _gateway: SQLGateway | None = PrivateAttr()

    def __init__(self, gateway: SQLGateway | None = None) -> None:
        super().__init__()
        self._gateway = gateway or SQLGateway()

    def allow_in_model_context(self) -> bool:
        return False

    def execute(self, request: ToolCallRequest, context: ToolExecutionContext) -> ToolCallResult:
        try:
            validated_input = QuerySQLInput.model_validate(request.parameters)
        except ValidationError as exc:
            return self._failed_result(request, context, f"Invalid tool input: {exc.errors()}")

        policy_result = self.check_permission(request, context)
        if policy_result.decision == PolicyDecision.DENY:
            return self._policy_result(request, context, policy_result, ToolExecutionStatus.DENIED)
        if policy_result.decision == PolicyDecision.ASK:
            return self._policy_result(request, context, policy_result, ToolExecutionStatus.ASKED)

        if self._gateway is None:
            gateway_required = PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                reasons=(
                    PolicyReason(
                        code="sql_gateway_required",
                        message="SQL execution requires SQL Gateway.",
                        rule_id="sql_gateway.required",
                    ),
                ),
                requires_approval=False,
            )
            return self._policy_result(
                request,
                context,
                gateway_required,
                ToolExecutionStatus.DENIED,
            )

        asset_context = None
        if validated_input.asset_context is not None:
            asset_context = SQLAssetContext.model_validate(validated_input.asset_context)
        self.gateway_review_count += 1
        review = self._gateway.review_sql(
            validated_input.sql,
            context.user_context,
            asset_context,
            audit_logger=context.audit_logger,
            request=request,
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
            tool_name=self.name,
        )
        if review.decision == PolicyDecision.DENY:
            gateway_policy = self._gateway_policy_result(review.reason, "sql_gateway.deny")
            return self._policy_result(
                request,
                context,
                gateway_policy,
                ToolExecutionStatus.DENIED,
            )
        if review.decision == PolicyDecision.ASK:
            gateway_policy = self._gateway_policy_result(review.reason, "sql_gateway.ask")
            return self._policy_result(
                request,
                context,
                gateway_policy,
                ToolExecutionStatus.ASKED,
            )

        self.mock_execution_count += 1
        reviewed_sql = review.rewritten_sql or validated_input.sql
        output = QuerySQLOutput(
            columns=["metric_date", "order_count"],
            rows=[{"metric_date": "mock_date", "order_count": 42}],
            reviewed_sql=reviewed_sql,
            review_reason=review.reason,
        )
        audit_event = context.audit_logger.record_tool_event(
            request,
            context.user_context,
            ToolExecutionStatus.SUCCEEDED,
            policy_result,
            metadata={
                "tool_name": self.name,
                "sql_gateway_decision": review.decision.value,
                "risk_count": len(review.risks),
            },
            task=context.task_context,
            session_id=context.session_id,
            agent_name=context.agent_name,
        )
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            status=ToolExecutionStatus.SUCCEEDED,
            output={
                "data": output.model_dump(mode="json"),
                "audit_event_id": str(audit_event.event_id),
                "policy_decision": policy_result.decision.value,
                "sql_gateway_decision": review.decision.value,
                "sql_gateway_reason": review.reason,
            },
            allow_in_model_context=self.allow_in_model_context(),
        )

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del validated_input, context
        raise NotImplementedError("QuerySQLTool uses its own SQL Gateway execution flow.")

    @staticmethod
    def _gateway_policy_result(reason: str, rule_id: str) -> PolicyEvaluationResult:
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY if rule_id.endswith("deny") else PolicyDecision.ASK,
            reasons=(PolicyReason(code=rule_id.split(".")[-1], message=reason, rule_id=rule_id),),
            requires_approval=rule_id.endswith("ask"),
        )
