from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.connectors.base import BaseConnector, ConnectorCallContext


class MetadataConnector(BaseConnector, ABC):
    """Catalog metadata connector interface for future OpenMetadata or DataHub adapters."""

    @abstractmethod
    def search_assets(self, query: str, context: ConnectorCallContext) -> dict[str, Any]:
        """Search governed metadata assets."""

    @abstractmethod
    def get_table_metadata(self, table_name: str, context: ConnectorCallContext) -> dict[str, Any]:
        """Fetch safe table metadata."""


class WarehouseConnector(BaseConnector, ABC):
    """Warehouse connector interface for future Doris, StarRocks, ClickHouse, or Hive adapters."""

    @abstractmethod
    def query_preview(self, sql: str, context: ConnectorCallContext) -> dict[str, Any]:
        """Return a safe query preview after SQL Gateway review."""

    @abstractmethod
    def get_column_profile(
        self,
        table_name: str,
        column_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Return safe column profile summary."""


class QualityConnector(BaseConnector, ABC):
    """Quality platform connector interface for Great Expectations, Soda, or internal engines."""

    @abstractmethod
    def generate_rule_suggestions(
        self,
        table_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Generate quality rule suggestions."""

    @abstractmethod
    def run_quality_check(self, table_name: str, context: ConnectorCallContext) -> dict[str, Any]:
        """Run quality checks or fetch latest check results."""


class MetricConnector(BaseConnector, ABC):
    """Metric platform or semantic-layer connector interface."""

    @abstractmethod
    def get_metric_definition(
        self,
        metric_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Fetch governed metric definition."""

    @abstractmethod
    def generate_metric_card(
        self,
        metric_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Generate a safe metric card summary."""


class LineageConnector(BaseConnector, ABC):
    """Lineage connector interface for OpenMetadata Lineage, Atlas, or DataHub."""

    @abstractmethod
    def get_lineage(self, table_name: str, context: ConnectorCallContext) -> dict[str, Any]:
        """Fetch safe upstream and downstream lineage."""


class PermissionConnector(BaseConnector, ABC):
    """Permission connector interface for IAM, Ranger, or internal authorization systems."""

    @abstractmethod
    def check_permission(
        self,
        principal_id: str,
        asset_name: str,
        action: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Check whether a principal can perform an action on an asset."""


class MaskingConnector(BaseConnector, ABC):
    """DLP and masking connector interface for Presidio or internal masking services."""

    @abstractmethod
    def mask_record(
        self,
        record: dict[str, Any],
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Mask one structured record."""


class WorkflowConnector(BaseConnector, ABC):
    """Workflow ticket connector interface for Jira, Feishu, DingTalk, or internal tickets."""

    @abstractmethod
    def create_approval_ticket(
        self,
        title: str,
        summary: str,
        approvers: tuple[str, ...],
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Create an approval ticket."""


class SchedulerConnector(BaseConnector, ABC):
    """Scheduler connector interface for DolphinScheduler or Airflow."""

    @abstractmethod
    def submit_dry_run_job(
        self,
        job_name: str,
        parameters: dict[str, Any],
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        """Submit a dry-run scheduling job."""
