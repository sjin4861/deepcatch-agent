from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List, Optional, TYPE_CHECKING, TypedDict

from .types import ChatResponse, ChatToolResult
from .tool_results import make_tool_result

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .services import AgentServices
    from .toolkit import ToolRegistry
    from .. import models as orm_models

    ConversationTools = AgentServices
else:  # pragma: no cover - runtime fallback for type hints
    AgentServices = Any  # type: ignore
    ToolRegistry = Any  # type: ignore
    ConversationTools = Any  # type: ignore

    class orm_models:  # type: ignore
        Plan = Any


@dataclass
class FishingPlanDetails:
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    departure: Optional[str] = None
    participants: Optional[int] = None
    fishing_type: Optional[str] = None
    budget: Optional[str] = None
    gear: Optional[str] = None
    transportation: Optional[str] = None
    target_species: Optional[str] = None

    def copy(self) -> "FishingPlanDetails":
        return replace(self)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def missing_keys(self) -> List[str]:
        required: List[str] = []
        if not self.date:
            required.append("date")
        if self.participants is None:
            required.append("participants")
        if not self.departure:
            required.append("departure")
        if not self.fishing_type:
            required.append("fishing_type")
        if not self.budget:
            required.append("budget")
        if not self.gear:
            required.append("gear")
        if not self.transportation:
            required.append("transportation")
        return required


@dataclass
class WeatherReport:
    target_date: str
    sunrise: str
    wind: str
    tide: str
    best_window: str
    summary: str

    def as_tool_result(self) -> ChatToolResult:
        lines = [
            f"일자: {self.target_date}",
            f"일출: {self.sunrise}",
            f"바람: {self.wind}",
            f"물때: {self.tide}",
            f"추천 시간대: {self.best_window}",
            self.summary,
        ]
        return make_tool_result(
            tool="weather_tide",
            title="구룡포 날씨/물때 정보",
            content="\n".join(lines),
            metadata=asdict(self),
        )


@dataclass
class FishReport:
    species: List[Dict[str, Any]]
    note: str

    def as_tool_result(self) -> ChatToolResult:
        lines = ["현재 어종 정보"]
        for item in self.species:
            lines.append(f"- {item['name']}: {item['count']}마리 추정")
        lines.append(self.note)
        return make_tool_result(
            tool="fish_insights",
            title="구룡포 어종 업데이트",
            content="\n".join(lines),
            metadata={"species": self.species, "note": self.note},
        )


@dataclass
class CallSummary:
    success: bool
    business_name: str
    status: str
    sid: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def as_tool_result(self) -> ChatToolResult:
        lines = [
            f"업체: {self.business_name}",
            f"상태: {self.status}",
        ]
        if self.sid:
            lines.append(f"통화 SID: {self.sid}")
        if self.message:
            lines.append(self.message)
        return make_tool_result(
            tool="call_agent",
            title="통화 결과",
            content="\n".join(lines),
            metadata=self.to_dict(),
        )


@dataclass
class PlanSnapshot:
    record: "orm_models.Plan"
    details: FishingPlanDetails
    stage: str
    call_summary: Optional[CallSummary] = None


class ConversationState(TypedDict, total=False):
    message: str
    tools: ConversationTools
    services: AgentServices
    tool_registry: ToolRegistry
    plan_record: "orm_models.Plan"
    plan_details: FishingPlanDetails
    stage: str
    missing_keys: List[str]
    weather: WeatherReport
    fish_info: FishReport
    call_result: CallSummary
    tool_results: List[ChatToolResult]
    action_queue: List[str]
    preferred_business: Optional[str]
    response: ChatResponse
    plan_snapshot: PlanSnapshot


FRIENDLY_LABELS: Dict[str, str] = {
    "date": "출조 날짜",
    "participants": "참여 인원",
    "departure": "출발지/집결지",
    "fishing_type": "낚시 유형",
    "budget": "예산",
    "gear": "장비 준비",
    "transportation": "이동 수단",
}
