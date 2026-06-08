from __future__ import annotations

from pydantic import Field

from app.agents.base import AgentResult, AgentTaskContext
from app.agents.registry import AgentRegistry
from app.agents.specialized import DataQualityAgent, MetadataAgent, MetricAgent, SecurityAgent
from app.audit import AuditLogger, InMemoryAuditLogger
from app.domain.common import DomainModel
from app.domain.tasks import GovernanceTask
from app.hooks import build_default_hook_manager
from app.policy import PolicyEngine
from app.tools import (
    CheckPermissionTool,
    ClassifySensitivityTool,
    DataToolRegistry,
    GenerateMetricCardTool,
    GenerateQualityRulesTool,
    GetColumnProfileTool,
    GetLineageTool,
    GetMetricDefinitionTool,
    GetTableMetadataTool,
    RunQualityCheckTool,
    SearchMetadataTool,
)


class OrchestratorResult(DomainModel):
    task_id: str = Field(description="Governance task id.")
    status: str = Field(description="Overall orchestration status.")
    agent_results: tuple[AgentResult, ...] = Field(description="Individual agent results.")
    summary: dict[str, object] = Field(description="Merged safe summary.")
    vetoed_by: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Agents that vetoed the output.",
    )


class AgentOrchestrator:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def run(self, task: GovernanceTask, context: AgentTaskContext) -> OrchestratorResult:
        agents = self.registry.select_agents_for_task(task)
        results = tuple(agent.run(context) for agent in agents)
        vetoed_by = tuple(result.agent_name for result in results if result.veto)
        return OrchestratorResult(
            task_id=str(task.task_id),
            status="vetoed" if vetoed_by else "completed",
            agent_results=results,
            summary=self._merge_results(results),
            vetoed_by=vetoed_by,
        )

    @staticmethod
    def _merge_results(results: tuple[AgentResult, ...]) -> dict[str, object]:
        return {
            "agents": tuple(result.agent_name for result in results),
            "findings": {result.agent_name: result.findings for result in results},
            "recommendations": tuple(
                recommendation
                for result in results
                for recommendation in result.recommendations
            ),
            "security_veto": any(result.veto for result in results),
        }


def build_agent_tool_registry() -> DataToolRegistry:
    registry = DataToolRegistry(hook_manager=build_default_hook_manager())
    registry.register(SearchMetadataTool())
    registry.register(GetTableMetadataTool())
    registry.register(GetColumnProfileTool())
    registry.register(GetLineageTool())
    registry.register(GenerateQualityRulesTool())
    registry.register(RunQualityCheckTool())
    registry.register(ClassifySensitivityTool())
    registry.register(CheckPermissionTool())
    registry.register(GetMetricDefinitionTool())
    registry.register(GenerateMetricCardTool())
    return registry


def build_default_agent_registry(
    *,
    policy_engine: PolicyEngine | None = None,
    audit_logger: AuditLogger | None = None,
    tool_registry: DataToolRegistry | None = None,
) -> AgentRegistry:
    resolved_policy = policy_engine or PolicyEngine()
    resolved_audit = audit_logger or InMemoryAuditLogger()
    resolved_tools = tool_registry or build_agent_tool_registry()
    return AgentRegistry(
        agents=(
            MetadataAgent(
                tool_registry=resolved_tools,
                policy_engine=resolved_policy,
                audit_logger=resolved_audit,
            ),
            DataQualityAgent(
                tool_registry=resolved_tools,
                policy_engine=resolved_policy,
                audit_logger=resolved_audit,
            ),
            SecurityAgent(
                tool_registry=resolved_tools,
                policy_engine=resolved_policy,
                audit_logger=resolved_audit,
            ),
            MetricAgent(
                tool_registry=resolved_tools,
                policy_engine=resolved_policy,
                audit_logger=resolved_audit,
            ),
        )
    )


def build_default_orchestrator(
    *,
    policy_engine: PolicyEngine | None = None,
    audit_logger: AuditLogger | None = None,
    tool_registry: DataToolRegistry | None = None,
) -> AgentOrchestrator:
    return AgentOrchestrator(
        build_default_agent_registry(
            policy_engine=policy_engine,
            audit_logger=audit_logger,
            tool_registry=tool_registry,
        )
    )
