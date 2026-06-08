import pytest
from pydantic import ValidationError

from app.domain import (
    DataClassificationResult,
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyReason,
    SensitivityLevel,
    SensitivityTag,
)


def test_sensitivity_level_serializes_and_deserializes() -> None:
    tag = SensitivityTag(name="finance_sensitive", level=SensitivityLevel.L3)

    payload = tag.model_dump_json()
    restored = SensitivityTag.model_validate_json(payload)

    assert restored.level == SensitivityLevel.L3
    assert restored.name == "finance_sensitive"


def test_l4_classification_requires_approval() -> None:
    tag = SensitivityTag(name="credential_sensitive", level=SensitivityLevel.L4)

    with pytest.raises(ValidationError):
        DataClassificationResult(
            asset_id=tag.tag_id,
            sensitivity_level=SensitivityLevel.L4,
            tags=(tag,),
            confidence=0.92,
        )


def test_policy_decision_allow_ask_deny_values() -> None:
    assert PolicyDecision.ALLOW.value == "allow"
    assert PolicyDecision.ASK.value == "ask"
    assert PolicyDecision.DENY.value == "deny"


def test_policy_evaluation_round_trips() -> None:
    result = PolicyEvaluationResult(
        decision=PolicyDecision.ASK,
        reasons=(
            PolicyReason(
                code="approval_required",
                message="High risk action requires approval.",
                rule_id="policy.plan_mode_required",
            ),
        ),
        requires_approval=True,
    )

    restored = PolicyEvaluationResult.model_validate_json(result.model_dump_json())

    assert restored.decision == PolicyDecision.ASK
    assert restored.reasons[0].rule_id == "policy.plan_mode_required"

