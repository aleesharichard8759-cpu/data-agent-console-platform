from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.common import DomainModel, new_id, utc_now


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalRequest(DomainModel):
    approval_id: UUID = Field(default_factory=new_id, description="Unique approval request id.")
    requester_id: str = Field(description="User or service requesting approval.")
    approver_ids: tuple[str, ...] = Field(description="Required approver identifiers.")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Approval status.")
    decision: ApprovalDecision | None = Field(default=None, description="Final approval decision.")
    reason: str = Field(description="Reason for the approval request.")
    target_type: str = Field(description="Approval target type, such as task or tool_call.")
    target_id: UUID = Field(description="Approval target identifier.")
    requires_approval: bool = Field(
        default=True,
        description="Approval requests always require review.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether this approval request may be included in model context.",
    )
    requested_at: datetime = Field(
        default_factory=utc_now,
        description="Approval request timestamp.",
    )
    decided_at: datetime | None = Field(default=None, description="Decision timestamp if decided.")

    @field_validator("requester_id", "reason", "target_type")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Approval text fields must not be empty.")
        return value.strip()

    @model_validator(mode="after")
    def validate_decision_consistency(self) -> ApprovalRequest:
        if self.status == ApprovalStatus.PENDING and self.decision is not None:
            raise ValueError("Pending approval requests must not have a final decision.")
        is_final_status = self.status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}
        if is_final_status and self.decision is None:
            raise ValueError("Finalized approval requests must have a decision.")
        return self
