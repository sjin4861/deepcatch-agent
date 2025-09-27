from __future__ import annotations

from typing import Dict, Iterable, Iterator, List, Optional, Sequence

from .base import ConversationTool


class ToolRegistry:
    """Simple registry/lookup for conversation tools."""

    def __init__(self, tools: Optional[Iterable[ConversationTool]] = None) -> None:
        self._tools: Dict[str, ConversationTool] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: ConversationTool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ConversationTool]:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self) -> Iterator[ConversationTool]:
        return iter(self.sorted())

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def sorted(self) -> List[ConversationTool]:
        return sorted(self._tools.values(), key=lambda tool: getattr(tool, "priority", 100))

    def by_action_sequence(self, actions: Sequence[str]) -> List[ConversationTool]:
        """Return tools ordered first by explicit actions, then by priority."""

        seen = set()
        ordered: List[ConversationTool] = []

        for action in actions:
            tool = self._tools.get(action)
            if tool and tool.name not in seen:
                ordered.append(tool)
                seen.add(tool.name)

        for tool in self.sorted():
            if tool.name not in seen:
                ordered.append(tool)
                seen.add(tool.name)

        return ordered


__all__ = ["ToolRegistry"]
