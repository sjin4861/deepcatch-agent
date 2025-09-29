# Deepcatch Agent
- 🏆 2025 POSTECH Digital Twin Chatbot Hackathon — 1st Place (Grand Prize, 25.09.28.)

**Deepcatch Agent**는 포항 구룡포 낚시 관광객을 위해 설계된 AI 기반 전화 예약 어시스턴트입니다. LangGraph로 구성된 에이전트가 기상/어획 데이터를 수집해 맞춤 플랜을 제안하고, Twilio 음성 통화를 통해 낚시점 예약까지 돕습니다. Next.js 대시보드에서는 대화 히스토리, 실시간 전사, 분석 인사이트를 한눈에 확인할 수 있습니다.

---

## 📚 Table of Contents

- [Deepcatch Agent](#deepcatch-agent)
  - [📚 Table of Contents](#-table-of-contents)
  - [프로젝트 개요](#프로젝트-개요)
  - [레포지토리 구조](#레포지토리-구조)
  - [주요 기능](#주요-기능)
  - [시스템 아키텍처](#시스템-아키텍처)
  - [사전 준비 사항](#사전-준비-사항)
  - [빠른 시작](#빠른-시작)
    - [공통](#공통)
    - [백엔드 (FastAPI)](#백엔드-fastapi)
    - [프런트엔드 (Next.js)](#프런트엔드-nextjs)
    - [실시간 중계 서버](#실시간-중계-서버)
  - [환경 변수](#환경-변수)
    - [백엔드 (.env)](#백엔드-env)
    - [프런트엔드 (.env.local)](#프런트엔드-envlocal)
  - [주요 워크플로](#주요-워크플로)
  - [테스트 \& 품질 체크](#테스트--품질-체크)
  - [문제 해결](#문제-해결)
  - [라이선스](#라이선스)

---

## 프로젝트 개요
- **목표**: 사용자의 낚시 일정 요구사항을 이해하고, 기상/어획 정보를 바탕으로 맞춤 플랜을 제안하며, 필요 시 전화 예약을 대행합니다.
- **구성**:
  - **LangGraph 에이전트**: 대화, 플래너, 전화 노드로 구성된 멀티툴 파이프라인
  - **FastAPI 백엔드**: 수산물/기상 API 래핑, Twilio 웹훅, LangGraph 실행, SQLite 상태 관리
  - **Next.js 프런트엔드**: 실시간 전사, 도구 결과, 추천 플랜을 시각화하는 대시보드
  - **Socket.IO 브리지**: OpenAI Realtime 및 Twilio 미디어 이벤트를 통합

---

## 레포지토리 구조

```text
deepcatch-agent/
├── front-end/                # Next.js 15 + Tailwind 대시보드
│   ├── src/
│   │   ├── app/              # App Router 페이지 및 API 라우트
│   │   ├── components/       # 대시보드, UI, 차트 컴포넌트
│   │   ├── ai/flows/         # Genkit 기반 요약 플로우
│   │   └── lib/              # 설정, 실시간 소켓 클라이언트 등
│   ├── package.json
│   └── README.md
├── server/                   # FastAPI + LangGraph + Twilio 백엔드
│   ├── src/                  # API, 에이전트, 서비스 레이어
│   ├── app/                  # (레거시) Flask 실험용 코드
│   ├── data/                 # 샘플 DB/CSV
│   ├── pyproject.toml
│   └── README.md
├── data/                     # SQLite DB (실험용)
└── README.md                 # ← 지금 보고 있는 파일
```

---

## 주요 기능

- **대화형 일정 수집**: LangGraph 플래너가 날짜, 인원, 예산 등 핵심 슬롯을 질의·보관
- **기상/물때 인사이트**: 구룡포 추석 연휴(10/5~10/8) 맞춤 예보, 풍속/파고 차트, 추천 일정 제공
- **어획 데이터 분석**: 최근 어획량 추세, 주요 어종 차트, 입항 선박 정보
- **실시간 통화 스트리밍**: Socket.IO를 통한 Twilio/OpenAI 음성 이벤트 전파, 대시보드 전사 렌더링
- **전화 예약 자동화**: Twilio API로 실제 전화 발신 및 결과 요약
- **맵 경로 시각화**: Kakao 지도 기반 추천 낚시점 경로/위치 표시

---

## 시스템 아키텍처

```text
사용자 ↔ Next.js 대시보드 ↔ FastAPI (LangGraph) ↔ 외부 API (기상청, DPG)
                                      ↘ Twilio ↔ 음성 통화
Socket.IO 브리지 ↔ OpenAI Realtime ↔ 실시간 전사/응답 스트리밍
```

- **대화 흐름**: 프런트 → `/chat` → LangGraph → Weather/Fish Tool 호출 → 응답/도구 메타데이터 → 대시보드 카드 반영
- **통화 흐름**: 프런트 → Socket.IO `start_call` → OpenAI/Twilio 연결 → 실시간 이벤트 → `RealtimeTranscription` 컴포넌트 업데이트

---

## 사전 준비 사항

| 항목 | 버전 | 비고 |
| ---- | ---- | ---- |
| Node.js | ≥ 18 | Next.js 15 대응 (npm 또는 pnpm 사용 가능) |
| Python | 3.10–3.11 | [`uv`](https://github.com/astral-sh/uv) 권장 |
| uv | 최신 | 백엔드 종속성/명령 실행 |
| SQLite | 기본 내장 | 테스트 데이터 `data/fishing.db` 포함 |
| ngrok (선택) | 최신 | Twilio 웹훅 로컬 연동용 |
| Twilio 계정 (선택) | - | 실제 전화 발신 시 필요 |

---

## 빠른 시작

### 공통

```bash
git clone https://github.com/사용자명/deepcatch-agent.git
cd deepcatch-agent
```

### 백엔드 (FastAPI)

```bash
cd server
uv sync                    # 의존성 설치 (pyproject.toml 기반)
cp .env.example .env       # 필요 시 환경 변수 수정
uv run uvicorn src.main:app --reload --port 8000
```

- 기본적으로 `http://localhost:8000`에서 API 제공
- `USE_SSL=true` 설정 후 `python run_https.py`로 HTTPS 실행 가능
- LangGraph/Socket.IO 서버도 FastAPI 앱에 포함되어 있습니다.

### 프런트엔드 (Next.js)

```bash
cd front-end
npm install               # pnpm / yarn 사용 가능
npm run dev               # http://localhost:9002 (package.json의 dev 스크립트)
```

필요 시 다음 환경 변수(.env.local) 설정:

```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SOCKET_URL=http://localhost:8000
NEXT_PUBLIC_KAKAO_MAP_KEY=카카오_지도_Javascript_키
```

### 실시간 중계 서버

- FastAPI 앱이 Socket.IO ASGI 서버(`/socket.io`)를 함께 제공하므로 추가 실행 없이 작동
- OpenAI Realtime을 사용할 경우 `.env`에 `OPENAI_API_KEY`를 추가하고 브라우저에서 통화를 시작하세요.

---

## 환경 변수

### 백엔드 (.env)

```ini
# Twilio (선택)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_NUMBER=

# DPG 선박/어획 API
DPG_SERVICE_KEY=...
FISHERY_API_DEV_MODE=true      # true면 mock 데이터 사용

# 기상청 API
WEATHER_AUTH_KEY=...
WEATHER_URL=https://apihub.kma.go.kr/api/typ01/url/fct_shrt_reg.php
WEATHER_CODE_URL=...

# OpenAI Realtime
OPENAI_API_KEY=sk-...

# 기타
USE_SSL=false
```

### 프런트엔드 (.env.local)

```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SOCKET_URL=http://localhost:8000
NEXT_PUBLIC_KAKAO_MAP_KEY=...
```

---

## 주요 워크플로

1. **대화 플로우**
   - 사용자가 프런트 대화창에서 문의 → FastAPI `/chat`
   - LangGraph `FishingPlannerGraph`가 도구 호출/응답 결정
   - Weather/Fish Tool 결과는 `toolResults`로 프런트에 스트리밍되어 인포 카드 및 차트에 반영

2. **기상 데이터 파이프라인**
   - `/api/v1/ship-safe/holiday/forecast`에서 추석 연휴 4일치 풍속/파고/물때 제공
   - WeatherTool이 Holiday Forecast를 병합해 최적 일정, 차트 메타데이터 생성
   - `HolidayWeatherWidget`에서 차트 및 하이라이트 렌더링

3. **실시간 통화**
   - `RealtimeTranscription` 컴포넌트가 Socket.IO 이벤트(`call_status`, `transcription_update`, `ai_response_*`) 수신
   - 통화 상태/경과 시간을 즉시 업데이트, 스트리밍 텍스트를 타자 효과로 표현
   - Twilio webhook(`/voice/status`) → 서버 → Socket.IO `call_status_update`

---

## 테스트 & 품질 체크

| 영역 | 명령 | 비고 |
| ---- | ---- | ---- |
| 백엔드 Lint/Test | `uv run pytest` | `app/tests/test_api.py` 등 |
| 백엔드 타입 검사 | `uv run python -m compileall src` | 빠른 문법 체크 |
| 프런트엔드 Lint | `npm run lint` | ESLint + Next.js 설정 |
| 프런트엔드 타입 체크 | `npm run typecheck` | TypeScript `--noEmit` |

---

## 문제 해결

- **통화 상태가 갱신되지 않을 때**: 프런트 `.env.local`의 `NEXT_PUBLIC_SOCKET_URL`이 FastAPI 호스트와 일치하는지 확인하세요.
- **기상/어획 API 에러**: `FISHERY_API_DEV_MODE=true` 상태에서 mock 데이터가 제공됩니다. 실제 API 인증키가 유효한지 점검하세요.
- **Kakao 지도 미표시**: 브라우저 콘솔의 `appkey` 에러를 확인하고 `NEXT_PUBLIC_KAKAO_MAP_KEY`를 재확인하세요.
- **OpenAI Realtime 연결 실패**: `OPENAI_API_KEY`와 네트워크 권한(방화벽 등)을 확인합니다.

---

## 라이선스

본 프로젝트는 [LICENSE](server/LICENSE)에 명시된 조건을 따릅니다. 내부 데이터(`data/` 하위 SQLite/CSV)는 데모 목적의 예시이며, 실제 서비스 배포 시 교체가 필요합니다.

---
