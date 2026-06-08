from datetime import timedelta

import pytest

from app.agents import AgentResult
from app.domain import SensitivityLevel, ToolCallResult, ToolExecutionStatus
from app.domain.common import new_id, utc_now
from app.memory import GovernanceMemory, MemorySafetyError, MemoryStore, MemoryType
from app.runtime import (
    GovernanceStep,
    GovernanceStepNode,
    GovernanceStepStatus,
    TaskRunResult,
    TaskRunStatus,
    compact_agent_result,
    compact_task_trace,
    compact_tool_result,
)


def make_memory(
    *,
    memory_type: MemoryType = MemoryType.METRIC,
    sensitivity_level: SensitivityLevel = SensitivityLevel.L2,
    title: str = "订单数指标口径",
    content_summary: str = "订单数按订单创建日期统计，排除取消订单。",
) -> GovernanceMemory:
    return GovernanceMemory(
        memory_type=memory_type,
        title=title,
        content_summary=content_summary,
        source_refs=("metric:order_count",),
        sensitivity_level=sensitivity_level,
        allow_retrieval=True,
        last_verified_at=utc_now(),
    )


def test_l3_detail_cannot_be_written_to_memory() -> None:
    store = MemoryStore()

    with pytest.raises(MemorySafetyError, match="L3"):
        store.add_memory(
            make_memory(
                sensitivity_level=SensitivityLevel.L3,
                content_summary="L3 detail summary should not be persisted.",
            )
        )


def test_l5_content_is_rejected() -> None:
    store = MemoryStore()

    with pytest.raises(MemorySafetyError, match="L3/L4/L5"):
        store.add_memory(
            make_memory(
                sensitivity_level=SensitivityLevel.L5,
                content_summary="L5 governance content is not memory eligible.",
            )
        )


def test_metric_definition_can_be_written_to_memory() -> None:
    store = MemoryStore()
    memory = make_memory()

    stored = store.add_memory(memory)
    results = store.search_memory("订单数")

    assert stored.memory_id == memory.memory_id
    assert results == (memory,)


def test_memory_retrieval_checks_expiration() -> None:
    store = MemoryStore()
    expired = make_memory(
        title="过期指标口径",
        content_summary="This safe summary is expired.",
    ).model_copy(update={"expires_at": utc_now() - timedelta(days=1)})
    store.add_memory(expired)

    assert store.verify_memory_freshness(expired.memory_id) is False
    assert store.search_memory("过期指标") == tuple()


def test_memory_rejects_sensitive_identifier_tokens() -> None:
    store = MemoryStore()

    with pytest.raises(MemorySafetyError, match="sensitive"):
        store.add_memory(
            make_memory(
                title="地址字段规则",
                content_summary="recipient_address field raw value must not be stored.",
            )
        )


def test_memory_allows_address_field_policy_summary_without_values() -> None:
    store = MemoryStore()
    memory = make_memory(
        memory_type=MemoryType.GOVERNANCE,
        title="shipping_address 字段脱敏策略",
        content_summary="shipping_address 是 L3 字段，仅保存字段名、等级和脱敏策略摘要。",
    )

    stored = store.add_memory(memory)

    assert stored.memory_id == memory.memory_id
    assert store.search_memory("shipping_address") == (memory,)


def test_memory_rejects_address_assignment_values() -> None:
    store = MemoryStore()

    with pytest.raises(MemorySafetyError, match="sensitive"):
        store.add_memory(
            make_memory(
                title="Unsafe address memory",
                content_summary="shipping_address=synthetic-address-value",
            )
        )


def test_large_tool_result_is_compacted_without_rows() -> None:
    result = ToolCallResult(
        tool_call_id=new_id(),
        status=ToolExecutionStatus.SUCCEEDED,
        output={
            "audit_event_id": "audit_001",
            "policy_decision": "allow",
            "data": {
                "columns": ["metric_date", "order_count"],
                "rows": [
                    {"metric_date": f"day_{index}", "order_count": index}
                    for index in range(20)
                ],
                "review_reason": "SQL passed gateway review.",
            },
            "sql_gateway_decision": "allow",
            "sql_gateway_reason": "SQL passed gateway review.",
        },
        allow_in_model_context=True,
    )

    compacted = compact_tool_result(result)

    assert compacted["evidence_refs"] == ("audit:audit_001",)
    assert compacted["sql_review"] == {
        "decision": "allow",
        "reason": "SQL passed gateway review.",
    }
    assert compacted["data_summary"]["rows"] == {"omitted": True, "count": 20}
    assert "day_19" not in str(compacted)


def test_compacted_tool_result_preserves_evidence_ref() -> None:
    result = ToolCallResult(
        tool_call_id=new_id(),
        status=ToolExecutionStatus.SUCCEEDED,
        output={"audit_event_id": "audit_002", "evidence_ref": "catalog:asset:order"},
    )

    compacted = compact_tool_result(result)

    assert "audit:audit_002" in compacted["evidence_refs"]
    assert "catalog:asset:order" in compacted["evidence_refs"]


def test_task_trace_compacts_to_structured_summary() -> None:
    task_id = new_id()
    task_result = TaskRunResult(
        task_id=task_id,
        status=TaskRunStatus.COMPLETED,
        steps=(
            GovernanceStep(
                task_id=task_id,
                node=GovernanceStepNode.EVIDENCE_COLLECTION,
                status=GovernanceStepStatus.SUCCEEDED,
                observation="Collected safe evidence.",
                audit_refs=("audit_003",),
            ),
        ),
        evidence=({"evidence_ref": "catalog:metric:order_count"},),
        recommendations=("Confirm metric owner.",),
        required_approvals=({"reason": "approval placeholder"},),
        audit_refs=("audit_003", "audit_004"),
    )

    compacted = compact_task_trace(task_result)

    assert compacted["task_id"] == str(task_id)
    assert compacted["steps"][0]["node"] == "evidence_collection"
    assert "catalog:metric:order_count" in compacted["evidence_refs"]
    assert "audit:audit_003" in compacted["evidence_refs"]
    assert compacted["required_approvals"] == ({"reason": "approval placeholder"},)


def test_agent_result_compaction_keeps_veto_and_tool_refs() -> None:
    tool_result = ToolCallResult(
        tool_call_id=new_id(),
        status=ToolExecutionStatus.SUCCEEDED,
        output={"audit_event_id": "audit_005"},
    )
    agent_result = AgentResult(
        agent_name="security_agent",
        task_id=str(new_id()),
        status="vetoed",
        findings={
            "sensitive_fields": [{"field": "contact_hash", "level": "L4"}],
            "allow_in_model_context": False,
        },
        recommendations=("Exclude L4 fields from model context.",),
        tool_results=(tool_result,),
        veto=True,
        veto_reason="L4 fields were detected.",
    )

    compacted = compact_agent_result(agent_result)

    assert compacted["veto"] is True
    assert compacted["veto_reason"] == "L4 fields were detected."
    assert compacted["tool_evidence_refs"] == ("audit:audit_005",)
