from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import FishingPlanDetails, WeatherReport


class WeatherTool(BaseTool):
    name = "weather"
    priority = 10

    def applies_to(self, context: ToolContext) -> bool:
        actions = context.state.get("action_queue", [])
        return "weather" in actions

    def execute(self, context: ToolContext) -> ToolOutput:
        details = self._resolve_details(context)
        target_date = context.services.resolve_target_date(details.date)
        display_date = target_date.strftime("%Y-%m-%d (%a)")
        sunrise = (
            datetime.combine(target_date, datetime.min.time()) + timedelta(hours=5, minutes=48)
        ).strftime("%H:%M")
        wind = "북동풍 4~6m/s"
        tide = "사리와 조금 사이, 오전에 물돌이"
        best_window = "05:30 ~ 09:30"
        summary = "오전엔 잔잔하고 오후에는 바람이 강해집니다. 오전 출조를 추천드려요."

        report = WeatherReport(
            target_date=display_date,
            sunrise=sunrise,
            wind=wind,
            tide=tide,
            best_window=best_window,
            summary=summary,
        )

        output = ToolOutput(updates={"weather": report})
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


__all__ = ["WeatherTool"]
