from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.classification import SensitivityLevel
from app.domain.identity import UserContext
from app.domain.policy import PolicyDecision, PolicyEvaluationResult, PolicyReason
from app.domain.tasks import GovernanceTaskLevel
from app.domain.tools import ToolCallRequest
from app.policy.defaults import default_policy_rules
from app.policy.rules import PolicyRule

if TYPE_CHECKING:
    from app.domain.tasks import GovernanceTask
    from app.tools.context import AuditLogger


class PolicyEngine:
    """Runtime policy engine for Allow / Ask / Deny tool-call decisions."""

    def __init__(self, rules: tuple[PolicyRule, ...] | None = None) -> None:
        self._rules: list[PolicyRule] = list(default_policy_rules() if rules is None else rules)
        self._last_result: PolicyEvaluationResult | None = None

    def evaluate(
        self,
        request: ToolCallRequest,
        user: UserContext,
        audit_logger: AuditLogger | None = None,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
    ) -> PolicyEvaluationResult:
        try:
            hard_boundary = self._evaluate_hard_boundaries(request)
            if hard_boundary is not None:
                self._last_result = hard_boundary
                self._audit_policy(
                    request, user, hard_boundary, audit_logger, task, session_id, agent_name
                )
                return hard_boundary

            matched_rules = [rule for rule in self._rules if self._matches(rule, request, user)]
            if not matched_rules:
                result = self._result(
                    decision=PolicyDecision.DENY,
                    rule_id="policy.default_deny",
                    code="default_deny",
                    message="No policy rule matched the tool call.",
                    requires_approval=False,
                )
                self._last_result = result
                self._audit_policy(
                    request, user, result, audit_logger, task, session_id, agent_name
                )
                return result

            rule = self._select_deciding_rule(matched_rules)
            result = self._result(
                decision=rule.effect,
                rule_id=rule.rule_id,
                code=rule.effect.value,
                message=rule.reason,
                requires_approval=rule.effect == PolicyDecision.ASK,
            )
            self._last_result = result
            self._audit_policy(request, user, result, audit_logger, task, session_id, agent_name)
            return result
        except Exception:
            result = self._result(
                decision=PolicyDecision.DENY,
                rule_id="policy.fail_closed",
                code="fail_closed",
                message="Policy evaluation failed closed.",
                requires_approval=False,
            )
            self._last_result = result
            self._audit_policy(request, user, result, audit_logger, task, session_id, agent_name)
            return result

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)

    def list_rules(self) -> tuple[PolicyRule, ...]:
        return tuple(sorted(self._rules, key=lambda rule: (rule.priority, rule.rule_id)))

    def explain_decision(
        self, result: PolicyEvaluationResult | None = None
    ) -> tuple[PolicyReason, ...]:
        decision = result or self._last_result
        if decision is None:
            return ()
        return decision.reasons

    def _evaluate_hard_boundaries(
        self, request: ToolCallRequest
    ) -> PolicyEvaluationResult | None:
        if request.task_level == GovernanceTaskLevel.G5:
            return self._result(
                decision=PolicyDecision.DENY,
                rule_id="policy.g5_denied",
                code="g5_denied",
                message="G5 governance tasks are denied by runtime hard boundary.",
                requires_approval=False,
            )
        if request.task_level == GovernanceTaskLevel.G4:
            return self._result(
                decision=PolicyDecision.ASK,
                rule_id="policy.g4_plan_required",
                code="plan_required",
                message="G4 governance tasks cannot execute automatically.",
                requires_approval=True,
            )
        if (
            request.sensitivity_level in {SensitivityLevel.L4, SensitivityLevel.L5}
            and request.allow_in_model_context
        ):
            return self._result(
                decision=PolicyDecision.DENY,
                rule_id="policy.l4_l5_model_context_denied",
                code="model_context_denied",
                message="L4/L5 data can never enter model context.",
                requires_approval=False,
            )
        return None

    def _matches(self, rule: PolicyRule, request: ToolCallRequest, user: UserContext) -> bool:
        return (
            self._matches_value(rule.match_tool_names, request.tool_name)
            and self._matches_value(rule.match_operations, request.action)
            and self._matches_value(rule.match_asset_types, request.asset_type)
            and self._matches_value(rule.match_sensitivity_levels, request.sensitivity_level)
            and self._matches_any(rule.match_roles, user.roles)
        )

    @staticmethod
    def _matches_value(allowed: tuple[object, ...], value: object | None) -> bool:
        if not allowed:
            return True
        if value is None:
            return False
        return value in allowed

    @staticmethod
    def _matches_any(allowed: tuple[object, ...], values: tuple[object, ...]) -> bool:
        if not allowed:
            return True
        return any(value in allowed for value in values)

    @staticmethod
    def _audit_policy(
        request: ToolCallRequest,
        user: UserContext,
        result: PolicyEvaluationResult,
        audit_logger: AuditLogger | None,
        task: GovernanceTask | None,
        session_id: str | None,
        agent_name: str | None,
    ) -> None:
        if audit_logger is None:
            return
        audit_logger.record_policy_evaluation(
            request,
            user,
            result,
            task=task,
            session_id=session_id,
            agent_name=agent_name,
        )

    @staticmethod
    def _select_deciding_rule(rules: list[PolicyRule]) -> PolicyRule:
        effect_rank = {
            PolicyDecision.DENY: 0,
            PolicyDecision.ASK: 1,
            PolicyDecision.ALLOW: 2,
        }
        return sorted(rules, key=lambda rule: (effect_rank[rule.effect], rule.priority))[0]

    @staticmethod
    def _result(
        decision: PolicyDecision,
        rule_id: str,
        code: str,
        message: str,
        requires_approval: bool,
    ) -> PolicyEvaluationResult:
        return PolicyEvaluationResult(
            decision=decision,
            reasons=(PolicyReason(code=code, message=message, rule_id=rule_id),),
            requires_approval=requires_approval,
        )
