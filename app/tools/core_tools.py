from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from app.connectors.base import ConnectorCallContext
from app.connectors.interfaces import MetadataConnector
from app.domain.classification import SensitivityLevel
from app.tools.base import DataTool
from app.tools.context import ToolExecutionContext


def _real_connector_required(capability: str) -> RuntimeError:
    return RuntimeError(
        f"{capability} requires a configured real connector. Built-in sample data has been removed."
    )


class SearchMetadataInput(BaseModel):
    query: str = Field(description="Metadata search keyword.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of metadata rows.")


class SearchMetadataOutput(BaseModel):
    results: list[dict[str, str]] = Field(description="Matched metadata assets.")


class SearchMetadataTool(DataTool):
    name = "search_metadata"
    description = "Search governed metadata through a configured real metadata connector."
    input_model = SearchMetadataInput
    output_model = SearchMetadataOutput
    max_rows = 50
    max_bytes = 128 * 1024
    _metadata_connector: MetadataConnector | None = PrivateAttr()

    def __init__(self, metadata_connector: MetadataConnector | None = None) -> None:
        super().__init__()
        if metadata_connector is None:
            from app.connectors import build_metadata_connector_from_env

            metadata_connector = build_metadata_connector_from_env()
        self._metadata_connector = metadata_connector

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(
        self, validated_input: BaseModel, context: ToolExecutionContext
    ) -> dict[str, Any]:
        payload = SearchMetadataInput.model_validate(validated_input)
        if self._metadata_connector is None:
            raise _real_connector_required("Metadata search")
        result = self._metadata_connector.search_assets(
            payload.query,
            ConnectorCallContext(
                user_context=context.user_context,
                audit_logger=context.audit_logger,
                session_id=context.session_id,
                task_id=str(context.task_context.task_id) if context.task_context else None,
                agent_name=context.agent_name,
            ),
        )
        rows = list(result.get("results", []))[: payload.limit]
        return {"results": rows}


class GetMetricDefinitionInput(BaseModel):
    metric_name: str = Field(description="Metric name to look up.")


class GetMetricDefinitionOutput(BaseModel):
    metric_name: str = Field(description="Metric name.")
    definition: str = Field(description="Business definition.")
    aggregation: str = Field(description="Aggregation logic.")
    owner: str = Field(description="Metric owner role.")


class GetMetricDefinitionTool(DataTool):
    name = "get_metric_definition"
    description = "Get a governed metric definition through a configured real metric connector."
    input_model = GetMetricDefinitionInput
    output_model = GetMetricDefinitionOutput
    max_rows = 1
    max_bytes = 64 * 1024

    def allow_in_model_context(self) -> bool:
        return True

    def _execute(
        self, validated_input: BaseModel, context: ToolExecutionContext
    ) -> dict[str, Any]:
        del validated_input, context
        raise _real_connector_required("Metric definition lookup")


class GenerateQualityRulesInput(BaseModel):
    table_name: str = Field(description="Table name for quality rule suggestions.")
    fields: list[str] = Field(default_factory=list, description="Candidate fields to inspect.")


class GenerateQualityRulesOutput(BaseModel):
    table_name: str = Field(description="Table name.")
    suggested_rules: list[dict[str, str]] = Field(description="Suggested data quality rules.")


class GenerateQualityRulesTool(DataTool):
    name = "generate_quality_rules"
    description = "Generate data quality rule suggestions through a configured real quality connector."
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
        del validated_input, context
        raise _real_connector_required("Quality rule generation")


def build_real_tool_registry():
    from app.tools.agent_tools import GetTableMetadataTool
    from app.tools.registry import DataToolRegistry
    from app.tools.sql_tool import QuerySQLTool

    registry = DataToolRegistry()
    registry.register(SearchMetadataTool())
    registry.register(GetTableMetadataTool())
    registry.register(GetMetricDefinitionTool())
    registry.register(GenerateQualityRulesTool())
    registry.register(QuerySQLTool())
    return registry
