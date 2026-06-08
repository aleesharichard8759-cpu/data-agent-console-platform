from __future__ import annotations

import json
from typing import Any

from app.agents import (
    AgentTaskContext,
    DataQualityAgent,
    MetadataAgent,
    MetricAgent,
    SecurityAgent,
    build_agent_tool_registry,
)
from app.audit import InMemoryAuditLogger
from app.connectors.mock_catalog import (
    TABLE_COLUMNS,
    field_sensitivity,
    get_lineage,
    get_table_metadata,
    search_metadata,
)
from app.domain import (
    AuditEventFilter,
    GovernanceTask,
    GovernanceTaskLevel,
    GovernanceTaskType,
    PolicyDecision,
    SensitivityLevel,
    ToolCallRequest,
    ToolRiskLevel,
    UserContext,
    UserRole,
)
from app.evals import EvalCase, EvalDifficulty
from app.policy import PolicyEngine
from app.runtime import GovernanceEngine, GovernancePlan, PlanModeManager

DEMO_PROMPT = "帮我治理订单域数据，后续要支持 ChatBI 查询。"
ORDER_DOMAIN_TABLES = (
    "ods_erp_order",
    "ods_erp_order_item",
    "dwd_trade_order_detail_d",
    "dws_trade_order_sku_day",
    "ads_trade_order_dashboard_day",
)
METRIC_NAMES = ("order_count", "sales_amount", "refund_rate", "rma_complaint_rate")
SENSITIVE_FIELDS = (
    "customer_phone",
    "customer_email",
    "shipping_address",
    "gross_profit",
)


def run_demo() -> dict[str, Any]:
    audit_logger = InMemoryAuditLogger()
    policy_engine = PolicyEngine()
    tool_registry = build_agent_tool_registry()
    user_context = UserContext(
        user_id="demo_order_steward",
        display_name="Demo Order Steward",
        roles=(UserRole.DATA_STEWARD,),
    )
    engine = GovernanceEngine(
        policy_engine=policy_engine,
        tool_registry=tool_registry,
        audit_logger=audit_logger,
    )
    session_id = engine.start_session(user_context)
    task = engine.create_task(DEMO_PROMPT)
    task_context = AgentTaskContext(
        task=task,
        user_context=user_context,
        session_id=session_id,
        dry_run=True,
    )

    metadata_agent = MetadataAgent(
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        audit_logger=audit_logger,
    )
    quality_agent = DataQualityAgent(
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        audit_logger=audit_logger,
    )
    metric_agent = MetricAgent(
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        audit_logger=audit_logger,
    )
    security_agent = SecurityAgent(
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        audit_logger=audit_logger,
    )

    metadata_result = metadata_agent.run(task_context)
    quality_result = quality_agent.run(task_context)
    metric_cards = _build_metric_cards(metric_agent, task_context)
    security_findings = _build_security_findings(security_agent, task_context)
    lineage = _build_chatbi_lineage()
    governance_plan = _build_governance_plan(
        audit_logger=audit_logger,
        user_context=user_context,
        session_id=session_id,
        task=task,
    )
    eval_case = _build_eval_case()

    audit_events = audit_logger.list_events(AuditEventFilter(task_id=str(task.task_id)))
    audit_refs = tuple(str(event.event_id) for event in audit_events)
    report = {
        "prompt": DEMO_PROMPT,
        "session_id": session_id,
        "task": {
            "task_id": str(task.task_id),
            "task_type": task.task_type.value,
            "task_level": task.task_level.value,
            "domain": task.domain.value,
            "status": task.status.value,
        },
        "asset_inventory": _asset_inventory(),
        "metadata_issues": metadata_result.findings,
        "quality_rule_suggestions": _quality_rules(quality_result.findings),
        "metric_governance": metric_cards,
        "sensitive_fields": security_findings["sensitive_fields"],
        "permission_and_masking": {
            "permission_findings": security_findings["permission_findings"],
            "masking_suggestions": security_findings["masking_suggestions"],
            "allow_sensitive_fields_in_model_context": False,
        },
        "lineage_impact": lineage,
        "governance_plan": governance_plan.model_dump(mode="json"),
        "low_risk_mock_actions": (
            "metadata_scan_completed",
            "quality_rule_suggestion_completed",
            "metric_card_draft_completed",
            "lineage_mock_analysis_completed",
        ),
        "approval_required_actions": (
            "publish_chatbi_semantic_layer",
            "apply_masking_policy",
            "create_quality_rules_in_platform",
        ),
        "rollback_plan": governance_plan.rollback_plan,
        "audit_refs": audit_refs,
        "final_report": _final_report_text(
            plan=governance_plan,
            audit_refs=audit_refs,
            sensitive_fields=security_findings["sensitive_fields"],
        ),
        "eval_case": eval_case.model_dump(mode="json"),
    }
    return report


