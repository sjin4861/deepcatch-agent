from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.config import logger
from src import fishery_api

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

        forecast = fishery_api.get_chuseok_holiday_forecast()
        logger.info(
            "[Tool:weather] holiday forecast loaded source=%s days=%s",
            forecast.source,
            len(forecast.days),
        )

        day_lookup = {day.date: day for day in forecast.days}
        best_payload = forecast.best.dict()
        best_day = day_lookup.get(forecast.best.date) if forecast.days else None
        if best_day is None and forecast.days:
            best_day = forecast.days[0]

        def _format_events(events: list) -> str:
            if not events:
                return "--"
            return ", ".join(f"{event.time} ({event.height:.2f}m)" for event in events)

        holiday_days_payload: List[Dict[str, Any]] = []
        for day in forecast.days:
            holiday_days_payload.append(
                {
                    "date": day.date,
                    "label": day.label,
                    "weekday": day.weekday,
                    "condition": day.condition,
                    "summary": day.summary,
                    "tempMin": round(day.temp_min, 1),
                    "tempMax": round(day.temp_max, 1),
                    "windSpeed": round(day.wind_speed, 1),
                    "windDirection": day.wind_direction,
                    "waveHeight": round(day.wave_height, 2),
                    "precipitationChance": day.precipitation_chance,
                    "tidePhase": day.tide_phase,
                    "moonAge": round(day.moon_age, 1),
                    "sunrise": day.sunrise,
                    "sunset": day.sunset,
                    "bestWindow": day.best_window,
                    "cautionWindow": day.caution_window,
                    "highTides": [
                        {"time": ev.time, "height": ev.height}
                        for ev in day.high_tides
                    ],
                    "lowTides": [
                        {"time": ev.time, "height": ev.height}
                        for ev in day.low_tides
                    ],
                    "comfortScore": round(day.comfort_score, 1),
                }
            )

        holiday_chart_payload = [
            {
                "date": point.date,
                "label": point.label,
                "windSpeed": round(point.wind_speed, 1),
                "waveHeight": round(point.wave_height, 2),
                "tempMin": round(point.temp_min, 1),
                "tempMax": round(point.temp_max, 1),
                "precipitationChance": point.precipitation_chance,
                "comfortScore": round(point.comfort_score, 1),
            }
            for point in forecast.chart
        ]

        best_window = best_day.best_window if best_day else best_window
        tide_phase = best_day.tide_phase if best_day else None
        moon_age = best_day.moon_age if best_day else None
        sunrise_value = best_day.sunrise if best_day else sunrise
        target_display = (
            f"{best_day.date} ({best_day.weekday})" if best_day else display_date
        )
        wind = (
            f"평균 풍속 {best_day.wind_speed:.1f} m/s ({best_day.wind_direction}), 파고 {best_day.wave_height:.1f} m"
            if best_day
            else wind
        )
        tide = (
            f"{best_day.tide_phase} · 만조 {_format_events(best_day.high_tides)} / 간조 {_format_events(best_day.low_tides)}"
            if best_day
            else tide
        )
        summary = (
            f"{forecast.best.label}: {forecast.best.reason}"
            if forecast.best and forecast.best.reason
            else summary
        )

        report = WeatherReport(
            target_date=target_display,
            sunrise=sunrise_value,
            wind=wind,
            tide=tide,
            best_window=best_window,
            summary=summary,
            tide_phase=tide_phase,
            moon_age=moon_age,
            holiday_range=forecast.range_label,
            holiday_days=holiday_days_payload,
            holiday_chart=holiday_chart_payload,
            holiday_best={
                "date": best_payload.get("date"),
                "label": best_payload.get("label"),
                "reason": best_payload.get("reason"),
                "score": best_payload.get("score"),
            },
            holiday_advisories=forecast.advisories,
            holiday_source=forecast.source,
        )

        # Planner 로 date 채워 넣기 (없으면)
        updates = {"weather": report}
        if not details.date:
            details.date = target_date.isoformat()
            updates["plan_details"] = details

        output = ToolOutput(updates=updates)
        output.add_tool_result(report.as_tool_result())
        logger.info(
            "[Tool:weather] 실행 완료 target_date=%s wind='%s' tide='%s' summary='%s'",
            display_date,
            wind,
            tide,
            summary,
        )
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
