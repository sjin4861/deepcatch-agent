from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .conversation_models import (
    CallSummary,
    ConversationState,
    FRIENDLY_LABELS,
    FishingPlanDetails,
    PlanSnapshot,
)
from .openai_client import get_openai_client
from .services import AgentServices
from .toolkit import ToolContext, ToolRegistry
from .toolkit.builtins import create_default_registry
from .types import ChatResponse

logger = logging.getLogger(__name__)


def determine_actions(message: str, missing_keys: List[str]) -> List[str]:
    lowered = message.lower()
    actions: List[str] = []
    if any(keyword in lowered for keyword in ["weather", "tide", "날씨", "물때", "기상"]):
        actions.append("weather")
    if any(keyword in lowered for keyword in ["fish", "어종", "조황", "물고기"]):
        actions.append("fish")
    if any(keyword in lowered for keyword in ["plan", "계획", "예약", "인원", "budget", "예산"]):
        actions.append("planner")
    if any(keyword in lowered for keyword in ["call", "전화", "연결", "예약해", "contact"]):
        actions.append("call")
    if any(keyword in lowered for keyword in ["map", "route", "지도", "길찾기", "경로"]):
        actions.append("map_route_generation_api")
    if not actions or missing_keys:
        if "planner" not in actions:
            actions.insert(0, "planner")
    return actions


def detect_business_name(message: str, candidates: List[str]) -> Optional[str]:
    lowered = message.lower()
    for candidate in candidates:
        if candidate.lower() in lowered:
            return candidate
    return None


def _ensure_services(state: ConversationState) -> AgentServices:
    services = state.get("services") or state.get("tools")
    if not isinstance(services, AgentServices):  # type: ignore[arg-type]
        raise RuntimeError("AgentServices not provided in conversation state.")
    return services


def _ensure_registry(state: ConversationState) -> ToolRegistry:
    registry = state.get("tool_registry")
    if isinstance(registry, ToolRegistry):
        return registry
    registry = create_default_registry()
    state["tool_registry"] = registry
    return registry


def _resolve_snapshot(state: ConversationState, services: AgentServices) -> PlanSnapshot:
    snapshot = state.get("plan_snapshot")
    if isinstance(snapshot, PlanSnapshot):
        return snapshot
    snapshot = services.load_plan()
    state["plan_snapshot"] = snapshot
    return snapshot


def chat_agent_node(state: ConversationState) -> ConversationState:
    services = _ensure_services(state)
    snapshot = _resolve_snapshot(state, services)
    missing_keys = snapshot.details.missing_keys()
    actions = determine_actions(state["message"], missing_keys)
    business_names = services.list_business_names(location=snapshot.details.location)
    preferred_business = detect_business_name(state["message"], business_names)

    next_state: ConversationState = {
        "services": services,
        "tools": services,  # Backward compatibility for legacy consumers
        "tool_registry": _ensure_registry(state),
        "plan_snapshot": snapshot,
        "plan_record": snapshot.record,
        "plan_details": snapshot.details,
        "stage": snapshot.stage,
        "missing_keys": missing_keys,
        "action_queue": actions,
        "tool_results": state.get("tool_results", []),
        "preferred_business": preferred_business,
    }
    if snapshot.call_summary:
        next_state["call_result"] = snapshot.call_summary
    return next_state


def tool_runner_node(state: ConversationState) -> ConversationState:
    services = _ensure_services(state)
    registry = _ensure_registry(state)

    tool_results = [*state.get("tool_results", [])]
    action_queue = list(state.get("action_queue", []))
    updates: Dict[str, Any] = {}
    # Track if plan_details already explicitly set by a tool to avoid multiple writes
    plan_details_written = False

    for tool in registry.by_action_sequence(action_queue):
        context = ToolContext(services=services, state={**state, **updates})
        if not tool.applies_to(context):
            continue

        output = tool.execute(context)
        updates.update(output.updates)
        # If this tool produced plan_details mark it so we don't overwrite later
        if "plan_details" in output.updates:
            plan_details_written = True
        tool_results.extend(output.tool_results)

        for action in output.follow_up_actions:
            if action not in action_queue:
                action_queue.append(action)
        updates["action_queue"] = action_queue

    if "plan_snapshot" not in updates:
        snapshot = state.get("plan_snapshot")
        if isinstance(snapshot, PlanSnapshot):
            updates["plan_snapshot"] = snapshot
    if "plan_record" not in updates and "plan_snapshot" in updates:
        updates["plan_record"] = updates["plan_snapshot"].record
    # Provide plan_details only if not already set this step to prevent concurrent multi-value assignment
    if not plan_details_written and "plan_details" not in updates and "plan_snapshot" in updates:
        updates["plan_details"] = updates["plan_snapshot"].details
    if "stage" not in updates and "plan_snapshot" in updates:
        updates["stage"] = updates["plan_snapshot"].stage

    updates["tool_results"] = tool_results
    updates.setdefault("action_queue", action_queue)

    return updates


