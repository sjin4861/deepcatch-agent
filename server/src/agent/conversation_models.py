from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
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
    tide_phase: Optional[str] = None  # 예: 사리, 조금, 중간
    moon_age: Optional[float] = None  # 음력 일령 (0~29.53)

    def as_tool_result(self) -> ChatToolResult:
        lines = [
            f"일자: {self.target_date}",
            f"일출: {self.sunrise}",
            f"바람: {self.wind}",
            f"물때: {self.tide}",
            f"추천 시간대: {self.best_window}",
            self.summary,
        ]
        if self.tide_phase:
            lines.insert(4, f"물때 단계: {self.tide_phase} (음력 {self.moon_age:.1f}일)" if self.moon_age is not None else f"물때 단계: {self.tide_phase}")
        return make_tool_result(
            tool="weather_tide",
            title="구룡포 날씨/물때 정보",
            content="\n".join(lines),
            metadata=asdict(self),
        )


@dataclass
class FisheryCatchReport:
    analysis_range: str
    top_species: List[Dict[str, Any]]
    total_catch: float
    summary: str
    raw_records: List[Dict[str, Any]]
    chart_series: List[Dict[str, Any]]
    chart_timeline: List[Dict[str, Any]]
    data_source: Optional[str] = None
    trend_highlights: List[Dict[str, Any]] = field(default_factory=list)

    def as_tool_result(self) -> ChatToolResult:
        lines = [
            f"분석 기간: {self.analysis_range}",
            f"총 어획량: {self.total_catch:.1f}kg",
        ]
        if self.top_species:
            lines.append("주요 어종 TOP5:")
        for idx, item in enumerate(self.top_species, start=1):
            share_text = f" ({item['share']:.1f}% 비중)" if item.get("share") is not None else ""
            lines.append(f"{idx}. {item['name']} - {item['catch']:.1f}kg{share_text}")
        if self.summary:
            lines.append(self.summary)
        if self.data_source:
            lines.append(f"데이터 출처: {self.data_source}")

        return make_tool_result(
            tool="fishery_catch",
            title="구룡포 어획량 분석",
            content="\n".join(lines),
            metadata={
                "analysisRange": self.analysis_range,
                "topSpecies": self.top_species,
                "totalCatchKg": self.total_catch,
                "summary": self.summary,
                "records": self.raw_records,
                "chartSeries": self.chart_series,
                "chartTimeline": self.chart_timeline,
                "dataSource": self.data_source,
                "trendHighlights": self.trend_highlights,
            },
        )


@dataclass
class CallSummary:
    success: bool
    business_name: str
    status: str
    sid: Optional[str] = None
    message: Optional[str] = None
    phone: Optional[str] = None  # 대상 업체 전화번호 (추가)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def as_tool_result(self) -> ChatToolResult:
        lines = [
            f"업체: {self.business_name}",
            f"상태: {self.status}",
        ]
        if self.sid:
            lines.append(f"통화 SID: {self.sid}")
        if self.phone:
            lines.append(f"전화번호: {self.phone}")
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
    fishery_catch: FisheryCatchReport
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
