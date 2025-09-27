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


@dataclass
class BusinessSelection:
    business: orm_models.Business | None
    candidates: List[orm_models.Business]


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
                    legacy_total = plan_payload.get("participants_total")
                    if details.participants is None and legacy_total is not None:
                        try:
                            details.participants = int(legacy_total)
                        except (TypeError, ValueError):
                            details.participants = None
                    if details.participants is None:
                        adults = plan_payload.get("participants_adults")
                        children = plan_payload.get("participants_children")
                        adult_val = _coerce_int(adults)
                        child_val = _coerce_int(children)
                        combined = (adult_val or 0) + (child_val or 0)
                        if combined > 0:
                            details.participants = combined
                call_payload = payload.get("call")
                if isinstance(call_payload, dict):
                    call_summary = CallSummary(**call_payload)

        if not details.location:
            details.location = plan.location or "구룡포"
        if plan.date and not details.date:
            details.date = plan.date
        if plan.time and not details.time:
            details.time = plan.time
        if plan.people is not None and details.participants is None:
            details.participants = plan.people
        if plan.departure and not details.departure:
            details.departure = plan.departure

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
        businesses = self.list_businesses(location=details.location)
        if preferred_name:
            lower = preferred_name.lower()
            for candidate in businesses:
                if candidate.name.lower() in lower:
                    return BusinessSelection(business=candidate, candidates=businesses)
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
                message="등록된 낚시점이 없어 전화를 연결하지 못했어요.",
            )

        twilio = get_twilio()
        base_url = os.getenv("URL", "http://localhost:8000")
        webhook = f"{base_url}/voice/start"
        call_data = twilio.start_call(business.phone, webhook)
        success = call_data.get("status") not in {"failed", "busy"}
        message = (
            "Twilio가 비활성화되어 시뮬레이션으로 처리했습니다."
            if call_data.get("sid") == "SIMULATED"
            else "예약 담당자에게 연결을 시도했습니다."
        )
        return CallSummary(
            success=success,
            business_name=business.name,
            status=call_data.get("status", "unknown"),
            sid=call_data.get("sid"),
            message=message,
        )

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
