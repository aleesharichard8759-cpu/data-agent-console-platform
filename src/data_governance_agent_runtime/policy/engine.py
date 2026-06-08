from __future__ import annotations

from collections.abc import Callable

from data_governance_agent_runtime.core.enums import ActionRisk, Decision, Environment
from data_governance_agent_runtime.core.models import PolicyDecision, RuntimeContext, ToolRequest

PolicyRule = Callable[[RuntimeContext, ToolRequest], PolicyDecision | None]


class PolicyEngine:
    """Allow / Ask / Deny policy engine. Exceptions fail closed."""

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self._rules = rules or [
            deny_production_environment,
            require_sql_gateway_for_sql_actions,
            ask_for_high_risk_actions,
            allow_mock_governance_actions,
        ]

    def evaluate(self, context: RuntimeContext, request: ToolRequest) -> PolicyDecision:
        try:
            for rule in self._rules:
                decision = rule(context, request)
                if decision is not None:
                    return decision
            return PolicyDecision(
                decision=Decision.DENY,
                reason="No policy rule allowed this request.",
                rule_id="policy.default_deny",
            )
        except Exception:
            return PolicyDecision(
                decision=Decision.DENY,
                reason="Policy evaluation failed closed.",
                rule_id="policy.fail_closed",
            )


def deny_production_environment(
    context: RuntimeContext, request: ToolRequest
) -> PolicyDecision | None:
    if context.environment == Environment.PRODUCTION:
        return PolicyDecision(
            decision=Decision.DENY,
            reason="Agents cannot execute against production environments.",
            rule_id="policy.no_production_agent_execution",
        )
    return None


def require_sql_gateway_for_sql_actions(
    context: RuntimeContext, request: ToolRequest
) -> PolicyDecision | None:
    del context
    if request.action.startswith("sql.") and not request.requires_sql_gateway:
        return PolicyDecision(
            decision=Decision.DENY,
            reason="SQL actions must be routed through SQL Gateway.",
            rule_id="policy.sql_gateway_required",
        )
    return None


def ask_for_high_risk_actions(
    context: RuntimeContext, request: ToolRequest
) -> PolicyDecision | None:
    high_risk = request.requires_approval or request.risk in {ActionRisk.HIGH, ActionRisk.CRITICAL}
    if high_risk and context.approved_plan_id is None:
        return PolicyDecision(
            decision=Decision.ASK,
            reason="High-risk governance action requires plan approval.",
            rule_id="policy.plan_mode_required",
        )
    return None


def allow_mock_governance_actions(
    context: RuntimeContext, request: ToolRequest
) -> PolicyDecision | None:
    del request
    if context.environment in {Environment.MOCK, Environment.DEVELOPMENT, Environment.STAGING}:
        return PolicyDecision(
            decision=Decision.ALLOW,
            reason="Request allowed for non-production governed mock execution.",
            rule_id="policy.mock_runtime_allow",
        )
    return None
