from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..conversation_models import ConversationState
    from ..services import AgentServices
    from ..types import ChatToolResult
else:  # pragma: no cover - runtime fallbacks
    ConversationState = Dict[str, Any]  # type: ignore
    AgentServices = Any  # type: ignore
    ChatToolResult = Any  # type: ignore


@dataclass
class ToolContext:
    """Runtime context supplied to tools during execution."""

    services: AgentServices
    state: ConversationState

    def with_updates(self, **overrides: Any) -> "ToolContext":
        """Return a shallow copy with overridden state values."""

        merged_state: ConversationState = {
            **self.state,
            **overrides,
        }
        return ToolContext(services=self.services, state=merged_state)


@dataclass
class ToolOutput:
    """Result object returned from a tool execution."""

    updates: Dict[str, Any] = field(default_factory=dict)
    tool_results: List[ChatToolResult] = field(default_factory=list)
    follow_up_actions: List[str] = field(default_factory=list)

    def add_update(self, key: str, value: Any) -> None:
        self.updates[key] = value

    def add_tool_result(self, result: ChatToolResult) -> None:
        self.tool_results.append(result)

    def extend(self, other: "ToolOutput") -> None:
        self.updates.update(other.updates)
        self.tool_results.extend(other.tool_results)
        self.follow_up_actions.extend(other.follow_up_actions)


@runtime_checkable
class ConversationTool(Protocol):
    """Protocol describing the interface required for conversation tools."""

    name: str
    priority: int

    def applies_to(self, context: ToolContext) -> bool:
        """Return True if the tool should run for the given context."""

    def execute(self, context: ToolContext) -> ToolOutput:
        """Run the tool and return conversation state updates."""


class BaseTool:
    """Convenience base class providing defaults for common properties."""

    name: str = "tool"
    priority: int = 100

    def applies_to(self, context: ToolContext) -> bool:  # pragma: no cover - default
        return True

    def execute(self, context: ToolContext) -> ToolOutput:  # pragma: no cover - abstract
        raise NotImplementedError


__all__ = [
    "ToolContext",
    "ToolOutput",
    "ConversationTool",
    "BaseTool",
]
