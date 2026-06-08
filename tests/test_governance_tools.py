import pytest

from data_governance_agent_runtime.audit.recorder import AuditRecorder
from data_governance_agent_runtime.core.enums import ActionRisk, Decision
from data_governance_agent_runtime.core.models import Actor, RuntimeContext, ToolRequest
from data_governance_agent_runtime.dlp.masking import DlpMasker
from data_governance_agent_runtime.policy.engine import PolicyEngine
from data_governance_agent_runtime.tools.registry import build_default_registry


def make_context() -> RuntimeContext:
    return RuntimeContext(
        actor=Actor(actor_id="tool_tester", roles=("data_steward",)),
        purpose="tool_unit_test",
    )


@pytest.mark.parametrize(
    ("tool_name", "action", "parameters", "expected_key"),
    [
        ("asset_inventory", "asset.inventory", {"domain": "trade"}, "assets"),
        (
            "metadata_completion",
            "metadata.complete",
            {"asset_name": "ads_governed_order_metric_1d", "domain": "trade"},
            "suggestions",
        ),
        (
            "quality_rule_suggestion",
            "quality.suggest_rules",
            {"table_name": "ads_governed_order_metric_1d"},
            "rules",
        ),
        (
            "metric_governance",
            "metric.check",
            {"metric_name": "net_revenue"},
            "checks",
        ),
        (
            "sensitive_field_detection",
            "sensitive.detect",
            {"fields": ["business_key", "email_hash"]},
            "detected_fields",
        ),
        (
            "lineage_impact",
            "lineage.impact",
            {"asset_name": "dwd_trade_order_detail_di"},
            "downstream_assets",
        ),
        ("permission_inspection", "permission.inspect", {}, "findings"),
        (
            "governance_report",
            "report.generate",
            {"assets_scanned": 2, "rules_suggested": 1, "open_risks": 1},
            "summary",
        ),
    ],
)
def test_mock_governance_tools_return_typed_payloads(
    tool_name: str,
    action: str,
    parameters: dict[str, object],
    expected_key: str,
) -> None:
    audit = AuditRecorder()
    registry = build_default_registry(PolicyEngine(), audit, DlpMasker())
    request = ToolRequest(
        tool_name=tool_name,
        action=action,
        risk=ActionRisk.MEDIUM,
        parameters=parameters,
    )

    result = registry.get(tool_name).invoke(make_context(), request)

    assert result.policy.decision == Decision.ALLOW
    assert expected_key in result.data
    assert len(audit.list_events()) == 1

