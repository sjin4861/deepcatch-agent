"""
수산물 유통 정보화 예측 서비스 API
선박 안전 기상 정보 API 구현
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import httpx
import os
from urllib.parse import unquote
import math
import random

from src.config import logger

# 라우터 생성
router = APIRouter(prefix="/api/v1", tags=["ship-safe"])

# 외부 API 기본 URL
BASE_API_URL = "https://dpg-apis.pohang-eum.co.kr"

# 개발 모드 설정 (환경변수로 제어)
DEVELOPMENT_MODE = os.getenv("FISHERY_API_DEV_MODE", "true").lower() in (
    "true",
    "1",
    "yes",
)

# API 엔드포인트 매핑
API_ENDPOINTS = {
    "ship_safe_stats_history": "/ship-safe/stats/history",  # 주요 기상 요소 과거 정보
    "catch_history": "/catch/history",  # 어획 데이터 조회 (INT-S3-007)
    "harbor_ships_status": "/harbor/ships/status",  # 선박 입항 정보 (INT-S3-001)
}

# 서비스 키 (환경변수에서 로드 & 퍼센트 인코딩 해제)
RAW_SERVICE_KEY = os.getenv("DPG_SERVICE_KEY", "") or ""
DECODED_SERVICE_KEY = unquote(RAW_SERVICE_KEY)

def get_service_key(prefer_decoded: bool = True) -> str:
    """서비스 키를 반환.
    - prefer_decoded=True 이면 퍼센트 인코딩을 해제한 값 우선 사용
    - 두 값이 동일한 경우 그대로 반환
    """
    if prefer_decoded:
        return DECODED_SERVICE_KEY
    return RAW_SERVICE_KEY

def service_key_variants() -> list[str]:  # 순회용
    if RAW_SERVICE_KEY == DECODED_SERVICE_KEY:
        return [RAW_SERVICE_KEY]
    return [DECODED_SERVICE_KEY, RAW_SERVICE_KEY]


SERVICE_KEY = get_service_key()


def _maybe_dump_fishery_payload(data: dict, *, label: str) -> None:
    """디버깅 용도로 payload 를 로컬 파일에 저장 (환경변수 FISHERY_DEBUG_DUMP=true 일 때).
    파일명: .fishery_debug_<label>.json (마지막 덮어쓰기)"""
    if os.getenv("FISHERY_DEBUG_DUMP", "false").lower() not in ("true", "1", "yes"):  # pragma: no cover
        return
    try:
        import json, pathlib, datetime as _dt
        path = pathlib.Path(".fishery_debug_" + label + ".json")
        payload = {"ts": _dt.datetime.utcnow().isoformat() + "Z", "data": data}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[fishery-dump] wrote {path}")
    except Exception as e:  # pragma: no cover
        logger.debug(f"fishery dump failed: {e}")

# 날씨 API 설정
WEATHER_URL = os.getenv("WEATHER_URL", "https://apihub.kma.go.kr/api/typ01/url/fct_shrt_reg.php")
WEATHER_AUTH_KEY = os.getenv("WEATHER_AUTH_KEY", "")
WEATHER_CODE_URL = os.getenv("WEATHER_CODE_URL", "https://apihub.kma.go.kr/api/typ01/url/fct_afs_srf.php")


# 실제 API 응답에 맞는 응답 모델들
class TopData(BaseModel):
    """실제 API에서 반환되는 top 데이터 구조"""

    beforeDay: Optional[dict] = Field(None, description="전날 데이터")
    nowDay: Optional[dict] = Field(None, description="당일 데이터")


class RealApiData(BaseModel):
    """실제 API data 구조"""

    top: TopData = Field(..., description="실제 기상 데이터")


class RealShipSafeStatsResponse(BaseModel):
    """실제 API 응답 구조"""

    id: str = Field(..., description="응답상태 고유번호")
    status: str = Field(..., description="응답상태")
    data: RealApiData = Field(..., description="응답값 객체")


# 기존 형식 유지 (호환성을 위해)
class WeatherData(BaseModel):
    temp: float = Field(..., description="기온")
    winsp: float = Field(..., description="풍속")
    windir: float = Field(..., description="풍향")
    logDateTime: str = Field(..., description="측정날짜")


class WeatherHistoryData(BaseModel):
    beforeDay: WeatherData = Field(..., description="전날 데이터")
    nowDay: WeatherData = Field(..., description="당일 데이터")


class ShipSafeStatsResponse(BaseModel):
    id: int = Field(..., description="응답상태 고유번호")
    status: str = Field(..., description="응답상태")
    data: WeatherHistoryData = Field(..., description="응답값 객체")


class TideEvent(BaseModel):
    time: str = Field(..., description="물때 시각 (HH:MM)")
    height: float = Field(..., description="조위 (m)")


class HolidayWeatherDay(BaseModel):
    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    label: str = Field(..., description="요약 라벨")
    weekday: str = Field(..., description="요일 (국문 약어)")
    condition: str = Field(..., description="날씨 상태 설명")
    summary: str = Field(..., description="간단 요약")
    temp_min: float = Field(..., description="최저 기온")
    temp_max: float = Field(..., description="최고 기온")
    wind_speed: float = Field(..., description="평균 풍속 (m/s)")
    wind_direction: str = Field(..., description="풍향 설명")
    wave_height: float = Field(..., description="평균 파고 (m)")
    precipitation_chance: int = Field(..., description="강수 확률 (%)")
    tide_phase: str = Field(..., description="물때 단계")
    moon_age: float = Field(..., description="음력 일령")
    sunrise: str = Field(..., description="일출 시각")
    sunset: str = Field(..., description="일몰 시각")
    best_window: str = Field(..., description="권장 출조 시간대")
    caution_window: Optional[str] = Field(None, description="주의가 필요한 시간대")
    high_tides: List[TideEvent] = Field(default_factory=list, description="만조 시각/조위")
    low_tides: List[TideEvent] = Field(default_factory=list, description="간조 시각/조위")
    comfort_score: float = Field(..., description="낚시 적합도 점수 (0-100)")


class HolidayChartPoint(BaseModel):
    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    label: str = Field(..., description="차트 라벨")
    wind_speed: float = Field(..., description="평균 풍속 (m/s)")
    wave_height: float = Field(..., description="평균 파고 (m)")
    temp_min: float = Field(..., description="최저 기온")
    temp_max: float = Field(..., description="최고 기온")
    precipitation_chance: int = Field(..., description="강수 확률 (%)")
    comfort_score: float = Field(..., description="낚시 적합도 점수 (0-100)")


class HolidayRecommendation(BaseModel):
    date: str = Field(..., description="추천 날짜")
    label: str = Field(..., description="추천 라벨")
    reason: str = Field(..., description="추천 이유")
    score: float = Field(..., description="적합도 점수 (0-100)")


class HolidayWeatherResponse(BaseModel):
    range_label: str = Field(..., description="조회 구간 라벨")
    start_date: str = Field(..., description="기간 시작일")
    end_date: str = Field(..., description="기간 종료일")
    source: str = Field(..., description="데이터 출처")
    days: List[HolidayWeatherDay] = Field(..., description="일자별 상세 정보")
    best: HolidayRecommendation = Field(..., description="최적 날짜 추천")
    chart: List[HolidayChartPoint] = Field(..., description="시각화용 차트 데이터")
    advisories: List[str] = Field(default_factory=list, description="주의/참고 사항")


_CHUSEOK_FORECAST_DATA: List[Dict[str, object]] = [
    {
        "date": "2025-10-05",
        "label": "추석 연휴 첫째 날",
        "weekday": "일",
        "condition": "맑음",
        "summary": "맑고 동남풍이 약해 오전 출조에 최적",
        "temp_min": 18.0,
        "temp_max": 26.0,
        "wind_speed": 4.8,
        "wind_direction": "동남 (ESE)",
        "wave_height": 0.4,
        "precipitation_chance": 10,
        "tide_phase": "사리 직후 안정기",
        "moon_age": 2.8,
        "sunrise": "05:57",
        "sunset": "18:03",
        "best_window": "06:00~10:30",
        "caution_window": "15:00 이후 동풍 강화",
        "high_tides": [
            {"time": "04:18", "height": 1.92},
            {"time": "16:42", "height": 1.63},
        ],
        "low_tides": [
            {"time": "10:22", "height": 0.21},
            {"time": "22:48", "height": 0.31},
        ],
        "score": 87.5,
        "recommendation_reason": "풍속 5m/s 이하, 파고 0.4m로 안정적이고 오전 썰물과 맞물려 입질이 활발할 가능성이 큽니다.",
    },
    {
        "date": "2025-10-06",
        "label": "추석 연휴 둘째 날",
        "weekday": "월",
        "condition": "구름 많음",
        "summary": "남동풍이 가장 약하고 파고 0.3m로 가장 안정",
        "temp_min": 17.0,
        "temp_max": 25.0,
        "wind_speed": 3.6,
        "wind_direction": "남동 (SE)",
        "wave_height": 0.3,
        "precipitation_chance": 20,
        "tide_phase": "조금",
        "moon_age": 3.8,
        "sunrise": "05:58",
        "sunset": "18:01",
        "best_window": "05:30~09:30",
        "caution_window": "18:00 이후 북동풍 전환",
        "high_tides": [
            {"time": "05:10", "height": 1.88},
            {"time": "17:35", "height": 1.52},
        ],
        "low_tides": [
            {"time": "11:18", "height": 0.26},
            {"time": "23:41", "height": 0.35},
        ],
        "score": 91.0,
        "recommendation_reason": "풍속과 파고가 가장 안정적이고 물때가 '조금'으로 초보자도 편하게 낚시하기 좋습니다.",
    },
    {
        "date": "2025-10-07",
        "label": "추석 연휴 셋째 날",
        "weekday": "화",
        "condition": "구름 많고 한때 약한 비",
        "summary": "북동풍이 강해지기 시작, 오전 위주 출조 권장",
        "temp_min": 17.0,
        "temp_max": 24.0,
        "wind_speed": 6.2,
        "wind_direction": "북동 (NE)",
        "wave_height": 0.7,
        "precipitation_chance": 40,
        "tide_phase": "조금",
        "moon_age": 4.8,
        "sunrise": "05:59",
        "sunset": "18:00",
        "best_window": "06:30~09:00",
        "caution_window": "13:00 이후 파고 상승",
        "high_tides": [
            {"time": "06:04", "height": 1.74},
            {"time": "18:28", "height": 1.38},
        ],
        "low_tides": [
            {"time": "00:36", "height": 0.43},
            {"time": "12:14", "height": 0.39},
        ],
        "score": 70.0,
        "recommendation_reason": "오전에는 여전히 출조 가능하지만 오후부터 북동풍과 파고가 상승합니다.",
    },
    {
        "date": "2025-10-08",
        "label": "추석 연휴 넷째 날",
        "weekday": "수",
        "condition": "흐리고 비",
        "summary": "북동풍 강하고 파고 1m 이상, 대체 일정 권장",
        "temp_min": 16.0,
        "temp_max": 22.0,
        "wind_speed": 8.1,
        "wind_direction": "북동 (NE)",
        "wave_height": 1.1,
        "precipitation_chance": 70,
        "tide_phase": "하현 전",
        "moon_age": 5.8,
        "sunrise": "06:00",
        "sunset": "17:58",
        "best_window": "대체 일정 고려",
        "caution_window": "하루 종일 풍속 8m/s 이상",
        "high_tides": [
            {"time": "06:58", "height": 1.58},
            {"time": "19:24", "height": 1.25},
        ],
        "low_tides": [
            {"time": "01:28", "height": 0.52},
            {"time": "13:46", "height": 0.61},
        ],
        "score": 52.0,
        "recommendation_reason": "풍속과 파고가 모두 높아 안전을 위해 일정을 조정하는 것이 좋습니다.",
    },
]

_CHUSEOK_FORECAST_ADVISORIES: List[str] = [
    "10월 6일이 연휴 중 가장 안정적인 조건으로 추천드립니다.",
    "7일 오후 이후부터 북동풍이 강해지므로 오전 위주 출조가 안전합니다.",
    "8일은 풍속과 파고가 모두 높아 예비 일정을 고려해 주세요.",
]


def _build_chuseok_holiday_weather() -> HolidayWeatherResponse:
    days: List[HolidayWeatherDay] = []
    chart: List[HolidayChartPoint] = []
    best_entry: Optional[Dict[str, object]] = None

    for entry in _CHUSEOK_FORECAST_DATA:
        day = HolidayWeatherDay(
            date=entry["date"],
            label=entry["label"],
            weekday=entry["weekday"],
            condition=entry["condition"],
            summary=entry["summary"],
            temp_min=float(entry["temp_min"]),
            temp_max=float(entry["temp_max"]),
            wind_speed=float(entry["wind_speed"]),
            wind_direction=str(entry["wind_direction"]),
            wave_height=float(entry["wave_height"]),
            precipitation_chance=int(entry["precipitation_chance"]),
            tide_phase=str(entry["tide_phase"]),
            moon_age=float(entry["moon_age"]),
            sunrise=str(entry["sunrise"]),
            sunset=str(entry["sunset"]),
            best_window=str(entry["best_window"]),
            caution_window=str(entry["caution_window"]) if entry.get("caution_window") else None,
            high_tides=[TideEvent(**event) for event in entry["high_tides"]],
            low_tides=[TideEvent(**event) for event in entry["low_tides"]],
            comfort_score=float(entry["score"]),
        )
        days.append(day)

        chart.append(
            HolidayChartPoint(
                date=entry["date"],
                label=entry["label"],
                wind_speed=float(entry["wind_speed"]),
                wave_height=float(entry["wave_height"]),
                temp_min=float(entry["temp_min"]),
                temp_max=float(entry["temp_max"]),
                precipitation_chance=int(entry["precipitation_chance"]),
                comfort_score=float(entry["score"]),
            )
        )

        if best_entry is None or float(entry["score"]) > float(best_entry["score"]):
            best_entry = entry

    assert best_entry is not None  # for type checkers
    best = HolidayRecommendation(
        date=str(best_entry["date"]),
        label=str(best_entry["label"]),
        reason=str(best_entry["recommendation_reason"]),
        score=float(best_entry["score"]),
    )

    return HolidayWeatherResponse(
        range_label="추석 연휴 (10/5~10/8)",
        start_date=_CHUSEOK_FORECAST_DATA[0]["date"],
        end_date=_CHUSEOK_FORECAST_DATA[-1]["date"],
        source="mock-holiday-forecast",
        days=days,
        best=best,
        chart=chart,
        advisories=_CHUSEOK_FORECAST_ADVISORIES,
    )


def get_chuseok_holiday_forecast() -> HolidayWeatherResponse:
    """추석 연휴(10/5~10/8) 기상/물때 정보."""

    return _build_chuseok_holiday_weather()

# 어획량 관련 응답 모델들
class CatchData(BaseModel):
    ship_id: str = Field(..., description="선박 ID")
    ship_name: str = Field(..., description="선박명")
    fish_type: str = Field(..., description="어종")
    catch_amount: float = Field(..., description="어획량(kg)")
    catch_date: str = Field(..., description="어획 날짜")
    catch_location: str = Field(..., description="어획 지역")
    captain_name: str = Field(..., description="선장명")


class CatchHistoryResponse(BaseModel):
    id: str = Field(..., description="응답상태 고유번호")
    status: str = Field(..., description="응답상태")
    data: dict = Field(..., description="어획 데이터")


class ShipStatus(BaseModel):
    ship_id: str = Field(..., description="선박 ID")
    ship_name: str = Field(..., description="선박명")
    harbor_name: str = Field(..., description="항구명")
    dock_area: str = Field(..., description="하역 구역")
    arrival_time: str = Field(..., description="입항 시간")
    total_catch: float = Field(..., description="총 어획량(kg)")
    status: str = Field(..., description="선박 상태")


class HarborShipsResponse(BaseModel):
    id: str = Field(..., description="응답상태 고유번호")
    status: str = Field(..., description="응답상태")
    data: dict = Field(..., description="선박 입항 데이터")

# 날씨 API 응답 모델들
class WeatherForecast(BaseModel):
    region_code: str = Field(..., description="예보구역코드", alias="REG_ID")
    start_time: str = Field(..., description="시작시각(년월일시분,KST)", alias="TM_ST")
    end_time: str = Field(..., description="종료시각(년월일시분,KST)", alias="TM_ED")
    region_type: str = Field(..., description="특성", alias="REG_SP")
    region_name: str = Field(..., description="예보구역명", alias="REG_NAME")
    station_id: str = Field(..., description="발표관서", alias="STN_ID")
    forecast_time: str = Field(..., description="발표시각(KST)", alias="TM_FC")
    input_time: str = Field(..., description="입력시각(KST)", alias="TM_IN")
    reference_number: str = Field(..., description="참조번호", alias="CNT")
    forecaster_name: str = Field(..., description="예보관명", alias="MAN_FC")
    effective_time: str = Field(..., description="발효시각(년월일시분,KST)", alias="TM_EF")
    period_mode: str = Field(..., description="구간 (A01(24시간),A02(12시간))", alias="MOD")
    effective_number: str = Field(..., description="발효번호", alias="NE")
    station_name: str = Field(..., description="발표관서", alias="STN")
    announcement_code: str = Field(..., description="발표코드", alias="C")
    forecaster_id: str = Field(..., description="예보관ID", alias="MAN_ID")
    wind_direction_start: str = Field(..., description="풍향1(16방위) (범위 시작값)", alias="W1")
    wind_direction_trend: str = Field(..., description="풍향경향", alias="T")
    wind_direction_end: str = Field(..., description="풍향2(16방위) (범위 종료값)", alias="W2")
    temperature: str = Field(..., description="기온", alias="TA")
    precipitation_probability: str = Field(..., description="강수확률(%)", alias="ST")
    sky_condition: str = Field(..., description="하늘상태", alias="SKY")
    precipitation_type: str = Field(..., description="강수유무", alias="PREP")
    weather_forecast: str = Field(..., description="예보", alias="WF")
    wind_speed_start: Optional[str] = Field(None, description="풍속1 (범위 시작값)", alias="S1")
    wind_speed_end: Optional[str] = Field(None, description="풍속2 (범위 종료값)", alias="S2")
    wave_height_start: Optional[str] = Field(None, description="파고1 (범위 시작값)", alias="WH1")
    wave_height_end: Optional[str] = Field(None, description="파고2 (범위 종료값)", alias="WH2")
    
    class Config:
        populate_by_name = True

# 하늘상태 및 강수유무 코드 변환 함수들
def convert_sky_condition(sky_code: str) -> str:
    """하늘상태 코드를 한글로 변환"""
    sky_map = {
        "DB01": "맑음",
        "DB02": "구름조금", 
        "DB03": "구름많음",
        "DB04": "흐림"
    }
    return sky_map.get(sky_code, sky_code)

def convert_precipitation_type(prep_code: str) -> str:
    """강수유무 코드를 한글로 변환"""
    prep_map = {
        "0": "강수없음",
        "1": "비",
        "2": "비/눈",
        "3": "눈", 
        "4": "눈/비"
    }
    return prep_map.get(prep_code, prep_code)

class WeatherResponse(BaseModel):
    forecasts: List[WeatherForecast] = Field(..., description="날씨 예보 목록")
    total_count: int = Field(..., description="총 예보 건수")
    region_name: str = Field(..., description="조회 지역명")
    forecast_time: str = Field(..., description="예보 발표시각")

# 예보구역 검색용 모델들
class WeatherRegion(BaseModel):
    REG_ID: str = Field(..., description="예보구역코드")
    TM_ST: str = Field(..., description="시작시각(년월일시분,KST)")
    TM_ED: str = Field(..., description="종료시각(년월일시분,KST)")
    REG_SP: str = Field(..., description="특성 (A:육상광역,B:육상국지,C:도시,D:산악,E:고속도로,H:해상광역,I:해상국지,J:연안바다,K:해수욕장,L:연안항로,M:먼항로,P:산악)")
    REG_NAME: str = Field(..., description="예보구역명")

class WeatherRegionResponse(BaseModel):
    regions: List[WeatherRegion] = Field(..., description="예보구역 목록")
    total_count: int = Field(..., description="총 구역 수")
    search_term: Optional[str] = Field(None, description="검색어")
    region_type: Optional[str] = Field(None, description="구역 특성 필터")


# 내부 헬퍼 함수들
def fetch_catch_history_data(
    *,
    fish_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ship_id: Optional[str] = None,
    timeout: float = 30.0,
) -> CatchHistoryResponse:
    """동일 프로세스 내에서 어획 이력 데이터를 조회하기 위한 동기 헬퍼."""

    if DEVELOPMENT_MODE or not SERVICE_KEY:
        logger.info(
            "Fishery API running in development mode or missing key; falling back to mock catch history data."
        )
        return _get_mock_catch_history_data(fish_type, start_date, end_date, ship_id)

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
        "Accept": "application/json, */*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    params: dict[str, str] = {"serviceKey": SERVICE_KEY}
    if fish_type:
        params["fish_type"] = fish_type
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if ship_id:
        params["ship_id"] = ship_id

    url = f"{BASE_API_URL}{API_ENDPOINTS['catch_history']}"

    try:
        with httpx.Client(
            verify=False,
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = client.get(url, params=params)
            logger.info(
                "Catch history API call finished with status %s for params %s",
                response.status_code,
                params,
            )
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    payload["data"].setdefault("source", "real")
                return CatchHistoryResponse(**payload)

            logger.error(
                "Catch history API error: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
    except httpx.RequestError as exc:
        logger.error("Catch history API request failed: %s", exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error while fetching catch history: %s", exc)

    logger.info("Falling back to mock catch history data after API failure")
    return _get_mock_catch_history_data(fish_type, start_date, end_date, ship_id)


def fetch_ship_safe_stats_history_sync(
    date: str,
    *,
    timeout: float = 30.0,
) -> Optional[ShipSafeStatsResponse]:
    """선박 안전 기상 정보 API를 동기 방식으로 호출."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
        "Accept": "application/json, */*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    url = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}"
    last_error: Optional[str] = None

    try:
        with httpx.Client(
            verify=False,
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            for attempt, key_variant in enumerate(service_key_variants(), start=1):
                params = {"serviceKey": key_variant, "date": date}
                try:
                    response = client.get(url, params=params, timeout=timeout)
                except httpx.RequestError as exc:
                    last_error = f"request error on attempt {attempt}: {exc}"
                    logger.warning(last_error)
                    continue

                logger.info(
                    "Ship-safe API attempt %s with %s key returned status %s",
                    attempt,
                    "decoded"
                    if key_variant == DECODED_SERVICE_KEY and RAW_SERVICE_KEY != DECODED_SERVICE_KEY
                    else "raw",
                    response.status_code,
                )

                if response.status_code != 200:
                    last_error = f"status {response.status_code}: {response.text[:200]}"
                    continue

                try:
                    data = response.json()
                except ValueError as exc:
                    last_error = f"json decode failed: {exc}"
                    logger.warning(last_error)
                    continue

                top_data = (data.get("data") or {}).get("top") if isinstance(data, dict) else None
                if isinstance(top_data, dict) and top_data:
                    _maybe_dump_fishery_payload(data, label="ship_safe_success")
                    return ShipSafeStatsResponse(**data)

                last_error = "empty top data"
                logger.warning("Ship-safe API attempt %s returned empty data", attempt)

    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error while fetching ship-safe stats: %s", exc)

    if last_error:
        logger.warning("Ship-safe stats API failed; reason: %s", last_error)
    return None


# API 엔드포인트들


@router.get("/ship-safe/stats/history", response_model=ShipSafeStatsResponse)
async def get_ship_safe_stats_history(
    date: str = Query(..., description="요청날짜 (YYYYMMDD 형식)", example="20250102")
):
    """주요 기상 요소 과거 정보 조회 (실패 시 모의 데이터 반환)."""

    if not RAW_SERVICE_KEY:
        logger.warning("DPG_SERVICE_KEY not set; returning mock weather data")
        return _get_mock_weather_data(date)

    response = await asyncio.to_thread(fetch_ship_safe_stats_history_sync, date)
    if response is not None:
        return response

    return _get_mock_weather_data(date)


@router.get("/ship-safe/holiday/forecast", response_model=HolidayWeatherResponse)
async def get_holiday_weather_forecast():
    """추석 연휴 기간(10/5~10/8) 기상 및 물때 정보."""

    return get_chuseok_holiday_forecast()

# 모의 데이터 생성 함수
def _get_mock_weather_data(date: str) -> ShipSafeStatsResponse:
    """개발/테스트용 모의 기상 데이터"""

    # 날짜 파싱 (YYYYMMDD -> YYYY-MM-DD)
    try:
        parsed_date = datetime.strptime(date, "%Y%m%d")
        formatted_date = parsed_date.strftime("%Y-%m-%d")

        # 전날 계산
        prev_date = parsed_date - timedelta(days=1)
        prev_formatted = prev_date.strftime("%Y-%m-%d")
    except:
        formatted_date = "2025-01-02"
        prev_formatted = "2025-01-01"

    before_day = WeatherData(
        temp=1.6, winsp=4.4, windir=1022.6, logDateTime=prev_formatted
    )

    now_day = WeatherData(
        temp=5.9, winsp=1.3, windir=1022.2, logDateTime=formatted_date
    )

    return ShipSafeStatsResponse(
        id=1,
        status="success",
        data=WeatherHistoryData(beforeDay=before_day, nowDay=now_day),
    )


@router.get("/debug/env-info")
async def get_environment_info():
    """
    환경변수 및 설정 정보 확인 (디버깅용)
    """
    return {
        "environment_variables": {
            "FISHERY_API_DEV_MODE": os.getenv("FISHERY_API_DEV_MODE", "not_set"),
            "DPG_SERVICE_KEY_SET": bool(os.getenv("DPG_SERVICE_KEY")),
            "DPG_SERVICE_KEY_LENGTH": len(os.getenv("DPG_SERVICE_KEY", "")),
            "DPG_SERVICE_KEY_PREVIEW": f"{RAW_SERVICE_KEY[:10]}{'*' * max(0, len(RAW_SERVICE_KEY) - 10)}" if RAW_SERVICE_KEY else "not_set"
        },
        "current_settings": {
            "BASE_API_URL": BASE_API_URL,
            "DEVELOPMENT_MODE": DEVELOPMENT_MODE,
            "API_ENDPOINTS": API_ENDPOINTS,
        },
        "suggestions": [
            "서버 재시작: 환경변수 변경 후 서버 재시작 필요",
            "환경변수 확인: echo $DPG_SERVICE_KEY",
            "환경변수 설정: export DPG_SERVICE_KEY=실제키값",
            "또는 .env 파일에 DPG_SERVICE_KEY=실제키값 추가",
        ],
    }


@router.get("/debug/test-api-key")
async def test_api_key_validity():
    """
    API 키 유효성 테스트 (실제 API 호출 없이)
    """
    if not RAW_SERVICE_KEY or RAW_SERVICE_KEY == "":
        return {
            "status": "error",
            "message": "API 키가 설정되지 않았습니다.",
            "solutions": [
                "환경변수 DPG_SERVICE_KEY 설정",
                ".env 파일에 DPG_SERVICE_KEY 추가",
                "서버 재시작",
            ],
        }

    # API 키 기본 형식 검증
    key_analysis = {
        "length": len(RAW_SERVICE_KEY),
        "contains_special_chars": any(c in RAW_SERVICE_KEY for c in "!@#$%^&*()"),
        "is_alphanumeric": RAW_SERVICE_KEY.replace("%", "").isalnum(),
        "starts_with": RAW_SERVICE_KEY[:3] if len(RAW_SERVICE_KEY) >= 3 else RAW_SERVICE_KEY,
        "preview": f"{RAW_SERVICE_KEY[:10]}{'*' * max(0, len(RAW_SERVICE_KEY) - 10)}"
    }

    return {
        "status": "info",
        "message": "API 키가 설정되어 있습니다.",
        "key_analysis": key_analysis,
        "next_step": "실제 API 호출로 유효성 확인하려면 /ship-safe/stats/history 엔드포인트를 호출하세요.",
    }


@router.get("/debug/test-raw-api")
async def test_raw_api_call():
    """
    실제 API를 직접 호출해서 응답을 확인 (디버깅용)
    """
    test_date = "20250102"
    
    if not RAW_SERVICE_KEY:
        return {"error": "SERVICE_KEY not set"}

    try:
        # 다양한 HTTPS 헤더 설정 테스트
        test_headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
            "Accept": "application/json, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Referer": BASE_API_URL,
        }

        async with httpx.AsyncClient(
            verify=False, timeout=10.0, headers=test_headers, follow_redirects=True
        ) as client:
            # 여러 가지 방법으로 API 호출 시도
            test_results = {}

            # 방법 1: Query Parameter로 serviceKey 전달
            params1 = {"serviceKey": DECODED_SERVICE_KEY, "date": test_date}
            url1 = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}"

            try:
                response1 = await client.get(url1, params=params1, timeout=10.0)
                test_results["method1_query_params"] = {
                    "url": str(response1.url),
                    "status": response1.status_code,
                    "content": response1.text[:300],
                    "headers": dict(response1.headers),
                }
            except Exception as e:
                test_results["method1_query_params"] = {"error": str(e)}

            # 방법 2: URL에 직접 포함
            url2 = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}?serviceKey={DECODED_SERVICE_KEY}&date={test_date}"
            try:
                response2 = await client.get(url2, timeout=10.0)
                test_results["method2_url_direct"] = {
                    "url": url2[:100] + "...",  # 키 보안을 위해 일부만 표시
                    "status": response2.status_code,
                    "content": response2.text[:300],
                    "headers": dict(response2.headers),
                }
            except Exception as e:
                test_results["method2_url_direct"] = {"error": str(e)}

            # 방법 3: Header로 전달
            headers3 = {"Authorization": f"Bearer {DECODED_SERVICE_KEY}"}
            params3 = {"date": test_date}

            try:
                response3 = await client.get(
                    url1, params=params3, headers=headers3, timeout=10.0
                )
                test_results["method3_header"] = {
                    "url": str(response3.url),
                    "status": response3.status_code,
                    "content": response3.text[:300],
                    "headers": dict(response3.headers),
                }
            except Exception as e:
                test_results["method3_header"] = {"error": str(e)}

            return {
                "service_key_info": {
                    "length": len(RAW_SERVICE_KEY),
                    "preview": f"{RAW_SERVICE_KEY[:10]}***{RAW_SERVICE_KEY[-5:]}" if len(RAW_SERVICE_KEY) > 15 else "***",
                    "contains_special": any(c in "!@#$%^&*()+={}[]|\\:;\"'<>,.?/" for c in RAW_SERVICE_KEY)
                },
                "test_results": test_results,
                "recommendations": [
                    "API 문서에서 정확한 인증 방법 확인",
                    "서비스 키 발급 기관에 문의",
                    "키 형식이나 인코딩 확인",
                    "IP 화이트리스트 설정 확인",
                ],
            }

    except Exception as e:
        return {"error": f"Test failed: {str(e)}"}


