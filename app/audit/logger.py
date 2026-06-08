from __future__ import annotations

import hashlib
import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import Field, ValidationError

from app.core.errors import UnsafeOperationError
from app.domain.audit import (
    AuditActor,
    AuditEvent,
    AuditEventFilter,
    AuditEventType,
    AuditTarget,
)
from app.domain.common import DomainModel, utc_now
from app.domain.identity import UserContext
from app.domain.policy import PolicyDecision, PolicyEvaluationResult
from app.domain.tasks import GovernanceTask
from app.domain.tools import ToolCallRequest, ToolExecutionStatus

SENSITIVE_METADATA_KEYS = (
    "address",
    "customer_phone",
    "email",
    "id_card",
    "password",
    "phone",
    "raw",
    "rows",
    "secret",
    "sql",
    "statement",
    "token",
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b"),
    re.compile(r"\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:\+?\d[\d\-\s()]{6,}\d)\b"),
)
AUDIT_CHAIN_GENESIS_HASH = "0" * 64


class AuditLogger(ABC):
    """Append-only audit logger abstraction."""

    @abstractmethod
    def log_event(self, event: AuditEvent) -> AuditEvent:
        """Persist one audit event and return the stored event."""

    @abstractmethod
    def list_events(
        self,
        event_filter: AuditEventFilter | Mapping[str, object] | None = None,
    ) -> tuple[AuditEvent, ...]:
        """List audit events, optionally filtered by safe indexed fields."""

    @abstractmethod
    def get_event(self, event_id: UUID | str) -> AuditEvent | None:
        """Get one audit event by id."""


class AuditWriteError(UnsafeOperationError):
    """Raised when audit persistence fails closed."""


class AuditIntegrityError(UnsafeOperationError):
    """Raised when append-only audit records fail hash-chain verification."""


class AuditRetentionPolicy(DomainModel):
    retention_days: int | None = Field(
        default=None,
        ge=1,
        description="Days to keep events in active query results; None keeps all events active.",
    )
    keep_expired_in_ledger: bool = Field(
        default=True,
        description="Expired events remain in the immutable ledger for external archival.",
    )


