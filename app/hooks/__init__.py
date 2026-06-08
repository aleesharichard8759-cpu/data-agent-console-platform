"""Runtime hook interfaces and default hooks."""

from app.hooks.base import Hook
from app.hooks.defaults import (
    AuditPostToolUseHook,
    AuditPreToolUseHook,
    DenySensitiveModelContextHook,
    MaskingPostToolUseHook,
    RequireApprovalHook,
    build_default_hook_manager,
)
from app.hooks.manager import HookManager
from app.hooks.types import HookContext, HookDecision, HookEventType, HookResult

__all__ = [
    "AuditPostToolUseHook",
    "AuditPreToolUseHook",
    "DenySensitiveModelContextHook",
    "Hook",
    "HookContext",
    "HookDecision",
    "HookEventType",
    "HookManager",
    "HookResult",
    "MaskingPostToolUseHook",
    "RequireApprovalHook",
    "build_default_hook_manager",
]
