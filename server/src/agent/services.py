from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import crud, models as orm_models
from ..twilio_client import get_twilio
from .conversation_models import CallSummary, FishingPlanDetails, PlanSnapshot
from src.config import settings

# ------------------------------------------------------------------
# Optional in-memory runtime buffers (status + transcript)
# ------------------------------------------------------------------
try:  # pragma: no cover - guard for packaging / circular import
    from . import call_runtime
except Exception:  # pragma: no cover
    call_runtime = None  # type: ignore


@dataclass
class BusinessSelection:
    business: orm_models.Business | None
    candidates: List[orm_models.Business]


class AgentServices:
    """Domain-facing operations shared across conversation tools and flows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ----------------------------------------------------------------------------------
    # Plan management
    # ----------------------------------------------------------------------------------
    def load_plan(self) -> PlanSnapshot:
        plan = crud.get_plan(self.db)
        stage = plan.status or "collecting"
        details = FishingPlanDetails()
        call_summary: Optional[CallSummary] = None

        if plan.status:
            try:
                payload = json.loads(plan.status)
            except json.JSONDecodeError:
                payload = {"stage": plan.status}
            if isinstance(payload, dict):
                stage = payload.get("stage", stage)
                plan_payload = payload.get("plan")
                if isinstance(plan_payload, dict):
                    details = FishingPlanDetails(
                        **{
                            key: plan_payload.get(key)
                            for key in FishingPlanDetails().__dict__.keys()
                        }
                    )
                call_payload = payload.get("call")
                if isinstance(call_payload, dict):
                    call_summary = CallSummary(**call_payload)

        if not details.location:
            details.location = plan.location or "구룡포"
        if plan.date and not details.date:
            details.date = plan.date
        if plan.time and not details.time:
            details.time = plan.time
        if plan.people and not details.participants_total:
            details.participants_total = plan.people
        if plan.phone_user and not details.phone_user:
            details.phone_user = plan.phone_user

        return PlanSnapshot(
            record=plan,
            details=details,
            stage=stage,
            call_summary=call_summary,
        )

    def persist_plan(
        self,
        plan: orm_models.Plan,
        details: FishingPlanDetails,
        stage: str,
        db_updates: Dict[str, Any],
        *,
        call_summary: Optional[CallSummary] = None,
    ) -> PlanSnapshot:
        if db_updates:
            crud.update_plan_from_dict(self.db, plan, db_updates)

        payload: Dict[str, Any] = {
            "stage": stage,
            "plan": details.to_dict(),
        }
        if call_summary is not None:
            payload["call"] = call_summary.to_dict()

        plan.status = json.dumps(payload, ensure_ascii=False)
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)

        return PlanSnapshot(
            record=plan,
            details=details,
            stage=stage,
            call_summary=call_summary,
        )

    # ----------------------------------------------------------------------------------
    # Businesses / calls
    # ----------------------------------------------------------------------------------
    def list_businesses(self, *, location: Optional[str] = None) -> List[orm_models.Business]:
        return crud.list_businesses(self.db, location=location)

    def list_business_names(self, *, location: Optional[str] = None) -> List[str]:
        return [business.name for business in self.list_businesses(location=location)]

    def pick_business(
        self,
        *,
        details: FishingPlanDetails,
        preferred_name: Optional[str] = None,
    ) -> BusinessSelection:
        # 1) 위치 정규화
        loc = (details.location or "").strip()
        if loc:
            # 간단한 로마자/한글 매핑 (확장 가능)
            normalized_map = {
                "guryongpo": "구룡포",
                "구룡포": "구룡포",
            }
            key = loc.lower()
            if key in normalized_map:
                loc = normalized_map[key]

        # 2) 1차: 위치 기반 필터
        businesses = self.list_businesses(location=loc) if loc else self.list_businesses()

        # 3) 위치에서 결과 없으면 전체 fallback
        if not businesses:
            all_list = self.list_businesses()
            businesses = all_list

        # 4) 선호 상호명 매칭 (부분 포함 허용)
        if preferred_name:
            lowered_pref = preferred_name.lower()
            # 완전 일치 우선
            for candidate in businesses:
                if candidate.name.lower() == lowered_pref:
                    return BusinessSelection(business=candidate, candidates=businesses)
            # 부분 포함
            for candidate in businesses:
                if candidate.name.lower() in lowered_pref or lowered_pref in candidate.name.lower():
                    return BusinessSelection(business=candidate, candidates=businesses)

        # 5) 최종: 첫 번째 선택 (없으면 None)
        return BusinessSelection(
            business=businesses[0] if businesses else None,
            candidates=businesses,
        )

    def start_reservation_call(
        self,
        *,
        details: FishingPlanDetails,
        preferred_name: Optional[str] = None,
    ) -> CallSummary:
        selection = self.pick_business(details=details, preferred_name=preferred_name)
        business = selection.business
        if business is None:
            return CallSummary(
                success=False,
                business_name="(업체 정보 없음)",
                status="no_business",
                message="등록된 낚시점이 없어 전화를 연결하지 못했어요. (DB 비어있거나 위치 필터 결과 없음)",
            )
        # --- Twilio webhook URL 구성 ---
        # 기존에는 환경변수 URL 을 사용했으나 Twilio Error 21205 (invalid URL: http://localhost) 발생 → 공개 https 필요
        twilio = get_twilio()
        base_url = settings.twilio_webhook_url or os.getenv("TWILIO_WEBHOOK_URL") or os.getenv("URL") or "http://localhost:8000"
        if base_url.endswith('/'):
            base_url = base_url.rstrip('/')
        # 로컬 주소면 경고 및 시뮬레이션 처리 유도
        simulated_local = False
        if base_url.startswith("http://localhost") or base_url.startswith("http://127.0.0.1"):
            # Twilio 는 퍼블릭 접근 가능한 https 만 허용 → 강제 안내
            simulated_local = True
        webhook = f"{base_url}/voice/start"
        call_data = twilio.start_call(business.phone, webhook)
        success = call_data.get("status") not in {"failed", "busy"}
        if call_data.get("sid") == "SIMULATED":
            message = "Twilio가 비활성화되어 시뮬레이션으로 처리했습니다."
        elif simulated_local:
            message = "로컬 URL(webhook)이 Twilio에서 거부될 수 있어 연결이 제한될 수 있습니다. ngrok 또는 공개 https 도메인을 설정하세요."
        else:
            message = "예약 담당자에게 연결을 시도했습니다."
        return CallSummary(
            success=success,
            business_name=business.name,
            status=call_data.get("status", "unknown"),
            sid=call_data.get("sid"),
            message=message,
            phone=business.phone,
        )

    # ------------------------------------------------------------------
    # Call Graph integration helpers (stubs / simplified adapters)
    # ------------------------------------------------------------------
    def now_iso(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def peek_call_status(self, call_sid: Optional[str]) -> Optional[str]:  # pragma: no cover - simple stub
        if not call_sid:
            return None
        if not call_runtime:
            return None
        return call_runtime.get_status(call_sid)

    def drain_transcript_buffer(self, call_sid: Optional[str]):  # pragma: no cover - stub
        if not call_sid or not call_runtime:
            return []
        return call_runtime.drain_transcript(call_sid)

    def call_completed(self, call_sid: Optional[str]) -> bool:  # pragma: no cover - stub
        if not call_sid or not call_runtime:
            return False
        return call_runtime.is_final(call_sid)

    def extract_slots_from_transcript(self, transcript):  # pragma: no cover - stub
        from .call_graph.models import ExtractedSlots
        # Improved heuristic extraction
        import re
        window = transcript[-12:]
        price = None
        capacity = None
        departure = None
        notes = []
        # 패턴 정의
        price_pattern = re.compile(r"(\d{1,3}(?:,\d{3})*|\d+)(?:\s*)(만원|만 원|만|원)")
        capacity_pattern = re.compile(r"(\d{1,2})\s*(명|인)")
        time_pattern = re.compile(r"(\d{1,2})\s*시\s*(\d{1,2})?\s*분?")
        for turn in window:
            text = turn.text
            if price is None:
                m = price_pattern.search(text)
                if m:
                    price = m.group(0)
            if capacity is None:
                m2 = capacity_pattern.search(text)
                if m2:
                    try:
                        capacity = int(m2.group(1))
                    except ValueError:
                        capacity = None
            if departure is None:
                if any(k in text for k in ["출발", "출항", "집결", "모임"]):
                    # 시간 구문이 같이 있으면 추출
                    mt = time_pattern.search(text)
                    departure = mt.group(0) if mt else text
            if any(k in text for k in ["날씨", "바람", "물때"]):
                notes.append(text)
        if notes and len(notes) > 2:
            notes = notes[:2]
        return ExtractedSlots(price_quote=price, capacity_confirmed=capacity, departure_time=departure, conditions_notes=" | ".join(notes) if notes else None)

    # ------------------------------------------------------------------
    # Runtime ingestion helpers (to be called by webhook handlers)
    # ------------------------------------------------------------------
    def record_transcript_turn(self, call_sid: Optional[str], speaker: str, text: str):  # pragma: no cover
        if not call_sid or not text or not call_runtime:
            return
        call_runtime.append_transcript(call_sid, speaker, text)

    def update_call_status(self, call_sid: Optional[str], status: str):  # pragma: no cover
        if not call_sid or not status or not call_runtime:
            return
        call_runtime.update_status(call_sid, status)

    # ----------------------------------------------------------------------------------
    # Utility helpers
    # ----------------------------------------------------------------------------------
    @staticmethod
    def resolve_target_date(date_text: Optional[str]) -> datetime.date:
        today = datetime.utcnow().date()
        if not date_text:
            return today + timedelta(days=1)

        lowered = date_text.lower()
        if "오늘" in lowered or "today" in lowered:
            return today
        if "모레" in lowered:
            return today + timedelta(days=2)
        if "내일" in lowered or "tomorrow" in lowered:
            return today + timedelta(days=1)

        match = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", date_text)
        if match:
            month, day = match.groups()
            year = today.year
            try:
                candidate = datetime(year=year, month=int(month), day=int(day)).date()
            except ValueError:
                candidate = today
            if candidate < today:
                candidate = datetime(year=year + 1, month=int(month), day=int(day)).date()
            return candidate

        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_text)
        if match:
            year, month, day = map(int, match.groups())
            try:
                return datetime(year=year, month=month, day=day).date()
            except ValueError:
                return today + timedelta(days=1)

        return today + timedelta(days=3)
