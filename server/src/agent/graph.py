from __future__ import annotations

from typing import Callable, Dict, Optional

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from .conversation_models import ConversationState
from .nodes import chat_agent_node, compose_response_node, tool_runner_node
from .services import AgentServices
from .toolkit import ToolRegistry
from .toolkit.builtins import create_default_registry
from .types import ChatResponse

RegistryFactory = Callable[[], ToolRegistry]


def build_fishing_planner_graph() -> CompiledStateGraph:
    graph = StateGraph(ConversationState)
    graph.add_node("chat_agent", chat_agent_node)
    graph.add_node("tool_runner", tool_runner_node)
    graph.add_node("compose_response", compose_response_node)

    graph.set_entry_point("chat_agent")
    graph.add_edge("chat_agent", "tool_runner")
    graph.add_edge("tool_runner", "compose_response")
    graph.add_edge("compose_response", END)

    return graph.compile()


class FishingPlannerAgent:
    """High-level facade exposing the unified LangGraph agent."""

    def __init__(
        self,
        *,
        registry_factory: RegistryFactory | None = None,
    ) -> None:
        self._graph = build_fishing_planner_graph()
        self._registry_factory = registry_factory or create_default_registry

    def __call__(
        self,
        *,
        message: str,
        db: Session,
        extra_state: Optional[Dict[str, object]] = None,
    ) -> ChatResponse:
        services = AgentServices(db)
        initial_state: ConversationState = {
            "message": message,
            "services": services,
            "tools": services,
            "tool_registry": self._registry_factory(),
            "tool_results": [],
        }
        if extra_state:
            initial_state.update(extra_state)

        state = self._graph.invoke(initial_state)
        response = state.get("response")
        if isinstance(response, ChatResponse):
            return response
        raise RuntimeError("에이전트가 유효한 응답을 생성하지 못했습니다.")


PlanAgent = FishingPlannerAgent
build_plan_agent = build_fishing_planner_graph

__all__ = [
    "FishingPlannerAgent",
    "PlanAgent",
    "build_fishing_planner_graph",
    "build_plan_agent",
]