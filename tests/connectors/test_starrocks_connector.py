from app.audit import InMemoryAuditLogger
from app.connectors import EnvSecretProvider, StarRocksMetadataConnector, StarRocksWarehouseConnector
from app.connectors.factory import UnconfiguredMetadataConnector, UnconfiguredWarehouseConnector
from app.domain.identity import UserContext, UserRole
from app.connectors.base import ConnectorCallContext, ConnectorSecurityError


def context() -> ConnectorCallContext:
    return ConnectorCallContext(
        user_context=UserContext(
            user_id="connector_tester",
            display_name="Connector Tester",
            roles=(UserRole.DATA_STEWARD,),
        ),
        audit_logger=InMemoryAuditLogger(),
    )


def test_env_secret_provider_resolves_secret_ref_json(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATAGENT_SECRET_PROD_STARROCKS_RMA_RO",
        '{"host":"sr-fe.internal","port":9030,"user":"rma_ro","password":"secret","database":"flexispot"}',
    )

    credentials = EnvSecretProvider().resolve_starrocks("secret://prod/starrocks/rma_ro")

    assert credentials.host == "sr-fe.internal"
    assert credentials.user == "rma_ro"
    assert credentials.password.get_secret_value() == "secret"
    assert credentials.database == "flexispot"


def test_unconfigured_warehouse_connector_fails_closed() -> None:
    connector = UnconfiguredWarehouseConnector()

    try:
        connector.query_preview("select 1 limit 1", context())
    except RuntimeError as exc:
        assert "No real warehouse connector is configured" in str(exc)
    else:
        raise AssertionError("unconfigured connector must fail closed")


def test_unconfigured_metadata_connector_fails_closed() -> None:
    connector = UnconfiguredMetadataConnector()

    try:
        connector.search_assets("rma", context())
    except RuntimeError as exc:
        assert "No real metadata connector is configured" in str(exc)
    else:
        raise AssertionError("unconfigured metadata connector must fail closed")


def test_starrocks_connector_enforces_allowed_tables_before_network(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATAGENT_SECRET_PROD_STARROCKS_RMA_RO",
        '{"host":"sr-fe.internal","user":"rma_ro","password":"secret"}',
    )
    connector = StarRocksWarehouseConnector(
        secret_ref="secret://prod/starrocks/rma_ro",
        allowed_tables=("ads_afs_rma_multi_dim_metric_1d",),
    )

    try:
        connector.query_preview("select order_count from ads_trade_order_dashboard_day limit 1", context())
    except ConnectorSecurityError as exc:
        assert "outside the configured StarRocks scope" in str(exc)
    else:
        raise AssertionError("disallowed tables must be blocked before query execution")


def test_starrocks_metadata_connector_enforces_allowed_tables_before_network(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATAGENT_SECRET_PROD_STARROCKS_RMA_RO",
        '{"host":"sr-fe.internal","user":"rma_ro","password":"secret","database":"rma_ads"}',
    )
    connector = StarRocksMetadataConnector(
        secret_ref="secret://prod/starrocks/rma_ro",
        allowed_tables=("ads_afs_rma_multi_dim_metric_1d",),
    )

    try:
        connector.get_table_metadata("ads_trade_order_dashboard_day", context())
    except ConnectorSecurityError as exc:
        assert "outside the configured StarRocks metadata scope" in str(exc)
    else:
        raise AssertionError("disallowed metadata tables must be blocked before query execution")
