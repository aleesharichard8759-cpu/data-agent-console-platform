from __future__ import annotations

from app.hooks.base import Hook
from app.hooks.types import HookContext, HookDecision, HookEventType, HookResult


class HookManager:
    def __init__(self, hooks: tuple[Hook, ...] | None = None) -> None:
        self._hooks: list[Hook] = list(hooks or ())

    def register_hook(self, hook: Hook) -> None:
        self._hooks.append(hook)

    def list_hooks(self) -> tuple[Hook, ...]:
        return tuple(self._hooks)

    def run_hooks(self, event_type: HookEventType, context: HookContext) -> HookResult:
        context.event_type = event_type
        metadata: dict[str, object] = {}
        for hook in self._hooks:
            if hook.event_type != event_type or not hook.matcher(context):
                continue
            result = hook.run(context)
            metadata[hook.name] = result.model_dump(mode="json")
            context.metadata.setdefault("hook_results", []).append(
                {"hook": hook.name, **result.model_dump(mode="json")}
            )
            if not result.continue_execution:
                return HookResult(
                    continue_execution=False,
                    decision=result.decision,
                    reason=result.reason,
                    system_message=result.system_message,
                    metadata=metadata,
                )
        return HookResult(
            continue_execution=True,
            decision=HookDecision.NONE,
            reason=None,
            system_message=None,
            metadata=metadata,
        )

