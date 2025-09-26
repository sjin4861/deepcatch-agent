# twilio_voice_handler.py

from fastapi import FastAPI, Request, Form, HTTPException
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import os
from enum import Enum

app = FastAPI(
    title="낚시 예약 AI 에이전트",
    description="Twilio를 사용한 자동 낚시집 예약 시스템",
    version="1.0.0"
)

# Twilio 설정
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

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
    PRICE_INQUIRY = "price_inquiry"
    ALTERNATIVE_DATE = "alternative_date"
    CONFIRMATION = "confirmation"
    COMPLETED = "completed"

class FishingRequest(BaseModel):
    """낚시 예약 요청 정보"""
    date: str = Field(..., description="희망 날짜 (YYYY-MM-DD)")
    time: str = Field(..., description="희망 시간 (HH:MM)")
    people_count: int = Field(..., ge=1, le=20, description="인원수")
    fishing_type: str = Field(default="바다낚시", description="낚시 종류")
    location: Optional[str] = Field(None, description="희망 지역")
    budget: Optional[str] = Field(None, description="예산 범위")

class BusinessInfo(BaseModel):
    """낚시집 정보"""
    name: str = Field(..., description="업체명")
    phone: str = Field(..., description="전화번호")
    location: str = Field(..., description="위치")
    services: List[str] = Field(default=[], description="제공 서비스")

class CallRequest(BaseModel):
    """전화 요청"""
    phone_number: str = Field(..., description="전화번호")
    business_name: str = Field(..., description="업체명")
    fishing_request: FishingRequest = Field(..., description="낚시 예약 정보")

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

# 전역 상태 관리
conversation_states: Dict[str, ConversationState] = {}

class FishingCallHandler:
    def __init__(self):
        pass
    
    def generate_greeting_message(self, request: FishingRequest, business_name: str) -> str:
        """인사말 생성"""
        return (
            f"안녕하세요. {business_name}이 맞나요? "
            f"낚시 예약 문의드리려고 연락드렸습니다. "
            f"{request.date} {request.time}부터 {request.people_count}명이서 "
            f"{request.fishing_type} 하려고 하는데 자리 있으신지 확인해주실 수 있나요?"
        )

fishing_handler = FishingCallHandler()

