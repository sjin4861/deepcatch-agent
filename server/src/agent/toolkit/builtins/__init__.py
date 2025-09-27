from .call import CallTool
from .fish import FishInsightsTool
from .planner import PlannerTool
from .weather import WeatherTool

__all__ = [
    "CallTool",
    "FishInsightsTool",
    "PlannerTool",
    "WeatherTool",
    "default_tools",
    "create_default_registry",
]


def default_tools():
    return [
        WeatherTool(),
        FishInsightsTool(),
        PlannerTool(),
        CallTool(),
    ]


def create_default_registry():
    from ..registry import ToolRegistry

    return ToolRegistry(default_tools())
