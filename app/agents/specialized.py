from __future__ import annotations

from app.agents.base import AgentResult, AgentTaskContext, BaseAgent
from app.domain.tools import ToolCallRequest, ToolRiskLevel


class MetadataAgent(BaseAgent):
    name = "metadata_agent"
    description = "Find metadata completeness issues and improvement suggestions."
    allowed_tools = ("search_metadata", "get_table_metadata")
    max_turns = 3

    def run(self, task_context: AgentTaskContext) -> AgentResult:
        table_name = self.table_hint(task_context.task)
        search_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="search_metadata",
                action="metadata.query",
                asset_type="metadata",
                parameters={"query": table_name.split("_")[1], "limit": 5},
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        metadata_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="get_table_metadata",
                action="table_metadata.query",
                asset_type="metadata",
                parameters={"table_name": table_name},
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        metadata_data = metadata_result.output.get("data", {})
        findings = {
            "missing_owner_tables": metadata_data.get("missing_owner_tables", []),
            "missing_comment_fields": metadata_data.get("missing_comment_fields", []),
            "duplicate_table_candidates": metadata_data.get("duplicate_table_candidates", []),
            "completion_suggestions": metadata_data.get("completion_suggestions", []),
        }
        return AgentResult(
            agent_name=self.name,
            task_id=str(task_context.task.task_id),
            status="completed",
            findings=findings,
            recommendations=tuple(findings["completion_suggestions"]),
            tool_results=(search_result, metadata_result),
        )


class DataQualityAgent(BaseAgent):
    name = "data_quality_agent"
    description = "Generate data quality rule suggestions and mock check evidence."
    allowed_tools = ("generate_quality_rules", "run_quality_check")
    max_turns = 3

    def run(self, task_context: AgentTaskContext) -> AgentResult:
        table_name = self.table_hint(task_context.task)
        rule_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="generate_quality_rules",
                action="quality_rule.suggest",
                asset_type="quality_rule",
                parameters={
                    "table_name": table_name,
                    "fields": ["order_id", "partition_date", "settlement_amount"],
                },
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        check_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="run_quality_check",
                action="quality_check.run",
                asset_type="quality_rule",
                parameters={"table_name": table_name},
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        rule_data = rule_result.output.get("data", {})
        check_data = check_result.output.get("data", {})
        findings = {
            "completeness_rules": check_data.get("completeness_rules", []),
            "uniqueness_rules": check_data.get("uniqueness_rules", []),
            "validity_rules": check_data.get("validity_rules", []),
            "consistency_rules": check_data.get("consistency_rules", []),
            "strong_rules": check_data.get("strong_rules", []),
            "weak_rules": check_data.get("weak_rules", []),
            "suggested_rules": rule_data.get("suggested_rules", []),
        }
        return AgentResult(
            agent_name=self.name,
            task_id=str(task_context.task.task_id),
            status="completed",
            findings=findings,
            recommendations=(
                "Review strong rules as blocking controls before implementation.",
                "Keep weak rules as warning or observation controls.",
            ),
            tool_results=(rule_result, check_result),
        )


class SecurityAgent(BaseAgent):
    name = "security_agent"
    description = "Classify sensitive fields and inspect permission risks."
    allowed_tools = ("classify_sensitivity", "check_permission")
    max_turns = 3

    def run(self, task_context: AgentTaskContext) -> AgentResult:
        table_name = self.table_hint(task_context.task)
        sensitivity_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="classify_sensitivity",
                action="sensitivity.classify",
                asset_type="security",
                parameters={
                    "fields": [
                        "order_id",
                        "contact_phone_hash",
                        "recipient_address_text",
                        "api_secret_marker",
                    ]
                },
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        permission_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="check_permission",
                action="permission.check",
                asset_type="security",
                parameters={"asset_name": table_name},
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        sensitivity_data = sensitivity_result.output.get("data", {})
        permission_data = permission_result.output.get("data", {})
        fields = sensitivity_data.get("sensitive_fields", [])
        has_l4_l5 = any(
            isinstance(field, dict) and field.get("level") in {"L4", "L5"} for field in fields
        )
        allow_context = (
            bool(sensitivity_data.get("allow_in_model_context", False)) and not has_l4_l5
        )
        findings = {
            "sensitive_fields": fields,
            "levels": sorted(
                {
                    str(field.get("level"))
                    for field in fields
                    if isinstance(field, dict) and field.get("level")
                }
            ),
            "masking_suggestions": sensitivity_data.get("masking_suggestions", []),
            "permission_findings": permission_data.get("findings", []),
            "allow_in_model_context": allow_context,
        }
        return AgentResult(
            agent_name=self.name,
            task_id=str(task_context.task.task_id),
            status="vetoed" if has_l4_l5 else "completed",
            findings=findings,
            recommendations=tuple(findings["masking_suggestions"]),
            tool_results=(sensitivity_result, permission_result),
            veto=has_l4_l5,
            veto_reason="L4/L5 fields were detected; model context access is denied."
            if has_l4_l5
            else None,
        )


class MetricAgent(BaseAgent):
    name = "metric_agent"
    description = "Create metric governance cards and pending questions."
    allowed_tools = ("get_metric_definition", "generate_metric_card")
    max_turns = 3

    def run(self, task_context: AgentTaskContext) -> AgentResult:
        metric_name = "order_count"
        definition_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="get_metric_definition",
                action="metric.definition.query",
                asset_type="metric_definition",
                parameters={"metric_name": metric_name},
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        card_result = self.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="generate_metric_card",
                action="metric.card.generate",
                asset_type="metric_definition",
                parameters={"metric_name": metric_name},
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        definition_data = definition_result.output.get("data", {})
        card_data = card_result.output.get("data", {})
        findings = {
            "business_definition": card_data.get("business_definition"),
            "technical_definition": card_data.get("technical_definition"),
            "metric_definition": definition_data.get("definition"),
            "dimensions": card_data.get("dimensions", []),
            "time_field": card_data.get("time_field"),
            "open_questions": card_data.get("open_questions", []),
        }
        return AgentResult(
            agent_name=self.name,
            task_id=str(task_context.task.task_id),
            status="completed",
            findings=findings,
            recommendations=tuple(card_data.get("open_questions", [])),
            tool_results=(definition_result, card_result),
        )
