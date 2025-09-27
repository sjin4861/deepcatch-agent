from __future__ import annotations

from typing import Optional

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import CallSummary, PlanSnapshot
from ...call_graph import CallExecutionAgent


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

        # 새로운 CallExecutionAgent 사용
        agent = CallExecutionAgent(context.services)
        # 전화 대상 번호는 사용자 입력 연락처(phone_user)가 아니라 선택된 상점 번호여야 한다.
        # CallExecutionAgent 내부에서 실제 Twilio 호출은 services.start_reservation_call을 통해 수행되고,
        # 그 시점에 비즈니스 선택이 다시 이루어지므로 여기서는 phone을 전달하지 않는다 (잘못된 대상 방지를 위해 제거).
        call_result = agent.run({
            'call_plan_details': details,
            'shop_name': preferred,
            # 'phone' 제거: prepare_node에서 더 이상 필수 검사하지 않음
        })

        summary = CallSummary(
            success=call_result.state == 'completed',
            business_name=call_result.shop_name or (preferred or 'Unknown'),
            status=str(call_result.state),
            sid=call_result.call_sid,
            message=call_result.message,
        )
        stage = "completed" if summary.success else "calling"
        updated_snapshot = context.services.persist_plan(
            snapshot.record,
            details,
            stage,
            {},
            call_summary=summary,
        )
        # Tool result 확장: transcript/slots 요약
        transcript_preview = '\n'.join([
            f"{t.speaker}: {t.text}" for t in call_result.transcript[:6]
        ])
        meta = call_result.to_summary_dict()
        output = ToolOutput(
            updates={
                'plan_snapshot': updated_snapshot,
                'plan_record': updated_snapshot.record,
                'call_result': summary,
                'stage': stage,
                'call_transcript': [t.__dict__ for t in call_result.transcript],
                'call_slots': call_result.slots.to_dict(),
            }
        )
        tr_tool = summary.as_tool_result()
        tr_tool['metadata'].update({'transcript_preview': transcript_preview, 'slots': meta['slots']})
        output.add_tool_result(tr_tool)
        return output

    @staticmethod
    def _ensure_snapshot(context: ToolContext) -> PlanSnapshot:
        snapshot: Optional[PlanSnapshot] = context.state.get("plan_snapshot")
        if snapshot is not None:
            return snapshot
        return context.services.load_plan()


__all__ = ["CallTool"]
