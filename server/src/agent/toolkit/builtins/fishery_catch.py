from __future__ import annotations

import re
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import FisheryCatchReport, FishingPlanDetails


@dataclass
class DateRange:
    start: date
    end: date
    label: str


class FisheryCatchTool(BaseTool):
    name = "fishery_catch"
    priority = 15

    def applies_to(self, context: ToolContext) -> bool:
        actions = context.state.get("action_queue", [])
        return "fishery_catch" in actions

    def execute(self, context: ToolContext) -> ToolOutput:
        details = self._resolve_details(context)
        message = context.state.get("message", "") or ""
        date_range = self._resolve_date_range(message, details, context)

        if date_range is None:
            report = FisheryCatchReport(
                analysis_range="알 수 없음",
                top_species=[],
                total_catch=0.0,
                summary="기간 정보를 찾지 못해 어획 데이터를 조회하지 못했습니다. 날짜 범위를 알려주세요.",
                raw_records=[],
                chart_series=[],
                chart_timeline=[],
                data_source=None,
            )
            output = ToolOutput(updates={"fishery_catch": report})
            output.add_tool_result(report.as_tool_result())
            return output

        analysis_range = self._resolve_analysis_range(date_range)

        response = context.services.fetch_catch_history_range(
            start_date=analysis_range.start,
            end_date=analysis_range.end,
            fish_type=(details.target_species or None),
        )
        report = self._summarize_response(
            response.dict() if hasattr(response, "dict") else {},
            analysis_range,
            details.target_species,
        )
        output = ToolOutput(updates={"fishery_catch": report})
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

    @staticmethod
    def _resolve_analysis_range(date_range: DateRange) -> DateRange:
        today = datetime.utcnow().date()
        window_days = 31

        end = min(date_range.end, today)
        start_candidate = end - timedelta(days=window_days)
        start = max(start_candidate, date_range.start)
        if start > end:
            start = end - timedelta(days=window_days)
        label = f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}"
        return DateRange(start=start, end=end, label=label)

    def _resolve_date_range(
        self,
        message: str,
        details: FishingPlanDetails,
        context: ToolContext,
    ) -> Optional[DateRange]:
        today = datetime.utcnow().date()
        explicit = self._parse_explicit_range(message, today)
        if explicit:
            return explicit

        single = self._parse_single_date(message, today)
        if single:
            start, label = single
            return DateRange(start=start, end=start, label=label)

        if details.date:
            target = context.services.resolve_target_date(details.date)
            label = target.strftime("%Y-%m-%d")
            return DateRange(start=target, end=target, label=label)

        return None

    def _parse_explicit_range(self, message: str, reference: date) -> Optional[DateRange]:
        text = message.replace("~", " ~ ")

        iso_match = re.search(
            r"(?P<start>\d{4}-\d{2}-\d{2})\s*(?:부터|까지|~|-|–|—)\s*(?P<end>\d{4}-\d{2}-\d{2})",
            text,
        )
        if iso_match:
            start = self._safe_parse_iso(iso_match.group("start"))
            end = self._safe_parse_iso(iso_match.group("end"))
            if start and end:
                if end < start:
                    start, end = end, start
                label = f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}"
                return DateRange(start=start, end=end, label=label)

        kor_match = re.search(
            r"(?P<s_month>\d{1,2})\s*월\s*(?P<s_day>\d{1,2})\s*일?\s*(?:부터|에서|~|-|–|—)\s*(?:(?P<e_month>\d{1,2})\s*월\s*)?(?P<e_day>\d{1,2})\s*일?",
            text,
        )
        if kor_match:
            start_month = int(kor_match.group("s_month"))
            start_day = int(kor_match.group("s_day"))
            end_month = kor_match.group("e_month")
            end_month_int = int(end_month) if end_month else start_month
            end_day = int(kor_match.group("e_day"))

            start_year = reference.year
            end_year = reference.year
            if start_month > end_month_int:
                end_year += 1

            start = self._safe_date(start_year, start_month, start_day)
            end = self._safe_date(end_year, end_month_int, end_day)
            if start and end:
                if end < start:
                    start, end = end, start
                label = f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}"
                return DateRange(start=start, end=end, label=label)

        if "추석" in message:
            chuseok = self._resolve_chuseok_range(reference.year)
            if chuseok:
                start, end = chuseok
                label = f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}"
                return DateRange(start=start, end=end, label=label)
        return None

    def _parse_single_date(self, message: str, reference: date) -> Optional[Tuple[date, str]]:
        iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", message)
        if iso_match:
            parsed = self._safe_parse_iso(iso_match.group(1))
            if parsed:
                return parsed, parsed.strftime("%Y-%m-%d")

        kor_match = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", message)
        if kor_match:
            month = int(kor_match.group(1))
            day = int(kor_match.group(2))
            start = self._safe_date(reference.year, month, day)
            if start:
                if start < reference:
                    start = self._safe_date(reference.year + 1, month, day) or start
                return start, start.strftime("%Y-%m-%d")
        return None

    @staticmethod
    def _safe_parse_iso(value: str) -> Optional[date]:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _safe_date(year: int, month: int, day: int) -> Optional[date]:
        try:
            return date(year, month, day)
        except ValueError:
            last_day = monthrange(year, month)[1]
            if day > last_day:
                try:
                    return date(year, month, last_day)
                except ValueError:
                    return None
            return None

    @staticmethod
    def _resolve_chuseok_range(year: int) -> Optional[Tuple[date, date]]:
        known_ranges: Dict[int, Tuple[date, date]] = {
            2024: (date(2024, 9, 16), date(2024, 9, 18)),
            2025: (date(2025, 10, 6), date(2025, 10, 8)),
        }
        if year in known_ranges:
            return known_ranges[year]
        if year - 1 in known_ranges:
            start_prev, end_prev = known_ranges[year - 1]
            return (
                date(year, start_prev.month, start_prev.day),
                date(year, end_prev.month, end_prev.day),
            )
        return None

    def _summarize_response(
        self,
        payload: Dict[str, object],
        analysis_range: DateRange,
        target_species: Optional[str],
    ) -> FisheryCatchReport:
        data: Dict[str, Any]
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            data = payload["data"]  # type: ignore[index]
        else:
            data = {}

        raw_records = data.get("records") or data.get("catch_records") or []
        if isinstance(raw_records, dict):
            records_iterable = list(raw_records.values())
        elif isinstance(raw_records, list):
            records_iterable = raw_records
        else:
            records_iterable = []

        species_totals: Dict[str, float] = defaultdict(float)
        species_daily: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        species_price_total: Dict[str, float] = defaultdict(float)
        species_price_count: Dict[str, int] = defaultdict(int)
        cleaned_records: List[Dict[str, Any]] = []

        for record in records_iterable:
            if not isinstance(record, dict):
                continue

            species_name = str(
                record.get("itemName")
                or record.get("fish_type")
                or record.get("species")
                or "알 수 없음"
            ).strip() or "알 수 없음"

            weight_raw = record.get("weight") or record.get("catch_amount")
            try:
                weight = float(weight_raw)
            except (TypeError, ValueError):
                continue
            if weight <= 0:
                continue

            date_text = record.get("logDatetime") or record.get("catch_date")
            normalized_date = self._normalize_record_date(date_text)
            if normalized_date:
                species_daily[species_name][normalized_date] += weight

            species_totals[species_name] += weight

            price_raw = record.get("price")
            try:
                price_value = float(price_raw)
            except (TypeError, ValueError, OverflowError):
                price_value = None
            if price_value is not None:
                species_price_total[species_name] += price_value
                species_price_count[species_name] += 1

            cleaned_record = {**record}
            if normalized_date:
                cleaned_record.setdefault("normalizedDate", normalized_date)
            cleaned_record.setdefault("species", species_name)
            cleaned_record.setdefault("weightKg", round(weight, 3))
            cleaned_records.append(cleaned_record)

        total_catch = sum(species_totals.values())

        sorted_species = sorted(
            species_totals.items(), key=lambda item: item[1], reverse=True
        )
        top_species: List[Dict[str, Any]] = []
        for name, catch in sorted_species[:5]:
            share = (catch / total_catch * 100) if total_catch else 0.0
            average_price = None
            if species_price_count[name]:
                average_price = species_price_total[name] / species_price_count[name]

            top_species.append(
                {
                    "name": name,
                    "catch": round(catch, 1),
                    "share": round(share, 1),
                    "averagePrice": round(average_price, 0)
                    if average_price is not None
                    else None,
                }
            )

        chart_series, chart_timeline = self._build_chart_payload(
            top_species, species_daily
        )

        trend_highlights: List[Dict[str, Any]] = []
        for species_name, daily_map in species_daily.items():
            if not daily_map:
                continue

            ordered_days = sorted(daily_map.items())
            if not ordered_days:
                continue

            window = min(7, len(ordered_days))
            first_window = ordered_days[:window]
            last_window = ordered_days[-window:]

            first_avg = sum(weight for _, weight in first_window) / window
            last_avg = sum(weight for _, weight in last_window) / window
            if first_avg == 0 and last_avg == 0:
                continue

            delta = last_avg - first_avg
            direction: str
            if delta > 1:
                direction = "up"
            elif delta < -1:
                direction = "down"
            else:
                direction = "flat"

            trend_highlights.append(
                {
                    "species": species_name,
                    "firstWindowAvgKg": round(first_avg, 2),
                    "lastWindowAvgKg": round(last_avg, 2),
                    "deltaKg": round(delta, 2),
                    "deltaPct": round(delta / first_avg * 100, 1) if first_avg else None,
                    "direction": direction,
                }
            )

        trend_highlights.sort(key=lambda item: item.get("deltaKg", 0.0), reverse=True)

        summary_parts: List[str] = []
        if top_species:
            leader = top_species[0]
            summary_parts.append(
                f"{analysis_range.label} 동안 {leader['name']} 어획량이 {leader['catch']:.1f}kg로 가장 많이 잡혔어요."
            )
            if len(top_species) > 1:
                runner_names = ", ".join(item["name"] for item in top_species[1:3])
                summary_parts.append(f"그 뒤를 {runner_names}가 이었습니다.")
            if target_species and target_species not in {
                item["name"] for item in top_species
            }:
                summary_parts.append(
                    f"요청하신 {target_species} 외의 어종도 활발하게 잡히고 있어요."
                )
        else:
            summary_parts.append("데이터가 충분하지 않아 참고용으로만 활용해주세요.")

        rising = [item for item in trend_highlights if item["direction"] == "up"]
        falling = [item for item in trend_highlights if item["direction"] == "down"]
        if rising:
            hottest = rising[0]
            summary_parts.append(
                f"최근 7일 평균을 보면 {hottest['species']} 어획량이 초반보다 {hottest['deltaKg']:.1f}kg 늘어나 10월 초 조황도 기대할 만해요."
            )
        if falling:
            coldest = sorted(trend_highlights, key=lambda item: item.get("deltaKg", 0.0))[0]
            summary_parts.append(
                f"반면 {coldest['species']}는 최근 {abs(coldest['deltaKg']):.1f}kg 줄어드는 추세라 출조 시 참고해주세요."
            )

        status = payload.get("status") if isinstance(payload, dict) else None
        if status and str(status).lower() not in {"success", "ok"}:
            summary_parts.append(f"(API 상태: {status})")

        data_source = None
        if isinstance(data, dict) and data.get("source"):
            data_source = str(data["source"])
        elif isinstance(payload, dict) and payload.get("source"):
            data_source = str(payload["source"])

        return FisheryCatchReport(
            analysis_range=analysis_range.label,
            top_species=top_species,
            total_catch=round(total_catch, 1),
            summary=" ".join(summary_parts).strip(),
            raw_records=cleaned_records[:100],
            chart_series=chart_series,
            chart_timeline=chart_timeline,
            data_source=data_source,
            trend_highlights=trend_highlights,
        )

    @staticmethod
    def _normalize_record_date(value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        text = str(value)
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
            try:
                return datetime.strptime(text[: len(fmt)], fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text.replace(" ", "T"))
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _build_chart_payload(
        top_species: List[Dict[str, Any]],
        species_daily: Dict[str, Dict[str, float]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not top_species:
            return [], []

        species_names = [item["name"] for item in top_species]
        timeline_map: Dict[str, Dict[str, float]] = defaultdict(dict)
        chart_series: List[Dict[str, Any]] = []

        for species in species_names:
            daily_data = species_daily.get(species, {})
            points = [
                {"date": day, "weight": round(weight, 2)}
                for day, weight in sorted(daily_data.items())
            ]
            chart_series.append(
                {
                    "species": species,
                    "points": points,
                }
            )
            for day, weight in daily_data.items():
                timeline_map[day][species] = round(weight, 2)

        chart_timeline: List[Dict[str, Any]] = []
        for day in sorted(timeline_map.keys()):
            row: Dict[str, Any] = {"date": day}
            for species in species_names:
                row[species] = timeline_map[day].get(species, 0.0)
            chart_timeline.append(row)

        return chart_series, chart_timeline


__all__ = ["FisheryCatchTool"]
