from app.domain import (
    DataDomain,
    GovernanceTaskLevel,
    PolicyDecision,
    SensitivityLevel,
    ToolCallRequest,
    ToolRiskLevel,
    UserContext,
    UserRole,
)
from app.policy import PolicyEngine, PolicyRule


def make_user() -> UserContext:
    return UserContext(
        user_id="user_policy_tester",
        display_name="Policy Tester",
        roles=(UserRole.DATA_STEWARD,),
    )


def make_request(
    action: str,
    asset_type: str | None = None,
    sensitivity_level: SensitivityLevel | None = None,
    tool_name: str = "governance_tool",
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_name=tool_name,
        action=action,
        asset_type=asset_type,
        data_domain=DataDomain.TRADE,
        sensitivity_level=sensitivity_level,
        risk_level=ToolRiskLevel.LOW,
    )


def test_policy_allow_metadata() -> None:
    engine = PolicyEngine()
    request = make_request(action="metadata.query", asset_type="metadata")

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.ALLOW
    assert result.reasons[0].rule_id == "default.allow_metadata_query"


def test_policy_deny_l3_detail() -> None:
    engine = PolicyEngine()
    request = make_request(
        action="data.detail.query",
        asset_type="table",
        sensitivity_level=SensitivityLevel.L3,
    )

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.DENY
    assert result.reasons[0].message == "L3 detail data query is denied."


def test_policy_deny_l5_secret() -> None:
    engine = PolicyEngine()
    request = make_request(
        action="metric.aggregate.query",
        asset_type="metric",
        sensitivity_level=SensitivityLevel.L5,
    )

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.DENY
    assert result.reasons[0].rule_id == "default.deny_l4_l5"


def test_policy_ask_create_quality_rule() -> None:
    engine = PolicyEngine()
    request = make_request(action="quality_rule.create", asset_type="quality_rule")

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.ASK
    assert result.requires_approval is True
    assert result.reasons[0].message == "Creating quality rules requires approval."


def test_policy_default_deny() -> None:
    engine = PolicyEngine()
    request = make_request(action="unknown.operation", asset_type="unknown")

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.DENY
    assert result.reasons[0].rule_id == "policy.default_deny"
    assert result.reasons[0].message


def test_policy_deny_overrides_allow() -> None:
    allow_delete = PolicyRule(
        rule_id="test.allow_delete",
        name="Unsafe allow delete",
        description="A deliberately unsafe allow rule for precedence testing.",
        effect=PolicyDecision.ALLOW,
        priority=1,
        match_operations=("data.delete",),
        reason="This unsafe allow must be overridden.",
    )
    deny_delete = PolicyRule(
        rule_id="test.deny_delete",
        name="Deny delete",
        description="Deletion must remain denied.",
        effect=PolicyDecision.DENY,
        priority=100,
        match_operations=("data.delete",),
        reason="Deletion is denied.",
    )
    engine = PolicyEngine(rules=(allow_delete, deny_delete))
    request = make_request(action="data.delete", asset_type="table")

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.DENY
    assert result.reasons[0].rule_id == "test.deny_delete"


def test_policy_g4_task_returns_ask() -> None:
    engine = PolicyEngine()
    request = ToolCallRequest(
        tool_name="governance_tool",
        action="permission.inspect",
        asset_type="permission",
        risk_level=ToolRiskLevel.LOW,
        task_level=GovernanceTaskLevel.G4,
    )

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.ASK
    assert result.requires_approval is True
    assert result.reasons[0].rule_id == "policy.g4_plan_required"


def test_policy_g5_task_is_denied() -> None:
    engine = PolicyEngine()
    request = ToolCallRequest(
        tool_name="governance_tool",
        action="permission.inspect",
        asset_type="permission",
        risk_level=ToolRiskLevel.HIGH,
        task_level=GovernanceTaskLevel.G5,
        requires_approval=True,
    )

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.DENY
    assert result.requires_approval is False
    assert result.reasons[0].rule_id == "policy.g5_denied"


def test_policy_denies_l5_model_context() -> None:
    engine = PolicyEngine()
    request = ToolCallRequest(
        tool_name="governance_tool",
        action="metric.aggregate.query",
        asset_type="metric",
        sensitivity_level=SensitivityLevel.L5,
        risk_level=ToolRiskLevel.LOW,
        allow_in_model_context=True,
    )

    result = engine.evaluate(request, make_user())

    assert result.decision == PolicyDecision.DENY
    assert result.reasons[0].rule_id == "policy.l4_l5_model_context_denied"


def test_policy_add_list_and_explain_decision() -> None:
    engine = PolicyEngine(rules=())
    rule = PolicyRule(
        rule_id="test.allow_custom_metadata",
        name="Allow custom metadata",
        description="Allow custom metadata operation.",
        effect=PolicyDecision.ALLOW,
        priority=50,
        match_operations=("custom.metadata.query",),
        reason="Custom metadata query is allowed.",
    )
    engine.add_rule(rule)
    request = make_request(action="custom.metadata.query", asset_type="metadata")

    result = engine.evaluate(request, make_user())
    explanation = engine.explain_decision()

    assert engine.list_rules()[0].rule_id == "test.allow_custom_metadata"
    assert result.decision == PolicyDecision.ALLOW
    assert explanation == result.reasons
