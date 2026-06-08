from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import Field

from app.domain.common import DomainModel
from app.domain.policy import PolicyDecision
from app.domain.tools import ToolCallRequest, ToolCallResult

if TYPE_CHECKING:
    from app.tools.base import DataTool
    from app.tools.context import ToolExecutionContext


class HookEventType(StrEnum):
    SESSION_START = "session_start"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PERMISSION_REQUEST = "permission_request"
    PERMISSION_DENIED = "permission_denied"
    TASK_COMPLETED = "task_completed"
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"


class HookDecision(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"
    NONE = "none"


class HookResult(DomainModel):
    continue_execution: bool = Field(description="Whether execution should continue.")
    decision: HookDecision = Field(default=HookDecision.NONE, description="Hook decision.")
    reason: str | None = Field(default=None, description="Hook decision reason.")
    system_message: str | None = Field(default=None, description="Optional system message.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Hook metadata.")


@dataclass
class HookContext:
    event_type: HookEventType
    request: ToolCallRequest
    execution_context: ToolExecutionContext
    tool: DataTool | None = None
    result: ToolCallResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def hook_decision_from_policy(decision: PolicyDecision) -> HookDecision:
    if decision == PolicyDecision.ALLOW:
        return HookDecision.ALLOW
    if decision == PolicyDecision.ASK:
        return HookDecision.ASK
    if decision == PolicyDecision.DENY:
        return HookDecision.DENY
    return HookDecision.NONE
