from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from app.connectors.base import ConnectorCallContext
from app.connectors.interfaces import WarehouseConnector
from app.domain.policy import PolicyDecision, PolicyEvaluationResult, PolicyReason
from app.domain.tools import ToolCallRequest, ToolCallResult, ToolExecutionStatus
from app.security import SQLAssetContext, SQLGateway
from app.tools.base import DataTool
from app.tools.context import ToolExecutionContext


class QuerySQLInput(BaseModel):
    sql: str = Field(description="SQL statement to review and execute.")
    asset_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional asset context for table and column safety review.",
    )


class QuerySQLOutput(BaseModel):
    columns: list[str] = Field(description="Result columns returned from the warehouse connector.")
    rows: list[dict[str, Any]] = Field(description="Result rows returned from the warehouse connector.")
    row_count: int = Field(description="Number of rows returned.")
    reviewed_sql: str = Field(description="SQL approved by SQL Gateway.")
    review_reason: str = Field(description="SQL Gateway review reason.")
    source: str = Field(default="warehouse", description="Result source system.")


class QuerySQLTool(DataTool):
    name = "query_sql"
    description = "Review SQL through SQL Gateway and execute it through a real warehouse connector."
    input_model = QuerySQLInput
    output_model = QuerySQLOutput
    max_rows = 100
    max_bytes = 256 * 1024

    gateway_review_count: int = 0
    warehouse_execution_count: int = 0
    _gateway: SQLGateway | None = PrivateAttr()
    _warehouse_connector: WarehouseConnector | None = PrivateAttr()

    def __init__(
        self,
        gateway: SQLGateway | None = None,
        warehouse_connector: WarehouseConnector | None = None,
    ) -> None:
        super().__init__()
        self._gateway = gateway or SQLGateway()
        if warehouse_connector is None:
            from app.connectors import build_warehouse_connector_from_env

            warehouse_connector = build_warehouse_connector_from_env()
        self._warehouse_connector = warehouse_connector

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

        if self._warehouse_connector is None:
            return self._failed_result(
                request,
                context,
                "SQL execution requires a configured real warehouse connector.",
            )

        reviewed_sql = review.rewritten_sql or validated_input.sql
        try:
            connector_result = self._warehouse_connector.query_preview(
                reviewed_sql,
                ConnectorCallContext(
                    user_context=context.user_context,
                    audit_logger=context.audit_logger,
                    session_id=context.session_id,
                    task_id=str(context.task_context.task_id) if context.task_context else None,
                    agent_name=context.agent_name,
                ),
            )
        except Exception as exc:
            return self._failed_result(
                request,
                context,
                f"Warehouse connector execution failed: {exc}",
            )

        if connector_result.get("allowed") is False:
            gateway_policy = self._gateway_policy_result(
                str(connector_result.get("reason", "Warehouse connector denied SQL execution.")),
                "warehouse_connector.deny",
            )
            return self._policy_result(
                request,
                context,
                gateway_policy,
                ToolExecutionStatus.DENIED,
            )

        self.warehouse_execution_count += 1
        output = QuerySQLOutput(
            columns=list(connector_result.get("columns", [])),
            rows=list(connector_result.get("rows", [])),
            row_count=int(connector_result.get("row_count", len(connector_result.get("rows", [])))),
            reviewed_sql=str(connector_result.get("reviewed_sql", reviewed_sql)),
            review_reason=review.reason,
            source=str(connector_result.get("source", "warehouse")),
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
