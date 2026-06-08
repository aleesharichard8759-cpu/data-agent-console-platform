from __future__ import annotations

from app.connectors.base import ConnectorConfig, ConnectorKind, StubConnector
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


def _stub_config(name: str, kind: ConnectorKind) -> ConnectorConfig:
    return ConnectorConfig(
        name=name,
        connector_kind=kind,
        timeout_seconds=5.0,
        enabled=False,
        is_mock=False,
    )


class OpenMetadataConnector(StubConnector, MetadataConnector):
    """TODO: implement OpenMetadata/DataHub API adapter with explicit credentials."""

    def __init__(self) -> None:
        super().__init__(_stub_config("openmetadata_stub", ConnectorKind.METADATA))

    def search_assets(self, query, context):
        return self._run_operation(context, "search_assets", {"query": query}, lambda: {})

    def get_table_metadata(self, table_name, context):
        return self._run_operation(
            context,
            "get_table_metadata",
            {"table_name": table_name},
            lambda: {},
        )


class WarehouseEngineConnector(StubConnector, WarehouseConnector):
    """TODO: implement Doris/StarRocks/ClickHouse/Hive adapter behind SQL Gateway."""

    def __init__(self) -> None:
        super().__init__(_stub_config("warehouse_engine_stub", ConnectorKind.WAREHOUSE))

    def query_preview(self, sql, context):
        return self._run_operation(context, "query_preview", {"sql": sql}, lambda: {})

    def get_column_profile(self, table_name, column_name, context):
        return self._run_operation(
            context,
            "get_column_profile",
            {"table_name": table_name, "column_name": column_name},
            lambda: {},
        )


class QualityPlatformConnector(StubConnector, QualityConnector):
    """TODO: implement Great Expectations/Soda/internal quality platform adapter."""

    def __init__(self) -> None:
        super().__init__(_stub_config("quality_platform_stub", ConnectorKind.QUALITY))

    def generate_rule_suggestions(self, table_name, context):
        return self._run_operation(
            context,
            "generate_rule_suggestions",
            {"table_name": table_name},
            lambda: {},
        )

    def run_quality_check(self, table_name, context):
        return self._run_operation(
            context,
            "run_quality_check",
            {"table_name": table_name},
            lambda: {},
        )


class MetricPlatformConnector(StubConnector, MetricConnector):
    """TODO: implement metric platform or semantic-layer adapter."""

    def __init__(self) -> None:
        super().__init__(_stub_config("metric_platform_stub", ConnectorKind.METRIC))

    def get_metric_definition(self, metric_name, context):
        return self._run_operation(
            context,
            "get_metric_definition",
            {"metric_name": metric_name},
            lambda: {},
        )

    def generate_metric_card(self, metric_name, context):
        return self._run_operation(
            context,
            "generate_metric_card",
            {"metric_name": metric_name},
            lambda: {},
        )


class AtlasLineageConnector(StubConnector, LineageConnector):
    """TODO: implement OpenMetadata Lineage/Atlas/DataHub lineage adapter."""

    def __init__(self) -> None:
        super().__init__(_stub_config("lineage_platform_stub", ConnectorKind.LINEAGE))

    def get_lineage(self, table_name, context):
        return self._run_operation(context, "get_lineage", {"table_name": table_name}, lambda: {})


class IAMPermissionConnector(StubConnector, PermissionConnector):
    """TODO: implement IAM/Ranger/internal permission adapter."""

    def __init__(self) -> None:
        super().__init__(_stub_config("iam_permission_stub", ConnectorKind.PERMISSION))

    def check_permission(self, principal_id, asset_name, action, context):
        return self._run_operation(
            context,
            "check_permission",
            {"principal_id": principal_id, "asset_name": asset_name, "action": action},
            lambda: {},
        )


class DLPMaskingConnector(StubConnector, MaskingConnector):
    """TODO: implement DLP/Presidio/internal masking adapter."""

    def __init__(self) -> None:
        super().__init__(_stub_config("dlp_masking_stub", ConnectorKind.MASKING))

    def mask_record(self, record, context):
        return self._run_operation(context, "mask_record", {"record": record}, lambda: {})


class TicketWorkflowConnector(StubConnector, WorkflowConnector):
    """TODO: implement Jira/Feishu/DingTalk/internal workflow adapter."""

    def __init__(self) -> None:
        super().__init__(_stub_config("ticket_workflow_stub", ConnectorKind.WORKFLOW))

    def create_approval_ticket(self, title, summary, approvers, context):
        return self._run_operation(
            context,
            "create_approval_ticket",
            {"title": title, "approvers": approvers},
            lambda: {},
        )


class WorkflowSchedulerConnector(StubConnector, SchedulerConnector):
    """TODO: implement DolphinScheduler/Airflow adapter."""

    def __init__(self) -> None:
        super().__init__(_stub_config("workflow_scheduler_stub", ConnectorKind.SCHEDULER))

    def submit_dry_run_job(self, job_name, parameters, context):
        return self._run_operation(
            context,
            "submit_dry_run_job",
            {"job_name": job_name, "parameters": parameters},
            lambda: {},
        )