@router.get("/ship-safe/stats/history/raw", response_model=RealShipSafeStatsResponse)
async def get_ship_safe_stats_history_raw(
    date: str = Query(..., description="요청날짜 (YYYYMMDD 형식)", example="20250102")
):
    """
    실제 API 응답 그대로 반환 (디버깅 및 실제 데이터 확인용)
    """
    try:
        if not RAW_SERVICE_KEY:
            raise HTTPException(status_code=400, detail="DPG_SERVICE_KEY not configured")
        # 최적화된 HTTPS 헤더 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
            "Accept": "application/json, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        async with httpx.AsyncClient(
            verify=False, timeout=30.0, headers=headers, follow_redirects=True
        ) as client:
            # method2 방식 사용 (테스트에서 성공한 방식)
            url = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}?serviceKey={DECODED_SERVICE_KEY}&date={date}"
            logger.info(f"Calling raw API: {url[:100]}...")
            response = await client.get(url, timeout=30.0)

            logger.info(f"Raw API Response status: {response.status_code}")
            logger.info(f"Raw API Response content: {response.text}")

            if response.status_code == 200:
                data = response.json()
                return RealShipSafeStatsResponse(**data)
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"API Error: {response.text}",
                )

    except Exception as e:
        logger.error(f"Raw API call failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catch/history", response_model=CatchHistoryResponse)
