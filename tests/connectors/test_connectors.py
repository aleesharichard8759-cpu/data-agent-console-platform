import json

import pytest

from app.audit import InMemoryAuditLogger
from app.connectors import (
    ConnectorCallContext,
    ConnectorError,
    ConnectorKind,
    ConnectorTimeoutError,
    ConnectorUnavailableError,
    MockLineageConnector,
    MockMaskingConnector,
    MockMetadataConnector,
    MockMetricConnector,
    MockPermissionConnector,
    MockQualityConnector,
    MockSchedulerConnector,
    MockWarehouseConnector,
    MockWorkflowConnector,
    OpenMetadataConnector,
    build_mock_connectors,
)
from app.domain import UserContext, UserRole


def make_context(audit_logger: InMemoryAuditLogger | None = None) -> ConnectorCallContext:
    return ConnectorCallContext(
        user_context=UserContext(
            user_id="connector_test_user",
            display_name="Connector Test User",
            roles=(UserRole.DATA_STEWARD,),
        ),
        audit_logger=audit_logger or InMemoryAuditLogger(),
        session_id="mock-session",
        task_id="mock-task",
        agent_name="connector_test",
    )


def test_all_mock_connectors_are_registered_with_timeouts_and_security_notes() -> None:
    connectors = build_mock_connectors()

    assert set(connectors) == set(ConnectorKind)
    for connector in connectors.values():
        assert connector.timeout_seconds > 0
        assert connector.config.enabled
        assert connector.config.is_mock
        assert connector.security_notes()


@pytest.mark.parametrize(
    ("connector", "caller"),
    [
        (MockMetadataConnector(), lambda c, ctx: c.search_assets("order", ctx)),
        (
            MockMetadataConnector(),
            lambda c, ctx: c.get_table_metadata("dwd_trade_order_detail_d", ctx),
        ),
        (
            MockWarehouseConnector(),
            lambda c, ctx: c.query_preview(
                "select order_status, count(1) from ads_trade_order_dashboard_day",
                ctx,
            ),
        ),
        (
            MockWarehouseConnector(),
            lambda c, ctx: c.get_column_profile("dwd_customer_detail_d", "customer_phone", ctx),
        ),
        (
            MockQualityConnector(),
            lambda c, ctx: c.generate_rule_suggestions("dwd_trade_order_detail_d", ctx),
        ),
        (
            MockQualityConnector(),
            lambda c, ctx: c.run_quality_check("dwd_trade_order_detail_d", ctx),
        ),
        (MockMetricConnector(), lambda c, ctx: c.get_metric_definition("gmv", ctx)),
        (MockMetricConnector(), lambda c, ctx: c.generate_metric_card("gmv", ctx)),
        (MockLineageConnector(), lambda c, ctx: c.get_lineage("dwd_trade_order_detail_d", ctx)),
        (
            MockPermissionConnector(),
            lambda c, ctx: c.check_permission(
                "mock_principal",
                "ads_trade_order_dashboard_day",
                "read_metadata",
                ctx,
            ),
        ),
        (
            MockMaskingConnector(),
            lambda c, ctx: c.mask_record({"customer_phone": "masked-input"}, ctx),
        ),
        (
            MockWorkflowConnector(),
            lambda c, ctx: c.create_approval_ticket(
                "Mock approval",
                "Safe mock approval summary.",
                ("mock_reviewer",),
                ctx,
            ),
        ),
        (
            MockSchedulerConnector(),
            lambda c, ctx: c.submit_dry_run_job(
                "mock_quality_job",
                {"table_name": "dwd_trade_order_detail_d"},
                ctx,
            ),
        ),
    ],
)
def test_each_mock_connector_call_works_and_audits(connector, caller) -> None:
    audit_logger = InMemoryAuditLogger()
    context = make_context(audit_logger)

    result = caller(connector, context)

    assert result["audit_event_id"]
    events = audit_logger.list_events({"event_type": "connector_called"})
    assert len(events) >= 1
    assert events[-1].raw_payload_allowed is False
    assert events[-1].task_id == "mock-task"


def test_connector_timeout_error_is_uniform_and_audited() -> None:
    audit_logger = InMemoryAuditLogger()
    context = make_context(audit_logger)
    connector = MockMetadataConnector(timeout_seconds=0)

    with pytest.raises(ConnectorTimeoutError) as exc:
        connector.search_assets("order", context)

    assert isinstance(exc.value, ConnectorError)
    events = audit_logger.list_events({"event_type": "connector_failed"})
    assert len(events) == 1
    assert events[0].reason == "Connector timeout_seconds must be positive."


def test_real_connector_stub_is_disabled_and_audited() -> None:
    audit_logger = InMemoryAuditLogger()
    context = make_context(audit_logger)
    connector = OpenMetadataConnector()

    with pytest.raises(ConnectorUnavailableError):
        connector.search_assets("order", context)

    events = audit_logger.list_events({"event_type": "connector_failed"})
    assert len(events) == 1
    assert events[0].metadata["is_mock"] is False


def test_connector_outputs_and_audit_do_not_leak_sensitive_values() -> None:
    audit_logger = InMemoryAuditLogger()
    context = make_context(audit_logger)
    connector = MockMaskingConnector()

    result = connector.mask_record(
        {
            "customer_phone": "mock-phone-placeholder",
            "customer_email": "mock-email-placeholder",
            "shipping_address": "mock-address-placeholder",
            "order_id": "mock-order-id",
        },
        context,
    )
    event_payload = json.dumps(
        [event.model_dump(mode="json") for event in audit_logger.list_events()],
        ensure_ascii=False,
        sort_keys=True,
    )
    result_payload = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert "mock-phone-placeholder" not in result_payload
    assert "mock-email-placeholder" not in result_payload
    assert "mock-address-placeholder" not in result_payload
    assert "mock-phone-placeholder" not in event_payload
    assert "mock-email-placeholder" not in event_payload
    assert "mock-address-placeholder" not in event_payload
    assert result["masked_record"]["customer_phone"] == "***MASKED***"
