from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, TypedDict

from .conversation_models import FishingPlanDetails


class PlannerResult(TypedDict):
    details: FishingPlanDetails
    db_updates: Dict[str, Any]
    missing: List[str]
    summary_lines: List[str]


class PlannerAgent:
    DATE_PATTERNS = [
        r"(내일|모레|오늘|이번\s*주말|다음\s*주말|다음\s*주)",
        r"(이번\s*[월화수목금토일]요일)",
        r"(다음\s*[월화수목금토일]요일)",
        r"(\d{1,2}\s*월\s*\d{1,2}\s*일)",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    TIME_PATTERN = r"((?:오전|오후)?\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?)"
    PARTICIPANT_PATTERN = r"(\d+)\s*(?:명|people|인)"
    PHONE_PATTERN = r"(\+?\d{1,3}[ -]?)?(0\d{1,2}|1\d{2,3})[- ]?\d{3,4}[- ]?\d{4}"
    MONEY_PATTERN = r"(\d{2,3}(?:,\d{3})?|\d+(?:\.\d+)?)\s*(?:만원|원|krw|KRW|만\s*원)"
    FISHING_TYPES = {
        "boat": ["선상", "boat", "배", "출조"],
        "pier": ["방파제", "pier", "포구", "방파"],
        "rock": ["갯바위", "rock", "shore"],
        "light_jigging": ["지깅", "jigging", "라이트"],
    }
    TRANSPORT_KEYWORDS = {
        "car": ["차", "car", "자가", "렌트"],
        "bus": ["버스", "bus"],
        "train": ["기차", "train", "kTX"],
        "public": ["대중교통", "public"],
    }
    GEAR_KEYWORDS = ["장비", "gear", "대여", "렌탈", "로드", "릴"]
    SPECIES_KEYWORDS = [
        "고등어",
        "mackerel",
        "한치",
        "squid",
        "문어",
        "octopus",
        "감성돔",
        "black seabream",
    ]

    def process(self, message: str, base_details: FishingPlanDetails) -> PlannerResult:
        details = base_details.copy()
        db_updates: Dict[str, Any] = {}
        summary_lines: List[str] = []
        lowered = message.lower()

        date_value = self._extract_first_match(self.DATE_PATTERNS, message)
        if date_value:
            details.date = date_value
            summary_lines.append(f"출조 날짜: {date_value}")
            db_updates["date"] = date_value

        time_match = re.search(self.TIME_PATTERN, message)
        if time_match:
            details.time = time_match.group(1)
            summary_lines.append(f"출발 시간: {details.time}")
            db_updates["time"] = details.time

        phone_match = re.search(self.PHONE_PATTERN, message)
        if phone_match:
            digits = re.sub("\D", "", phone_match.group(0))
            formatted = (
                f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
                if len(digits) >= 11
                else phone_match.group(0)
            )
            details.phone_user = formatted
            summary_lines.append(f"연락처: {formatted}")
            db_updates["phone_user"] = formatted

        participant_updates = self._extract_participants(message)
        if participant_updates:
            details.participants_adults = participant_updates.get(
                "adults", details.participants_adults
            )
            details.participants_children = participant_updates.get(
                "children", details.participants_children
            )
            if details.participants_adults is not None and details.participants_children is not None:
                details.participants_total = (
                    details.participants_adults + details.participants_children
                )
            if participant_updates.get("total") is not None:
                details.participants_total = participant_updates["total"]
            if details.participants_total is not None:
                db_updates["people"] = details.participants_total
            summary_lines.append(
                "인원: 성인 {}/ 어린이 {}".format(
                    details.participants_adults or "미정",
                    details.participants_children or "미정",
                )
            )

        for ftype, keywords in self.FISHING_TYPES.items():
            if any(keyword in lowered for keyword in keywords):
                details.fishing_type = ftype
                summary_lines.append(f"낚시 유형: {ftype}")
                break

        money_match = re.search(self.MONEY_PATTERN, message)
        if money_match:
            budget_raw = money_match.group(0)
            details.budget = budget_raw.replace("  ", " ")
            summary_lines.append(f"예산: {details.budget}")

        for keyword in self.GEAR_KEYWORDS:
            if keyword in message:
                details.gear = (
                    "대여 필요" if "대여" in message or "렌탈" in message else "자체 지참"
                )
                summary_lines.append(f"장비: {details.gear}")
                break

        for transport, keywords in self.TRANSPORT_KEYWORDS.items():
            if any(keyword in message for keyword in keywords):
                details.transportation = transport
                summary_lines.append(f"이동수단: {transport}")
                break

        for species in self.SPECIES_KEYWORDS:
            if species.lower() in lowered:
                details.target_species = species
                summary_lines.append(f"관심 어종: {species}")
                break

        if "구룡포" in message:
            details.location = "구룡포"
            summary_lines.append("위치: 구룡포")
            db_updates["location"] = "구룡포"

        missing = details.missing_keys()
        if not summary_lines:
            summary_lines.append("새로운 계획 정보가 감지되지 않았습니다.")
        else:
            summary_lines.append("누락된 정보: " + (", ".join(missing) if missing else "없음"))

        return PlannerResult(
            details=details,
            db_updates=db_updates,
            missing=missing,
            summary_lines=summary_lines,
        )

    @staticmethod
    def _extract_first_match(patterns: List[str], message: str) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _extract_participants(message: str) -> Dict[str, int]:
        results: Dict[str, int] = {}
        adult_match = re.search(
            r"(\d+)\s*(?:명|people|인)\s*(?:의\s*)?(?:성인|adult)",
            message,
            re.IGNORECASE,
        )
        child_match = re.search(
            r"(\d+)\s*(?:명|people|인)\s*(?:의\s*)?(?:어린이|아이|child)",
            message,
            re.IGNORECASE,
        )
        if adult_match:
            results["adults"] = int(adult_match.group(1))
        if child_match:
            results["children"] = int(child_match.group(1))
        if not results:
            total_match = re.search(r"(\d+)\s*(?:명|people|인)", message)
            if total_match:
                results["total"] = int(total_match.group(1))
        return results


planner_agent = PlannerAgent()