async def get_catch_history(
    fish_type: Optional[str] = Query(
        None, description="어종명 (예: 고등어, 삼치, 오징어)"
    ),
    start_date: Optional[str] = Query(None, description="조회 시작 날짜 (YYYYMMDD)"),
    end_date: Optional[str] = Query(None, description="조회 종료 날짜 (YYYYMMDD)"),
    ship_id: Optional[str] = Query(None, description="특정 선박 ID"),
):
    """
    특정 품목과 관련된 과거 어획 데이터를 선박 단위로 조회 (INT-S3-007)
    """
    try:
        if not RAW_SERVICE_KEY:
            logger.warning("DPG_SERVICE_KEY not set, using mock data")
            return _get_mock_catch_history_data(
                fish_type, start_date, end_date, ship_id
            )

        # HTTPS 요청을 위한 헤더 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
            "Accept": "application/json, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        async with httpx.AsyncClient(
            verify=False, timeout=30.0, headers=headers, follow_redirects=True
        ) as client:
            params = {"serviceKey": DECODED_SERVICE_KEY}
            if fish_type:
                params["fish_type"] = fish_type
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            if ship_id:
                params["ship_id"] = ship_id

            url = f"{BASE_API_URL}{API_ENDPOINTS['catch_history']}"
            logger.info(f"Calling catch history API: {url} with params: {params}")

            response = await client.get(url, params=params, timeout=30.0)

            logger.info(f"Catch History API Response status: {response.status_code}")
            logger.info(f"Catch History API Response content: {response.text[:500]}...")

            if response.status_code == 200:
                data = response.json()
                return CatchHistoryResponse(**data)
            else:
                logger.error(
                    f"External API error: {response.status_code}, content: {response.text}"
                )
                logger.info("Falling back to mock data due to API error")
                return _get_mock_catch_history_data(
                    fish_type, start_date, end_date, ship_id
                )

    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        return _get_mock_catch_history_data(fish_type, start_date, end_date, ship_id)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류")


