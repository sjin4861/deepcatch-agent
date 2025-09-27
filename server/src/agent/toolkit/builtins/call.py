from __future__ import annotations

from typing import Optional

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import CallSummary, PlanSnapshot


class CallTool(BaseTool):
    name = "call"
    priority = 40

    def applies_to(self, context: ToolContext) -> bool:
        actions = context.state.get("action_queue", [])
        return "call" in actions

    def execute(self, context: ToolContext) -> ToolOutput:
        snapshot = self._ensure_snapshot(context)
        details = snapshot.details
        preferred = context.state.get("preferred_business")

        summary = context.services.start_reservation_call(
            details=details,
            preferred_name=preferred,
        )

        stage = "completed" if summary.success else "calling"
        updated_snapshot = context.services.persist_plan(
            snapshot.record,
            details,
            stage,
            {},
            call_summary=summary,
        )

        output = ToolOutput(
            updates={
                "plan_snapshot": updated_snapshot,
                "plan_record": updated_snapshot.record,
                "plan_details": updated_snapshot.details,
                "call_result": summary,
                "stage": stage,
            }
        )
        output.add_tool_result(summary.as_tool_result())
        return output

    @staticmethod
    def _ensure_snapshot(context: ToolContext) -> PlanSnapshot:
        snapshot: Optional[PlanSnapshot] = context.state.get("plan_snapshot")
        if snapshot is not None:
            return snapshot
        return context.services.load_plan()


__all__ = ["CallTool"]
