from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
import os
try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

from src.config import settings, logger

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import FishingPlanDetails, WeatherReport


class WeatherTool(BaseTool):
    name = "weather"
    priority = 10

    def applies_to(self, context: ToolContext) -> bool:
        actions = context.state.get("action_queue", [])
        return "weather" in actions

    def execute(self, context: ToolContext) -> ToolOutput:
        logger.info("[Tool:weather] 실행 시작 - action_queue=%s", context.state.get("action_queue"))
        details = self._resolve_details(context)
        target_date = context.services.resolve_target_date(details.date)
        display_date = target_date.strftime("%Y-%m-%d (%a)")

        # 외부 기상 API 연계 (ship-safe mock + 변환) 시도
        # 실패 시 기존 static fallback
        wind = "구룡포 해상 바람 데이터 불러오는 중..."  # placeholder
        tide = "물때 정보 수집 중"
        best_window = "--"
        summary = "기본 예보 로딩"
        sunrise = (
            datetime.combine(target_date, datetime.min.time()) + timedelta(hours=5, minutes=48)
        ).strftime("%H:%M")

        if httpx is not None:
            try:
                # ship-safe mock/실제 API (내부 FastAPI) 호출
                base_url = os.getenv("INTERNAL_API_BASE", "http://localhost:8000")
                date_param = target_date.strftime("%Y%m%d")
                with httpx.Client(timeout=5.0) as client:
                    r = client.get(f"{base_url}/api/v1/ship-safe/stats/history", params={"date": date_param})
                    if r.status_code == 200:
                        data = r.json()
                        top = data.get("data", {})
                        # 기존 mock 구조 (beforeDay/nowDay)
                        before = top.get("beforeDay") or {}
                        now = top.get("nowDay") or {}
                        temp = now.get("temp") or before.get("temp")
                        winsp = now.get("winsp") or before.get("winsp")
                        if winsp is not None:
                            wind = f"평균 풍속 {winsp} m/s"
                        if temp is not None:
                            summary = f"기온 {temp}°, 평균 풍속 {winsp} m/s 기준 오전 출조 권장"
                        tide = "(Mock) 물때 데이터 (추후 API 연동)"
                        best_window = "05:30~09:30" if (isinstance(winsp, (int, float)) and winsp < 6) else "이른 오전 (~08:00)"
                        logger.info("[Tool:weather] ship-safe fetch success temp=%s winsp=%s", temp, winsp)
                    else:
                        logger.warning(f"weather tool external api fallback status={r.status_code}")
            except Exception as e:  # pragma: no cover
                logger.debug(f"weather tool fetch failed: {e}")
                if not summary:
                    summary = "외부 기상 API 호출 실패로 기본 값을 사용합니다."
        else:
            logger.debug("httpx 미설치로 weather API 호출 스킵, static fallback 사용")

        report = WeatherReport(
            target_date=display_date,
            sunrise=sunrise,
            wind=wind,
            tide=tide,
            best_window=best_window,
            summary=summary,
        )

        # Planner 로 date 채워 넣기 (없으면)
        updates = {"weather": report}
        if not details.date:
            details.date = target_date.isoformat()
            updates["plan_details"] = details

        output = ToolOutput(updates=updates)
        output.add_tool_result(report.as_tool_result())
        logger.info("[Tool:weather] 실행 완료 target_date=%s wind='%s' tide='%s'", display_date, wind, tide)
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
