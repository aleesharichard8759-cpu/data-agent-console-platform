import json
from datetime import timedelta

import pytest

from app.audit import (
    AuditIntegrityError,
    AuditRetentionPolicy,
    AuditWriteError,
    ImmutableFileAuditLogger,
    InMemoryAuditLogger,
)
from app.domain import (
    AuditActor,
    AuditEvent,
    AuditEventFilter,
    AuditEventType,
    AuditTarget,
    DataDomain,
    GovernanceTask,
    GovernanceTaskLevel,
    GovernanceTaskType,
    PolicyDecision,
    ToolCallRequest,
    ToolRiskLevel,
    UserContext,
    UserRole,
)
from app.domain.common import utc_now
from app.policy import PolicyEngine, PolicyRule
from app.security import SQLGateway
from app.tools import DataToolRegistry, SearchMetadataTool, ToolExecutionContext


def make_user() -> UserContext:
    return UserContext(
        user_id="audit_user",
        display_name="Audit User",
        roles=(UserRole.DATA_STEWARD,),
    )


def make_task() -> GovernanceTask:
    return GovernanceTask(
        title="订单域数据质量治理",
        task_type=GovernanceTaskType.DATA_QUALITY,
        task_level=GovernanceTaskLevel.G2,
        domain=DataDomain.TRADE,
        objective="Generate governed quality controls for the order domain.",
        created_by="audit_user",
    )


def make_allow_policy() -> PolicyEngine:
    return PolicyEngine(
        rules=(
            PolicyRule(
                rule_id="test.allow_metadata",
                name="Allow metadata",
                description="Allow metadata tests.",
                effect=PolicyDecision.ALLOW,
                priority=1,
                match_operations=("metadata.query",),
                reason="Metadata query is allowed.",
            ),
        )
    )


def make_deny_policy() -> PolicyEngine:
    return PolicyEngine(
        rules=(
            PolicyRule(
                rule_id="test.deny_metadata",
                name="Deny metadata",
                description="Deny metadata tests.",
                effect=PolicyDecision.DENY,
                priority=1,
                match_operations=("metadata.query",),
                reason="Metadata query is denied for audit test.",
            ),
        )
    )


def make_metadata_request() -> ToolCallRequest:
    return ToolCallRequest(
        tool_name="search_metadata",
        action="metadata.query",
        asset_type="metadata",
        parameters={"query": "order", "limit": 5},
        risk_level=ToolRiskLevel.LOW,
    )


def make_context(
    audit_logger: InMemoryAuditLogger,
    policy_engine: PolicyEngine,
    task: GovernanceTask | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        user_context=make_user(),
        task_context=task,
        policy_engine=policy_engine,
        audit_logger=audit_logger,
        session_id="audit_session",
        agent_name="audit_agent",
    )


def make_direct_audit_event(**overrides) -> AuditEvent:
    payload = {
        "event_type": AuditEventType.TOOL_EXECUTED,
        "actor": AuditActor(actor_id="audit_user", actor_type="user"),
        "target": AuditTarget(target_id="tool_call", target_type="tool_call"),
        "user_id": "audit_user",
        "action": "tool.execute",
        "outcome": "succeeded",
        "metadata": {"summary": "safe audit event"},
    }
    payload.update(overrides)
    return AuditEvent(**payload)


def test_tool_call_produces_audit_events() -> None:
    audit_logger = InMemoryAuditLogger()
    registry = DataToolRegistry()
    registry.register(SearchMetadataTool())

    result = registry.execute_tool(
        make_metadata_request(),
        make_context(audit_logger, make_allow_policy(), make_task()),
    )

    event_types = [event.event_type for event in audit_logger.list_events()]
    assert result.output["audit_event_id"]
    assert AuditEventType.TOOL_REQUESTED in event_types
    assert AuditEventType.POLICY_EVALUATED in event_types
    assert AuditEventType.ERROR_RAISED in event_types


def test_deny_produces_permission_denied_event() -> None:
    audit_logger = InMemoryAuditLogger()
    registry = DataToolRegistry()
    registry.register(SearchMetadataTool())

    registry.execute_tool(make_metadata_request(), make_context(audit_logger, make_deny_policy()))

    denied_events = audit_logger.list_events(
        AuditEventFilter(event_type=AuditEventType.PERMISSION_DENIED)
    )
    assert denied_events
    assert denied_events[0].policy_decision == PolicyDecision.DENY
    assert denied_events[0].reason == "Metadata query is denied for audit test."


