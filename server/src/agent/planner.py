from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, TypedDict, Tuple

from src.config import logger

from .conversation_models import FRIENDLY_LABELS, FishingPlanDetails
from .openai_client import OpenAIChatClient, get_openai_client


class PlannerResult(TypedDict):
    details: FishingPlanDetails
    db_updates: Dict[str, Any]
    missing: List[str]
    summary_lines: List[str]


class PlannerAgent:
    DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    DEFAULT_PLAN_VALUES = {
        "time": "새벽 5시 ~ 오전 11시",
        "participants": 2,
        "departure": "포항역 집결 04:00 출발",
        "fishing_type": "방파제 낚시",
        "budget": "1인당 150,000원 예상",
        "gear": "현장 대여 + 개인 장비 병행",
        "transportation": "자가용 이동",
        "target_species": "가을철 어종(고등어·한치)",
    }
    DEFAULT_LOCATION = "구룡포"
    MISSING_ENUM = [
        "date",
        "participants",
        "departure",
        "fishing_type",
        "budget",
        "gear",
        "transportation",
        "location",
        "time",
        "target_species",
    ]
    PLAN_FIELD_ORDER = [
        "date",
        "time",
        "location",
        "participants",
        "departure",
        "fishing_type",
        "budget",
        "gear",
        "transportation",
        "target_species",
    ]
    SYSTEM_PROMPT = (
        "Developer: 당신은 낚시 챗봇을 위한 간결한 한국어 플래닝 어시스턴트입니다. 입력으로 (1) 최신 사용자 메시지, "
        "(2) 현재 구조화된 계획 스냅샷, (3) 필수 입력 필드 목록을 받습니다.\n\n"
        "작업을 시작하기 전에, 수행할 주요 단계를 3~7개로 구성한 간략한 체크리스트를 제시하세요. 각 단계는 개념적 수준에서 작성하며, "
        "세부 구현이 아닌 전체 과정을 설명해야 합니다.\n\n"
        "반드시 제공된 스키마에 맞춘 정확한 JSON을 생성하세요. 'missing_information'에는 반드시 'required_fields'에서 지정된 키만 사용해야 합니다. "
        "'summary' 배열은 최대 세 개의 짧은 한국어 불릿 문장으로, 가장 중요한 업데이트나 확인 사항을 강조해야 합니다.\n\n"
        "## 출력 형식\n"
        "아래 스키마에 따라 JSON 객체로 응답하세요:\n"
        "{\n"
        "  \"missing_information\": [\"<string>\", ...],  // 아직 입력이 필요하거나 지정되지 않은 필수 필드의 키를 'required_fields'에서 가져와 기록합니다.\n"
        "  \"summary\": [\"<string>\", ...]               // 최대 3개의 간단한 한국어 불릿 포인트 문장으로, 주요 업데이트나 확인 사항을 요약하세요.\n"
        "}\n\n"
        "- 'missing_information'은 string 타입의 배열이며, 각 값은 'required_fields'에 명시된 필수 필드의 키여야 합니다.\n"
        "- 'summary'는 최대 3개까지의 간결한 한국어 불릿 포인트 문장 배열로 작성하세요.\n"
        "- 모든 필수 필드가 입력된 경우 'missing_information'은 빈 배열이어야 합니다.\n"
        "- 사용자 입력 또는 계획 스냅샷에서 모호함이 있을 경우 해당 키를 'missing_information'에 포함하세요."
    )

    # Legacy rule-based patterns kept for fallback when LLM is unavailable
    DATE_PATTERNS = [
        r"(내일|모레|오늘|이번\s*주말|다음\s*주말|다음\s*주)",
        r"(이번\s*[월화수목금토일]요일)",
        r"(다음\s*[월화수목금토일]요일)",
        r"(\d{1,2}\s*월\s*\d{1,2}\s*일)",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    TIME_PATTERN = r"((?:오전|오후)?\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?)"
    PARTICIPANT_PATTERN = r"(\d+)\s*(?:명|people|인)"
    DEPARTURE_PATTERN = r"(?:출발|집결)\s*(?:지|장|시간)?\s*(?:은|는|:|-)?\s*([\w\s가-힣]+)"
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

    def __init__(
        self,
        client: Optional[OpenAIChatClient] = None,
    ) -> None:
        self.client = client or get_openai_client()
        self.response_format = self._build_response_format()
        self._response_override: Optional[Dict[str, Any]] = None

    @contextmanager
    def mock_response(self, payload: Dict[str, Any]):
        previous = self._response_override
        self._response_override = payload
        try:
            yield
        finally:
            self._response_override = previous

    def process(self, message: str, base_details: FishingPlanDetails) -> PlannerResult:
        if not message.strip():
            return self._fallback_process(message, base_details)

        details = base_details.copy()
        data: Optional[Dict[str, Any]]

        if self._response_override is not None:
            data = self._response_override
        else:
            data = self._invoke_model(message, base_details)

        if not data:
            return self._fallback_process(message, base_details)

        updates = data.get("plan_updates", {})
        db_updates = self._apply_plan_updates(details, updates)
        fallback_db_updates = self._apply_participant_fallback(details, message)
        if fallback_db_updates:
            db_updates.update(fallback_db_updates)
        departure_updates = self._apply_departure_fallback(details, message)
        if departure_updates:
            db_updates.update(departure_updates)
        default_db_updates, defaults_applied = self._apply_default_plan_fields(details, message)
        if default_db_updates:
            db_updates.update(default_db_updates)
        missing = self._normalize_missing(data.get("missing_information", []), details)
        summary_lines = self._ensure_summary(
            data.get("summary", []),
            missing,
            details,
            defaults_applied=defaults_applied,
        )

        return PlannerResult(
            details=details,
            db_updates=db_updates,
            missing=missing,
            summary_lines=summary_lines,
        )

    def _invoke_model(
        self,
        message: str,
        base_details: FishingPlanDetails,
    ) -> Optional[Dict[str, Any]]:
        if not self.client.enabled:
            return None

        try:
            messages = self._build_messages(message, base_details)
            raw_content = self._call_model(messages)
            return self._parse_model_output(raw_content)
        except Exception as exc:  # pragma: no cover - guarded network call
            logger.exception("PlannerAgent 모델 호출 실패: %s", exc)
            return None

    def _build_messages(
        self,
        message: str,
        base_details: FishingPlanDetails,
    ) -> List[Dict[str, str]]:
        payload = {
            "latest_message": message,
            "current_plan": base_details.to_dict(),
            "required_fields": base_details.missing_keys(),
            "field_labels": FRIENDLY_LABELS,
        }
        user_content = json.dumps(payload, ensure_ascii=False)
        return [
            {"role": "user", "content": user_content},
        ]

    def _call_model(self, messages: List[Dict[str, str]]) -> str:
        return self.client.chat_completion(
            system_prompt=self.SYSTEM_PROMPT,
            messages=messages,
            response_format=self.response_format,
        )

    def _parse_model_output(self, content: str) -> Optional[Dict[str, Any]]:
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("PlannerAgent JSON 파싱 실패: %s", content)
            return None

    def _apply_plan_updates(
        self,
        details: FishingPlanDetails,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        db_updates: Dict[str, Any] = {}
        updates = updates or {}

        if "date" in updates and updates["date"]:
            details.date = str(updates["date"])
            db_updates["date"] = details.date
        if "time" in updates and updates["time"]:
            details.time = str(updates["time"])
            db_updates["time"] = details.time
        if "location" in updates and updates["location"]:
            details.location = str(updates["location"])
            db_updates["location"] = details.location
        if "departure" in updates and updates["departure"]:
            details.departure = str(updates["departure"])
            db_updates["departure"] = details.departure

        for key in ("gear", "budget", "fishing_type", "transportation", "target_species"):
            if key in updates and updates[key]:
                setattr(details, key, str(updates[key]))


        # Participants handling
        participants_value = self._safe_int(updates.get("participants"))
        if participants_value is None:
            adults = self._safe_int(updates.get("participants_adults"))
            children = self._safe_int(updates.get("participants_children"))
            total = self._safe_int(updates.get("participants_total"))
            if total is not None:
                participants_value = total
            else:
                adult_val = adults or 0
                child_val = children or 0
                combined = adult_val + child_val
                if combined > 0:
                    participants_value = combined

        if participants_value is not None:
            details.participants = participants_value
            db_updates["people"] = participants_value

        return db_updates

    def _apply_participant_fallback(
        self,
        details: FishingPlanDetails,
        message: str,
    ) -> Dict[str, Any]:
        """Populate participant counts from message text when the model omits them."""
        if details.participants is not None:
            return {}

        extracted = self._extract_participants(message)
        if not extracted:
            return {}

        participants_value = extracted.get("total")
        if participants_value is None:
            adult_val = extracted.get("adults", 0)
            child_val = extracted.get("children", 0)
            combined = adult_val + child_val
            if combined > 0:
                participants_value = combined

        if participants_value is None:
            return {}

        details.participants = participants_value
        return {"people": participants_value}

    def _apply_departure_fallback(
        self,
        details: FishingPlanDetails,
        message: str,
    ) -> Dict[str, Any]:
        if details.departure:
            return {}
        inferred = self._extract_departure(message)
        if not inferred:
            return {}
        details.departure = inferred
        return {"departure": inferred}

    def _apply_default_plan_fields(
        self,
        details: FishingPlanDetails,
        message: str,
    ) -> Tuple[Dict[str, Any], bool]:
        db_updates: Dict[str, Any] = {}
        defaults_applied = False

        def assign(field: str, value: Any, db_key: Optional[str] = None) -> None:
            nonlocal defaults_applied
            current = getattr(details, field)
            if current is None or (isinstance(current, str) and not current.strip()):
                setattr(details, field, value)
                defaults_applied = True
                if db_key:
                    db_updates[db_key] = value

        if not details.location:
            assign("location", self.DEFAULT_LOCATION, "location")

        if not details.date:
            inferred = self._infer_default_date(message)
            if inferred:
                assign("date", inferred, "date")

        default_sequence = [
            ("time", self.DEFAULT_PLAN_VALUES["time"], "time"),
            ("participants", self.DEFAULT_PLAN_VALUES["participants"], "people"),
            ("departure", self.DEFAULT_PLAN_VALUES["departure"], "departure"),
            ("fishing_type", self.DEFAULT_PLAN_VALUES["fishing_type"], None),
            ("budget", self.DEFAULT_PLAN_VALUES["budget"], None),
            ("gear", self.DEFAULT_PLAN_VALUES["gear"], None),
            ("transportation", self.DEFAULT_PLAN_VALUES["transportation"], None),
            ("target_species", self.DEFAULT_PLAN_VALUES["target_species"], None),
        ]

        for field, value, db_field in default_sequence:
            assign(field, value, db_field)

        return db_updates, defaults_applied

    def _infer_default_date(self, message: str) -> str:
        today = datetime.utcnow().date()
        base = today
        lowered = message.lower()

        if "다음 주" in message or "다음주" in lowered:
            base = today + timedelta(days=7)
        elif "이번 주말" in message or "이번주말" in lowered:
            base = today

        candidate = base
        if candidate.weekday() < 5:
            candidate = candidate + timedelta(days=5 - candidate.weekday())

        if candidate <= today:
            candidate = candidate + timedelta(days=7)

        return candidate.isoformat()

    def _is_field_missing(self, details: FishingPlanDetails, key: str) -> bool:
        key = key.strip().lower()
        mapping = {
            "date": details.date,
            "time": details.time,
            "location": details.location,
            "departure": details.departure,
            "participants": details.participants,
            "fishing_type": details.fishing_type,
            "budget": details.budget,
            "gear": details.gear,
            "transportation": details.transportation,
            "target_species": details.target_species,
        }
        value = mapping.get(key)
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (int, float)):
            return False
        return False

    def _normalize_missing(
        self,
        missing_from_model: Iterable[str],
        details: FishingPlanDetails,
    ) -> List[str]:
        ordered: List[str] = []
        seen: set[str] = set()
        for key in missing_from_model or []:
            normalized = str(key).strip()
            if normalized and normalized not in seen:
                ordered.append(normalized)
                seen.add(normalized)

        filtered: List[str] = []
        for key in ordered:
            if self._is_field_missing(details, key) and key not in filtered:
                filtered.append(key)

        for key in details.missing_keys():
            if key not in filtered:
                filtered.append(key)
        return filtered

    def _ensure_summary(
        self,
        summary_lines: Iterable[str],
        missing: List[str],
        details: FishingPlanDetails,
        *,
        defaults_applied: bool = False,
    ) -> List[str]:
        lines = [line.strip() for line in summary_lines or [] if line and str(line).strip()]
        if not lines:
            lines = self._summary_from_details(details)
        missing_line = "누락된 정보: " + (", ".join(missing) if missing else "없음")
        if missing_line not in lines:
            lines.append(missing_line)
        if defaults_applied and "기본 추천 값을 자동으로 채워드렸어요." not in lines:
            lines.append("기본 추천 값을 자동으로 채워드렸어요.")
        return lines

    def _summary_from_details(self, details: FishingPlanDetails) -> List[str]:
        lines: List[str] = []
        if details.date:
            lines.append(f"출조 날짜: {details.date}")
        if details.time:
            lines.append(f"출발 시간: {details.time}")
        if details.location:
            lines.append(f"위치: {details.location}")
        if details.departure:
            lines.append(f"출발지: {details.departure}")
        if details.participants is not None:
            lines.append(f"총 인원: {details.participants}명")
        if details.fishing_type:
            lines.append(f"낚시 유형: {details.fishing_type}")
        if details.budget:
            lines.append(f"예산: {details.budget}")
        if details.gear:
            lines.append(f"장비: {details.gear}")
        if details.transportation:
            lines.append(f"이동수단: {details.transportation}")
        if details.target_species:
            lines.append(f"관심 어종: {details.target_species}")
        if not lines:
            lines.append("새로운 계획 정보가 감지되지 않았습니다.")
        return lines

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _build_response_format(self) -> Dict[str, Any]:
        plan_properties = {
            "date": {"type": "string"},
            "time": {"type": "string"},
            "location": {"type": "string"},
            "participants": {"type": "integer"},
            "departure": {"type": "string"},
            "fishing_type": {"type": "string"},
            "budget": {"type": "string"},
            "gear": {"type": "string"},
            "transportation": {"type": "string"},
            "target_species": {"type": "string"},
        }
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "planner_agent_response",
                "schema": {
                    "type": "object",
                    "properties": {
                        "plan_updates": {
                            "type": "object",
                            "properties": plan_properties,
                            "additionalProperties": False,
                        },
                        "missing_information": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": self.MISSING_ENUM,
                            },
                        },
                        "summary": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["plan_updates", "missing_information", "summary"],
                    "additionalProperties": False,
                },
            },
        }

    def _fallback_process(
        self,
        message: str,
        base_details: FishingPlanDetails,
    ) -> PlannerResult:
        details = base_details.copy()
        db_updates: Dict[str, Any] = {}
        lowered = message.lower()

        date_value = self._extract_first_match(self.DATE_PATTERNS, message)
        if date_value:
            details.date = date_value
            db_updates["date"] = date_value

        time_match = re.search(self.TIME_PATTERN, message)
        if time_match:
            details.time = time_match.group(1)
            db_updates["time"] = details.time


        participant_updates = self._extract_participants(message)
        if participant_updates:
            total = participant_updates.get("total")
            if total is None:
                adult_val = participant_updates.get("adults", 0)
                child_val = participant_updates.get("children", 0)
                combined = adult_val + child_val
                if combined > 0:
                    total = combined
            if total is not None:
                details.participants = total
                db_updates["people"] = total

        for ftype, keywords in self.FISHING_TYPES.items():
            if any(keyword in lowered for keyword in keywords):
                details.fishing_type = ftype
                break

        money_match = re.search(self.MONEY_PATTERN, message)
        if money_match:
            budget_raw = money_match.group(0)
            details.budget = budget_raw.replace("  ", " ")

        for keyword in self.GEAR_KEYWORDS:
            if keyword in message:
                details.gear = (
                    "대여 필요" if "대여" in message or "렌탈" in message else "자체 지참"
                )
                break

        for transport, keywords in self.TRANSPORT_KEYWORDS.items():
            if any(keyword in message for keyword in keywords):
                details.transportation = transport
                break

        for species in self.SPECIES_KEYWORDS:
            if species.lower() in lowered:
                details.target_species = species
                break

        if "구룡포" in message:
            details.location = "구룡포"
            db_updates["location"] = "구룡포"

        departure_value = self._extract_departure(message)
        if departure_value:
            details.departure = departure_value
            db_updates["departure"] = departure_value

        default_db_updates, defaults_applied = self._apply_default_plan_fields(details, message)
        if default_db_updates:
            db_updates.update(default_db_updates)

        missing = details.missing_keys()
        summary_seed = self._summary_from_details(details)
        summary_lines = self._ensure_summary(
            summary_seed,
            missing,
            details,
            defaults_applied=defaults_applied,
        )

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
    def _extract_departure(message: str) -> Optional[str]:
        match = re.search(PlannerAgent.DEPARTURE_PATTERN, message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
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
