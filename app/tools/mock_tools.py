from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.connectors.mock_catalog import search_metadata
from app.domain.classification import SensitivityLevel
from app.tools.base import DataTool
from app.tools.context import ToolExecutionContext


class SearchMetadataInput(BaseModel):
    query: str = Field(description="Metadata search keyword.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of metadata rows.")


class SearchMetadataOutput(BaseModel):
    results: list[dict[str, str]] = Field(description="Matched metadata assets.")


class SearchMetadataTool(DataTool):
    name = "search_metadata"
    description = "Search governed metadata from mock catalog."
    input_model = SearchMetadataInput
    output_model = SearchMetadataOutput
    max_rows = 50
    max_bytes = 128 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(
        self, validated_input: BaseModel, context: ToolExecutionContext
    ) -> dict[str, Any]:
        del context
        payload = SearchMetadataInput.model_validate(validated_input)
        return {"results": search_metadata(payload.query, payload.limit)}


class GetMetricDefinitionInput(BaseModel):
    metric_name: str = Field(description="Metric name to look up.")


class GetMetricDefinitionOutput(BaseModel):
    metric_name: str = Field(description="Metric name.")
    definition: str = Field(description="Business definition.")
    aggregation: str = Field(description="Aggregation logic.")
    owner: str = Field(description="Metric owner role.")


class GetMetricDefinitionTool(DataTool):
    name = "get_metric_definition"
    description = "Get a mock governed metric definition."
    input_model = GetMetricDefinitionInput
    output_model = GetMetricDefinitionOutput
    max_rows = 1
    max_bytes = 64 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(
        self, validated_input: BaseModel, context: ToolExecutionContext
    ) -> dict[str, Any]:
        del context
        payload = GetMetricDefinitionInput.model_validate(validated_input)
        return {
            "metric_name": payload.metric_name,
            "definition": "Governed aggregate metric definition from mock catalog.",
            "aggregation": "sum",
            "owner": "data_steward",
        }


class GenerateQualityRulesInput(BaseModel):
    table_name: str = Field(description="Table name for quality rule suggestions.")
    fields: list[str] = Field(default_factory=list, description="Candidate fields to inspect.")


class GenerateQualityRulesOutput(BaseModel):
    table_name: str = Field(description="Table name.")
    suggested_rules: list[dict[str, str]] = Field(description="Suggested data quality rules.")


class GenerateQualityRulesTool(DataTool):
    name = "generate_quality_rules"
    description = "Generate mock data quality rule suggestions."
    input_model = GenerateQualityRulesInput
    output_model = GenerateQualityRulesOutput
    max_rows = 20
    max_bytes = 128 * 1024

    def is_read_only(self) -> bool:
        return False

    def requires_approval(self) -> bool:
        return True

    def get_sensitivity_level(self) -> SensitivityLevel:
        return SensitivityLevel.L2

    def _execute(
        self, validated_input: BaseModel, context: ToolExecutionContext
    ) -> dict[str, Any]:
        del context
        payload = GenerateQualityRulesInput.model_validate(validated_input)
        rules = [
            {
                "rule_type": "not_null",
                "field": field,
                "severity": "warning",
            }
            for field in payload.fields
        ]
        if not rules:
            rules = [
                {
                    "rule_type": "freshness",
                    "field": "partition_date",
                    "severity": "warning",
                }
            ]
        return {"table_name": payload.table_name, "suggested_rules": rules}


def build_mock_tool_registry():
    from app.tools.registry import DataToolRegistry
    from app.tools.sql_tool import QuerySQLTool

    registry = DataToolRegistry()
    registry.register(SearchMetadataTool())
    registry.register(GetMetricDefinitionTool())
    registry.register(GenerateQualityRulesTool())
    registry.register(QuerySQLTool())
    return registry
