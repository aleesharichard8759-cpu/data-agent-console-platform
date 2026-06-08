from __future__ import annotations

from typing import Any

from data_governance_agent_runtime.core.enums import ActionRisk
from data_governance_agent_runtime.core.models import RuntimeContext, SqlRequest, ToolRequest
from data_governance_agent_runtime.sql.gateway import SqlGateway
from data_governance_agent_runtime.tools.base import DataTool


class AssetInventoryTool(DataTool):
    name = "asset_inventory"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context, request
        return {
            "assets": [
                {
                    "name": "ads_governed_order_metric_1d",
                    "layer": "ADS",
                    "domain": "trade",
                    "owner": "data_steward",
                    "sensitive_level": "L2",
                },
                {
                    "name": "dwd_customer_contact_snapshot_di",
                    "layer": "DWD",
                    "domain": "customer",
                    "owner": "data_steward",
                    "email_hash": "hash_placeholder",
                    "sensitive_level": "L3",
                },
            ]
        }


class MetadataCompletionTool(DataTool):
    name = "metadata_completion"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context
        asset_name = str(request.parameters.get("asset_name", "unknown_asset"))
        return {
            "asset_name": asset_name,
            "suggestions": [
                {"field": "owner", "value": "data_steward", "confidence": 0.74},
                {"field": "business_domain", "value": request.parameters.get("domain", "待确认")},
            ],
        }


class QualityRuleSuggestionTool(DataTool):
    name = "quality_rule_suggestion"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context
        table_name = str(request.parameters.get("table_name", "unknown_table"))
        return {
            "table_name": table_name,
            "rules": [
                {
                    "rule_type": "not_null",
                    "field": "business_key",
                    "severity": "blocker",
                    "description": "Core business key must not be null.",
                },
                {
                    "rule_type": "freshness",
                    "field": "dt",
                    "severity": "warning",
                    "description": "Partition should arrive within the agreed SLA.",
                },
            ],
        }


class MetricGovernanceTool(DataTool):
    name = "metric_governance"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context
        metric_name = str(request.parameters.get("metric_name", "unknown_metric"))
        return {
            "metric_name": metric_name,
            "checks": [
                {"item": "business_definition", "status": "待确认"},
                {"item": "aggregation_logic", "status": "待确认"},
                {"item": "owner", "status": "missing"},
            ],
        }


class SensitiveFieldDetectionTool(DataTool):
    name = "sensitive_field_detection"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context
        fields = request.parameters.get("fields", [])
        detected: list[dict[str, str]] = []
        if isinstance(fields, list):
            for field in fields:
                field_name = str(field)
                lowered = field_name.lower()
                sensitive_tokens = ("phone", "email", "address", "secret", "token")
                if any(token in lowered for token in sensitive_tokens):
                    detected.append(
                        {"field": field_name, "sensitive_level": "L3", "action": "mask"}
                    )
        return {"detected_fields": detected}


class LineageImpactTool(DataTool):
    name = "lineage_impact"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context
        asset_name = str(request.parameters.get("asset_name", "unknown_asset"))
        return {
            "asset_name": asset_name,
            "downstream_assets": [
                "dws_trade_order_summary_1d",
                "ads_governed_order_metric_1d",
            ],
            "risk": "medium",
        }


class PermissionInspectionTool(DataTool):
    name = "permission_inspection"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context, request
        return {
            "findings": [
                {
                    "principal": "analytics_role",
                    "asset": "dwd_customer_contact_snapshot_di",
                    "issue": "sensitive_asset_requires_review",
                    "recommended_action": "expire_or_reapprove",
                }
            ]
        }


class GovernanceReportTool(DataTool):
    name = "governance_report"

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        del context
        return {
            "summary": {
                "assets_scanned": request.parameters.get("assets_scanned", 0),
                "rules_suggested": request.parameters.get("rules_suggested", 0),
                "open_risks": request.parameters.get("open_risks", 0),
            },
            "next_actions": [
                "Confirm data owners for assets marked 待确认.",
                "Route high-risk actions to governance approval.",
            ],
        }


class SqlQueryTool(DataTool):
    name = "sql_query"

    def __init__(self, *args: Any, gateway: SqlGateway | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._gateway = gateway or SqlGateway()

    def _execute(self, context: RuntimeContext, request: ToolRequest) -> dict[str, object]:
        statement = str(request.parameters.get("statement", ""))
        result = self._gateway.execute(
            SqlRequest(statement=statement, purpose=context.purpose, max_rows=100)
        )
        return result.model_dump(mode="json")


def default_tool_requests(task_domain: str) -> list[ToolRequest]:
    return [
        ToolRequest(
            tool_name="asset_inventory",
            action="asset.inventory",
            risk=ActionRisk.LOW,
            parameters={"domain": task_domain},
        ),
        ToolRequest(
            tool_name="sensitive_field_detection",
            action="sensitive.detect",
            risk=ActionRisk.MEDIUM,
            parameters={"fields": ["business_key", "email_hash", "gross_margin"]},
        ),
        ToolRequest(
            tool_name="quality_rule_suggestion",
            action="quality.suggest_rules",
            risk=ActionRisk.MEDIUM,
            parameters={"table_name": "ads_governed_order_metric_1d"},
        ),
        ToolRequest(
            tool_name="governance_report",
            action="report.generate",
            risk=ActionRisk.LOW,
            parameters={"assets_scanned": 2, "rules_suggested": 2, "open_risks": 1},
        ),
    ]