class InMemoryAuditLogger(AuditLogger):
    """In-memory audit logger for MVP runtime execution and tests."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def log_event(self, event: AuditEvent) -> AuditEvent:
        stored_event = self._sanitize_event(event)
        self._events.append(stored_event)
        return stored_event

    def list_events(
        self,
        event_filter: AuditEventFilter | Mapping[str, object] | None = None,
    ) -> tuple[AuditEvent, ...]:
        normalized_filter = self._normalize_filter(event_filter)
        if normalized_filter is None:
            return tuple(self._events)
        return tuple(
            event for event in self._events if self._matches_filter(event, normalized_filter)
        )

    def get_event(self, event_id: UUID | str) -> AuditEvent | None:
        event_id_text = str(event_id)
        for event in self._events:
            if str(event.event_id) == event_id_text:
                return event
        return None

    def record_tool_requested(
        self,
        request: ToolCallRequest,
        user: UserContext,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return self.log_event(
            self._build_event(
                event_type=AuditEventType.TOOL_REQUESTED,
                request=request,
                user=user,
                action=request.action,
                outcome="requested",
                task=task,
                session_id=session_id,
                agent_name=agent_name,
                request_payload=request.parameters,
                request_summary=self._tool_request_summary(request),
                metadata=metadata,
            )
        )

    def record_policy_evaluation(
        self,
        request: ToolCallRequest,
        user: UserContext,
        policy_result: PolicyEvaluationResult,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return self.log_event(
            self._build_event(
                event_type=AuditEventType.POLICY_EVALUATED,
                request=request,
                user=user,
                action="policy.evaluate",
                outcome=policy_result.decision.value,
                task=task,
                session_id=session_id,
                agent_name=agent_name,
                policy_result=policy_result,
                request_payload=request.parameters,
                request_summary=self._tool_request_summary(request),
                metadata=metadata,
            )
        )

    def record_sql_review(
        self,
        *,
        sql: str,
        user: UserContext,
        decision: PolicyDecision,
        reason: str,
        risks: tuple[object, ...],
        request: ToolCallRequest | None = None,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        risk_types = tuple(getattr(risk, "risk_type", risk) for risk in risks)
        risk_values = tuple(getattr(risk_type, "value", str(risk_type)) for risk_type in risk_types)
        event = self._build_event(
            event_type=AuditEventType.SQL_REVIEWED,
            request=request,
            user=user,
            action="sql.review",
            outcome=decision.value,
            task=task,
            session_id=session_id,
            agent_name=agent_name,
            policy_decision=decision,
            reason=reason,
            request_payload={"sql": sql},
            request_summary=f"sql_hash={self._hash_payload(sql)} length={len(sql)}",
            result_summary=f"decision={decision.value} risks={','.join(risk_values) or 'none'}",
            metadata={"risk_types": risk_values, "tool_name": tool_name, **(metadata or {})},
        )
        return self.log_event(event)

    def record_result_masked(
        self,
        request: ToolCallRequest,
        user: UserContext,
        masked_fields: tuple[str, ...],
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return self.log_event(
            self._build_event(
                event_type=AuditEventType.RESULT_MASKED,
                request=request,
                user=user,
                action="dlp.mask",
                outcome="masked",
                task=task,
                session_id=session_id,
                agent_name=agent_name,
                result_payload={"masked_fields": masked_fields},
                result_summary=f"masked_fields={len(masked_fields)}",
                metadata={"masked_fields": masked_fields, **(metadata or {})},
            )
        )

    def record_tool_event(
        self,
        request: ToolCallRequest,
        user: UserContext,
        status: ToolExecutionStatus,
        policy_result: PolicyEvaluationResult | None,
        metadata: dict[str, Any] | None = None,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
    ) -> AuditEvent:
        return self.log_event(
            self._build_event(
                event_type=self._event_type_for_status(status),
                request=request,
                user=user,
                action=request.action,
                outcome=status.value,
                task=task,
                session_id=session_id,
                agent_name=agent_name,
                policy_result=policy_result,
                request_payload=request.parameters,
                request_summary=self._tool_request_summary(request),
                result_summary=f"tool_status={status.value}",
                metadata=metadata,
            )
        )

    def _build_event(
        self,
        *,
        event_type: AuditEventType,
        request: ToolCallRequest | None,
        user: UserContext,
        action: str,
        outcome: str,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        policy_result: PolicyEvaluationResult | None = None,
        policy_decision: PolicyDecision | None = None,
        reason: str | None = None,
        request_payload: object | None = None,
        result_payload: object | None = None,
        request_summary: str | None = None,
        result_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        resolved_reason = reason
        if resolved_reason is None and policy_result is not None and policy_result.reasons:
            resolved_reason = policy_result.reasons[0].message
        resolved_decision = policy_decision
        if resolved_decision is None and policy_result is not None:
            resolved_decision = policy_result.decision
        return AuditEvent(
            event_type=event_type,
            actor=self._actor_from_user(user),
            target=self._target_from_request(request),
            user_id=user.user_id,
            role=self._primary_role(user),
            session_id=session_id,
            task_id=str(task.task_id) if task is not None else None,
            agent_name=agent_name,
            tool_name=request.tool_name if request is not None else None,
            asset_refs=self._asset_refs_from_request(request),
            sensitivity_level=request.sensitivity_level if request is not None else None,
            policy_decision=resolved_decision,
            action=action,
            outcome=outcome,
            reason=resolved_reason,
            request_summary=request_summary,
            result_summary=result_summary,
            request_hash=(
                self._hash_payload(request_payload) if request_payload is not None else None
            ),
            result_hash=self._hash_payload(result_payload) if result_payload is not None else None,
            raw_payload_allowed=False,
            metadata=metadata or {},
        )

    @staticmethod
    def _actor_from_user(user: UserContext) -> AuditActor:
        return AuditActor(
            actor_id=user.user_id,
            actor_type="service" if user.is_service_account else "user",
            display_name=user.display_name,
            department=user.department.name if user.department else None,
        )

    @staticmethod
    def _target_from_request(request: ToolCallRequest | None) -> AuditTarget | None:
        if request is None:
            return None
        return AuditTarget(
            target_id=str(request.tool_call_id),
            target_type="tool_call",
            qualified_name=request.tool_name,
            sensitivity_level=request.sensitivity_level.value
            if request.sensitivity_level is not None
            else None,
        )

    @staticmethod
    def _primary_role(user: UserContext) -> str | None:
        if not user.roles:
            return None
        return user.roles[0].value

    @staticmethod
    def _asset_refs_from_request(request: ToolCallRequest | None) -> tuple[str, ...]:
        if request is None:
            return tuple()
        refs = [request.tool_name]
        if request.asset_type is not None:
            refs.append(f"asset_type:{request.asset_type}")
        if request.data_domain is not None:
            refs.append(f"domain:{request.data_domain.value}")
        return tuple(refs)

    @staticmethod
    def _tool_request_summary(request: ToolCallRequest) -> str:
        parameter_keys = ",".join(sorted(request.parameters)) or "none"
        asset_type = request.asset_type or "unknown"
        return (
            f"tool={request.tool_name} action={request.action} "
            f"asset_type={asset_type} parameter_keys={parameter_keys}"
        )

    @staticmethod
    def _event_type_for_status(status: ToolExecutionStatus) -> AuditEventType:
        if status == ToolExecutionStatus.DENIED:
            return AuditEventType.PERMISSION_DENIED
        if status == ToolExecutionStatus.ASKED:
            return AuditEventType.APPROVAL_REQUIRED
        if status == ToolExecutionStatus.SUCCEEDED:
            return AuditEventType.TOOL_EXECUTED
        if status == ToolExecutionStatus.MASKED:
            return AuditEventType.RESULT_MASKED
        if status == ToolExecutionStatus.FAILED:
            return AuditEventType.ERROR_RAISED
        return AuditEventType.TOOL_REQUESTED

    def _sanitize_event(self, event: AuditEvent) -> AuditEvent:
        return event.model_copy(
            update={
                "metadata": self._sanitize_metadata(event.metadata),
                "raw_payload_allowed": False,
                "allow_in_model_context": False,
            }
        )

    def _sanitize_metadata(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if self._is_sensitive_key(key_text):
                    sanitized[key_text] = {"redacted": True, "sha256": self._hash_payload(item)}
                else:
                    sanitized[key_text] = self._sanitize_metadata(item)
            return sanitized
        if isinstance(value, tuple):
            return tuple(self._sanitize_metadata(item) for item in value)
        if isinstance(value, list):
            return {
                "item_count": len(value),
                "sha256": self._hash_payload(value),
            }
        if isinstance(value, str) and self._contains_sensitive_value(value):
            return {"redacted": True, "sha256": self._hash_payload(value)}
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in SENSITIVE_METADATA_KEYS)

    @staticmethod
    def _contains_sensitive_value(value: str) -> bool:
        return any(pattern.search(value) is not None for pattern in SENSITIVE_VALUE_PATTERNS)

    @staticmethod
    def _hash_payload(payload: object) -> str:
        encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _normalize_filter(
        event_filter: AuditEventFilter | Mapping[str, object] | None,
    ) -> AuditEventFilter | None:
        if event_filter is None:
            return None
        if isinstance(event_filter, AuditEventFilter):
            return event_filter
        return AuditEventFilter.model_validate(event_filter)

    @staticmethod
    def _matches_filter(event: AuditEvent, event_filter: AuditEventFilter) -> bool:
        expected = event_filter.model_dump(exclude_none=True)
        return all(getattr(event, key) == value for key, value in expected.items())


class ImmutableFileAuditLogger(InMemoryAuditLogger):
    """Append-only JSONL audit logger with hash-chain integrity checks."""

    def __init__(
        self,
        ledger_path: str | Path,
        *,
        retention_policy: AuditRetentionPolicy | None = None,
    ) -> None:
        super().__init__()
        self._ledger_path = Path(ledger_path)
        self._retention_policy = retention_policy or AuditRetentionPolicy()
        self._last_record_hash = AUDIT_CHAIN_GENESIS_HASH
        self._load_ledger()

    @property
    def ledger_path(self) -> Path:
        return self._ledger_path

    @property
    def retention_policy(self) -> AuditRetentionPolicy:
        return self._retention_policy

    def log_event(self, event: AuditEvent) -> AuditEvent:
        stored_event = self._sanitize_event(event)
        record = self._build_record(stored_event)
        self._append_record(record)
        self._events.append(stored_event)
        self._last_record_hash = record["record_hash"]
        return stored_event

    def list_events(
        self,
        event_filter: AuditEventFilter | Mapping[str, object] | None = None,
    ) -> tuple[AuditEvent, ...]:
        self.verify_integrity()
        retained_events = tuple(event for event in self._events if self._within_retention(event))
        normalized_filter = self._normalize_filter(event_filter)
        if normalized_filter is None:
            return retained_events
        return tuple(
            event for event in retained_events if self._matches_filter(event, normalized_filter)
        )

    def get_event(self, event_id: UUID | str) -> AuditEvent | None:
        event_id_text = str(event_id)
        for event in self.list_events():
            if str(event.event_id) == event_id_text:
                return event
        return None

    def verify_integrity(self) -> bool:
        previous_hash = AUDIT_CHAIN_GENESIS_HASH
        for line_number, record in self._iter_records():
            expected_hash = self._record_hash(record["event"], previous_hash)
            if record.get("previous_hash") != previous_hash:
                raise AuditIntegrityError(
                    f"Audit ledger chain break at line {line_number}: previous_hash mismatch."
                )
            if record.get("record_hash") != expected_hash:
                raise AuditIntegrityError(
                    f"Audit ledger chain break at line {line_number}: record_hash mismatch."
                )
            previous_hash = expected_hash
        return True

    def retained_event_count(self) -> int:
        return len(self.list_events())

    def expired_event_count(self) -> int:
        return sum(1 for event in self._events if not self._within_retention(event))

    def _load_ledger(self) -> None:
        if not self._ledger_path.exists():
            return
        previous_hash = AUDIT_CHAIN_GENESIS_HASH
        loaded_events: list[AuditEvent] = []
        for line_number, record in self._iter_records():
            expected_hash = self._record_hash(record["event"], previous_hash)
            if record.get("previous_hash") != previous_hash:
                raise AuditIntegrityError(
                    f"Audit ledger chain break at line {line_number}: previous_hash mismatch."
                )
            if record.get("record_hash") != expected_hash:
                raise AuditIntegrityError(
                    f"Audit ledger chain break at line {line_number}: record_hash mismatch."
                )
            try:
                loaded_events.append(AuditEvent.model_validate(record["event"]))
            except ValidationError as exc:
                raise AuditIntegrityError(
                    f"Audit ledger contains invalid event at line {line_number}."
                ) from exc
            previous_hash = expected_hash
        self._events = loaded_events
        self._last_record_hash = previous_hash

    def _build_record(self, event: AuditEvent) -> dict[str, Any]:
        event_payload = event.model_dump(mode="json")
        return {
            "record_version": 1,
            "previous_hash": self._last_record_hash,
            "record_hash": self._record_hash(event_payload, self._last_record_hash),
            "event": event_payload,
        }

    def _append_record(self, record: Mapping[str, Any]) -> None:
        try:
            self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self._ledger_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
        except OSError as exc:
            raise AuditWriteError("Audit ledger write failed closed.") from exc

    def _iter_records(self):
        try:
            with self._ledger_path.open("r", encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        raise AuditIntegrityError(
                            f"Audit ledger contains invalid JSON at line {line_number}."
                        ) from exc
                    if not isinstance(record, dict) or not isinstance(record.get("event"), dict):
                        raise AuditIntegrityError(
                            f"Audit ledger contains invalid record at line {line_number}."
                        )
                    yield line_number, record
        except FileNotFoundError:
            return
        except OSError as exc:
            raise AuditWriteError("Audit ledger read failed closed.") from exc

    def _within_retention(self, event: AuditEvent) -> bool:
        if self._retention_policy.retention_days is None:
            return True
        cutoff = utc_now() - timedelta(days=self._retention_policy.retention_days)
        event_time = event.timestamp
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=cutoff.tzinfo)
        return event_time >= cutoff

    @staticmethod
    def _record_hash(event_payload: Mapping[str, Any], previous_hash: str) -> str:
        payload = {
            "event": event_payload,
            "previous_hash": previous_hash,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
