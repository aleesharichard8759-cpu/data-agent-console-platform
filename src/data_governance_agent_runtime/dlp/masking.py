from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from data_governance_agent_runtime.core.models import DlpResult

SENSITIVE_FIELD_TOKENS = (
    "address",
    "credential",
    "customer_name",
    "email",
    "id_card",
    "password",
    "phone",
    "secret",
    "token",
)


class DlpMasker:
    """Masks sensitive-looking fields by field name and inherited metadata labels."""

    def mask(self, payload: Mapping[str, Any]) -> DlpResult:
        masked_fields: list[str] = []
        masked = self._mask_value(payload, path="", masked_fields=masked_fields)
        if not isinstance(masked, dict):
            return DlpResult(data={"value": masked}, masked_fields=tuple(masked_fields))
        return DlpResult(data=masked, masked_fields=tuple(masked_fields))

    def _mask_value(self, value: Any, path: str, masked_fields: list[str]) -> Any:
        if isinstance(value, Mapping):
            output: dict[str, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if self._is_sensitive_key(str(key)):
                    output[str(key)] = "***MASKED***"
                    masked_fields.append(child_path)
                else:
                    output[str(key)] = self._mask_value(item, child_path, masked_fields)
            return output
        if isinstance(value, list):
            return [
                self._mask_value(item, f"{path}[{index}]", masked_fields)
                for index, item in enumerate(value)
            ]
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in SENSITIVE_FIELD_TOKENS)

