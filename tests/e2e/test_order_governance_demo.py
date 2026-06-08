import json

from app.domain import GovernanceTaskType
from scripts.demo_order_governance import DEMO_PROMPT, run_demo


def test_order_governance_demo_generates_complete_report() -> None:
    report = run_demo()

    assert report["prompt"] == DEMO_PROMPT
    assert report["task"]["task_type"] == GovernanceTaskType.DATA_DOMAIN_GOVERNANCE.value
    assert report["task"]["task_level"] == "G4"
    assert report["asset_inventory"]
    assert report["metadata_issues"]["missing_owner_tables"] == ["ods_erp_order"]
    assert "order_status" in report["metadata_issues"]["missing_comment_fields"]
    assert report["quality_rule_suggestions"]["strong_rules"]
    assert report["quality_rule_suggestions"]["weak_rules"]
    assert report["quality_rule_suggestions"]["observation_rules"]
    assert report["governance_plan"]["approval_required"] is True
    assert report["governance_plan"]["risk_level"] == "G4"
    assert report["rollback_plan"]
    assert report["audit_refs"]


def test_order_governance_demo_generates_metric_cards_for_chatbi() -> None:
    report = run_demo()
    metrics = {card["metric_name"]: card for card in report["metric_governance"]}

    assert set(metrics) == {
        "order_count",
        "sales_amount",
        "refund_rate",
        "rma_complaint_rate",
    }
    for card in metrics.values():
        assert card["business_definition"]
        assert card["technical_definition"]
        assert card["dimensions"]
        assert card["time_field"] == "metric_date"
        assert card["audit_event_id"]


def test_order_governance_demo_outputs_safe_sensitive_field_summary_only() -> None:
    report = run_demo()
    fields = {item["field_name"]: item for item in report["sensitive_fields"]}

    assert set(fields) == {
        "customer_phone",
        "customer_email",
        "shipping_address",
        "gross_profit",
    }
    for field in fields.values():
        assert field["sensitivity_level"] == "L3"
        assert field["masking_strategy"]
        assert field["allow_in_model_context"] is False


def test_order_governance_demo_lineage_reaches_chatbi() -> None:
    report = run_demo()
    chain = report["lineage_impact"]["chain"]

    assert chain[0] == "ods_erp_order"
    assert "dwd_trade_order_detail_d" in chain
    assert "dws_trade_order_sku_day" in chain
    assert "ads_trade_order_dashboard_day" in chain
    assert chain[-1] == "chatbi_order_semantic_layer"


def test_order_governance_demo_generates_eval_case() -> None:
    report = run_demo()
    eval_case = report["eval_case"]

    assert eval_case["case_id"] == "demo_order_domain_chatbi_governance"
    assert eval_case["task_type"] == "data_domain_governance"
    assert eval_case["expected_policy_decision"] == "ask"
    assert "security_agent" in eval_case["expected_agents"]


def test_order_governance_demo_does_not_output_sensitive_plaintext() -> None:
    report = run_demo()
    eval_case = report.pop("eval_case")
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)

    for forbidden in (
        "raw_customer_phone",
        "raw_email",
        "password=",
        "api_key=",
        "token=",
        "plain_phone",
    ):
        assert forbidden not in serialized
    assert "raw_customer_phone" in eval_case["must_not_include"]
