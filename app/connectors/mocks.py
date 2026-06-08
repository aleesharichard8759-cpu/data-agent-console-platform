from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorCallContext, ConnectorConfig, ConnectorKind
from app.connectors.interfaces import (
    LineageConnector,
    MaskingConnector,
    MetadataConnector,
    MetricConnector,
    PermissionConnector,
    QualityConnector,
    SchedulerConnector,
    WarehouseConnector,
    WorkflowConnector,
)
from app.connectors.mock_catalog import (
    get_lineage,
    get_table_metadata,
    search_metadata,
)
from app.connectors.mock_warehouse import get_column_profile, run_quality_check
from app.security.sql_gateway import SQLGateway


def _mock_config(name: str, kind: ConnectorKind, timeout_seconds: float = 5.0) -> ConnectorConfig:
    return ConnectorConfig(
        name=name,
        connector_kind=kind,
        timeout_seconds=timeout_seconds,
        enabled=True,
        is_mock=True,
    )


class MockMetadataConnector(MetadataConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_metadata", ConnectorKind.METADATA, timeout_seconds))

    def search_assets(self, query: str, context: ConnectorCallContext) -> dict[str, Any]:
        return self._run_operation(
            context,
            "search_assets",
            {"query": query},
            lambda: {"results": search_metadata(query, limit=10)},
        )

    def get_table_metadata(self, table_name: str, context: ConnectorCallContext) -> dict[str, Any]:
        return self._run_operation(
            context,
            "get_table_metadata",
            {"table_name": table_name},
            lambda: get_table_metadata(table_name),
        )


class MockWarehouseConnector(WarehouseConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_warehouse", ConnectorKind.WAREHOUSE, timeout_seconds))
        self._sql_gateway = SQLGateway()

    def query_preview(self, sql: str, context: ConnectorCallContext) -> dict[str, Any]:
        def handler() -> dict[str, Any]:
            review = self._sql_gateway.review_sql(
                sql,
                context.user_context,
                audit_logger=context.audit_logger,
                session_id=context.session_id,
                agent_name=context.agent_name,
                tool_name=self.name,
            )
            if not review.allowed:
                return {
                    "allowed": False,
                    "decision": review.decision.value,
                    "reason": review.reason,
                    "risks": [risk.model_dump(mode="json") for risk in review.risks],
                    "rows": [],
                }
            return {
                "allowed": True,
                "decision": review.decision.value,
                "reviewed_sql": review.rewritten_sql or sql.strip(),
                "columns": ["metric_date", "order_count"],
                "rows": [{"metric_date": "mock_date", "order_count": 42}],
            }

        return self._run_operation(context, "query_preview", {"sql": sql}, handler)

    def get_column_profile(
        self,
        table_name: str,
        column_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        return self._run_operation(
            context,
            "get_column_profile",
            {"table_name": table_name, "column_name": column_name},
            lambda: get_column_profile(table_name, column_name),
        )


class MockQualityConnector(QualityConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_quality", ConnectorKind.QUALITY, timeout_seconds))

    def generate_rule_suggestions(
        self,
        table_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        def handler() -> dict[str, Any]:
            result = run_quality_check(table_name)
            return {
                "table_name": table_name,
                "suggested_rules": {
                    "completeness": result["completeness_rules"],
                    "uniqueness": result["uniqueness_rules"],
                    "validity": result["validity_rules"],
                    "consistency": result["consistency_rules"],
                },
            }

        return self._run_operation(
            context,
            "generate_rule_suggestions",
            {"table_name": table_name},
            handler,
        )

    def run_quality_check(self, table_name: str, context: ConnectorCallContext) -> dict[str, Any]:
        return self._run_operation(
            context,
            "run_quality_check",
            {"table_name": table_name},
            lambda: run_quality_check(table_name),
        )


class MockMetricConnector(MetricConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_metric", ConnectorKind.METRIC, timeout_seconds))

    def get_metric_definition(
        self,
        metric_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        return self._run_operation(
            context,
            "get_metric_definition",
            {"metric_name": metric_name},
            lambda: {
                "metric_name": metric_name,
                "definition": "Governed mock metric definition.",
                "business_grain": "day, shop, sku",
                "aggregation": "sum",
                "owner": "data_steward",
            },
        )

    def generate_metric_card(
        self,
        metric_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        return self._run_operation(
            context,
            "generate_metric_card",
            {"metric_name": metric_name},
            lambda: {
                "metric_name": metric_name,
                "business_definition": "Governed business meaning for mock metric.",
                "technical_definition": "Mock semantic-layer expression; no live query.",
                "dimensions": ["shop", "sku", "date"],
                "time_field": "metric_date",
                "questions_to_confirm": ["Confirm owner and SLA before publishing."],
            },
        )


class MockLineageConnector(LineageConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_lineage", ConnectorKind.LINEAGE, timeout_seconds))

    def get_lineage(self, table_name: str, context: ConnectorCallContext) -> dict[str, Any]:
        return self._run_operation(
            context,
            "get_lineage",
            {"table_name": table_name},
            lambda: get_lineage(table_name),
        )


class MockPermissionConnector(PermissionConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_permission", ConnectorKind.PERMISSION, timeout_seconds))

    def check_permission(
        self,
        principal_id: str,
        asset_name: str,
        action: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        return self._run_operation(
            context,
            "check_permission",
            {"principal_id": principal_id, "asset_name": asset_name, "action": action},
            lambda: {
                "principal_id": principal_id,
                "asset_name": asset_name,
                "action": action,
                "allowed": action in {"read_metadata", "read_metric"},
                "requires_approval": action not in {"read_metadata", "read_metric"},
                "reason": "Mock permission decision; real IAM is not connected.",
            },
        )


class MockMaskingConnector(MaskingConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_masking", ConnectorKind.MASKING, timeout_seconds))

    def mask_record(
        self,
        record: dict[str, Any],
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        return self._run_operation(
            context,
            "mask_record",
            {"record": record},
            lambda: {
                "masked_record": self._sanitize(record),
                "masked_fields": [key for key in record if self._is_sensitive_key(key)],
            },
        )


class MockWorkflowConnector(WorkflowConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_workflow", ConnectorKind.WORKFLOW, timeout_seconds))

    def create_approval_ticket(
        self,
        title: str,
        summary: str,
        approvers: tuple[str, ...],
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        return self._run_operation(
            context,
            "create_approval_ticket",
            {"title": title, "approvers": approvers},
            lambda: {
                "ticket_id": "mock-ticket-001",
                "title": title,
                "summary": summary,
                "approvers": approvers,
                "status": "waiting_approval",
                "system": "mock_workflow",
            },
        )


class MockSchedulerConnector(SchedulerConnector):
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        super().__init__(_mock_config("mock_scheduler", ConnectorKind.SCHEDULER, timeout_seconds))

    def submit_dry_run_job(
        self,
        job_name: str,
        parameters: dict[str, Any],
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        return self._run_operation(
            context,
            "submit_dry_run_job",
            {"job_name": job_name, "parameters": parameters},
            lambda: {
                "job_id": "mock-job-001",
                "job_name": job_name,
                "status": "dry_run_created",
                "parameters_summary": sorted(parameters),
                "real_scheduler_called": False,
            },
        )


def build_mock_connectors() -> dict[ConnectorKind, BaseConnector]:
    return {
        ConnectorKind.METADATA: MockMetadataConnector(),
        ConnectorKind.WAREHOUSE: MockWarehouseConnector(),
        ConnectorKind.QUALITY: MockQualityConnector(),
        ConnectorKind.METRIC: MockMetricConnector(),
        ConnectorKind.LINEAGE: MockLineageConnector(),
        ConnectorKind.PERMISSION: MockPermissionConnector(),
        ConnectorKind.MASKING: MockMaskingConnector(),
        ConnectorKind.WORKFLOW: MockWorkflowConnector(),
        ConnectorKind.SCHEDULER: MockSchedulerConnector(),
    }
