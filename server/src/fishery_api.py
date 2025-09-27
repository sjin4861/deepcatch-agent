"""
수산물 유통 정보화 예측 서비스 API
선박 안전 기상 정보 API 구현
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import math
import os
import random

import httpx
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

# 서비스 키 (환경변수에서 로드)
SERVICE_KEY = os.getenv("DPG_SERVICE_KEY", "")


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


# API 엔드포인트들


@router.get("/ship-safe/stats/history", response_model=ShipSafeStatsResponse)
async def get_ship_safe_stats_history(
    date: str = Query(..., description="요청날짜 (YYYYMMDD 형식)", example="20250102")
):
    """
    주요 기상 요소 과거 정보 조회
    경상북도 포항시 구룡포읍_트윈으로 지키는 선박 안전 서비스
    """
    try:
        # 서비스 키 검증
        if not SERVICE_KEY or SERVICE_KEY == "":
            logger.warning("DPG_SERVICE_KEY not set or empty, using mock data")
            return _get_mock_weather_data(date)

        logger.info(
            f"Using SERVICE_KEY: {SERVICE_KEY[:10]}{'*' * (len(SERVICE_KEY) - 10) if len(SERVICE_KEY) > 10 else ''}"
        )

        # HTTPS 요청을 위한 추가 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
            "Accept": "application/json, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        # 실제 환경에서는 외부 API 호출
        async with httpx.AsyncClient(
            verify=False,  # SSL 인증서 검증 비활성화
            timeout=30.0,
            headers=headers,
            follow_redirects=True,  # 리다이렉트 자동 추적
        ) as client:
            params = {"serviceKey": SERVICE_KEY, "date": date}

            # URL 인코딩 문제 해결을 위해 수동으로 URL 구성
            url = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}"

            # 로그에 실제 호출 URL 전체 출력
            logger.info(f"Calling external API: {url}")
            logger.info(f"Service Key (first 15 chars): {SERVICE_KEY[:15]}...")
            logger.info(f"Date parameter: {date}")

            response = await client.get(url, params=params, timeout=30.0)

            logger.info(f"API Response status: {response.status_code}")
            logger.info(f"API Response content: {response.text[:500]}...")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Successfully parsed JSON data: {data}")

                # 실제 API 응답 형식에 맞게 데이터 변환
                if "data" in data and "top" in data["data"]:
                    # 실제 응답에 맞는 데이터가 있는지 확인
                    top_data = data["data"]["top"]
                    if top_data:  # top 데이터가 비어있지 않은 경우
                        return ShipSafeStatsResponse(**data)
                    else:
                        logger.warning("API returned empty top data, using mock data")
                        return _get_mock_weather_data(date)
                else:
                    # 예상과 다른 응답 형식인 경우 로그 남기고 mock 데이터 반환
                    logger.warning(f"Unexpected API response format: {data}")
                    return _get_mock_weather_data(date)
            else:
                logger.error(
                    f"External API error: {response.status_code}, content: {response.text}"
                )
                # 실제 API 실패 시 모의 데이터로 fallback
                logger.info("Falling back to mock data due to API error")
                return _get_mock_weather_data(date)

    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        # 개발/테스트용 모의 데이터 반환
        return _get_mock_weather_data(date)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류")


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
            "DPG_SERVICE_KEY_PREVIEW": (
                f"{SERVICE_KEY[:10]}{'*' * max(0, len(SERVICE_KEY) - 10)}"
                if SERVICE_KEY
                else "not_set"
            ),
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
    if not SERVICE_KEY or SERVICE_KEY == "":
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
        "length": len(SERVICE_KEY),
        "contains_special_chars": any(c in SERVICE_KEY for c in "!@#$%^&*()"),
        "is_alphanumeric": SERVICE_KEY.replace("%", "").isalnum(),
        "starts_with": SERVICE_KEY[:3] if len(SERVICE_KEY) >= 3 else SERVICE_KEY,
        "preview": f"{SERVICE_KEY[:10]}{'*' * max(0, len(SERVICE_KEY) - 10)}",
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

    if not SERVICE_KEY:
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
            params1 = {"serviceKey": SERVICE_KEY, "date": test_date}
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
            url2 = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}?serviceKey={SERVICE_KEY}&date={test_date}"

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
            headers3 = {"Authorization": f"Bearer {SERVICE_KEY}"}
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
                    "length": len(SERVICE_KEY),
                    "preview": (
                        f"{SERVICE_KEY[:10]}***{SERVICE_KEY[-5:]}"
                        if len(SERVICE_KEY) > 15
                        else "***"
                    ),
                    "contains_special": any(
                        c in "!@#$%^&*()+={}[]|\\:;\"'<>,.?/" for c in SERVICE_KEY
                    ),
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
        if not SERVICE_KEY:
            raise HTTPException(
                status_code=400, detail="DPG_SERVICE_KEY not configured"
            )

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
            url = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}?serviceKey={SERVICE_KEY}&date={date}"

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
        if not SERVICE_KEY:
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
            params = {"serviceKey": SERVICE_KEY}
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
        if not SERVICE_KEY:
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
            params = {"serviceKey": SERVICE_KEY}
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
            "updated_at": "2025-01-02T08:00:00",
        },
    )
