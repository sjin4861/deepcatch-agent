# main.py - 낚시 예약 AI 에이전트

from fastapi import FastAPI, Request, Form, HTTPException, Response, Depends
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import os
import logging
from enum import Enum
from dotenv import load_dotenv
from sqlalchemy.orm import Session
# CORS Error 방지를 위한 미들웨어
from fastapi.middleware.cors import CORSMiddleware
# 지침에 따른 데이터베이스 연결
from .database import get_db, engine
from . import models, crud
from .agent import ChatRequest, ChatResponse, PlanAgent

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 데이터베이스 테이블 생성
models.Base.metadata.create_all(bind=engine)

# 환경 변수 로드
try:
    load_dotenv()
except ImportError:
    logger.warning(
        "python-dotenv가 설치되지 않았습니다. 환경 변수를 직접 설정해주세요."
    )

URL = os.getenv("URL", "http://localhost:8000")  # 기본값 설정
US_PHONENUMBER = os.getenv("US_PHONENUMBER")
KO_PHONENUMBER = os.getenv("KO_PHONENUMBER")

app = FastAPI(
    title="낚시 예약 AI 에이전트",
    description="Twilio를 사용한 자동 낚시집 예약 시스템",
    version="1.0.0",
)

# Next.js 프론트엔드 서버 주소 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Twilio 설정
TWILIO_ACCOUNT_SID = os.getenv("ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("AUTH_TOKEN")

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    raise ValueError("Twilio 환경 변수가 설정되지 않았습니다: ACCOUNT_SID, AUTH_TOKEN")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


class CallStatus(str, Enum):
    """통화 상태"""

    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    BUSY = "busy"
    FAILED = "failed"
    NO_ANSWER = "no-answer"


class ConversationStep(str, Enum):
    """대화 단계"""

    GREETING = "greeting"
    AVAILABILITY_CHECK = "availability_check"
    # long_distance_casting 시나리오용
    AWAITING_BAIT_QUESTION = "awaiting_bait_question"
    AWAITING_PRICE_INFO = "awaiting_price_info"
    # boat_fishing 시나리오용
    AWAITING_PEOPLE_COUNT = "awaiting_people_count"
    AWAITING_ALTERNATIVE_DATE = "awaiting_alternative_date"
    AWAITING_ALTERNATIVE_RESPONSE = "awaiting_alternative_response"
    AWAITING_FINAL_PRICE = "awaiting_final_price"
    # 공통
    PRICE_INQUIRY = "price_inquiry"
    ALTERNATIVE_DATE = "alternative_date"
    CONFIRMATION = "confirmation"
    COMPLETED = "completed"


class FishingRequest(BaseModel):
    """낚시 예약 요청 정보"""

    scenario_type: str = Field(
        default="long_distance_casting",
        description="시나리오 타입 (long_distance_casting, boat_fishing)",
    )
    date: str = Field(default="내일", description="희망 날짜 (내일, 이번 주말 등)")
    time: Optional[str] = Field(
        default="새벽 5시", description="희망 시간 (새벽 5시, 오전 6시 등)"
    )
    people_count: int = Field(default=4, ge=1, le=20, description="인원수")
    fishing_type: str = Field(default="갯바위 원투 낚시", description="낚시 종류")
    location: Optional[str] = Field(default="구룡포", description="희망 지역")
    budget: Optional[str] = Field(default="10만원 내외", description="예산 범위")
    details: Optional[Dict] = Field(
        default_factory=lambda: {
            "experience": {"초보자": 2, "경험자": 2},
            "bait": {"청갯지렁이": 2, "크릴 새우": 2},
        },
        description="세부 정보",
    )


# 지침에 따른 데이터 구조
class Plan(BaseModel):
    """사용자 계획 (지침 요구사항)"""

    date: str = Field(..., description="날짜")
    people: int = Field(..., description="인원")
    location: str = Field(..., description="지역")
    phone_user: str = Field(..., description="사용자 전화번호")


class Business(BaseModel):
    """낚시집 정보 (지침 요구사항)"""

    name: str = Field(..., description="업체명")
    phone: str = Field(..., description="전화번호")
    location: str = Field(..., description="위치")


class Reservation(BaseModel):
    """예약 결과 (지침 요구사항)"""

    success: bool = Field(..., description="예약 성공 여부")
    business_name: str = Field(..., description="업체명")
    details: str = Field(..., description="세부 내용")


class BusinessInfo(BaseModel):
    """낚시집 정보 (확장)"""

    name: str = Field(..., description="업체명")
    phone: str = Field(..., description="전화번호")
    location: str = Field(..., description="위치")
    services: List[str] = Field(default=[], description="제공 서비스")


class CallRequest(BaseModel):
    """전화 요청"""

    business_name: str = Field(default="구룡포 동인호", description="업체명")
    fishing_request: FishingRequest = Field(
        default_factory=lambda: FishingRequest(
            scenario_type="boat_fishing",
            date="이번 추석 당일",
            time="오후 시간대",
            people_count=5,
            fishing_type="선상낚시",
            location="구룡포",
            budget="25만원 내외",
            details={
                "family_type": {"성인": 2, "초등학생": 3},
                "course": "오후 코스",
                "includes": "회떠드리는 것 포함",
            },
        ),
        description="낚시 예약 정보",
    )

    class Config:
        schema_extra = {
            "examples": {
                "long_distance_casting": {
                    "summary": "갯바위 원투 낚시 (장비 대여)",
                    "value": {
                        "business_name": "구룡포낚시프라자",
                        "fishing_request": {
                            "scenario_type": "long_distance_casting",
                            "date": "내일",
                            "time": "새벽 5시",
                            "people_count": 4,
                            "fishing_type": "갯바위 원투 낚시",
                            "location": "구룡포",
                            "budget": "10만원 내외",
                            "details": {
                                "experience": {"초보자": 2, "경험자": 2},
                                "bait": {"청갯지렁이": 2, "크릴 새우": 2},
                                "equipment": "원투대 4세트",
                            },
                        },
                    },
                },
                "boat_fishing": {
                    "summary": "선상낚시 (가족 단위)",
                    "value": {
                        "business_name": "구룡포 동인호",
                        "fishing_request": {
                            "scenario_type": "boat_fishing",
                            "date": "이번 추석 당일",
                            "time": "오후 시간대",
                            "people_count": 5,
                            "fishing_type": "선상낚시",
                            "location": "구룡포",
                            "budget": "25만원 내외",
                            "details": {
                                "family_type": {"성인": 2, "초등학생": 3},
                                "course": "오후 코스",
                                "includes": "회떠드리는 것 포함",
                            },
                        },
                    },
                },
            }
        }


class CallResponse(BaseModel):
    """전화 응답"""

    status: str = Field(..., description="상태")
    call_sid: Optional[str] = Field(None, description="통화 ID")
    message: str = Field(..., description="메시지")


class SpeechResponse(BaseModel):
    """음성 인식 결과"""

    speech_result: str = Field(..., description="음성 인식 텍스트")
    confidence: Optional[float] = Field(None, description="인식 정확도")
    call_sid: str = Field(..., description="통화 ID")


class ConversationState(BaseModel):
    """대화 상태"""

    call_sid: str
    step: ConversationStep
    fishing_request: FishingRequest
    business_name: str
    responses: List[str] = []
    is_successful: bool = False
    extracted_info: Dict = Field(default_factory=dict)


# 전역 상태 관리
conversation_states: Dict[str, ConversationState] = {}


class FishingCallHandler:
    def __init__(self):
        pass

    def generate_greeting_message(
        self, fishing_request: FishingRequest, business_name: str
    ) -> str:
        """시나리오에 맞는 인사말 생성"""
        time_part = f" {fishing_request.time}" if fishing_request.time else ""

        if fishing_request.scenario_type == "boat_fishing":
            # 선상낚시 시나리오
            return (
                f"안녕하세요, {business_name} 선장님 맞으시죠? "
                f"{fishing_request.date}{time_part}에 가족 단위로 선상낚시 가능한지 확인해보고 싶습니다."
            )
        else:
            # 기본 (long_distance_casting) 시나리오
            return (
                f"안녕하세요, {business_name} 맞으시죠? "
                f"{fishing_request.date}{time_part}에 {fishing_request.fishing_type} 장비 대여 가능한지 확인해보고 싶습니다."
            )

    def generate_initial_prompt(self, state: ConversationState) -> str:
        req = state.fishing_request
        return (
            f"안녕하세요, {state.business_name} 맞으시죠? "
            f"{req.date}에 {req.fishing_type} 장비 대여 가능한지 확인해보고 싶습니다."
        )


fishing_handler = FishingCallHandler()
plan_agent = PlanAgent()


@app.post("/call/initiate", response_model=CallResponse)
async def initiate_fishing_call(call_request: CallRequest):
    """
    낚시집에 전화 걸기

    자동으로 환경 변수에 설정된 번호를 사용합니다:
    - from: US_PHONENUMBER (미국 번호)
    - to: KO_PHONENUMBER (한국 번호)

    업체명과 낚시 요청 정보만 입력하면 됩니다.
    """
    try:
        # 입력 검증
        if not KO_PHONENUMBER:
            raise HTTPException(
                status_code=400,
                detail="KO_PHONENUMBER 환경 변수가 설정되지 않았습니다.",
            )

        if not US_PHONENUMBER:
            raise HTTPException(
                status_code=400,
                detail="US_PHONENUMBER 환경 변수가 설정되지 않았습니다.",
            )

        # 현재 진행 중인 통화가 있는지 확인
        active_calls = [
            state
            for state in conversation_states.values()
            if state.step not in [ConversationStep.COMPLETED]
        ]

        if active_calls:
            logger.warning(f"이미 진행 중인 통화가 {len(active_calls)}개 있습니다.")
            # 필요시 기존 통화를 확인하거나 제한할 수 있음

        logger.info(
            f"전화 연결 시작: {call_request.business_name} (from: {US_PHONENUMBER} -> to: {KO_PHONENUMBER})"
        )

        # TwiML 핸들러 URL
        webhook_url = f"{URL}/voice/start"

        call = client.calls.create(
            to=KO_PHONENUMBER,  # 한국 번호 (받는 번호)
            from_=US_PHONENUMBER,  # 미국 번호 (보내는 번호)
            url=webhook_url,
            method="POST",
            status_callback=f"{URL}/voice/status",
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )

        # 대화 상태 저장
        conversation_states[call.sid] = ConversationState(
            call_sid=call.sid,
            step=ConversationStep.GREETING,
            fishing_request=call_request.fishing_request,
            business_name=call_request.business_name,
            responses=[],
            extracted_info={},
        )

        logger.info(f"전화 연결 성공: {call.sid}")

        return CallResponse(
            status="success", call_sid=call.sid, message="전화 연결이 시작되었습니다."
        )

    except Exception as e:
        logger.error(f"전화 연결 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"전화 연결 실패: {str(e)}")


@app.post("/voice/start")
async def handle_voice_start(request: Request):
    """통화 시작 시 TwiML 응답"""
    form = await request.form()
    call_sid = form.get("CallSid")

    if call_sid not in conversation_states:
        response = VoiceResponse()
        response.say(
            "시스템 오류가 발생했습니다.", voice="Polly.Seoyeon", language="ko-KR"
        )
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    state = conversation_states[call_sid]
    response = VoiceResponse()

    # 첫 번째 메시지 + 응답 대기
    gather = response.gather(
        input="speech",
        action=f"/voice/process?call_sid={call_sid}",
        method="POST",
        timeout=15,
        speech_timeout="auto",
        language="ko-KR",
        enhanced=True,
        profanity_filter=False,
    )

    greeting_msg = fishing_handler.generate_greeting_message(
        state.fishing_request, state.business_name
    )

    gather.say(greeting_msg, voice="Polly.Seoyeon", language="ko-KR")

    # 타임아웃 시 메시지
    response.say(
        "응답을 듣지 못했습니다. 나중에 다시 연락드리겠습니다.",
        voice="Polly.Seoyeon",
        language="ko-KR",
    )
    response.hangup()

    return Response(content=str(response), media_type="application/xml")


@app.post("/voice/process")
async def process_speech_result(
    request: Request,
    call_sid: str,
    SpeechResult: Optional[str] = Form(None),
    CallSid: Optional[str] = Form(None),
):
    """음성 인식 결과 처리"""
    actual_call_sid = CallSid or call_sid

    if actual_call_sid not in conversation_states:
        response = VoiceResponse()
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    state = conversation_states[actual_call_sid]
    response = VoiceResponse()

    if not SpeechResult:
        response.say(
            "죄송합니다. 연결 상태가 좋지 않은 것 같습니다. "
            "나중에 다시 연락드리겠습니다.",
            voice="Polly.Seoyeon",
            language="ko-KR",
        )
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # 응답 저장
    state.responses.append(f"{state.step.value}: {SpeechResult}")

    # 시나리오에 맞는 대화 로직
    speech_lower = SpeechResult.lower()
    logger.info(f"대화 단계: {state.step}, 응답: {SpeechResult}")

    # 자동응답기나 음성사서함 감지
    answering_machine_phrases = [
        "메시지",
        "녹음",
        "신호음",
        "삐",
        "번을 눌러",
        "전화번호를 남기",
        "사용 방법",
        "시간이 지났습니다",
        "나중에 다시",
        "휴무",
        "영업시간",
    ]

    if any(phrase in speech_lower for phrase in answering_machine_phrases):
        logger.info("자동응답기 감지됨 - 전화를 종료합니다")
        state.step = ConversationStep.COMPLETED
        state.is_successful = False
        state.extracted_info["failure_reason"] = "자동응답기 연결"

        response.say(
            "죄송합니다. 나중에 다시 연락드리겠습니다.",
            voice="Polly.Seoyeon",
            language="ko-KR",
        )
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    if state.step == ConversationStep.GREETING:
        # 시나리오 타입에 따른 분기 처리
        if state.fishing_request.scenario_type == "boat_fishing":
            # 선상낚시 시나리오
            if "가능" in speech_lower and (
                "몇" in speech_lower and ("명" in speech_lower or "분" in speech_lower)
            ):
                # "네 가능합니다. 몇 분이세요?"
                state.step = ConversationStep.AWAITING_ALTERNATIVE_DATE
                gather = response.gather(
                    input="speech",
                    action=f"/voice/process?call_sid={actual_call_sid}",
                    method="POST",
                    timeout=15,
                    speech_timeout="auto",
                    language="ko-KR",
                    enhanced=True,
                )
                gather.say(
                    "5명인데, 성인 2명, 초등학생 3명이십니다.",
                    voice="Polly.Seoyeon",
                    language="ko-KR",
                )
            elif "몇" in speech_lower and (
                "명" in speech_lower or "분" in speech_lower
            ):
                # 바로 "몇 분이세요?" 물어봄
                state.step = ConversationStep.AWAITING_ALTERNATIVE_DATE
                gather = response.gather(
                    input="speech",
                    action=f"/voice/process?call_sid={actual_call_sid}",
                    method="POST",
                    timeout=15,
                    speech_timeout="auto",
                    language="ko-KR",
                    enhanced=True,
                )
                gather.say(
                    "5명인데, 성인 2명, 초등학생 3명이십니다.",
                    voice="Polly.Seoyeon",
                    language="ko-KR",
                )
            else:
                # 예상치 못한 응답 - 재확인
                gather = response.gather(
                    input="speech",
                    action=f"/voice/process?call_sid={actual_call_sid}",
                    method="POST",
                    timeout=15,
                    speech_timeout="auto",
                    language="ko-KR",
                    enhanced=True,
                )
                gather.say(
                    "안녕하세요, 이번 추석 당일 오후 시간대에 가족 단위로 선상낚시 가능한지 확인해보고 싶습니다.",
                    voice="Polly.Seoyeon",
                    language="ko-KR",
                )
        else:
            # long_distance_casting 시나리오 (기존 로직)
            if "몇" in speech_lower and ("명" in speech_lower or "분" in speech_lower):
                state.step = ConversationStep.AWAITING_BAIT_QUESTION
                gather = response.gather(
                    input="speech",
                    action=f"/voice/process?call_sid={actual_call_sid}",
                    method="POST",
                    timeout=15,
                    speech_timeout="auto",
                    language="ko-KR",
                    enhanced=True,
                )
                gather.say(
                    "4명인데, 초보자 2명, 경험자 2명이십니다.",
                    voice="Polly.Seoyeon",
                    language="ko-KR",
                )
            else:
                # 예상치 못한 응답 - 재확인
                gather = response.gather(
                    input="speech",
                    action=f"/voice/process?call_sid={actual_call_sid}",
                    method="POST",
                    timeout=15,
                    speech_timeout="auto",
                    language="ko-KR",
                    enhanced=True,
                )
                gather.say(
                    "안녕하세요, 내일 새벽 5시에 갯바위 원투 낚시 장비 대여 가능한지 확인해보고 싶습니다.",
                    voice="Polly.Seoyeon",
                    language="ko-KR",
                )

    elif state.step == ConversationStep.AWAITING_BAIT_QUESTION:
        # 사장님이 장비 상황을 알려주고 미끼를 물어봄
        if "미끼" in speech_lower:
            state.step = ConversationStep.AWAITING_PRICE_INFO
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say(
                "네, 청갯지렁이 2개랑 크릴 새우 2개로 준비 부탁드립니다. 가격은 얼마인가요?",
                voice="Polly.Seoyeon",
                language="ko-KR",
            )
        else:
            # 미끼 질문이 아직 안 나왔을 경우 - 계속 대기
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say("네, 알겠습니다.", voice="Polly.Seoyeon", language="ko-KR")

    elif state.step == ConversationStep.AWAITING_ALTERNATIVE_DATE:
        # 선상낚시 시나리오: 추석 당일은 자리가 없어서 다른 날짜 제안
        if (
            "안 되" in speech_lower
            or "없어서" in speech_lower
            or "10월" in speech_lower
        ):
            state.step = ConversationStep.AWAITING_ALTERNATIVE_RESPONSE
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say(
                "10월 8일은 안되고 10월 9일에는 자리가 있나요?",
                voice="Polly.Seoyeon",
                language="ko-KR",
            )
        else:
            # 다시 물어보기
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say("네, 알겠습니다.", voice="Polly.Seoyeon", language="ko-KR")

    elif state.step == ConversationStep.AWAITING_ALTERNATIVE_RESPONSE:
        # 선상낚시 시나리오: 10월 9일 가능하다는 응답
        if (
            "있습니다" in speech_lower
            or "가능" in speech_lower
            or "오후" in speech_lower
        ):
            state.step = ConversationStep.AWAITING_FINAL_PRICE
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say(
                "네, 가격은 얼마인가요?", voice="Polly.Seoyeon", language="ko-KR"
            )
        else:
            # 다시 물어보기
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say(
                "10월 9일에는 자리가 있나요?", voice="Polly.Seoyeon", language="ko-KR"
            )

    elif state.step == ConversationStep.AWAITING_FINAL_PRICE:
        # 선상낚시 시나리오: 가격 정보 받고 완료
        if "만원" in speech_lower or "원" in speech_lower:
            state.step = ConversationStep.COMPLETED
            state.is_successful = True

            # 가격 정보 저장
            state.extracted_info["price_info"] = SpeechResult

            response.say(
                "네, 알겠습니다. 확인해보고 다시 연락드리겠습니다. 좋은 하루 되세요. 감사합니다.",
                voice="Polly.Seoyeon",
                language="ko-KR",
            )
            response.hangup()
        else:
            # 가격 정보를 다시 요청
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say(
                "죄송합니다. 가격을 다시 한번 말씀해주시겠어요?",
                voice="Polly.Seoyeon",
                language="ko-KR",
            )

    elif state.step == ConversationStep.AWAITING_PRICE_INFO:
        # 사장님이 가격 정보를 알려줌
        if "원" in speech_lower or "만원" in speech_lower or "보증금" in speech_lower:
            state.step = ConversationStep.COMPLETED
            state.is_successful = True

            # 가격 정보 저장
            state.extracted_info["price_info"] = SpeechResult

            response.say(
                "네, 알겠습니다. 확인해보고 다시 연락드리겠습니다. 좋은 하루 되세요. 감사합니다.",
                voice="Polly.Seoyeon",
                language="ko-KR",
            )
            response.hangup()
        else:
            # 가격 정보를 다시 요청
            gather = response.gather(
                input="speech",
                action=f"/voice/process?call_sid={actual_call_sid}",
                method="POST",
                timeout=15,
                speech_timeout="auto",
                language="ko-KR",
                enhanced=True,
            )
            gather.say(
                "죄송합니다. 가격을 다시 한번 말씀해주시겠어요?",
                voice="Polly.Seoyeon",
                language="ko-KR",
            )

    elif state.step == ConversationStep.PRICE_INQUIRY:
        state.step = ConversationStep.CONFIRMATION
        state.is_successful = True
        response.say(
            "네 알겠습니다. 확인해보고 다시 연락드리겠습니다. "
            "좋은 하루 되세요. 감사합니다.",
            voice="Polly.Seoyeon",
            language="ko-KR",
        )
        response.hangup()

    elif state.step == ConversationStep.ALTERNATIVE_DATE:
        state.step = ConversationStep.COMPLETED
        response.say(
            "네 알겠습니다. 확인해보고 다시 연락드리겠습니다. " "감사합니다.",
            voice="Polly.Seoyeon",
            language="ko-KR",
        )
        response.hangup()

    return Response(content=str(response), media_type="application/xml")


@app.post("/voice/status")
async def voice_status_callback(
    request: Request,
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
):
    """통화 상태 콜백"""
    logger.info(f"통화 상태 업데이트: {CallSid} - {CallStatus}")
    return {"status": "received", "call_sid": CallSid, "call_status": CallStatus}


@app.get("/call/{call_sid}/status")
async def get_call_status(call_sid: str):
    """통화 상태 조회"""
    if call_sid not in conversation_states:
        raise HTTPException(status_code=404, detail="통화를 찾을 수 없습니다.")

    state = conversation_states[call_sid]
    return {
        "call_sid": call_sid,
        "current_step": state.step,
        "business_name": state.business_name,
        "responses": state.responses,
        "is_successful": state.is_successful,
    }


@app.get("/call/{call_sid}/result")
async def get_call_result(call_sid: str):
    """통화 결과 조회"""
    if call_sid not in conversation_states:
        raise HTTPException(status_code=404, detail="통화를 찾을 수 없습니다.")

    state = conversation_states[call_sid]
    return {
        "call_sid": call_sid,
        "business_name": state.business_name,
        "fishing_request": state.fishing_request,
        "conversation_log": state.responses,
        "success": state.is_successful,
        "final_step": state.step,
        "extracted_info": state.extracted_info,
        "failure_reason": (
            state.extracted_info.get("failure_reason", None)
            if not state.is_successful
            else None
        ),
    }


# 지침에 따른 API 엔드포인트 추가


@app.post("/chat", response_model=ChatResponse)
async def chat_message(payload: ChatRequest, db: Session = Depends(get_db)):
    """사용자 메시지를 받아 여행 계획 정보를 업데이트하고 응답합니다."""

    message_text = payload.message.strip()
    if not message_text:
        return ChatResponse(
            message="어떤 여행을 계획 중이신가요? 날짜와 인원수를 알려주시면 도와드릴게요!",
        )

    logger.info("채팅 메시지 수신: %s", message_text)

    try:
        response = plan_agent(message=message_text, db=db)
        return response

    except Exception as exc:
        logger.exception("채팅 처리 중 오류 발생")
        raise HTTPException(
            status_code=500,
            detail=f"채팅 처리 중 오류가 발생했습니다: {exc}",
        )


@app.get("/status")
async def get_status(db: Session = Depends(get_db)):
    """현재 상태 확인 (지침 요구사항)"""
    try:
        plan = crud.get_plan(db)
        missing = crud.missing_fields(plan)

        if missing:
            status = "정보 수집 중..."
        elif conversation_states:
            status = "통화 중..."
        else:
            status = "대기 중"

        return {
            "status": status,
            "active_calls": len(conversation_states),
            "plan": {
                "date": plan.date,
                "people": plan.people,
                "location": plan.location,
                "missing_fields": missing,
            },
        }
    except Exception as e:
        logger.error(f"상태 조회 오류: {str(e)}")
        return {"status": "error", "message": str(e)}


@app.get("/businesses")
async def get_businesses(location: Optional[str] = None, db: Session = Depends(get_db)):
    """낚시집 목록 (지침 요구사항)"""
    try:
        businesses = crud.list_businesses(db, location)
        return {
            "businesses": [
                {"name": b.name, "phone": b.phone, "location": b.location}
                for b in businesses
            ]
        }
    except Exception as e:
        logger.error(f"업체 목록 조회 오류: {str(e)}")
        return {"businesses": [], "error": str(e)}


@app.post("/reservation")
async def save_reservation(reservation: Reservation, db: Session = Depends(get_db)):
    """예약 결과 저장 (지침 요구사항)"""
    try:
        # 예약 결과를 데이터베이스에 저장 (schemas가 필요하므로 일단 dict로 처리)
        logger.info(
            f"예약 결과 저장: {reservation.business_name} - {reservation.success}"
        )

        # 실제 저장은 schemas 모듈을 확인한 후 구현
        return {"message": "예약 결과가 저장되었습니다", "reservation": reservation}

    except Exception as e:
        logger.error(f"예약 저장 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"예약 저장 실패: {str(e)}")


@app.get("/")
async def root():
    """API 루트"""
    return {
        "message": "낚시 예약 AI 에이전트 API",
        "docs": "/docs",
        "version": "1.0.0",
        "endpoints": {
            "chat": "POST /chat - 사용자 메시지 받기",
            "status": "GET /status - 현재 상태 확인",
            "call": "POST /call/initiate - 전화 시작",
            "call_status": "GET /call/{call_sid}/status - 전화 상태",
            "businesses": "GET /businesses - 낚시집 목록",
            "reservation": "POST /reservation - 예약 결과 저장",
        },
    }


if __name__ == "__main__":
    try:
        import uvicorn

        # 지침에 따른 포트 8000 사용
        logger.info("낚시 예약 AI 에이전트 서버 시작...")
        logger.info("지침에 따른 구성:")
        logger.info("- FastAPI 백엔드 (Port 8000)")
        logger.info("- SQLite 데이터베이스")
        logger.info("- Twilio 음성 API 연동")
        uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
    except ImportError:
        print("uvicorn을 설치해주세요: pip install uvicorn")
        print("또는 다음 명령어를 실행하세요:")
        print("cd server && uvicorn src.main:app --reload --port 8000")