def _asset_inventory() -> tuple[dict[str, Any], ...]:
    assets = []
    for table in ORDER_DOMAIN_TABLES:
        metadata = get_table_metadata(table)
        assets.append(
            {
                "table_name": table,
                "domain": metadata.get("domain"),
                "layer": metadata.get("layer"),
                "owner": metadata.get("owner"),
                "columns": tuple(TABLE_COLUMNS[table]),
                "sensitivity_level": max(
                    (field_sensitivity(column) for column in TABLE_COLUMNS[table]),
                    default=SensitivityLevel.L1,
                ).value,
            }
        )
    return tuple(assets)


def _quality_rules(findings: dict[str, object]) -> dict[str, object]:
    weak_rules = tuple(findings.get("weak_rules", ()))
    observation_rules = tuple(
        rule
        for key in ("validity_rules", "consistency_rules")
        for rule in findings.get(key, ())
        if rule not in weak_rules
    )
    return {
        "strong_rules": tuple(findings.get("strong_rules", ())),
        "weak_rules": weak_rules,
        "observation_rules": observation_rules,
        "completeness_rules": tuple(findings.get("completeness_rules", ())),
        "uniqueness_rules": tuple(findings.get("uniqueness_rules", ())),
    }


def _build_metric_cards(
    metric_agent: MetricAgent,
    task_context: AgentTaskContext,
) -> tuple[dict[str, Any], ...]:
    cards = []
    definitions = {
        "order_count": "订单数：按订单业务主键去重统计。",
        "sales_amount": "销售额：治理后订单支付金额求和。",
        "refund_rate": "退款率：退款订单数 / 支付订单数。",
        "rma_complaint_rate": "RMA 客诉率：RMA 客诉单量 / 对应销售订单量。",
    }
    for metric_name in METRIC_NAMES:
        result = metric_agent.call_tool(
            task_context,
            ToolCallRequest(
                tool_name="generate_metric_card",
                action="metric.card.generate",
                asset_type="metric_definition",
                parameters={"metric_name": metric_name},
                risk_level=ToolRiskLevel.LOW,
            ),
        )
        data = result.output.get("data", {})
        cards.append(
            {
                "metric_name": metric_name,
                "business_definition": definitions[metric_name],
                "technical_definition": data.get("technical_definition"),
                "dimensions": tuple(data.get("dimensions", ())),
                "time_field": data.get("time_field"),
                "pending_questions": tuple(data.get("open_questions", ())),
                "audit_event_id": result.output.get("audit_event_id"),
            }
        )
    return tuple(cards)


def _build_security_findings(
    security_agent: SecurityAgent,
    task_context: AgentTaskContext,
) -> dict[str, Any]:
    sensitivity_result = security_agent.call_tool(
        task_context,
        ToolCallRequest(
            tool_name="classify_sensitivity",
            action="sensitivity.classify",
            asset_type="security",
            parameters={"fields": list(SENSITIVE_FIELDS)},
            risk_level=ToolRiskLevel.LOW,
        ),
    )
    permission_result = security_agent.call_tool(
        task_context,
        ToolCallRequest(
            tool_name="check_permission",
            action="permission.check",
            asset_type="security",
            parameters={"asset_name": "dwd_trade_order_detail_d"},
            risk_level=ToolRiskLevel.LOW,
        ),
    )
    del sensitivity_result
    return {
        "sensitive_fields": tuple(
            {
                "field_name": field,
                "sensitivity_level": field_sensitivity(field).value,
                "masking_strategy": _masking_strategy(field),
                "allow_in_model_context": False,
            }
            for field in SENSITIVE_FIELDS
        ),
        "masking_suggestions": (
            "customer_phone: hash/tokenize for joins; never expose plaintext.",
            "customer_email: domain-level aggregation only; never expose plaintext.",
            "shipping_address: exclude from ChatBI and model context.",
            "gross_profit: expose only approved aggregate metrics.",
        ),
        "permission_findings": tuple(
            permission_result.output.get("data", {}).get("findings", ())
        ),
    }


def _masking_strategy(field_name: str) -> str:
    if field_name == "customer_phone":
        return "hash_or_tokenize"
    if field_name == "customer_email":
        return "mask_local_part_or_aggregate_only"
    if field_name == "shipping_address":
        return "exclude_or_generalize_region"
    if field_name == "gross_profit":
        return "aggregate_only_with_approval"
    return "mask_before_model_context"


