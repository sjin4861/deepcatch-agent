from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from ..base import BaseTool, ToolContext, ToolOutput
from ...conversation_models import FishingPlanDetails
from ...tool_results import make_tool_result


class MapRouteTool(BaseTool):
    name = "map_route_generation_api"
    priority = 35

    ARRIVAL_LOCATION: Dict[str, Any] = {
        "name": "포항시 구룡포",
        "label": "포항시 구룡포",
        "lat": 35.9896,
        "lng": 129.5689,
        "address": "경북 포항시 남구 구룡포읍",
    }

    DEFAULT_DEPARTURE: Dict[str, Any] = {
        "name": "체인지업가든 포항",
        "label": "체인지업가든 포항",
        "lat": 36.01200160051033,
        "lng": 129.32373891016633,
        "address": None,
    }

    POHANG_STATION: Dict[str, Any] = {
        "name": "포항역",
        "label": "포항역",
        "lat": 36.0141,
        "lng": 129.3609,
        "address": "경북 포항시 북구 대흥동",
    }

    DEPARTURE_ALIASES: Dict[str, Dict[str, Any]] = {
        "체인지업가든 포항": DEFAULT_DEPARTURE,
        "체인지업가든": DEFAULT_DEPARTURE,
        "change up garden": DEFAULT_DEPARTURE,
        "changeup garden": DEFAULT_DEPARTURE,
        "포항역": POHANG_STATION,
        "pohang station": POHANG_STATION,
        "포항 고속버스터미널": {
            "name": "포항 고속버스터미널",
            "lat": 36.0207,
            "lng": 129.3437,
            "address": "경북 포항시 북구 죽도동",
        },
        "포항시청": {
            "name": "포항시청",
            "lat": 36.0194,
            "lng": 129.3419,
            "address": "경북 포항시 남구 대잠동",
        },
    }

    def applies_to(self, context: ToolContext) -> bool:
        actions = context.state.get("action_queue", [])
        return self.name in actions

    def execute(self, context: ToolContext) -> ToolOutput:
        details = self._resolve_details(context)
        departure = self._resolve_departure(details)
        arrival = dict(self.ARRIVAL_LOCATION)
        businesses = self._build_business_markers(context, details)
        route = self._build_route_summary(departure, arrival)

        metadata = {
            "map": {
                "departure": departure,
                "arrival": arrival,
                "businesses": businesses,
                "route": route,
            }
        }

        distance_km = route.get("distance_km")
        duration_minutes = route.get("duration_minutes")

        content_lines = [
            f"{departure['label']}에서 {arrival['label']}까지 차량 경로를 생성했어요.",
        ]
        if distance_km is not None and duration_minutes is not None:
            content_lines.append(
                f"거리 약 {distance_km:.1f}km, 예상 소요 시간은 {int(round(duration_minutes))}분입니다."
            )
        if businesses:
            content_lines.append(f"지도에는 주변 낚시점 {len(businesses)}곳을 함께 표시했어요.")

        output = ToolOutput()
        output.add_tool_result(
            make_tool_result(
                tool=self.name,
                title="구룡포 주변 낚시점",
                content="\n".join(content_lines),
                metadata=metadata,
            )
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

    def _resolve_departure(self, details: FishingPlanDetails) -> Dict[str, Any]:
        raw_departure = (details.departure or "").strip()
        normalized = raw_departure.lower()
        match = None
        for key, payload in self.DEPARTURE_ALIASES.items():
            if key.lower() in normalized or key in raw_departure:
                match = payload
                break
        base = match or self.DEFAULT_DEPARTURE
        label_source = base.get("label", base["name"])
        label = raw_departure or label_source
        return {
            "name": base["name"],
            "label": label,
            "lat": base["lat"],
            "lng": base["lng"],
            "address": base.get("address"),
        }

    def _build_business_markers(
        self,
        context: ToolContext,
        details: FishingPlanDetails,
    ) -> List[Dict[str, Any]]:
        requested_location = details.location or self.ARRIVAL_LOCATION["name"]
        normalized_target = self._normalize_location(requested_location)
        all_businesses = context.services.list_businesses()
        candidates = [
            biz
            for biz in all_businesses
            if self._normalize_location(getattr(biz, "location", None)) == normalized_target
        ]
        if not candidates:
            candidates = all_businesses

        markers: List[Dict[str, Any]] = []
        for biz in candidates:
            if biz.latitude is None or biz.longitude is None:
                continue
            markers.append(
                {
                    "name": biz.name,
                    "phone": biz.phone,
                    "address": getattr(biz, "address", None),
                    "lat": biz.latitude,
                    "lng": biz.longitude,
                }
            )
        return markers

    @staticmethod
    def _normalize_location(value: Optional[str]) -> str:
        if not value:
            return "구룡포"
        stripped = value.strip()
        lowered = stripped.lower()
        mapping = {
            "guryongpo": "구룡포",
            "구룡포": "구룡포",
        }
        return mapping.get(lowered, stripped)

    @staticmethod
    def _build_route_summary(
        departure: Dict[str, Any],
        arrival: Dict[str, Any],
    ) -> Dict[str, Any]:
        lat1 = departure["lat"]
        lng1 = departure["lng"]
        lat2 = arrival["lat"]
        lng2 = arrival["lng"]
        distance_km = MapRouteTool._haversine_km(lat1, lng1, lat2, lng2)
        # Assume average driving speed 45 km/h for estimate
        duration_minutes = (distance_km / 45.0) * 60 if distance_km else None
        bounds = {
            "south": min(lat1, lat2),
            "west": min(lng1, lng2),
            "north": max(lat1, lat2),
            "east": max(lng1, lng2),
        }
        return {
            "mode": "DRIVING",
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "bounds": bounds,
        }

    @staticmethod
    def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        radius = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lng2 - lng1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c


__all__ = ["MapRouteTool"]