@router.get("/harbor/ships/status", response_model=HarborShipsResponse)
async def get_harbor_ships_status(
    harbor_name: Optional[str] = Query(None, description="특정 항구명 (없으면 전체)")
):
    """
    실시간 선박 입항 및 하역 구역, 총 어획량 정보 조회 (INT-S3-001)
    """
    try:
        if not RAW_SERVICE_KEY:
            logger.warning("DPG_SERVICE_KEY not set, using mock data")
            return _get_mock_harbor_ships_data(harbor_name)

        # HTTPS 요청을 위한 헤더 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
            "Accept": "application/json, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        async with httpx.AsyncClient(
            verify=False, timeout=30.0, headers=headers, follow_redirects=True
        ) as client:
            params = {"serviceKey": DECODED_SERVICE_KEY}
            if harbor_name:
                params["harbor_name"] = harbor_name

            url = f"{BASE_API_URL}{API_ENDPOINTS['harbor_ships_status']}"
            logger.info(f"Calling harbor ships API: {url} with params: {params}")

            response = await client.get(url, params=params, timeout=30.0)

            logger.info(f"Harbor Ships API Response status: {response.status_code}")
            logger.info(f"Harbor Ships API Response content: {response.text[:500]}...")

            if response.status_code == 200:
                data = response.json()
                return HarborShipsResponse(**data)
            else:
                logger.error(
                    f"External API error: {response.status_code}, content: {response.text}"
                )
                logger.info("Falling back to mock data due to API error")
                return _get_mock_harbor_ships_data(harbor_name)

    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        return _get_mock_harbor_ships_data(harbor_name)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류")


