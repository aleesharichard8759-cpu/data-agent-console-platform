from __future__ import annotations

from data_governance_agent_runtime.audit.recorder import AuditRecorder
from data_governance_agent_runtime.dlp.masking import DlpMasker
from data_governance_agent_runtime.policy.engine import PolicyEngine
from data_governance_agent_runtime.tools.base import DataTool
from data_governance_agent_runtime.tools.governance import (
    AssetInventoryTool,
    GovernanceReportTool,
    LineageImpactTool,
    MetadataCompletionTool,
    MetricGovernanceTool,
    PermissionInspectionTool,
    QualityRuleSuggestionTool,
    SensitiveFieldDetectionTool,
    SqlQueryTool,
)


class ToolRegistry:
    def __init__(self, tools: dict[str, DataTool]) -> None:
        self._tools = tools

    def get(self, name: str) -> DataTool:
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))


def build_default_registry(
    policy: PolicyEngine,
    audit: AuditRecorder,
    dlp: DlpMasker,
) -> ToolRegistry:
    tools: list[DataTool] = [
        AssetInventoryTool(policy, audit, dlp),
        MetadataCompletionTool(policy, audit, dlp),
        QualityRuleSuggestionTool(policy, audit, dlp),
        MetricGovernanceTool(policy, audit, dlp),
        SensitiveFieldDetectionTool(policy, audit, dlp),
        LineageImpactTool(policy, audit, dlp),
        PermissionInspectionTool(policy, audit, dlp),
        GovernanceReportTool(policy, audit, dlp),
        SqlQueryTool(policy, audit, dlp),
    ]
    return ToolRegistry({tool.name: tool for tool in tools})