@app.post("/call/initiate", response_model=CallResponse)
async def initiate_fishing_call(call_request: CallRequest):
    """낚시집에 전화 걸기"""
    try:
        # TwiML 핸들러 URL (실제 배포 시 도메인 변경 필요)
        webhook_url = "https://your-domain.com/voice/start"
        
        call = client.calls.create(
            to=call_request.phone_number,
            from_=TWILIO_PHONE_NUMBER,
            url=webhook_url,
            method='POST',
            status_callback=f"https://your-domain.com/voice/status",
            status_callback_method='POST',
            status_callback_event=['initiated', 'ringing', 'answered', 'completed']
        )
        
        # 대화 상태 저장
        conversation_states[call.sid] = ConversationState(
            call_sid=call.sid,
            step=ConversationStep.GREETING,
            fishing_request=call_request.fishing_request,
            business_name=call_request.business_name,
            responses=[]
        )
        
        return CallResponse(
            status="success",
            call_sid=call.sid,
            message="전화 연결이 시작되었습니다."
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전화 연결 실패: {str(e)}")

@app.post("/voice/start")
async def handle_voice_start(request: Request):
    """통화 시작 시 TwiML 응답"""
    form = await request.form()
    call_sid = form.get('CallSid')
    
    if call_sid not in conversation_states:
        response = VoiceResponse()
        response.say("시스템 오류가 발생했습니다.", voice='Polly.Seoyeon', language='ko-KR')
        response.hangup()
        return str(response)
    
    state = conversation_states[call_sid]
    response = VoiceResponse()
    
    # 첫 번째 메시지 + 응답 대기
    gather = response.gather(
        input='speech',
        action=f'/voice/process?call_sid={call_sid}',
        method='POST',
        timeout=15,
        speech_timeout='auto',
        language='ko-KR',
        enhanced=True,
        profanity_filter=False
    )
    
    greeting_msg = fishing_handler.generate_greeting_message(
        state.fishing_request, 
        state.business_name
    )
    
    gather.say(greeting_msg, voice='Polly.Seoyeon', language='ko-KR')
    
    # 타임아웃 시 메시지
    response.say(
        "응답을 듣지 못했습니다. 나중에 다시 연락드리겠습니다.",
        voice='Polly.Seoyeon', 
        language='ko-KR'
    )
    response.hangup()
    
    return str(response)

@app.post("/voice/process")
async def process_speech_result(
    request: Request,
    call_sid: str,
    SpeechResult: Optional[str] = Form(None),
    CallSid: Optional[str] = Form(None)
):
    """음성 인식 결과 처리"""
    actual_call_sid = CallSid or call_sid
    
    if actual_call_sid not in conversation_states:
        response = VoiceResponse()
        response.hangup()
        return str(response)
    
    state = conversation_states[actual_call_sid]
    response = VoiceResponse()
    
    if not SpeechResult:
        response.say(
            "죄송합니다. 연결 상태가 좋지 않은 것 같습니다. "
            "나중에 다시 연락드리겠습니다.",
            voice='Polly.Seoyeon', language='ko-KR'
        )
        response.hangup()
        return str(response)
    
    # 응답 저장
    state.responses.append(f"{state.step.value}: {SpeechResult}")
    
    # 응답 분석 및 다음 단계 결정
    speech_lower = SpeechResult.lower()
    
    if state.step == ConversationStep.GREETING:
        if any(word in speech_lower for word in ["가능", "예약", "된다", "괜찮다"]):
            # 예약 가능한 경우
            state.step = ConversationStep.PRICE_INQUIRY
            gather = response.gather(
                input='speech',
                action=f'/voice/process?call_sid={actual_call_sid}',
                method='POST',
                timeout=15,
                speech_timeout='auto',
                language='ko-KR',
                enhanced=True
            )
            gather.say(
                "네 감사합니다. 그럼 비용은 어떻게 되나요?",
                voice='Polly.Seoyeon', language='ko-KR'
            )
            
        elif any(word in speech_lower for word in ["불가능", "안된다", "없다", "어렵다"]):
            # 예약 불가능한 경우
            state.step = ConversationStep.ALTERNATIVE_DATE
            gather = response.gather(
                input='speech',
                action=f'/voice/process?call_sid={actual_call_sid}',
                method='POST',
                timeout=15,
                speech_timeout='auto',
                language='ko-KR',
                enhanced=True
            )
            gather.say(
                "그렇다면 다른 날짜는 어떠신가요? "
                "이번 주말이나 다음 주 중에 가능한 날이 있을까요?",
                voice='Polly.Seoyeon', language='ko-KR'
            )
        else:
            # 재확인
            gather = response.gather(
                input='speech',
                action=f'/voice/process?call_sid={actual_call_sid}',
                method='POST',
                timeout=15,
                speech_timeout='auto',
                language='ko-KR',
                enhanced=True
            )
            gather.say(
                "죄송합니다. 다시 한번 말씀해주세요. "
                f"{state.fishing_request.date} {state.fishing_request.time}에 "
                f"{state.fishing_request.people_count}명 낚시 예약이 가능한가요?",
                voice='Polly.Seoyeon', language='ko-KR'
            )
    
    elif state.step == ConversationStep.PRICE_INQUIRY:
        state.step = ConversationStep.CONFIRMATION
        state.is_successful = True
        response.say(
            "네 알겠습니다. 확인해보고 다시 연락드리겠습니다. "
            "좋은 하루 되세요. 감사합니다.",
            voice='Polly.Seoyeon', language='ko-KR'
        )
        response.hangup()
        
    elif state.step == ConversationStep.ALTERNATIVE_DATE:
        state.step = ConversationStep.COMPLETED
        response.say(
            "네 알겠습니다. 확인해보고 다시 연락드리겠습니다. "
            "감사합니다.",
            voice='Polly.Seoyeon', language='ko-KR'
        )
        response.hangup()
    
    return str(response)

@app.post("/voice/status")
async def voice_status_callback(
    request: Request,
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None)
):
    """통화 상태 콜백"""
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
        "is_successful": state.is_successful
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
        "final_step": state.step
    }

@app.get("/")
async def root():
    """API 루트"""
    return {"message": "낚시 예약 AI 에이전트 API", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)