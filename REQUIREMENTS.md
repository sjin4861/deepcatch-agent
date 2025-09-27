# 낚시 예약 AI 에이전트 MVP Requirements

## 프로젝트 개요

사용자의 낚시 계획을 받아서 자동으로 낚시집에 전화를 걸어 예약하는 AI 에이전트

## 기술 스택

- **Frontend**: Next.js
- **Backend**: FastAPI
- **음성**: Twilio API
- **DB**: SQLite

## 1. 핵심 기능

### 1.1 사용자 정보 수집

- 날짜, 시간, 인원, 지역 입력받기
- 누락된 정보 있으면 다시 물어보기

### 1.2 자동 전화 걸기

- 조건에 맞는 낚시집 찾기
- Twilio로 전화 걸기
- 안되면 다음 업체 시도

### 1.3 실시간 상태 표시

- 현재 통화 대화 내용 대본 표시
- 수집한 정보 보여주기

### 1.4 결과 처리

- 통화를 통해 얻은 정보 저장

## 2. 간단한 구조

```
프론트엔드 (Next.js - Port 3000)
    ↕ HTTP API 
백엔드 (FastAPI - Port 8000)
    ↕
SQLite DB + Twilio
```

## 3. API 설계

```python
# 사용자 입력
POST /chat - 사용자 메시지 받기
GET /status - 현재 상태 확인

# 전화 기능  
POST /call - 전화 시작
GET /call/status - 전화 상태

# 데이터
GET /businesses - 낚시집 목록
POST /reservation - 예약 결과 저장
```

## 4. 데이터 구조

```python
# 사용자 계획
class Plan:
    date: str
    time: str
    people: int
    location: str
    departure: str

# 낚시집 정보
class Business:
    name: str
    phone: str
    location: str

# 예약 결과
class Reservation:
    success: bool
    business_name: str
    details: str
```

## 5. 화면 구성

### 메인 페이지

- 채팅창 (사용자 입력)
- 진행 상황 표시
- 수집된 정보 박스
- 결과 표시 영역

### 상태 표시

- "정보 수집 중..."
- "업체 검색 중..."  
- "○○낚시터 통화 중..."
- "예약 완료!" / "다음 업체 시도 중..."

## 6. 개발 순서

### Phase 1: 기본 구조

- Next.js + FastAPI 연결
- 간단한 채팅 인터페이스
- SQLite DB 연결

### Phase 2: 핵심 로직

- 사용자 정보 수집 로직
- 낚시집 데이터베이스 구축
- 조건별 업체 검색

### Phase 3: 전화 기능

- Twilio 연동
- 자동 전화 걸기
- 음성 처리

### Phase 4: 완성

- 실시간 상태 업데이트
- 결과 저장/표시
- 기본 에러 처리

## 7. 필수 파일 구조

```
fishing-agent/
├── frontend/          # Next.js
│   ├── pages/
│   └── components/
├── backend/           # FastAPI
│   ├── main.py       # API 서버
│   ├── models.py     # 데이터 모델
│   ├── database.py   # DB 연결
│   └── twilio_client.py
└── data/
    ├── fishing.db    # SQLite
    └── businesses.csv # 낚시집 목록
```

## 8. 간단 배포

### 개발 환경

```bash
# 백엔드 실행
cd backend && uvicorn main:app --reload --port 8000

# 프론트엔드 실행  
cd frontend && npm run dev
```

### 운영 환경

- PM2로 두 서비스 실행
- 도메인 하나에 포트만 다르게
- 또는 Nginx로 `/api` 경로 분기

## 9. 테스트 계획

- 정보 수집 플로우 테스트
- 실제 낚시집 1-2곳과 통화 테스트
- 전체 예약 과정 End-to-End 테스트
