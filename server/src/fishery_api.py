"""
수산물 유통 정보화 예측 서비스 API
선박 안전 기상 정보 API 구현
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Optional, List
import httpx
import os
from urllib.parse import unquote
from src.config import logger

# 라우터 생성
router = APIRouter(prefix="/api/v1", tags=["ship-safe"])

# 외부 API 기본 URL
BASE_API_URL = "https://dpg-apis.pohang-eum.co.kr"

# 개발 모드 설정 (환경변수로 제어)
DEVELOPMENT_MODE = os.getenv("FISHERY_API_DEV_MODE", "true").lower() in ("true", "1", "yes")

# API 엔드포인트 매핑
API_ENDPOINTS = {
    "ship_safe_stats_history": "/ship-safe/stats/history",  # 주요 기상 요소 과거 정보
    "catch_history": "/catch/history",                      # 어획 데이터 조회 (INT-S3-007)
    "harbor_ships_status": "/harbor/ships/status",          # 선박 입항 정보 (INT-S3-001)
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
        # 서비스 키 확보 (디코드/원본 순차 시도)
        if not RAW_SERVICE_KEY:
            logger.warning("DPG_SERVICE_KEY not set or empty, using mock data")
            return _get_mock_weather_data(date)
        logger.info(
            "Using SERVICE_KEY decoded=%s raw_preview=%s",
            DECODED_SERVICE_KEY != RAW_SERVICE_KEY,
            f"{RAW_SERVICE_KEY[:10]}{'*' * max(0,len(RAW_SERVICE_KEY)-10)}" if RAW_SERVICE_KEY else "<empty>"
        )
        
        # HTTPS 요청을 위한 추가 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
            "Accept": "application/json, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }
        
        # 실제 환경에서는 외부 API 호출
        async with httpx.AsyncClient(
            verify=False,  # SSL 인증서 검증 비활성화
            timeout=30.0,
            headers=headers,
            follow_redirects=True  # 리다이렉트 자동 추적
        ) as client:
            last_error_text = None
            key_variants = service_key_variants()
            for idx, key_variant in enumerate(key_variants):
                params = {"serviceKey": key_variant, "date": date}
                url = f"{BASE_API_URL}{API_ENDPOINTS['ship_safe_stats_history']}"
                logger.info(
                    "Calling external API attempt=%s key_variant=%s url=%s date=%s",
                    idx + 1,
                    "decoded" if key_variant == DECODED_SERVICE_KEY and RAW_SERVICE_KEY != DECODED_SERVICE_KEY else "raw",
                    url,
                    date,
                )
                response = await client.get(url, params=params, timeout=30.0)
                logger.info(f"API Response status: {response.status_code}")
                preview = response.text[:300]
                logger.info(f"API Response content: {preview}...")
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        logger.warning("JSON parse failed, fallback to mock")
                        break
                    # 성공 형식 추정: {"id":"1","status":"success","data":{"top":{...}}}
                    top_data = (data.get("data") or {}).get("top") if isinstance(data, dict) else None
                    if top_data and isinstance(top_data, dict) and len(top_data) > 0:
                        # 디버그 dump
                        _maybe_dump_fishery_payload(data, label="ship_safe_success")
                        return ShipSafeStatsResponse(**data)
                    else:
                        logger.warning(
                            "API returned empty top data (attempt=%s variant=%s). will %s",
                            idx + 1,
                            "decoded" if key_variant == DECODED_SERVICE_KEY and RAW_SERVICE_KEY != DECODED_SERVICE_KEY else "raw",
                            "try alternate variant" if idx + 1 < len(key_variants) else "fallback to mock",
                        )
                        # 빈 top & 다음 variant 남아 있으면 계속, 아니면 mock
                        if idx + 1 < len(key_variants):
                            continue
                        _maybe_dump_fishery_payload(data, label="ship_safe_empty_top")
                        return _get_mock_weather_data(date)
                    logger.warning(f"Unexpected API response format: {data}")
                    _maybe_dump_fishery_payload(data, label="ship_safe_unexpected")
                    return _get_mock_weather_data(date)
                else:
                    last_error_text = response.text
                    # 401 & invalid key 메시지이면 다음 variant 시도
                    if response.status_code == 401 and "유효하지 않은" in response.text and idx == 0 and len(service_key_variants()) > 1:
                        logger.warning("First key variant rejected (401 invalid). Trying alternate encoding variant...")
                        continue
                    logger.error(
                        "External API error final status=%s content=%s", response.status_code, preview
                    )
                    break
            # 실패 → mock 사용
            logger.info("Falling back to mock data due to API error (%s)", last_error_text)
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
        temp=1.6,
        winsp=4.4,
        windir=1022.6,
        logDateTime=prev_formatted
    )
    
    now_day = WeatherData(
        temp=5.9,
        winsp=1.3,
        windir=1022.2,
        logDateTime=formatted_date
    )
    
    return ShipSafeStatsResponse(
        id=1,
        status="success",
        data=WeatherHistoryData(
            beforeDay=before_day,
            nowDay=now_day
        )
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
            "API_ENDPOINTS": API_ENDPOINTS
        },
        "suggestions": [
            "서버 재시작: 환경변수 변경 후 서버 재시작 필요",
            "환경변수 확인: echo $DPG_SERVICE_KEY",
            "환경변수 설정: export DPG_SERVICE_KEY=실제키값",
            "또는 .env 파일에 DPG_SERVICE_KEY=실제키값 추가"
        ]
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
                "서버 재시작"
            ]
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
        "next_step": "실제 API 호출로 유효성 확인하려면 /ship-safe/stats/history 엔드포인트를 호출하세요."
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
            "Referer": BASE_API_URL
        }
        
        async with httpx.AsyncClient(
            verify=False,
            timeout=10.0,
            headers=test_headers,
            follow_redirects=True
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
                    "headers": dict(response1.headers)
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
                    "headers": dict(response2.headers)
                }
            except Exception as e:
                test_results["method2_url_direct"] = {"error": str(e)}
            
            # 방법 3: Header로 전달
            headers3 = {"Authorization": f"Bearer {DECODED_SERVICE_KEY}"}
            params3 = {"date": test_date}
            
            try:
                response3 = await client.get(url1, params=params3, headers=headers3, timeout=10.0)
                test_results["method3_header"] = {
                    "url": str(response3.url),
                    "status": response3.status_code,
                    "content": response3.text[:300],
                    "headers": dict(response3.headers)
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
                    "IP 화이트리스트 설정 확인"
                ]
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
            "Connection": "keep-alive"
        }
        
        async with httpx.AsyncClient(
            verify=False,
            timeout=30.0,
            headers=headers,
            follow_redirects=True
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
                    detail=f"API Error: {response.text}"
                )
                
    except Exception as e:
        logger.error(f"Raw API call failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/catch/history", response_model=CatchHistoryResponse)
async def get_catch_history(
    fish_type: Optional[str] = Query(None, description="어종명 (예: 고등어, 삼치, 오징어)"),
    start_date: Optional[str] = Query(None, description="조회 시작 날짜 (YYYYMMDD)"),
    end_date: Optional[str] = Query(None, description="조회 종료 날짜 (YYYYMMDD)"),
    ship_id: Optional[str] = Query(None, description="특정 선박 ID")
):
    """
    특정 품목과 관련된 과거 어획 데이터를 선박 단위로 조회 (INT-S3-007)
    """
    try:
        if not RAW_SERVICE_KEY:
            logger.warning("DPG_SERVICE_KEY not set, using mock data")
            return _get_mock_catch_history_data(fish_type, start_date, end_date, ship_id)
        
        # HTTPS 요청을 위한 헤더 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepCatch-Agent/1.0)",
            "Accept": "application/json, */*",
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
                logger.error(f"External API error: {response.status_code}, content: {response.text}")
                logger.info("Falling back to mock data due to API error")
                return _get_mock_catch_history_data(fish_type, start_date, end_date, ship_id)
                
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
            "Connection": "keep-alive"
        }
        
        async with httpx.AsyncClient(
            verify=False,
            timeout=30.0,
            headers=headers,
            follow_redirects=True
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
                logger.error(f"External API error: {response.status_code}, content: {response.text}")
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
    ship_id: Optional[str] = None
) -> CatchHistoryResponse:
    """어획 이력 모의 데이터"""
    
    # 모든 선박 데이터
    all_records = [
        {
            "ship_id": "S001",
            "ship_name": "해운호",
            "fish_type": fish_type or "고등어",
            "catch_amount": 450.2,
            "catch_date": start_date or "20250102",
            "catch_location": "동해 연안",
            "captain_name": "김선장"
        },
        {
            "ship_id": "S002",
            "ship_name": "바다별호", 
            "fish_type": fish_type or "고등어",
            "catch_amount": 380.7,
            "catch_date": end_date or "20250102",
            "catch_location": "울릉도 근해",
            "captain_name": "이선장"
        }
    ]
    
    # ship_id 필터링
    if ship_id:
        filtered_records = [record for record in all_records if record["ship_id"] == ship_id]
    else:
        filtered_records = all_records
    
    total_catch = sum(record["catch_amount"] for record in filtered_records)
    
    return CatchHistoryResponse(
        id="1",
        status="success",
        data={
            "fish_type": fish_type or "고등어",
            "total_catch": total_catch,
            "ship_count": len(filtered_records),
            "catch_records": filtered_records
        }
    )

def _get_mock_harbor_ships_data(harbor_name: Optional[str] = None) -> HarborShipsResponse:
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
                    "status": "하역중"
                },
                {
                    "ship_id": "S002",
                    "ship_name": "바다별호",
                    "harbor_name": "구룡포항",
                    "dock_area": "B구역",
                    "arrival_time": "2025-01-02T06:15:00",
                    "total_catch": 890.3,
                    "status": "입항완료"
                }
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
            logger.info(f"Full URL with params: {response.url if 'response' in locals() else 'Not available yet'}")
            
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