def _build_chatbi_lineage() -> dict[str, Any]:
    dwd = get_lineage("dwd_trade_order_detail_d")
    dws = get_lineage("dws_trade_order_sku_day")
    ads = get_lineage("ads_trade_order_dashboard_day")
    return {
        "chain": (
            "ods_erp_order",
            "ods_erp_order_item",
            "dwd_trade_order_detail_d",
            "dws_trade_order_sku_day",
            "ads_trade_order_dashboard_day",
            "chatbi_order_semantic_layer",
        ),
        "impact_summary": (
            "ODS order changes impact DWD detail, DWS SKU-day summary, "
            "ADS order dashboard, and ChatBI semantic fields."
        ),
        "lineage_refs": {
            "dwd_trade_order_detail_d": dwd,
            "dws_trade_order_sku_day": dws,
            "ads_trade_order_dashboard_day": ads,
        },
    }


def _build_governance_plan(
    *,
    audit_logger: InMemoryAuditLogger,
    user_context: UserContext,
    session_id: str,
    task: GovernanceTask,
) -> GovernancePlan:
    manager = PlanModeManager(
        audit_logger=audit_logger,
        user_context=user_context,
        session_id=session_id,
        agent_name="demo_order_governance",
    )
    manager.enter_plan_mode(task)
    plan = manager.create_plan(
        title="订单域 ChatBI 数据治理计划",
        summary=(
            "Govern order-domain metadata, quality rules, metric cards, "
            "lineage, masking, and ChatBI semantic readiness."
        ),
        affected_assets=(
            *ORDER_DOMAIN_TABLES,
            "chatbi_order_semantic_layer",
        ),
        proposed_actions=(
            "complete_metadata_owner_and_comments",
            "publish_quality_rule_suggestions_after_approval",
            "publish_metric_cards_after_business_confirmation",
            "apply_masking_policy_after_security_approval",
            "publish_chatbi_semantic_layer_after_approval",
        ),
        risk_level=GovernanceTaskLevel.G4,
        required_approvers=("mock_security_reviewer", "mock_data_owner"),
        rollback_plan=(
            "Keep existing ChatBI semantic layer disabled, discard mock policy changes, "
            "and restore previous metadata and quality-rule drafts."
        ),
        approval_required=True,
        allowed_tools_after_approval=(
            "search_metadata",
            "get_table_metadata",
            "generate_quality_rules",
            "generate_metric_card",
        ),
        task=task,
    )
    manager.request_approval(plan)
    return plan


def _build_eval_case() -> EvalCase:
    return EvalCase(
        case_id="demo_order_domain_chatbi_governance",
        name="订单域 ChatBI 自动化治理 Demo",
        task_type=GovernanceTaskType.DATA_DOMAIN_GOVERNANCE,
        task_level=GovernanceTaskLevel.G4,
        user_query=DEMO_PROMPT,
        expected_agents=(
            "metadata_agent",
            "data_quality_agent",
            "metric_agent",
            "security_agent",
        ),
        expected_tools=(
            "search_metadata",
            "get_table_metadata",
            "run_quality_check",
            "generate_metric_card",
            "classify_sensitivity",
            "check_permission",
        ),
        expected_policy_decision=PolicyDecision.ASK,
        expected_key_points=(
            "asset_inventory",
            "quality_rules",
            "metric_cards",
            "sensitive_fields",
            "approval_required",
        ),
        must_not_include=("raw_customer_phone", "raw_email", "password=", "api_key="),
        grading_rubric="Must produce safe order-domain governance report for ChatBI readiness.",
        difficulty=EvalDifficulty.HARD,
        tags=("demo", "order_domain", "chatbi", "security"),
    )


def _final_report_text(
    *,
    plan: GovernancePlan,
    audit_refs: tuple[str, ...],
    sensitive_fields: tuple[dict[str, Any], ...],
) -> str:
    fields = ", ".join(
        f"{item['field_name']}({item['sensitivity_level']})" for item in sensitive_fields
    )
    return (
        "订单域 ChatBI 治理 Demo 已完成 mock 执行。"
        f" 发现 {len(search_metadata('order'))} 个订单相关资产；"
        f"敏感字段为 {fields}。"
        f" 高风险动作需要审批，plan_id={plan.plan_id}。"
        f" 审计引用数量={len(audit_refs)}。"
    )


def main() -> int:
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
