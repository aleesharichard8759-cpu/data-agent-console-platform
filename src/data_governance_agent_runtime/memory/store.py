from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeMemory:
    """Small in-memory task memory. Persistent adapters can replace this later."""

    facts: dict[str, str] = field(default_factory=dict)

    def remember(self, key: str, value: str) -> None:
        self.facts[key] = value

    def compact(self, max_items: int = 20) -> dict[str, str]:
        items = list(self.facts.items())[-max_items:]
        self.facts = dict(items)
        return dict(self.facts)

