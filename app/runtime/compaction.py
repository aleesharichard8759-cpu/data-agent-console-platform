from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from app.domain.tools import ToolCallResult

if TYPE_CHECKING:
    from app.agents import AgentResult
    from app.runtime.governance_engine import TaskRunResult


MAX_PREVIEW_ITEMS = 5


def compact_tool_result(result: ToolCallResult) -> dict[str, object]:
    """Compact a tool result into a safe summary without raw row payloads."""

    output = result.output
    data = output.get("data")
    compacted: dict[str, object] = {
        "tool_call_id": str(result.tool_call_id),
        "status": result.status.value,
        "allow_in_model_context": result.allow_in_model_context,
        "masked_fields": result.masked_fields,
        "evidence_refs": _evidence_refs_from_output(output),
        "policy_decision": output.get("policy_decision"),
        "approval_required": output.get("approval_required", False),
    }
    if "sql_gateway_decision" in output or "sql_gateway_reason" in output:
        compacted["sql_review"] = {
            "decision": output.get("sql_gateway_decision"),
            "reason": output.get("sql_gateway_reason"),
        }
    if isinstance(data, Mapping):
        compacted["data_summary"] = _compact_mapping(data)
    elif data is not None:
        compacted["data_summary"] = {"type": type(data).__name__}
    if result.error_message is not None:
        compacted["error_message"] = result.error_message
    return compacted


def compact_task_trace(task_result: TaskRunResult) -> dict[str, object]:
    """Compact a task run trace into structured evidence and decision summaries."""

    return {
        "task_id": str(task_result.task_id),
        "status": task_result.status.value,
        "steps": tuple(
            {
                "node": step.node.value,
                "status": step.status.value,
                "observation": step.observation,
                "audit_refs": step.audit_refs,
            }
            for step in task_result.steps
        ),
        "evidence_refs": _collect_evidence_refs(task_result.evidence, task_result.audit_refs),
        "evidence_count": len(task_result.evidence),
        "recommendation_count": len(task_result.recommendations),
        "recommendations": task_result.recommendations[:MAX_PREVIEW_ITEMS],
        "required_approvals": task_result.required_approvals,
        "audit_refs": task_result.audit_refs,
    }


def compact_agent_result(result: AgentResult) -> dict[str, object]:
    """Compact a specialized agent result while preserving veto and evidence refs."""

    return {
        "agent_name": result.agent_name,
        "task_id": result.task_id,
        "status": result.status,
        "finding_keys": tuple(sorted(result.findings)),
        "findings_summary": _compact_mapping(result.findings),
        "recommendations": result.recommendations[:MAX_PREVIEW_ITEMS],
        "tool_evidence_refs": tuple(
            ref
            for tool_result in result.tool_results
            for ref in _evidence_refs_from_output(tool_result.output)
        ),
        "veto": result.veto,
        "veto_reason": result.veto_reason,
    }


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    summary: dict[str, object] = {"keys": tuple(sorted(str(key) for key in value))}
    for key, item in value.items():
        key_text = str(key)
        if key_text in {"rows", "raw_rows", "records", "result_set"}:
            summary[key_text] = {
                "omitted": True,
                "count": len(item) if isinstance(item, list) else None,
            }
        elif isinstance(item, list):
            summary[key_text] = {
                "type": "list",
                "count": len(item),
                "preview": item[:MAX_PREVIEW_ITEMS]
                if _is_safe_preview_key(key_text)
                else "omitted",
            }
        elif isinstance(item, Mapping):
            summary[key_text] = _compact_mapping(item)
        else:
            summary[key_text] = item
    return summary


def _evidence_refs_from_output(output: Mapping[str, Any]) -> tuple[str, ...]:
    refs: list[str] = []
    audit_event_id = output.get("audit_event_id")
    if isinstance(audit_event_id, str):
        refs.append(f"audit:{audit_event_id}")
    evidence_ref = output.get("evidence_ref")
    if isinstance(evidence_ref, str):
        refs.append(evidence_ref)
    return tuple(refs)


def _collect_evidence_refs(
    evidence: tuple[dict[str, object], ...],
    audit_refs: tuple[str, ...],
) -> tuple[str, ...]:
    refs = [f"audit:{ref}" for ref in audit_refs]
    for item in evidence:
        ref = item.get("evidence_ref")
        if isinstance(ref, str):
            refs.append(ref)
    return tuple(refs)


def _is_safe_preview_key(key: str) -> bool:
    lowered = key.lower()
    return not any(token in lowered for token in ("row", "record", "phone", "email", "token"))
