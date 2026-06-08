from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.classification import SensitivityLevel, SensitivityTag
from app.domain.common import DomainModel, new_id


class DataDomain(StrEnum):
    TRADE = "trade"
    PRODUCT = "product"
    INVENTORY = "inventory"
    LOGISTICS = "logistics"
    FINANCE = "finance"
    CUSTOMER = "customer"
    SUPPLY_CHAIN = "supply_chain"
    MARKETING = "marketing"
    ORGANIZATION = "organization"
    SECURITY = "security"
    UNKNOWN = "unknown"


class AssetOwner(DomainModel):
    owner_id: str = Field(description="Owner identifier, usually a user or group id.")
    name: str = Field(description="Owner display name.")
    role: str = Field(description="Owner responsibility, such as data_owner or data_steward.")
    department: str | None = Field(default=None, description="Owner department name.")


class DataAsset(DomainModel):
    asset_id: UUID = Field(default_factory=new_id, description="Unique data asset identifier.")
    name: str = Field(description="Asset name.")
    qualified_name: str = Field(description="Fully qualified asset name.")
    domain: DataDomain = Field(default=DataDomain.UNKNOWN, description="Business data domain.")
    owner: AssetOwner | None = Field(default=None, description="Asset owner.")
    sensitivity_level: SensitivityLevel = Field(
        default=SensitivityLevel.L1,
        description="Asset sensitivity level.",
    )
    sensitivity_tags: tuple[SensitivityTag, ...] = Field(
        default_factory=tuple,
        description="Sensitivity tags attached to this asset.",
    )
    description: str | None = Field(default=None, description="Business description of the asset.")
    is_production: bool = Field(
        default=False,
        description="Whether this asset belongs to production.",
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether accessing this asset requires governance approval.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether this asset may be represented in AI model context.",
    )

    @field_validator("name", "qualified_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Asset name fields must not be empty.")
        return value.strip()

    @model_validator(mode="after")
    def validate_security_boundary(self) -> DataAsset:
        if self.sensitivity_level in {SensitivityLevel.L4, SensitivityLevel.L5}:
            if not self.requires_approval:
                raise ValueError("L4/L5 assets must require approval.")
            if self.allow_in_model_context:
                raise ValueError("L4/L5 assets cannot enter model context.")
        if self.is_production and self.allow_in_model_context:
            raise ValueError("Production assets cannot enter model context.")
        return self


class DatabaseAsset(DataAsset):
    database_type: str = Field(description="Database type, such as mysql, doris, or starrocks.")
    environment: str = Field(description="Environment name, such as mock, dev, staging, or prod.")


class TableAsset(DataAsset):
    database: str = Field(description="Database name that contains the table.")
    schema_name: str | None = Field(default=None, description="Schema name if applicable.")
    table_name: str = Field(description="Physical table name.")
    columns: tuple[ColumnAsset, ...] = Field(
        default_factory=tuple,
        description="Column assets that belong to the table.",
    )


class ColumnAsset(DataAsset):
    table_qualified_name: str = Field(description="Fully qualified table name for this column.")
    column_name: str = Field(description="Physical column name.")
    data_type: str = Field(description="Column data type.")
    nullable: bool = Field(default=True, description="Whether the column can contain null values.")
    masking_required: bool = Field(default=False, description="Whether the column must be masked.")


class MetricAsset(DataAsset):
    metric_name: str = Field(description="Metric business name.")
    definition: str = Field(description="Metric definition.")
    aggregation: str = Field(description="Aggregation logic, such as sum or count_distinct.")
    grain: str = Field(description="Metric grain, such as order_day or sku_day.")
    source_assets: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Source asset qualified names used by this metric.",
    )


TableAsset.model_rebuild()
