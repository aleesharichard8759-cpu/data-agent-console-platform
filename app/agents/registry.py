from __future__ import annotations

from app.agents.base import BaseAgent
from app.core.errors import RuntimeErrorBase
from app.domain.tasks import GovernanceTask, GovernanceTaskType


class AgentNotFoundError(RuntimeErrorBase):
    """Raised when an agent is not registered."""


class DuplicateAgentError(RuntimeErrorBase):
    """Raised when an agent is registered twice."""


class AgentRegistry:
    def __init__(self, agents: tuple[BaseAgent, ...] | None = None) -> None:
        self._agents: dict[str, BaseAgent] = {}
        for agent in agents or ():
            self.register(agent)

    def register(self, agent: BaseAgent) -> None:
        if agent.name in self._agents:
            raise DuplicateAgentError(f"Agent already registered: {agent.name}")
        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> BaseAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise AgentNotFoundError(f"Agent not found: {name}") from exc

    def list_agents(self) -> tuple[BaseAgent, ...]:
        return tuple(self._agents[name] for name in sorted(self._agents))

    def select_agents_for_task(self, task: GovernanceTask) -> tuple[BaseAgent, ...]:
        names = self._agent_names_for_task(task)
        return tuple(self.get_agent(name) for name in names if name in self._agents)

    @staticmethod
    def _agent_names_for_task(task: GovernanceTask) -> tuple[str, ...]:
        if task.task_type == GovernanceTaskType.DATA_DOMAIN_GOVERNANCE:
            return ("metadata_agent", "data_quality_agent", "security_agent", "metric_agent")
        if task.task_type == GovernanceTaskType.DATA_QUALITY:
            return ("metadata_agent", "data_quality_agent")
        if task.task_type == GovernanceTaskType.METADATA_COMPLETION:
            return ("metadata_agent",)
        if task.task_type == GovernanceTaskType.METRIC_GOVERNANCE:
            return ("metadata_agent", "metric_agent")
        if task.task_type in {
            GovernanceTaskType.SENSITIVE_DATA_DISCOVERY,
            GovernanceTaskType.PERMISSION_INSPECTION,
        }:
            return ("security_agent",)
        if task.task_type == GovernanceTaskType.GOVERNANCE_REPORT:
            return ("metadata_agent", "data_quality_agent", "security_agent", "metric_agent")
        return ("metadata_agent",)