def compose_response_node(state: ConversationState) -> ConversationState:
    plan = state.get("plan_details")
    missing = state.get("missing_keys", [])
    call_summary: Optional[CallSummary] = state.get("call_result")
    tool_results = state.get("tool_results", [])
    actions = state.get("action_queue", [])
    user_message = state.get("message", "")

    if call_summary:
        if call_summary.success:
            message = (
                f"{call_summary.business_name}와의 예약을 시도했고 상태는 '{call_summary.status}' 입니다. "
                "통화 로그를 확인해 주세요. 필요한 다른 도움이 있을까요?"
            )
        else:
            message = (
                f"{call_summary.business_name}에 전화 연결을 하지 못했습니다. "
                "다른 업체로 시도해 볼까요, 아니면 정보를 다시 확인해 드릴까요?"
            )
        call_suggested = False
    elif missing:
        lines = ["아래 정보를 알려주시면 맞춤형 계획을 완성할 수 있어요:"]
        for key in missing:
            label = FRIENDLY_LABELS.get(key, key)
            lines.append(f"- {label}")
        message = "\n".join(lines)
        call_suggested = False
    else:
        summary_lines = ["모든 준비가 완료되었습니다!", "정리된 계획:"]
        if plan:
            summary_lines.append(f"- 날짜: {plan.date or '미정'}")
            if plan.time:
                summary_lines.append(f"- 시간: {plan.time}")
            if getattr(plan, "departure", None):
                summary_lines.append(f"- 출발지: {plan.departure}")
            if getattr(plan, "participants", None) is not None:
                summary_lines.append(f"- 인원: {plan.participants}명")
            if plan.fishing_type:
                summary_lines.append(f"- 방식: {plan.fishing_type}")
            if plan.budget:
                summary_lines.append(f"- 예산: {plan.budget}")
            if plan.gear:
                summary_lines.append(f"- 장비: {plan.gear}")
            if plan.transportation:
                summary_lines.append(f"- 이동: {plan.transportation}")
            if plan.target_species:
                summary_lines.append(f"- 목표 어종: {plan.target_species}")
        if state.get("weather"):
            summary_lines.append("- 날씨/물때 정보가 도구 결과에 포함되어 있어요.")
        if state.get("fish_info"):
            summary_lines.append("- 최신 어종 상황을 함께 확인했습니다.")
        summary_lines.append("전화 연결을 원하시면 말씀만 해주세요!")
        message = "\n".join(summary_lines)
        call_suggested = "call" not in actions

    generated_message = message
    client = get_openai_client()
    if client.enabled:
        plan_dict = plan.to_dict() if isinstance(plan, FishingPlanDetails) else {}
        weather_dict = asdict(state["weather"]) if state.get("weather") else {}
        fish_dict = asdict(state["fish_info"]) if state.get("fish_info") else {}
        call_dict = call_summary.to_dict() if call_summary else {}

        try:
            generated_message = client.generate(
                prompt=(
                    "You are Guryongpo Fishing Assistant."
                    " Respond in friendly Korean, summarizing the plan and next steps."
                    " Always mention any missing information if present, and reference tool insights."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "user_message": user_message,
                                "plan": plan_dict,
                                "missing": missing,
                                "weather": weather_dict,
                                "fish": fish_dict,
                                "call": call_dict,
                                "call_suggested": call_suggested,
                                "fallback": message,
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
            )
        except Exception as exc:  # pragma: no cover - degraded path
            logger.warning("OpenAI chat generation failed: %s", exc)
            generated_message = message

    return {
        "response": ChatResponse(
            message=generated_message,
            toolResults=tool_results,
            callSuggested=call_suggested,
            stage=state.get("stage"),
        )
    }
