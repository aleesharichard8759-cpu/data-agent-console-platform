from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from app.audit import AuditLogger
from app.core.errors import RuntimeErrorBase, UnsafeOperationError
from app.domain.common import DomainModel
from app.domain.identity import UserContext
from app.domain.tasks import GovernanceTask
from app.domain.tools import ToolCallRequest, ToolCallResult
from app.policy import PolicyEngine
from app.tools import DataToolRegistry, ToolExecutionContext


class AgentPermissionMode(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class AgentPermissionError(RuntimeErrorBase):
    """Raised when an agent attempts to use a tool outside its boundary."""


class AgentTaskContext(DomainModel):
    task: GovernanceTask = Field(description="Governance task assigned to the agent.")
    user_context: UserContext = Field(description="Runtime user context.")
    session_id: str | None = Field(default=None, description="Runtime session id.")
    dry_run: bool = Field(default=True, description="Whether tool execution is dry-run mock mode.")


class AgentResult(DomainModel):
    agent_name: str = Field(description="Agent name.")
    task_id: str = Field(description="Governance task id.")
    status: str = Field(description="Agent run status.")
    findings: dict[str, object] = Field(description="Structured agent findings.")
    recommendations: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Governance recommendations.",
    )
    tool_results: tuple[ToolCallResult, ...] = Field(
        default_factory=tuple,
        description="Tool results produced by the agent.",
    )
    veto: bool = Field(default=False, description="Whether this agent vetoes the task output.")
    veto_reason: str | None = Field(default=None, description="Reason for veto, if any.")


class BaseAgent(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    allowed_tools: ClassVar[tuple[str, ...]]
    disallowed_tools: ClassVar[tuple[str, ...]] = ("query_sql",)
    max_turns: ClassVar[int] = 4
    permission_mode: ClassVar[AgentPermissionMode] = AgentPermissionMode.ALLOW

    def __init__(
        self,
        *,
        tool_registry: DataToolRegistry,
        policy_engine: PolicyEngine,
        audit_logger: AuditLogger,
    ) -> None:
        if policy_engine is None:
            raise UnsafeOperationError("Subagents require Policy Engine.")
        if audit_logger is None:
            raise UnsafeOperationError("Subagents require Audit Logger.")
        if "query_sql" in self.allowed_tools:
            raise UnsafeOperationError("Subagents cannot whitelist direct SQL tools.")
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.audit_logger = audit_logger

    @abstractmethod
    def run(self, task_context: AgentTaskContext) -> AgentResult:
        """Run this specialized agent."""

    def call_tool(
        self,
        task_context: AgentTaskContext,
        request: ToolCallRequest,
    ) -> ToolCallResult:
        self.assert_tool_allowed(request)
        return self.tool_registry.execute_tool(
            request,
            ToolExecutionContext(
                user_context=task_context.user_context,
                task_context=task_context.task,
                policy_engine=self.policy_engine,
                audit_logger=self.audit_logger,
                dry_run=task_context.dry_run,
                plan_mode=False,
                session_id=task_context.session_id,
                agent_name=self.name,
            ),
        )

    def assert_tool_allowed(self, request: ToolCallRequest) -> None:
        if request.tool_name == "query_sql" or request.action.startswith("sql."):
            raise AgentPermissionError("Subagents are not allowed to execute SQL tools.")
        if request.tool_name in self.disallowed_tools:
            raise AgentPermissionError(f"Tool is explicitly disallowed: {request.tool_name}")
        if request.tool_name not in self.allowed_tools:
            raise AgentPermissionError(f"Tool is not allowed for {self.name}: {request.tool_name}")

    @staticmethod
    def table_hint(task: GovernanceTask) -> str:
        if task.domain.value == "trade":
            return "ods_erp_order"
        if task.domain.value == "product":
            return "dim_product_sku"
        return "governed_mock_asset"
