from __future__ import annotations

import os

from app.connectors.base import ConnectorCallContext, ConnectorConfig, ConnectorKind
from app.connectors.interfaces import MetadataConnector, WarehouseConnector
from app.connectors.starrocks import StarRocksMetadataConnector, StarRocksWarehouseConnector
from app.connectors.stubs import OpenMetadataConnector, WarehouseEngineConnector


def build_warehouse_connector_from_env() -> WarehouseConnector:
    """Build the configured real warehouse connector, failing closed when absent."""

    secret_ref = os.getenv("DATAGENT_STARROCKS_SECRET_REF")
    if not secret_ref:
        return UnconfiguredWarehouseConnector()

    allowed_tables = tuple(
        table.strip().lower()
        for table in os.getenv("DATAGENT_STARROCKS_ALLOWED_TABLES", "").split(",")
        if table.strip()
    )
    max_rows = int(os.getenv("DATAGENT_STARROCKS_MAX_ROWS", "100"))
    timeout_seconds = float(os.getenv("DATAGENT_STARROCKS_TIMEOUT_SECONDS", "30"))
    return StarRocksWarehouseConnector(
        secret_ref=secret_ref,
        database=os.getenv("DATAGENT_STARROCKS_DATABASE") or None,
        allowed_tables=allowed_tables,
        max_rows=max_rows,
        timeout_seconds=timeout_seconds,
    )


def build_metadata_connector_from_env() -> MetadataConnector:
    """Build the configured metadata connector, failing closed when absent."""

    secret_ref = os.getenv("DATAGENT_STARROCKS_SECRET_REF")
    if not secret_ref:
        return UnconfiguredMetadataConnector()

    allowed_tables = tuple(
        table.strip().lower()
        for table in os.getenv("DATAGENT_STARROCKS_ALLOWED_TABLES", "").split(",")
        if table.strip()
    )
    timeout_seconds = float(os.getenv("DATAGENT_STARROCKS_TIMEOUT_SECONDS", "30"))
    return StarRocksMetadataConnector(
        secret_ref=secret_ref,
        database=os.getenv("DATAGENT_STARROCKS_DATABASE") or None,
        allowed_tables=allowed_tables,
        timeout_seconds=timeout_seconds,
    )


class UnconfiguredWarehouseConnector(WarehouseEngineConnector):
    """Disabled real connector used when no StarRocks secret_ref is configured."""

    def __init__(self) -> None:
        super().__init__()
        self.config = ConnectorConfig(
            name="warehouse_unconfigured",
            connector_kind=ConnectorKind.WAREHOUSE,
            provider="starrocks",
            enabled=False,
            is_mock=False,
            timeout_seconds=5.0,
        )

    def query_preview(self, sql, context: ConnectorCallContext):
        del sql, context
        raise RuntimeError(
            "No real warehouse connector is configured. Set DATAGENT_STARROCKS_SECRET_REF "
            "and the matching DATAGENT_SECRET_* or DATAGENT_STARROCKS_* credentials."
        )

    def get_column_profile(self, table_name, column_name, context: ConnectorCallContext):
        del table_name, column_name, context
        raise RuntimeError(
            "No real warehouse connector is configured. Set DATAGENT_STARROCKS_SECRET_REF."
        )


class UnconfiguredMetadataConnector(OpenMetadataConnector):
    """Disabled metadata connector used when no StarRocks secret_ref is configured."""

    def __init__(self) -> None:
        super().__init__()
        self.config = ConnectorConfig(
            name="metadata_unconfigured",
            connector_kind=ConnectorKind.METADATA,
            provider="starrocks",
            enabled=False,
            is_mock=False,
            timeout_seconds=5.0,
        )

    def search_assets(self, query, context: ConnectorCallContext):
        del query, context
        raise RuntimeError(
            "No real metadata connector is configured. Set DATAGENT_STARROCKS_SECRET_REF "
            "and the matching StarRocks credentials."
        )

    def get_table_metadata(self, table_name, context: ConnectorCallContext):
        del table_name, context
        raise RuntimeError(
            "No real metadata connector is configured. Set DATAGENT_STARROCKS_SECRET_REF."
        )
