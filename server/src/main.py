# main.py - 낚시 예약 AI 에이전트
from fastapi import FastAPI, Request, Form, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from src.config import settings, logger
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import os
import json
from dotenv import load_dotenv
import openai
from src.realtime_server import sio

load_dotenv()
URL = os.getenv("URL", "http://localhost:8000")  # 기본값 설정
US_PHONENUMBER = os.getenv("US_PHONENUMBER")
KO_PHONENUMBER = os.getenv("KO_PHONENUMBER")

app = FastAPI(
    title="낚시 예약 AI 에이전트",
    description="Twilio와 OpenAI를 사용한 실시간 음성 대화 시스템",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Twilio 및 OpenAI 클라이언트 설정
twilio_client = Client(os.getenv('ACCOUNT_SID'), os.getenv('AUTH_TOKEN'))
openai_client = openai.OpenAI(api_key=settings.openai_api_key)

# 인메모리 대화 상태 저장소
conversation_history: Dict[str, List[Dict[str, str]]] = {}

class CallRequest(BaseModel):
    to_number: str = Field(..., description="전화를 받을 상대방 번호 (E.164 형식)")

class CallResponse(BaseModel):
    status: str
    call_sid: Optional[str] = None
    message: str

@app.post("/call/initiate", response_model=CallResponse)
async def initiate_call(req: CallRequest):
    """지정된 번호로 전화를 걸고 TwiML 웹훅을 설정합니다."""
    logger.info(f"전화 시작 요청 수신: {req.to_number}")
    try:
        webhook_url = f"{URL}/voice/start"
        call = twilio_client.calls.create(
            to=req.to_number,
            from_=US_PHONENUMBER,
            url=webhook_url,
            method='POST',
            status_callback=f"{URL}/voice/status",
            status_callback_method='POST',
            status_callback_event=['initiated', 'ringing', 'answered', 'completed', 'busy', 'failed', 'no-answer', 'canceled'],
        )
        logger.info(f"Twilio 통화 생성 성공: {call.sid}")
        # 새 통화에 대한 대화 기록 초기화
        conversation_history[call.sid] = [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."}]
        return CallResponse(status="success", call_sid=call.sid, message="전화 연결이 시작되었습니다.")
    except TwilioRestException as e:
        logger.error(f"Twilio API 오류: {e}")
        raise HTTPException(status_code=400, detail=f"Twilio 오류: {e.msg}")
    except Exception as e:
        logger.error(f"통화 시작 중 예상치 못한 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.post("/voice/start")
async def handle_voice_start(request: Request):
    """통화 시작 시 초기 메시지를 재생하고 사용자 입력을 받습니다."""
    form = await request.form()
    call_sid = form.get('CallSid')
    logger.info(f"통화 시작됨 (SID: {call_sid})")
    
    response = VoiceResponse()
    response.say("안녕하세요! 무엇을 도와드릴까요?", voice='Polly.Seoyeon', language='ko-KR')
    
    # 첫 번째 사용자 입력을 받기 위해 Gather 동사 추가
    gather = Gather(input='speech',
                    action='/voice/process-speech',
                    method='POST',
                    speech_timeout='auto', # 사용자가 말 멈추면 자동 종료
                    speech_model='experimental_conversations',
                    language='ko-KR')
    response.append(gather)

    # 사용자가 아무 말도 하지 않을 경우를 대비한 리디렉션
    response.redirect('/voice/process-speech', method='POST')
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/voice/process-speech")
async def process_speech(request: Request):
    """사용자 음성 입력을 처리하고 LLM 응답을 생성하여 반환합니다."""
    form = await request.form()
    call_sid = form.get('CallSid')
    user_speech = form.get('SpeechResult')
    
    logger.info(f"음성 수신 (SID: {call_sid}): {user_speech}")

    response = VoiceResponse()

    if user_speech:
        # 프론트엔드로 사용자 발화 전송
        await sio.emit('user_speech', {'text': user_speech})

        # 대화 기록에 사용자 발화 추가
        if call_sid in conversation_history:
            conversation_history[call_sid].append({"role": "user", "content": user_speech})
        else:
            # 만약을 대비한 초기화
            conversation_history[call_sid] = [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."},
                                              {"role": "user", "content": user_speech}]

        
        try:
            # OpenAI LLM 호출
            llm_response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=conversation_history[call_sid],
                max_tokens=150,
                temperature=0.7,
            )
            ai_message = llm_response.choices[0].message.content
            logger.info(f"LLM 응답 (SID: {call_sid}): {ai_message}")

            # 프론트엔드로 AI 응답 전송
            await sio.emit('ai_response', {'text': ai_message})

            # 대화 기록에 AI 응답 추가
            conversation_history[call_sid].append({"role": "assistant", "content": ai_message})

            # AI 응답을 사용자에게 음성으로 전달
            response.say(ai_message, voice='Polly.Seoyeon', language='ko-KR')

        except Exception as e:
            logger.error(f"OpenAI 처리 오류 (SID: {call_sid}): {e}")
            response.say("죄송합니다. 시스템에 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", voice='Polly.Seoyeon', language='ko-KR')
    else:
        # 사용자가 아무 말도 하지 않은 경우
        logger.info(f"사용자 입력 없음 (SID: {call_sid})")
        response.say("아무 말씀도 안 하셨네요. 도움이 필요하시면 말씀해주세요.", voice='Polly.Seoyeon', language='ko-KR')

    # 다시 사용자 입력을 기다림
    gather = Gather(input='speech',
                    action='/voice/process-speech',
                    method='POST',
                    speech_timeout='auto',
                    speech_model='experimental_conversations',
                    language='ko-KR')
    response.append(gather)
    
    response.redirect('/voice/process-speech', method='POST')

    return Response(content=str(response), media_type="application/xml")

@app.post("/voice/status")
async def voice_status_callback(request: Request):
    """통화 상태 변경 시 호출되는 웹훅. 통화 종료 시 프론트엔드에 알림."""
    form = await request.form()
    call_sid = form.get('CallSid')
    call_status = form.get('CallStatus')

    
    logger.info(f"통화 상태 업데이트 (SID: {call_sid}): {call_status}")
    # 통화 종료 상태 목록
    final_statuses = ['completed', 'busy', 'failed', 'no-answer', 'canceled']

    if call_status in final_statuses:
        logger.info(f"통화 종료됨 (SID: {call_sid}). 프론트엔드에 알림 전송.")
        # Socket.IO를 통해 프론트엔드에 이벤트 전송
        await sio.emit('call_ended', {'call_sid': call_sid})
        
        # 대화 기록 삭제
        if call_sid in conversation_history:
            del conversation_history[call_sid]
            logger.info(f"대화 기록 삭제 (SID: {call_sid})")

    return Response(status_code=200)

# --- 기존의 복잡한 WebSocket 및 미디어 스트리밍 관련 코드는 모두 제거 ---

# Socket.IO 앱 마운트 (realtime_server.py에서 가져옴)
from src.realtime_server import socket_app
app.mount("/socket.io", socket_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