def test_sql_review_produces_sql_reviewed_event() -> None:
    audit_logger = InMemoryAuditLogger()
    gateway = SQLGateway()

    review = gateway.review_sql(
        "select order_count from ads_order_summary",
        make_user(),
        audit_logger=audit_logger,
        session_id="audit_session",
        agent_name="audit_agent",
        tool_name="query_sql",
    )

    events = audit_logger.list_events({"event_type": AuditEventType.SQL_REVIEWED})
    assert review.decision == PolicyDecision.ALLOW
    assert len(events) == 1
    assert events[0].request_hash
    assert "select order_count" not in (events[0].request_summary or "")


def test_audit_log_does_not_store_sensitive_raw_payload_by_default() -> None:
    audit_logger = InMemoryAuditLogger()
    gateway = SQLGateway()
    raw_sql = "select customer_phone from dwd_order_detail limit 1"
    sensitive_value = "synthetic_sensitive_phone_value"

    gateway.review_sql(
        raw_sql,
        make_user(),
        audit_logger=audit_logger,
        metadata={"customer_phone": sensitive_value, "rows": [{"customer_phone": sensitive_value}]},
    )

    event_dump = audit_logger.list_events()[0].model_dump_json()
    assert raw_sql not in event_dump
    assert sensitive_value not in event_dump
    assert '"raw_payload_allowed":false' in event_dump
    assert "sha256" in event_dump


def test_audit_logger_forces_raw_payload_disabled_and_hashes_sensitive_values() -> None:
    audit_logger = InMemoryAuditLogger()
    event = AuditEvent(
        event_type=AuditEventType.TOOL_EXECUTED,
        actor=AuditActor(actor_id="audit_user", actor_type="user"),
        target=AuditTarget(target_id="tool_call", target_type="tool_call"),
        user_id="audit_user",
        action="tool.execute",
        outcome="succeeded",
        raw_payload_allowed=True,
        metadata={
            "note": "api_key=synthetic-secret-value",
            "safe": "order domain summary",
        },
    )

    stored = audit_logger.log_event(event)
    event_dump = stored.model_dump_json()

    assert stored.raw_payload_allowed is False
    assert "synthetic-secret-value" not in event_dump
    assert "sha256" in event_dump


def test_list_events_can_filter_by_task_id() -> None:
    audit_logger = InMemoryAuditLogger()
    task = make_task()
    registry = DataToolRegistry()
    registry.register(SearchMetadataTool())

    registry.execute_tool(
        make_metadata_request(),
        make_context(audit_logger, make_allow_policy(), task),
    )

    task_events = audit_logger.list_events({"task_id": str(task.task_id)})
    assert task_events
    assert {event.task_id for event in task_events} == {str(task.task_id)}


def test_immutable_file_audit_logger_persists_and_verifies_hash_chain(tmp_path) -> None:
    ledger_path = tmp_path / "audit-ledger.jsonl"
    audit_logger = ImmutableFileAuditLogger(ledger_path)
    event = make_direct_audit_event(metadata={"note": "safe metadata summary"})

    stored = audit_logger.log_event(event)
    reloaded = ImmutableFileAuditLogger(ledger_path)

    assert ledger_path.exists()
    assert reloaded.verify_integrity() is True
    assert reloaded.get_event(stored.event_id) is not None
    assert reloaded.get_event(stored.event_id).raw_payload_allowed is False


def test_immutable_file_audit_logger_detects_tampering(tmp_path) -> None:
    ledger_path = tmp_path / "audit-ledger.jsonl"
    audit_logger = ImmutableFileAuditLogger(ledger_path)
    audit_logger.log_event(make_direct_audit_event())
    record = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
    record["event"]["outcome"] = "tampered"
    ledger_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(AuditIntegrityError, match="record_hash"):
        ImmutableFileAuditLogger(ledger_path)


def test_immutable_file_audit_logger_write_failure_fails_closed(tmp_path) -> None:
    ledger_path = tmp_path / "audit-ledger-directory"
    ledger_path.mkdir()

    with pytest.raises(AuditWriteError):
        ImmutableFileAuditLogger(ledger_path)


def test_immutable_file_audit_logger_applies_retention_policy(tmp_path) -> None:
    ledger_path = tmp_path / "audit-ledger.jsonl"
    audit_logger = ImmutableFileAuditLogger(
        ledger_path,
        retention_policy=AuditRetentionPolicy(retention_days=1),
    )
    expired_event = make_direct_audit_event(
        timestamp=utc_now() - timedelta(days=2),
        occurred_at=utc_now() - timedelta(days=2),
    )
    active_event = make_direct_audit_event()

    audit_logger.log_event(expired_event)
    audit_logger.log_event(active_event)

    assert audit_logger.verify_integrity() is True
    assert audit_logger.retained_event_count() == 1
    assert audit_logger.expired_event_count() == 1
    assert audit_logger.get_event(active_event.event_id) is not None
    assert audit_logger.get_event(expired_event.event_id) is None
