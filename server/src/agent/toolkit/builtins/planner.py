from __future__ import annotations

from typing import Optional

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import ConversationState, FishingPlanDetails, PlanSnapshot
from ...planner import planner_agent
from ...tool_results import make_tool_result


class PlannerTool(BaseTool):
    name = "planner"
    priority = 30

    def applies_to(self, context: ToolContext) -> bool:
        actions = context.state.get("action_queue", [])
        missing = context.state.get("missing_keys", [])
        return "planner" in actions or bool(missing)

    def execute(self, context: ToolContext) -> ToolOutput:
        snapshot = self._ensure_snapshot(context)
        plan_details = snapshot.details
        message = context.state.get("message", "")

        result = planner_agent.process(message, plan_details)
        new_stage = "collecting" if result["missing"] else "ready"
        updated_snapshot = context.services.persist_plan(
            snapshot.record,
            result["details"],
            new_stage,
            result["db_updates"],
        )

        output = ToolOutput(
            updates={
                "plan_snapshot": updated_snapshot,
                "plan_record": updated_snapshot.record,
                "plan_details": result["details"],
                "missing_keys": result["missing"],
                "stage": new_stage,
            }
        )
        output.add_tool_result(
            make_tool_result(
                tool="planner_agent",
                title="낚시 계획 업데이트",
                content="\n".join(result["summary_lines"]),
                metadata={
                    "plan": result["details"].to_dict(),
                    "missing": result["missing"],
                },
            )
        )
        # 계획이 모두 채워졌고 아직 전화 stage가 아니며 call action이 큐에 없다면 call 예약 액션 추가
        if not result["missing"] and context.state.get('stage') not in ('calling','completed'):
            existing_actions = context.state.get('action_queue', [])
            if 'call' not in existing_actions:
                output.add_follow_up_action('call')
        return output

    @staticmethod
    def _ensure_snapshot(context: ToolContext) -> PlanSnapshot:
        snapshot: Optional[PlanSnapshot] = context.state.get("plan_snapshot")
        if snapshot is not None:
            return snapshot
        return context.services.load_plan()


__all__ = ["PlannerTool"]
