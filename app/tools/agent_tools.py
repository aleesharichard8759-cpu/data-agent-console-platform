from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.connectors.mock_catalog import get_lineage, get_table_metadata
from app.connectors.mock_warehouse import get_column_profile, run_quality_check
from app.domain.classification import SensitivityLevel
from app.tools.base import DataTool
from app.tools.context import ToolExecutionContext


class GetTableMetadataInput(BaseModel):
    table_name: str = Field(description="Table name to inspect.")


class GetTableMetadataOutput(BaseModel):
    table_name: str = Field(description="Table name.")
    columns: list[dict[str, str | bool]] = Field(description="Table column metadata.")
    missing_owner_tables: list[str] = Field(description="Tables without owner.")
    missing_comment_fields: list[str] = Field(description="Fields without business comments.")
    duplicate_table_candidates: list[str] = Field(description="Potential duplicate tables.")
    completion_suggestions: list[str] = Field(description="Metadata completion suggestions.")


class GetTableMetadataTool(DataTool):
    name = "get_table_metadata"
    description = "Return mock table metadata quality issues."
    input_model = GetTableMetadataInput
    output_model = GetTableMetadataOutput
    max_rows = 20
    max_bytes = 128 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = GetTableMetadataInput.model_validate(validated_input)
        return get_table_metadata(payload.table_name)


class GetColumnProfileInput(BaseModel):
    table_name: str = Field(description="Table name to profile.")
    column_name: str = Field(description="Column name to profile.")


class GetColumnProfileOutput(BaseModel):
    table_name: str = Field(description="Table name.")
    column_name: str = Field(description="Column name.")
    null_rate: float = Field(description="Mock null rate.")
    unique_rate: float = Field(description="Mock unique rate.")
    sample_summary: str = Field(description="Masked sample summary.")
    sample_values_returned: bool = Field(description="Whether raw sample values are returned.")
    sensitivity_level: str = Field(description="Sensitivity level.")
    masking_applied: bool = Field(description="Whether masking was applied.")


class GetColumnProfileTool(DataTool):
    name = "get_column_profile"
    description = "Return safe mock column profile summary without sensitive plaintext."
    input_model = GetColumnProfileInput
    output_model = GetColumnProfileOutput
    max_rows = 1
    max_bytes = 64 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = GetColumnProfileInput.model_validate(validated_input)
        return get_column_profile(payload.table_name, payload.column_name)


class GetLineageInput(BaseModel):
    table_name: str = Field(description="Table name to inspect.")


class GetLineageOutput(BaseModel):
    table_name: str = Field(description="Table name.")
    upstream: tuple[str, ...] = Field(description="Mock upstream assets.")
    downstream: tuple[str, ...] = Field(description="Mock downstream assets.")
    impact_summary: str = Field(description="Mock lineage impact summary.")


class GetLineageTool(DataTool):
    name = "get_lineage"
    description = "Return mock lineage for governed catalog assets."
    input_model = GetLineageInput
    output_model = GetLineageOutput
    max_rows = 20
    max_bytes = 64 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = GetLineageInput.model_validate(validated_input)
        return get_lineage(payload.table_name)


class RunQualityCheckInput(BaseModel):
    table_name: str = Field(description="Table name to check.")


class RunQualityCheckOutput(BaseModel):
    completeness_rules: list[str] = Field(description="Completeness rule suggestions.")
    uniqueness_rules: list[str] = Field(description="Uniqueness rule suggestions.")
    validity_rules: list[str] = Field(description="Validity rule suggestions.")
    consistency_rules: list[str] = Field(description="Consistency rule suggestions.")
    strong_rules: list[str] = Field(description="Rules suitable for blocking checks.")
    weak_rules: list[str] = Field(description="Rules suitable for warning checks.")


class RunQualityCheckTool(DataTool):
    name = "run_quality_check"
    description = "Run mock quality evidence checks."
    input_model = RunQualityCheckInput
    output_model = RunQualityCheckOutput
    max_rows = 20
    max_bytes = 128 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = RunQualityCheckInput.model_validate(validated_input)
        return run_quality_check(payload.table_name)


