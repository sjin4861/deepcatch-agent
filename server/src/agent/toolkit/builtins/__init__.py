from .call import CallTool
from .fishery_catch import FisheryCatchTool
from .map_route import MapRouteTool
from .planner import PlannerTool
from .weather import WeatherTool

__all__ = [
    "CallTool",
    "FisheryCatchTool",
    "PlannerTool",
    "WeatherTool",
    "MapRouteTool",
    "default_tools",
    "create_default_registry",
]


def default_tools():
    return [
        WeatherTool(),
        FisheryCatchTool(),
        PlannerTool(),
        MapRouteTool(),
        CallTool(),
    ]


def create_default_registry():
    from ..registry import ToolRegistry

    return ToolRegistry(default_tools())
