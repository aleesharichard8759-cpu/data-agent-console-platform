from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.common import DomainModel, new_id, utc_now


class SensitivityLevel(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class SensitivityTag(DomainModel):
    tag_id: UUID = Field(default_factory=new_id, description="Unique sensitivity tag identifier.")
    name: str = Field(
        description="Sensitivity tag name, such as personal_data or finance_sensitive."
    )
    level: SensitivityLevel = Field(description="Sensitivity level assigned to this tag.")
    description: str | None = Field(default=None, description="Human-readable tag explanation.")
    masking_required: bool = Field(
        default=True,
        description="Whether data with this tag must be masked.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether data with this tag may be placed in an AI model context.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Sensitivity tag name must not be empty.")
        return value.strip()


class DataClassificationResult(DomainModel):
    result_id: UUID = Field(
        default_factory=new_id,
        description="Unique classification result identifier.",
    )
    asset_id: UUID = Field(description="Classified asset identifier.")
    sensitivity_level: SensitivityLevel = Field(
        description="Final sensitivity level for the asset."
    )
    tags: tuple[SensitivityTag, ...] = Field(
        default_factory=tuple,
        description="Sensitivity tags attached to the asset.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Classifier confidence from 0 to 1.",
    )
    evidence: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Evidence used to assign the classification.",
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether this classification requires governance approval.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether classified data may be used in AI model context.",
    )
    classified_at: datetime = Field(
        default_factory=utc_now,
        description="Timestamp when classification was produced.",
    )

    @field_validator("requires_approval", mode="before")
    @classmethod
    def default_requires_approval(cls, value: bool | None) -> bool:
        return bool(value) if value is not None else False

    @model_validator(mode="after")
    def validate_security_boundary(self) -> DataClassificationResult:
        if self.sensitivity_level in {SensitivityLevel.L4, SensitivityLevel.L5}:
            if not self.requires_approval:
                raise ValueError("L4/L5 classification results must require approval.")
            if self.allow_in_model_context:
                raise ValueError("L4/L5 classification results cannot enter model context.")
        return self
