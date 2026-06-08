from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from app.hooks.types import HookContext, HookEventType, HookResult


class Hook(ABC):
    name: ClassVar[str]
    event_type: ClassVar[HookEventType]

    def matcher(self, context: HookContext) -> bool:
        return context.event_type == self.event_type

    @abstractmethod
    def run(self, context: HookContext) -> HookResult:
        raise NotImplementedError

