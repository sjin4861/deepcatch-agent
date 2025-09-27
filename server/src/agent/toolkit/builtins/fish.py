from __future__ import annotations

from typing import Optional

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import FishReport, FishingPlanDetails


class FishInsightsTool(BaseTool):
    name = "fish"
    priority = 20

    def applies_to(self, context: ToolContext) -> bool:
        actions = context.state.get("action_queue", [])
        return "fish" in actions

    def execute(self, context: ToolContext) -> ToolOutput:
        details = self._resolve_details(context)
        base_species = [
            {"name": "고등어", "count": 24},
            {"name": "한치", "count": 8},
            {"name": "갑오징어", "count": 6},
        ]
        note = "초가을 어군이 가까이 붙어 있어 선상 라이트지깅이 유리합니다."
        if details.target_species:
            note += f" 특히 {details.target_species} 조황이 좋은 편입니다."

        report = FishReport(species=base_species, note=note)

        output = ToolOutput(updates={"fish_info": report})
        output.add_tool_result(report.as_tool_result())
        return output

    @staticmethod
    def _resolve_details(context: ToolContext) -> FishingPlanDetails:
        details: Optional[FishingPlanDetails] = context.state.get("plan_details")
        if details is not None:
            return details
        snapshot = context.state.get("plan_snapshot")
        if snapshot is None:
            snapshot = context.services.load_plan()
        return snapshot.details


__all__ = ["FishInsightsTool"]
