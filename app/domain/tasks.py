from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.assets import DataAsset, DataDomain
from app.domain.common import DomainModel, new_id, utc_now


class GovernanceTaskType(StrEnum):
    ASSET_INVENTORY = "asset_inventory"
    DATA_DOMAIN_GOVERNANCE = "data_domain_governance"
    METADATA_COMPLETION = "metadata_completion"
    DATA_QUALITY = "data_quality"
    METRIC_GOVERNANCE = "metric_governance"
    SENSITIVE_DATA_DISCOVERY = "sensitive_data_discovery"
    LINEAGE_IMPACT = "lineage_impact"
    PERMISSION_INSPECTION = "permission_inspection"
    GOVERNANCE_REPORT = "governance_report"


class GovernanceTaskLevel(StrEnum):
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"


class GovernanceTaskStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    CANCELED = "canceled"


class GovernanceTask(DomainModel):
    task_id: UUID = Field(default_factory=new_id, description="Unique governance task identifier.")
    title: str = Field(description="Short task title.")
    task_type: GovernanceTaskType = Field(description="Governance task type.")
    task_level: GovernanceTaskLevel = Field(
        description="Governance task risk and importance level."
    )
    status: GovernanceTaskStatus = Field(
        default=GovernanceTaskStatus.CREATED,
        description="Current governance task status.",
    )
    domain: DataDomain = Field(description="Business data domain for the task.")
    objective: str = Field(description="Task objective.")
    target_assets: tuple[DataAsset, ...] = Field(
        default_factory=tuple,
        description="Assets targeted by this governance task.",
    )
    created_by: str = Field(description="User or service account that created the task.")
    requires_approval: bool = Field(
        default=False,
        description="Whether this task must be approved before execution.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether this task description may be included in model context.",
    )
    created_at: datetime = Field(default_factory=utc_now, description="Task creation timestamp.")

    @field_validator("title", "objective", "created_by")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Governance task text fields must not be empty.")
        return value.strip()

    @model_validator(mode="after")
    def validate_security_boundary(self) -> GovernanceTask:
        if self.task_level in {GovernanceTaskLevel.G4, GovernanceTaskLevel.G5}:
            if not self.requires_approval:
                raise ValueError("G4/G5 governance tasks must require approval.")
            if self.allow_in_model_context:
                raise ValueError("G4/G5 governance tasks cannot enter model context.")
        return self