# 모의 데이터 생성 함수들
def _get_mock_catch_history_data(
    fish_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ship_id: Optional[str] = None,
) -> CatchHistoryResponse:
    """30일치 어획 이력 모의 데이터

    각 어종마다 뚜렷한 추세(상승/하락/완만)를 부여해 그래프에서
    흐름을 쉽게 구분할 수 있도록 구성한다.
    """

    def parse_yyyymmdd(value: Optional[str]) -> datetime:
        if value:
            for fmt in ("%Y%m%d", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return datetime.utcnow()

    end_dt = parse_yyyymmdd(end_date)
    start_dt = parse_yyyymmdd(start_date)
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    today = datetime.utcnow().date()
    window_days = 31  # inclusive 범위: 32일 (예: 08.28 ~ 09.28)

    end_date = min(end_dt.date(), today)
    min_start_allowed = end_date - timedelta(days=window_days)

    requested_start_date = start_dt.date()
    if requested_start_date > end_date:
        requested_start_date = end_date

    if requested_start_date < min_start_allowed:
        start_date = min_start_allowed
    else:
        start_date = requested_start_date

    if (end_date - start_date).days < window_days:
        start_date = end_date - timedelta(days=window_days)

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.min.time())

    species_profiles: List[Dict[str, object]] = [
        # name, base weight, trend (end-to-end percent change), seasonal & weekly oscillation strengths,
        # phase offsets, random noise scale, base price, and price trend.
        {
            "name": "갈치",
            "base": 520.0,
            "trend": -0.45,  # 분기 내 점진적 감소
            "seasonal": 0.22,
            "weekly": 0.08,
            "phase": 0.0,
            "noise": 0.05,
            "price": 2600000,
            "price_trend": 0.28,  # 공급 감소로 가격 상승
        },
        {
            "name": "한치",
            "base": 190.0,
            "trend": 0.55,  # 뚜렷한 증가 추세
            "seasonal": 0.28,
            "weekly": 0.11,
            "phase": 0.6,
            "noise": 0.06,
            "price": 1850000,
            "price_trend": -0.2,
        },
        {
            "name": "갑오징어",
            "base": 210.0,
            "trend": 0.18,
            "seasonal": 0.15,
            "weekly": 0.05,
            "phase": 1.1,
            "noise": 0.04,
            "price": 2150000,
            "price_trend": -0.05,
        },
        {
            "name": "문어",
            "base": 150.0,
            "trend": -0.25,
            "seasonal": 0.12,
            "weekly": 0.09,
            "phase": 2.2,
            "noise": 0.05,
            "price": 3300000,
            "price_trend": 0.18,
        },
        {
            "name": "고등어",
            "base": 240.0,
            "trend": 0.80,
            "seasonal": 0.2,
            "weekly": 0.07,
            "phase": 1.7,
            "noise": 0.05,
            "price": 4600000,
            "price_trend": -0.12,
        },
        {
            "name": "붉은멸",
            "base": 110.0,
            "trend": -0.15,
            "seasonal": 0.18,
            "weekly": 0.09,
            "phase": 2.8,
            "noise": 0.07,
            "price": 950000,
            "price_trend": 0.05,
        },
    ]

    if fish_type:
        species_profiles = [
            profile
            for profile in species_profiles
            if fish_type in str(profile["name"])
        ] or species_profiles

    records = []
    total_catch = 0.0
    total_days = (end_dt - start_dt).days + 1
    current_id = 1

    date_cursor = start_dt
    for day_index in range(total_days):
        progress = day_index / max(1, total_days - 1)
        seasonal_phase = 2 * math.pi * progress

        for profile in species_profiles:
            base = float(profile["base"])
            trend = float(profile["trend"])
            seasonal_strength = float(profile["seasonal"])
            weekly_strength = float(profile["weekly"])
            phase = float(profile["phase"])
            noise_strength = float(profile["noise"])
            price_base = float(profile["price"])
            price_trend = float(profile["price_trend"])

            trend_factor = max(0.15, 1 + trend * progress)
            seasonal_term = 1 + seasonal_strength * math.sin(seasonal_phase + phase)
            weekly_term = 1 + weekly_strength * math.sin(
                seasonal_phase * 2 + phase * 0.5
            )

            seed = int(date_cursor.strftime("%Y%m%d")) + sum(
                ord(ch) for ch in str(profile["name"])
            )
            rng = random.Random(seed)
            noise_term = 1 + noise_strength * rng.uniform(-1.0, 1.0)

            weight = base * trend_factor * seasonal_term * weekly_term * noise_term
            weight = max(18.0, weight)

            price_factor = max(0.2, 1 + price_trend * progress)
            price_noise = 1 + 0.08 * rng.uniform(-1.0, 1.0)
            price_value = price_base * price_factor * price_noise

            record = {
                "id": f"MOCK-{current_id:04d}",
                "ship_id": f"S{(current_id % 7) + 1:03d}",
                "ship_name": ["해운호", "바다별호", "청해호", "동해스타", "포항매리"][
                    current_id % 5
                ],
                "itemName": profile["name"],
                "fish_type": profile["name"],
                "price": round(price_value, 2),
                "weight": round(weight, 2),
                "weight_unit": "kg",
                "logDatetime": (date_cursor + timedelta(hours=6)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "catch_date": date_cursor.strftime("%Y-%m-%d"),
                "catch_location": "구룡포 근해",
                "captain_name": ["김선장", "이선장", "박선장", "최선장"][
                    current_id % 4
                ],
            }

            if ship_id and record["ship_id"] != ship_id:
                current_id += 1
                continue

            records.append(record)
            total_catch += record["weight"]
            current_id += 1

        date_cursor += timedelta(days=1)

    return CatchHistoryResponse(
        id="mock-month",
        status="success",
        data={
            "records": records,
            "total_catch": round(total_catch, 2),
            "days": (end_dt - start_dt).days + 1,
            "source": "mock-month",
        },
    )


def _get_mock_harbor_ships_data(
    harbor_name: Optional[str] = None,
) -> HarborShipsResponse:
    """선박 입항 정보 모의 데이터"""
    return HarborShipsResponse(
        id="1",
        status="success",
        data={
            "harbor_name": harbor_name or "구룡포항",
            "total_ships": 2,
            "total_catch": 2140.8,
            "ships": [
                {
                    "ship_id": "S001",
                    "ship_name": "해운호",
                    "harbor_name": "구룡포항",
                    "dock_area": "A구역",
                    "arrival_time": "2025-01-02T05:30:00",
                    "total_catch": 1250.5,
                    "status": "하역중",
                },
                {
                    "ship_id": "S002",
                    "ship_name": "바다별호",
                    "harbor_name": "구룡포항",
                    "dock_area": "B구역",
                    "arrival_time": "2025-01-02T06:15:00",
                    "total_catch": 890.3,
                    "status": "입항완료",
                },
            ],

            "updated_at": "2025-01-02T08:00:00"
        }
    )

@router.get("/weather/forecast", response_model=WeatherResponse)
async def get_weather_forecast(
    reg: Optional[str] = Query(None, description="예보구역코드 (예: 11B20304), 없으면 전체"),
    stn: Optional[str] = Query(None, description="발표관서번호, 없으면 전체"),
    tmfc: Optional[str] = Query(None, description="발표시간 (YYYYMMDDHH, KST), 없으면 전체, 0이면 가장 최근"),
    tmfc1: Optional[str] = Query(None, description="발표시간 시작 (YYYYMMDDHH, KST)"),
    tmfc2: Optional[str] = Query(None, description="발표시간 종료 (YYYYMMDDHH, KST)"),
    tmef1: Optional[str] = Query(None, description="발효시간 시작 (YYYYMMDDHH, KST)"),
    tmef2: Optional[str] = Query(None, description="발효시간 종료 (YYYYMMDDHH, KST)"),
    disp: int = Query(1, description="표출형태 - 0: 포트란 적합, 1: CSV 적합(기본값)"),
    help: Optional[int] = Query(None, description="도움말 - 1: 도움말 정보 표시")
):
    """
    기상청 단기예보 API를 통한 날씨 정보 조회
    CSV 형식 응답을 파싱하여 구조화된 데이터로 반환
    """
    try:
        if not WEATHER_AUTH_KEY:
            raise HTTPException(status_code=400, detail="WEATHER_AUTH_KEY가 설정되지 않았습니다.")
        
        # 기상청 API 헤더 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Weather/1.0)",
            "Accept": "text/csv, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }
        
        async with httpx.AsyncClient(
            verify=False,
            timeout=30.0,
            headers=headers,
            follow_redirects=True
        ) as client:
            # 파라미터 구성 - None이 아닌 값들만 포함
            params = {
                "authKey": WEATHER_AUTH_KEY,
                "disp": disp
            }
            
            # 선택적 파라미터들 추가
            if reg is not None:
                params["reg"] = reg
            if stn is not None:
                params["stn"] = stn
            if tmfc is not None:
                params["tmfc"] = tmfc
            if tmfc1 is not None:
                params["tmfc1"] = tmfc1
            if tmfc2 is not None:
                params["tmfc2"] = tmfc2
            if tmef1 is not None:
                params["tmef1"] = tmef1
            if tmef2 is not None:
                params["tmef2"] = tmef2
            if help is not None:
                params["help"] = help
            
            logger.info(f"Calling KMA weather API: {WEATHER_URL}")
            logger.info(f"Parameters: {params}")
            response = await client.get(WEATHER_URL, params=params, timeout=30.0)
            
            logger.info(f"Weather API Response status: {response.status_code}")
            logger.info(f"Final URL called: {response.url}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(f"Full response content: {response.text}")
            logger.info(f"Weather API Response content preview: {response.text[:200]}...")
            
            if response.status_code == 200:
                # 고정폭 형식 응답 파싱
                content = response.text.strip()
                
                # 줄 단위로 분리
                lines = content.split('\n')
                if len(lines) < 2:
                    logger.warning("Invalid format from weather API")
                    raise HTTPException(status_code=500, detail="기상청 API에서 잘못된 형식을 반환했습니다.")
                
                # 데이터 행들을 파싱 (주석과 헤더 라인 제외)
                forecasts = []
                data_found = False
                
                for line in lines:
                    line_stripped = line.strip()
                    # 주석이나 헤더 라인 제외
                    if not line_stripped or line_stripped.startswith('#') or 'REG_ID' in line_stripped or '7777END' in line_stripped:
                        continue
                    
                    data_found = True
                    
                    # 공백으로 구분된 형식 파싱 (실제 응답 형태에 맞춤)
                    # REG_ID TM_FC TM_EF MOD NE STN C MAN_ID MAN_FC W1 T W2 S1 S2 WH1 WH2 SKY PREP WF
                    try:
                        # 공백으로 분리하되 큰따옴표로 둘러싸인 부분은 하나로 처리
                        import re
                        # 큰따옴표로 둘러싸인 부분을 찾아서 공백을 임시 문자로 대체
                        temp_line = line
                        quoted_parts = re.findall(r'"[^"]*"', temp_line)
                        for i, quoted in enumerate(quoted_parts):
                            temp_line = temp_line.replace(quoted, f"__QUOTED_{i}__")
                        
                        parts = temp_line.split()
                        
                        # 큰따옴표 부분 복원
                        for i, quoted in enumerate(quoted_parts):
                            for j, part in enumerate(parts):
                                if f"__QUOTED_{i}__" in part:
                                    parts[j] = part.replace(f"__QUOTED_{i}__", quoted.strip('"'))
                        
                        if len(parts) >= 19:  # 모든 필드가 있는지 확인
                            reg_id = parts[0]
                            tm_fc = parts[1]
                            tm_ef = parts[2]
                            mod = parts[3]
                            ne = parts[4]
                            stn = parts[5]
                            c = parts[6]
                            man_id = parts[7]
                            man_fc = parts[8]
                            w1 = parts[9]
                            t = parts[10]
                            w2 = parts[11]
                            s1 = parts[12]
                            s2 = parts[13]
                            wh1 = parts[14]
                            wh2 = parts[15]
                            sky = parts[16]
                            prep = parts[17]
                            wf = ' '.join(parts[18:])  # 나머지는 모두 WF (예보)
                            
                            # 유효한 데이터인지 확인
                            if reg_id and tm_fc and tm_ef:
                                forecast_data = {
                                    'REG_ID': reg_id,
                                    'TM_ST': '',  # 고정폭 형식에서는 제공되지 않음
                                    'TM_ED': '',  # 고정폭 형식에서는 제공되지 않음
                                    'REG_SP': '',  # 고정폭 형식에서는 제공되지 않음
                                    'REG_NAME': '',  # 고정폭 형식에서는 제공되지 않음
                                    'STN_ID': stn,
                                    'TM_FC': tm_fc,
                                    'TM_IN': '',  # 고정폭 형식에서는 제공되지 않음
                                    'CNT': '',  # 고정폭 형식에서는 제공되지 않음
                                    'MAN_FC': man_fc,
                                    'TM_EF': tm_ef,
                                    'MOD': mod,
                                    'NE': ne,
                                    'STN': stn,
                                    'C': c,
                                    'MAN_ID': man_id,
                                    'W1': w1,
                                    'T': t,
                                    'W2': w2,
                                    'TA': '',  # 해상예보에서는 기온 정보가 없을 수 있음
                                    'ST': '',  # 해상예보에서는 강수확률이 없을 수 있음
                                    'SKY': convert_sky_condition(sky),  # 한글 변환
                                    'PREP': convert_precipitation_type(prep),  # 한글 변환
                                    'WF': wf,
                                    'S1': s1,
                                    'S2': s2,
                                    'WH1': wh1,
                                    'WH2': wh2
                                }
                                forecast = WeatherForecast(**forecast_data)
                                forecasts.append(forecast)
                    except Exception as parse_e:
                        logger.debug(f"Failed to parse forecast line: {line[:50]}... Error: {parse_e}")
                        continue
                
                # 데이터가 없는 경우 체크
                if not data_found or len(forecasts) == 0:
                    logger.warning("No forecast data found in API response")
                    logger.warning(f"API Response was: {content}")
                    
                    # help=1로 다시 호출해서 사용법 확인
                    try:
                        help_params = {"disp": 0, "authKey": WEATHER_AUTH_KEY, "help": 1}
                        help_response = await client.get(WEATHER_URL, params=help_params, timeout=10.0)
                        if help_response.status_code == 200:
                            logger.info(f"API Help response: {help_response.text}")
                    except Exception as help_e:
                        logger.debug(f"Failed to get help: {help_e}")
                    
                    raise HTTPException(status_code=404, detail="요청한 조건에 맞는 예보 데이터가 없습니다. API 파라미터나 날짜를 확인해주세요.")
                
                # 응답 구성
                region_name = reg or "Unknown"
                forecast_time = forecasts[0].forecast_time if forecasts else ""
                
                return WeatherResponse(
                    forecasts=forecasts,
                    total_count=len(forecasts),
                    region_name=region_name,
                    forecast_time=forecast_time
                )
            else:
                logger.error(f"Weather API error: {response.status_code}, content: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=f"기상청 API 오류: {response.text}")
                
    except httpx.RequestError as e:
        logger.error(f"Weather API request error: {e}")
        raise HTTPException(status_code=500, detail=f"기상청 API 연결 오류: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Weather API unexpected error: {e}")
        raise HTTPException(status_code=500, detail="날씨 API 서버 내부 오류")


@router.get("/weather/regions", response_model=WeatherRegionResponse)
async def get_weather_regions(
    search: Optional[str] = Query(None, description="예보구역명 검색어 (예: 포항, 바다, 해상)"),
    reg_sp: Optional[str] = Query(None, description="구역 특성 필터 (A:육상광역, H:해상광역, J:연안바다 등)")
):
    """
    기상청 단기예보구역 조회 및 검색
    예보구역코드와 이름을 조회하여 날씨 API 호출에 필요한 정보 제공
    """
    try:
        if not WEATHER_AUTH_KEY:
            raise HTTPException(status_code=400, detail="WEATHER_AUTH_KEY가 설정되지 않았습니다.")
        
        # 기상청 API 헤더 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Weather/1.0)",
            "Accept": "text/csv, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }
        
        async with httpx.AsyncClient(
            verify=False,
            timeout=30.0,
            headers=headers,
            follow_redirects=True
        ) as client:
            # WEATHER_AUTH_KEY를 사용하여 파라미터 구성 (disp=0으로 고정폭 형식 요청)
            params = {"disp": 0, "authKey": WEATHER_AUTH_KEY}
            url_to_call = WEATHER_CODE_URL
            
            logger.info(f"Calling KMA weather regions API: {url_to_call}")
            
            response = await client.get(url_to_call, params=params, timeout=30.0)
            
            logger.info(f"Weather Regions API Response status: {response.status_code}")
            logger.info(f"Weather Regions API Response content preview: {response.text[:200]}...")
            
            if response.status_code == 200:
                # 고정폭 형식 응답 파싱 (disp=0)
                content = response.text.strip()
                
                # 줄 단위로 분리
                lines = content.split('\n')
                if len(lines) < 2:
                    logger.warning("Invalid format from weather regions API")
                    raise HTTPException(status_code=500, detail="기상청 API에서 잘못된 형식을 반환했습니다.")
                
                # 데이터 행들을 파싱 (주석과 헤더 라인 제외)
                all_regions = []
                for line in lines:
                    line_stripped = line.strip()
                    # 주석이나 헤더 라인 제외
                    if not line_stripped or line_stripped.startswith('#') or 'REG_ID' in line_stripped:
                        continue
                    
                    # 고정폭 형식 파싱
                    # REG_ID(8자) TM_ST(12자) TM_ED(12자) REG_SP(6자) REG_NAME(나머지)
                    # 11000000 199001010000 210012310000 A      육상
                    try:
                        if len(line) >= 40:  # 최소 길이 확인
                            reg_id = line[0:8].strip()
                            tm_st = line[9:21].strip()
                            tm_ed = line[22:34].strip()
                            reg_sp = line[35:41].strip()
                            reg_name = line[42:].strip() if len(line) > 42 else ""
                            
                            # 유효한 데이터인지 확인
                            if reg_id and tm_st and tm_ed and reg_sp and reg_name:
                                region = WeatherRegion(
                                    REG_ID=reg_id,
                                    TM_ST=tm_st,
                                    TM_ED=tm_ed,
                                    REG_SP=reg_sp,
                                    REG_NAME=reg_name
                                )
                                all_regions.append(region)
                    except Exception as parse_e:
                        logger.debug(f"Failed to parse fixed-width line: {line[:50]}... Error: {parse_e}")
                        continue
                
                # 필터링 적용
                filtered_regions = all_regions
                
                # 구역 특성 필터 (reg_sp)
                if reg_sp:
                    filtered_regions = [r for r in filtered_regions if r.REG_SP == reg_sp.upper()]
                
                # 검색어 필터 (search)
                if search:
                    search_lower = search.lower()
                    filtered_regions = [
                        r for r in filtered_regions 
                        if search_lower in r.REG_NAME.lower()
                    ]
                
                # 동일한 지역명에 대해 최신 설정만 유지 (TM_ST 기준으로 정렬 후 최신것만)
                region_latest = {}
                for region in filtered_regions:
                    key = f"{region.REG_NAME}_{region.REG_SP}"
                    if key not in region_latest or region.TM_ST > region_latest[key].TM_ST:
                        region_latest[key] = region
                
                # 최신 설정만 포함된 리스트로 변경
                filtered_regions = list(region_latest.values())
                
                # TM_ST 기준으로 내림차순 정렬 (최신순)
                filtered_regions.sort(key=lambda x: x.TM_ST, reverse=True)
                
                return WeatherRegionResponse(
                    regions=filtered_regions,
                    total_count=len(filtered_regions),
                    search_term=search,
                    region_type=reg_sp
                )
            else:
                logger.error(f"Weather Regions API error: {response.status_code}, content: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=f"기상청 구역 API 오류: {response.text}")
                
    except httpx.RequestError as e:
        logger.error(f"Weather Regions API request error: {e}")
        raise HTTPException(status_code=500, detail=f"기상청 구역 API 연결 오류: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Weather Regions API unexpected error: {e}")
        raise HTTPException(status_code=500, detail="날씨 구역 API 서버 내부 오류")
