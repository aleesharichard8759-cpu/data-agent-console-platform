from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from app.core.errors import RuntimeErrorBase, UnsafeOperationError
from app.domain.classification import SensitivityLevel
from app.domain.common import DomainModel, new_id, utc_now


class MemoryType(StrEnum):
    BUSINESS = "business"
    METRIC = "metric"
    GOVERNANCE = "governance"
    SECURITY = "security"
    FEEDBACK = "feedback"
    REFERENCE = "reference"


class GovernanceMemory(DomainModel):
    memory_id: UUID = Field(default_factory=new_id, description="Unique memory id.")
    memory_type: MemoryType = Field(description="Governance memory type.")
    title: str = Field(description="Short memory title.")
    content_summary: str = Field(description="Safe summarized memory content.")
    source_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Evidence, audit, document, or metric references.",
    )
    sensitivity_level: SensitivityLevel = Field(description="Memory sensitivity level.")
    allow_retrieval: bool = Field(description="Whether this memory may be retrieved.")
    expires_at: datetime | None = Field(default=None, description="Memory expiry timestamp.")
    last_verified_at: datetime | None = Field(
        default=None,
        description="Last time this memory was verified.",
    )

    @field_validator("title", "content_summary")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Memory text fields must not be empty.")
        return value.strip()


class MemorySafetyError(UnsafeOperationError):
    """Raised when memory content violates governance memory safety rules."""


class MemoryNotFoundError(RuntimeErrorBase):
    """Raised when a requested memory item is not found."""


class MemoryStore:
    """In-memory safe summary store. It is not an authorization system."""

    _email_pattern = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
    _phone_pattern = re.compile(r"\b(?:\+?\d[\d\-\s()]{6,}\d)\b")
    _secret_assignment_pattern = re.compile(
        r"\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+",
        re.IGNORECASE,
    )
    _address_assignment_pattern = re.compile(
        r"\b(?:address|recipient_address|shipping_address|customer_address)\s*[:=]\s*\S+",
        re.IGNORECASE,
    )
    _address_field_tokens = ("address", "recipient_address", "shipping_address", "customer_address")
    _address_context_tokens = ("地址明细", "地址原文", "raw address", "plaintext address")
    _sensitive_value_tokens = ("明细", "plaintext", "raw value", "敏感值")

    def __init__(self) -> None:
        self._memories: dict[UUID, GovernanceMemory] = {}

    def add_memory(self, memory: GovernanceMemory) -> GovernanceMemory:
        self._assert_memory_safe(memory)
        self._memories[memory.memory_id] = memory
        return memory

    def search_memory(self, query: str) -> tuple[GovernanceMemory, ...]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return tuple()
        return tuple(
            memory
            for memory in self.list_memory()
            if memory.allow_retrieval
            and self.verify_memory_freshness(memory.memory_id)
            and (
                normalized_query in memory.title.lower()
                or normalized_query in memory.content_summary.lower()
            )
        )

    def list_memory(self) -> tuple[GovernanceMemory, ...]:
        return tuple(self._memories[memory_id] for memory_id in sorted(self._memories))

    def delete_memory(self, memory_id: UUID | str) -> bool:
        try:
            normalized_id = UUID(str(memory_id))
        except ValueError as exc:
            raise MemoryNotFoundError(f"Invalid memory id: {memory_id}") from exc
        return self._memories.pop(normalized_id, None) is not None

    def verify_memory_freshness(self, memory_id: UUID | str) -> bool:
        memory = self._get_memory(memory_id)
        if memory.expires_at is None:
            return True
        return memory.expires_at > utc_now()

    def _get_memory(self, memory_id: UUID | str) -> GovernanceMemory:
        try:
            normalized_id = UUID(str(memory_id))
        except ValueError as exc:
            raise MemoryNotFoundError(f"Invalid memory id: {memory_id}") from exc
        try:
            return self._memories[normalized_id]
        except KeyError as exc:
            raise MemoryNotFoundError(f"Memory not found: {memory_id}") from exc

    def _assert_memory_safe(self, memory: GovernanceMemory) -> None:
        if memory.sensitivity_level in {
            SensitivityLevel.L3,
            SensitivityLevel.L4,
            SensitivityLevel.L5,
        }:
            raise MemorySafetyError("L3/L4/L5 content cannot be written to memory.")
        combined_text = " ".join((memory.title, memory.content_summary, *memory.source_refs))
        if self._contains_sensitive_value(combined_text):
            raise MemorySafetyError("Memory content contains sensitive values or identifiers.")
        if (
            memory.memory_type == MemoryType.SECURITY
            and self._contains_security_value(combined_text)
        ):
            raise MemorySafetyError("Security memory may store policy summaries only.")

    def _contains_sensitive_value(self, text: str) -> bool:
        lowered = text.lower()
        contains_address_field = any(token in lowered for token in self._address_field_tokens)
        contains_sensitive_detail = any(token in lowered for token in self._sensitive_value_tokens)
        return (
            self._email_pattern.search(text) is not None
            or self._phone_pattern.search(text) is not None
            or self._secret_assignment_pattern.search(text) is not None
            or self._address_assignment_pattern.search(text) is not None
            or any(token in lowered for token in self._address_context_tokens)
            or (contains_address_field and contains_sensitive_detail)
        )

    def _contains_security_value(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in self._sensitive_value_tokens)
