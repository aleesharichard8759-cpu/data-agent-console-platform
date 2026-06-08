from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import Field

from app.core.errors import RuntimeErrorBase
from app.domain.audit import AuditActor, AuditEvent, AuditEventType, AuditTarget
from app.domain.common import DomainModel
from app.domain.identity import UserContext
from app.tools.context import AuditLogger


class ConnectorKind(StrEnum):
    METADATA = "metadata"
    WAREHOUSE = "warehouse"
    QUALITY = "quality"
    METRIC = "metric"
    LINEAGE = "lineage"
    PERMISSION = "permission"
    MASKING = "masking"
    WORKFLOW = "workflow"
    SCHEDULER = "scheduler"


class ConnectorConfig(DomainModel):
    name: str = Field(description="Connector instance name.")
    connector_kind: ConnectorKind = Field(description="Connector category.")
    timeout_seconds: float = Field(
        default=5.0,
        ge=0.0,
        description="Connector operation timeout budget in seconds.",
    )
    enabled: bool = Field(
        default=False,
        description="Whether connector calls are enabled. Real connectors default to false.",
    )
    is_mock: bool = Field(
        default=True,
        description="Whether this connector is a mock implementation.",
    )


@dataclass(frozen=True)
class ConnectorCallContext:
    user_context: UserContext
    audit_logger: AuditLogger
    session_id: str | None = None
    task_id: str | None = None
    agent_name: str | None = "connector"


class ConnectorError(RuntimeErrorBase):
    """Base class for safe connector errors."""


class ConnectorTimeoutError(ConnectorError):
    """Raised when a connector timeout budget is invalid or exceeded."""


class ConnectorUnavailableError(ConnectorError):
    """Raised when a real connector is not configured or not enabled."""


class ConnectorSecurityError(ConnectorError):
    """Raised when a connector request violates a safety boundary."""


T = TypeVar("T")

SENSITIVE_KEY_TOKENS = (
    "address",
    "api_key",
    "customer_email",
    "customer_phone",
    "email",
    "password",
    "phone",
    "secret",
    "shipping_address",
    "token",
)


class BaseConnector:
    """Shared connector safety wrapper. Real network calls are intentionally absent."""

    config: ConnectorConfig

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def timeout_seconds(self) -> float:
        return self.config.timeout_seconds

    def security_notes(self) -> tuple[str, ...]:
        return (
            "Connector implementations must not read production credentials by default.",
            "Connector calls must use explicit timeout_seconds and audit every operation.",
            "Connector outputs must not include plaintext sensitive values or raw result sets.",
        )

    def _run_operation(
        self,
        context: ConnectorCallContext,
        operation: str,
        request_payload: Mapping[str, Any],
        handler: Callable[[], T],
    ) -> T:
        try:
            self._assert_callable()
            result = handler()
            safe_result = self._sanitize(result)
            audit_event = self._log_call(
                context=context,
                event_type=AuditEventType.CONNECTOR_CALLED,
                operation=operation,
                outcome="succeeded",
                request_payload=request_payload,
                result_payload=safe_result,
                reason="Connector mock operation completed.",
            )
            if isinstance(safe_result, dict):
                safe_result.setdefault("audit_event_id", str(audit_event.event_id))
            return safe_result
        except ConnectorError as exc:
            self._log_call(
                context=context,
                event_type=AuditEventType.CONNECTOR_FAILED,
                operation=operation,
                outcome="failed",
                request_payload=request_payload,
                result_payload={"error_type": type(exc).__name__},
                reason=str(exc),
            )
            raise
        except Exception as exc:
            safe_error = ConnectorError("Connector operation failed safely.")
            self._log_call(
                context=context,
                event_type=AuditEventType.CONNECTOR_FAILED,
                operation=operation,
                outcome="failed",
                request_payload=request_payload,
                result_payload={"error_type": type(exc).__name__},
                reason=str(safe_error),
            )
            raise safe_error from exc

    def _assert_callable(self) -> None:
        if self.config.timeout_seconds <= 0:
            raise ConnectorTimeoutError("Connector timeout_seconds must be positive.")
        if not self.config.enabled:
            raise ConnectorUnavailableError("Connector is disabled by default.")

    def _log_call(
        self,
        *,
        context: ConnectorCallContext,
        event_type: AuditEventType,
        operation: str,
        outcome: str,
        request_payload: Mapping[str, Any],
        result_payload: object,
        reason: str,
    ) -> AuditEvent:
        request_hash = self._hash_payload(request_payload)
        result_hash = self._hash_payload(result_payload)
        return context.audit_logger.log_event(
            AuditEvent(
                event_type=event_type,
                actor=AuditActor(
                    actor_id=context.user_context.user_id,
                    actor_type="service"
                    if context.user_context.is_service_account
                    else "user",
                    display_name=context.user_context.display_name,
                    department=context.user_context.department.name
                    if context.user_context.department
                    else None,
                ),
                target=AuditTarget(
                    target_id=self.config.name,
                    target_type=f"{self.config.connector_kind.value}_connector",
                    qualified_name=self.config.name,
                ),
                user_id=context.user_context.user_id,
                role=context.user_context.roles[0].value
                if context.user_context.roles
                else None,
                session_id=context.session_id,
                task_id=context.task_id,
                agent_name=context.agent_name,
                tool_name=f"connector:{self.config.name}",
                action=f"connector.{self.config.connector_kind.value}.{operation}",
                outcome=outcome,
                reason=reason,
                request_summary=(
                    f"connector={self.config.name} operation={operation} "
                    f"request_hash={request_hash}"
                ),
                result_summary=f"outcome={outcome} result_hash={result_hash}",
                request_hash=request_hash,
                result_hash=result_hash,
                raw_payload_allowed=False,
                metadata={
                    "connector_name": self.config.name,
                    "connector_kind": self.config.connector_kind.value,
                    "operation": operation,
                    "timeout_seconds": self.config.timeout_seconds,
                    "is_mock": self.config.is_mock,
                    "request": self._sanitize(dict(request_payload)),
                    "result": self._sanitize(result_payload),
                },
            )
        )

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if self._is_sensitive_key(key_text):
                    sanitized[key_text] = "***MASKED***"
                else:
                    sanitized[key_text] = self._sanitize(item)
            return sanitized
        if isinstance(value, tuple):
            return tuple(self._sanitize(item) for item in value)
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str) and self._looks_like_secret(value):
            return "***MASKED***"
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in SENSITIVE_KEY_TOKENS)

    @staticmethod
    def _looks_like_secret(value: str) -> bool:
        lowered = value.lower()
        return any(token in lowered for token in ("password=", "token=", "api_key=", "secret="))

    @staticmethod
    def _hash_payload(payload: object) -> str:
        encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class StubConnector(BaseConnector):
    """Base for future real connectors. It never connects unless implemented explicitly."""

    def _assert_callable(self) -> None:
        raise ConnectorUnavailableError(
            f"{self.config.name} is a real connector stub and is not implemented."
        )