class ClassifySensitivityInput(BaseModel):
    fields: list[str] = Field(description="Field names to classify.")


class ClassifySensitivityOutput(BaseModel):
    sensitive_fields: list[dict[str, str | bool]] = Field(description="Classified fields.")
    masking_suggestions: list[str] = Field(description="Masking suggestions.")
    allow_in_model_context: bool = Field(description="Whether output may enter model context.")


class ClassifySensitivityTool(DataTool):
    name = "classify_sensitivity"
    description = "Classify mock field sensitivity levels."
    input_model = ClassifySensitivityInput
    output_model = ClassifySensitivityOutput
    max_rows = 50
    max_bytes = 128 * 1024

    def get_sensitivity_level(self) -> SensitivityLevel:
        return SensitivityLevel.L4

    def allow_in_model_context(self) -> bool:
        return False

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = ClassifySensitivityInput.model_validate(validated_input)
        fields = payload.fields or [
            "order_id",
            "contact_phone_hash",
            "recipient_address_text",
            "api_secret_marker",
        ]
        classified = [self._classify_field(field) for field in fields]
        allow_context = all(item["level"] in {"L1", "L2", "L3"} for item in classified)
        return {
            "sensitive_fields": classified,
            "masking_suggestions": [
                "Hash or tokenize contact-like identifiers before model use.",
                "Exclude L4/L5 fields from model context.",
            ],
            "allow_in_model_context": allow_context,
        }

    @staticmethod
    def _classify_field(field: str) -> dict[str, str | bool]:
        lowered = field.lower()
        if "secret" in lowered or "token" in lowered:
            return {"field": field, "level": "L5", "requires_masking": True}
        if any(token in lowered for token in ("phone", "email", "address")):
            return {"field": field, "level": "L4", "requires_masking": True}
        if "amount" in lowered or "gross_profit" in lowered or "profit" in lowered:
            return {"field": field, "level": "L3", "requires_masking": False}
        return {"field": field, "level": "L2", "requires_masking": False}


class CheckPermissionInput(BaseModel):
    asset_name: str = Field(description="Asset name to inspect.")


class CheckPermissionOutput(BaseModel):
    findings: list[str] = Field(description="Permission findings.")
    requires_review: bool = Field(description="Whether review is required.")


class CheckPermissionTool(DataTool):
    name = "check_permission"
    description = "Return mock permission inspection findings."
    input_model = CheckPermissionInput
    output_model = CheckPermissionOutput
    max_rows = 20
    max_bytes = 64 * 1024

    def allow_in_model_context(self) -> bool:
        return False

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = CheckPermissionInput.model_validate(validated_input)
        return {
            "findings": [
                f"{payload.asset_name} should be limited to governed roles.",
                "High-sensitivity fields require approval before access.",
            ],
            "requires_review": True,
        }


class GenerateMetricCardInput(BaseModel):
    metric_name: str = Field(description="Metric name.")


class GenerateMetricCardOutput(BaseModel):
    business_definition: str = Field(description="Business metric definition.")
    technical_definition: str = Field(description="Technical metric definition.")
    dimensions: list[str] = Field(description="Metric dimensions.")
    time_field: str = Field(description="Metric time field.")
    open_questions: list[str] = Field(description="Questions that need confirmation.")


class GenerateMetricCardTool(DataTool):
    name = "generate_metric_card"
    description = "Generate a mock metric governance card."
    input_model = GenerateMetricCardInput
    output_model = GenerateMetricCardOutput
    max_rows = 1
    max_bytes = 64 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(self, validated_input: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        del context
        payload = GenerateMetricCardInput.model_validate(validated_input)
        return {
            "business_definition": f"{payload.metric_name} governed business definition.",
            "technical_definition": "Aggregate from governed ADS/DWS mock assets only.",
            "dimensions": ["date", "business_domain", "channel"],
            "time_field": "metric_date",
            "open_questions": ["Confirm final owner and exception handling rules."],
        }
