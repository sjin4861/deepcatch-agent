# Fishing Reservation Agent Backend

Implements MVP requirements for fishing reservation AI agent.

## Stack

- FastAPI
- SQLite (SQLAlchemy)
- Twilio (simulated if credentials absent)

## Run

### HTTPS 서버 시작

```bash
# 방법 1: 자동 SSL 설정 스크립트 사용 (추천)
python run_https.py

# 방법 2: main.py 직접 실행
python src/main.py

# 방법 3: uvicorn 명령어로 직접 실행
python generate_ssl.py  # 먼저 인증서 생성
uvicorn src.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt --reload
```

### HTTP 서버 시작

```bash
# HTTP만 사용하고 싶은 경우
USE_SSL=false python src/main.py

# 또는 기존 방식 (HTTP만)
uvicorn src.main:app --reload --port 8000
```

## Endpoints

### 기존 API
- POST /chat {"message": "..."}
- GET /status
- GET /businesses?location=부산
- POST /reservation
- POST /call
- GET /call/status
- (stubs) POST /twilio/voice, POST /twilio/status

### 선박 안전 및 기상 정보 API
- GET /api/v1/ship-safe/stats/history?date=20250102 - 주요 기상 요소 과거 정보 (기온, 풍속, 풍향)
- GET /api/v1/ship-safe/stats/history/raw?date=20250102 - 실제 API 응답 그대로 반환

### 어획량 관련 API
- GET /api/v1/catch/history?fish_type=고등어 - 특정 품목 과거 어획 데이터 조회 (INT-S3-007)
- GET /api/v1/harbor/ships/status?harbor_name=구룡포항 - 실시간 선박 입항 및 하역 구역 정보 (INT-S3-001)

### 날씨 예보 API
- GET /api/v1/weather/forecast?reg=11B20304&tmfc=0 - 기상청 단기예보 조회 (전체 파라미터 지원)
- GET /api/v1/weather/forecast?help=1 - API 사용법 확인
- GET /api/v1/weather/forecast?reg=12A10000&tmfc1=2025092718&tmfc2=2025092800 - 해상예보 예시
- GET /api/v1/weather/regions?search=포항&reg_sp=H - 예보구역 검색 및 조회

### 디버깅 API
- GET /api/v1/debug/env-info - 환경변수 및 설정 정보 확인
- GET /api/v1/debug/test-api-key - API 키 유효성 테스트
- GET /api/v1/debug/test-raw-api - 실제 API 호출 테스트

## Chat Flow

Send user free-form Korean text. Server extracts: 날짜(YYYY-MM-DD), 시간(HH:MM), 인원, 지역, 연락처 번호.
Missing fields returned in `missing` array with Korean prompts.
When all collected, status advances to `searching` and you can start a call.

## Environment Variables (optional)

```bash
# Twilio 설정
ACCOUNT_SID=...
AUTH_TOKEN=...
US_PHONENUMBER=+1...

# DPG API 설정
DPG_SERVICE_KEY=yqfuaX1YKzxki2YCEvIgG...  # 실제 서비스 키로 교체 필요
FISHERY_API_DEV_MODE=true                   # true: mock 데이터 사용, false: 실제 API 호출

# 기상청 API 설정
WEATHER_AUTH_KEY=...                        # 기상청 Open API 인증키
WEATHER_URL=https://apihub.kma.go.kr/api/typ01/url/fct_shrt_reg.php  # 기상청 단기예보 API URL
WEATHER_CODE_URL=...                        # 기상청 예보구역 조회 API URL (authKey 포함 가능)

# SSL 설정
USE_SSL=true                                # true: HTTPS, false: HTTP
```

If omitted, call operations are simulated and mock data is used.

## Data Loading

`app/data/businesses.csv` auto-imported at startup if businesses table empty.

## Tests

Basic tests in `app/tests/test_api.py` (requires `pytest` if you add it to deps).

## Next Steps

- Integrate real Twilio webhook logic
- Add business search ranking
- Persist multiple plans per user
- Add authentication
