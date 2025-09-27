from __future__ import annotations
"""Utility functions to test CallExecutionAgent directly without planner tool.

Provides a simple function `run_call_flow` you can import in a REPL or
expose through a temporary FastAPI endpoint for manual QA.
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from .services import AgentServices
from .call_graph import CallExecutionAgent
from .conversation_models import FishingPlanDetails, CallSummary
import logging
logger = logging.getLogger(__name__)


def build_minimal_plan(
    *,
    date: str = "2025-10-03",
    fishing_type: str = "선상",
    budget: str = "20만원",
    gear: str = "있음",
    transportation: str = "자차",
    participants: int = 3,
    target_species: str = "고등어",
    location: str = "구룡포",
) -> FishingPlanDetails:
    """현재 PlannerAgent 의 FishingPlanDetails 스키마(단일 participants 필드)에 맞춘 최소 플랜 구성.

    과거 participants_adults/children/total 필드는 제거됨. 테스트 목적상 participants 기본값 3 사용.
    phone_user 는 현재 통화 플로우에서 직접 사용되지 않지만 레거시 호환을 위해 매개변수 유지.
    """
    return FishingPlanDetails(
        date=date,
        fishing_type=fishing_type,
        budget=budget,
        gear=gear,
        transportation=transportation,
        participants=participants,
        target_species=target_species,
        location=location,
    )


def run_call_flow(db: Session, *, shop_name: Optional[str] = None, simulate: bool = False) -> Dict[str, Any]:
    """Execute the call sub-graph standalone.

    simulate=True 일 경우 실제 Twilio 호출을 피하고 가짜 성공 상태를 반환.
    예외 발생 시 500을 직접 던지지 않고 result dict 안에 error로 캡슐화.
    """
    services = AgentServices(db)
    # 테스트 전용: 사용자 연락처는 더 이상 발신/수신 대상이 아니므로 placeholder 사용
    plan = build_minimal_plan()

    # simulate=True 여도 이제는 실제 call 실행 로직을 그대로 태우되, Twilio 호출만 가짜로 대체
    original_start_call = services.start_reservation_call
    if simulate:
        logger.warning("[run_call_flow] Simulation mode: Twilio outbound replaced with fake start_reservation_call")

        def fake_start_reservation_call(*, details, preferred_name=None):  # type: ignore
            selection = services.pick_business(details=details, preferred_name=preferred_name)
            business = selection.business
            if business is None:
                return CallSummary(
                    success=False,
                    business_name="(업체 없음)",
                    status="no_business",
                    message="시뮬레이션: 비즈니스 선택 실패",
                )
            return CallSummary(
                success=True,
                business_name=business.name,
                status="completed",
                sid="SIMULATED-CALL",
                message="시뮬레이션 통화 완료",
                phone=business.phone,
            )

        services.start_reservation_call = fake_start_reservation_call  # type: ignore[attr-defined]

    try:
        # 사전 비즈니스 후보 로깅 (문제 진단용)
        pre_candidates = services.list_business_names(location=plan.location)
        logger.info("[run_call_flow] location=%s initial_candidates=%s", plan.location, pre_candidates)
        if not pre_candidates:
            all_names = services.list_business_names()
            logger.info("[run_call_flow] fallback all_candidates=%s", all_names)

        agent = CallExecutionAgent(services)
        result = agent.run({
            'call_plan_details': plan,
            'shop_name': shop_name,
            # phone 제거: CallExecutionAgent 내부에서 상점 선택 후 Twilio 호출
        })
        return {
            'state': str(result.state),
            'call_sid': result.call_sid,
            'shop_name': result.shop_name,
            'started_at': result.started_at,
            'ended_at': result.ended_at,
            'transcript_len': len(result.transcript),
            'transcript_preview': [
                { 'speaker': t.speaker, 'text': t.text } for t in result.transcript[:6]
            ],
            'slots': result.slots.to_dict(),
            'error': result.message,
            'simulated': simulate,
            'candidate_count': len(pre_candidates),
        }
    except Exception as exc:
        logger.exception("[run_call_flow] Call execution failed")
        return {
            'state': 'failed',
            'call_sid': None,
            'shop_name': shop_name,
            'started_at': None,
            'ended_at': None,
            'transcript_len': 0,
            'slots': {},
            'error': str(exc),
            'simulated': False,
        }
