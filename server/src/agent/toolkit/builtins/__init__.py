from .call import CallTool
from .fish import FishInsightsTool
from .planner import PlannerTool
from .weather import WeatherTool
from .map_route import MapRouteTool

__all__ = [
    "CallTool",
    "FishInsightsTool",
    "PlannerTool",
    "WeatherTool",
    "MapRouteTool",
    "default_tools",
    "create_default_registry",
]


def default_tools():
    return [
        WeatherTool(),
        FishInsightsTool(),
        PlannerTool(),
        MapRouteTool(),
        CallTool(),
    ]


def create_default_registry():
    from ..registry import ToolRegistry

    return ToolRegistry(default_tools())
