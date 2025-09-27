# main.py - 낚시 예약 AI 에이전트
from fastapi import FastAPI, Request, HTTPException, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from src.config import settings, logger
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Tuple
from uuid import uuid4
from datetime import datetime

import os
import json
from dotenv import load_dotenv

from sqlalchemy.orm import Session
# 지침에 따른 데이터베이스 연결
from .database import get_db, engine, seed_businesses_if_needed, reseed_businesses, SessionLocal, run_migrations
from . import models, crud
from .agent import ChatRequest, ChatResponse, PlanAgent
from .agent.services import AgentServices
from .agent import call_runtime
from .agent.call_test_flow import run_call_flow

# 데이터베이스 테이블 생성
models.Base.metadata.create_all(bind=engine)
run_migrations()


def clear_persistent_data() -> None:
    """서버 시작 시 모든 영속 데이터를 초기화합니다."""
    session = SessionLocal()
    try:
        session.query(models.Reservation).delete()
        session.query(models.Plan).delete()
        session.query(models.Business).delete()
        session.commit()
        logger.info("데이터베이스 초기화 완료: reservations, plans, businesses 테이블을 비웠습니다.")
    except Exception:
        session.rollback()
        logger.exception("데이터베이스 초기화 중 오류가 발생했습니다.")
        raise
    finally:
        session.close()

import openai
from src.realtime_server import sio
from src.fishery_api import router as fishery_router

load_dotenv()
US_PHONENUMBER = os.getenv("US_PHONENUMBER")
KO_PHONENUMBER = os.getenv("KO_PHONENUMBER")

app = FastAPI(
    title="낚시 예약 AI 에이전트",
    description="Twilio와 OpenAI를 사용한 실시간 음성 대화 시스템",
    version="2.0.0"
)


@app.on_event("startup")
def on_startup() -> None:
    clear_persistent_data()

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

conversation_history: Dict[str, List[Dict[str, str]]] = {}
assistant_stream_buffers: Dict[str, str] = {}

############################
# 기존 함수 in_scenario 재정의 완료
############################


class CallRequest(BaseModel):
    to_number: Optional[str] = Field(None, description="수신 번호(E.164)")

class CallResponse(BaseModel):
    status: str
    call_sid: Optional[str] = None
    message: str


plan_agent = PlanAgent()
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


class CallStatus(BaseModel):
    call_sid: str
    status: Optional[str]
    transcript_turns: int
    last_lines: List[Dict[str, str]] = []


class CallTestRequest(BaseModel):
    shop_name: Optional[str] = Field(None, description="테스트용 선호 업체명")
    simulate: bool = Field(False, description="실제 통화 대신 시뮬레이션")

class CallTestResponse(BaseModel):
    result: Dict[str, Any]


@app.post("/call", response_model=CallTestResponse)
async def call_invoke(req: CallTestRequest, db: Session = Depends(get_db)):
        """시나리오 기반 또는 실전화 콜 실행 (단독 CallExecutionAgent).

        Body:
            - shop_name: 특정 상점 우선 선택 (부분 매칭 허용)
            - simulate: True 면 Twilio 실제 발신 대신 시뮬레이션 (그래프/시나리오/추출은 동일 수행)
        반환: state / slots / transcript 일부 (front-end 가 확장 필요 시 수정 가능)
        """
        logger.info("/call 시작 shop=%s simulate=%s", req.shop_name, req.simulate)
        out = run_call_flow(db, shop_name=req.shop_name, simulate=req.simulate)
        return CallTestResponse(result=out)


@app.get("/debug/businesses")
async def debug_list_businesses(db: Session = Depends(get_db), location: Optional[str] = None, force: bool = False):
    """현재 DB의 비즈니스 목록을 확인하거나 ?force=true 로 CSV 재시드를 실행.

    Query Params:
      - location: 위치 필터 (옵션)
      - force: true 일 경우 reseed_businesses(force=True) 실행 후 목록 반환
    """
    if force:
        summary = reseed_businesses(force=True, normalize=True)
    else:
        summary = {"reseed": False}
    services = AgentServices(db)
    names = services.list_business_names(location=location)
    all_names = services.list_business_names() if location else names
    return {
        "location": location,
        "count": len(names),
        "names": names,
        "all_total": len(all_names),
        "reseed_summary": summary,
    }


@app.get("/call/status/{call_sid}", response_model=CallStatus)
async def get_call_status(call_sid: str):
    """런타임에 저장된 통화 상태 & 최근 transcript 일부 반환 (Swagger 테스트용)."""
    status = call_runtime.get_status(call_sid)
    # transcript는 drain하지 않고 내부 dict 직접 접근 (readonly)
    turns = call_runtime._transcripts.get(call_sid, [])  # type: ignore[attr-defined]
    preview = turns[-5:]
    return CallStatus(
        call_sid=call_sid,
        status=status,
        transcript_turns=len(turns),
        last_lines=[{"speaker": t["speaker"], "text": t["text"], "ts": t["ts"]} for t in preview],
    )

@app.post("/call/initiate", response_model=CallResponse)
async def initiate_call(req: CallRequest):
    """지정된 번호로 전화를 걸고 TwiML 웹훅을 설정합니다.
    - settings.twilio_webhook_url 로 교체
    - 번호 기본 검증 및 상세 오류 로그 추가
    """
    # 번호 결정 로직 (요청 > KO > US)
    chosen_number = (req.to_number or KO_PHONENUMBER or US_PHONENUMBER or '').strip()
    logger.info(f"전화 시작 요청 수신 to={req.to_number} | fallback→ {chosen_number if req.to_number != chosen_number else '사용 안함'}")

    if not chosen_number:
        raise HTTPException(status_code=400, detail="수신 번호가 제공되지 않았고 KO_PHONENUMBER / US_PHONENUMBER 환경변수도 비어 있습니다.")

    raw_number = chosen_number

    # 기본 형식 검증 (심플)
    if not raw_number.startswith('+'):
        raise HTTPException(status_code=400, detail="E.164 형식(+국가코드...)으로 번호를 입력하세요.")
    if len(raw_number) < 8:
        raise HTTPException(status_code=400, detail="전화번호 길이가 너무 짧습니다.")

    # Twilio Trial 계정: 인증된 번호만 허용될 수 있음 - 안내 로그
    if not US_PHONENUMBER:
        logger.warning("US_PHONENUMBER 환경변수가 설정되지 않았습니다.")

    base_webhook = settings.twilio_webhook_url.rstrip('/')  # 공개 ngrok 주소 기대
    voice_url = f"{base_webhook}/voice/start"
    status_callback_url = f"{base_webhook}/voice/status"
    logger.debug(f"Webhook URL 사용: {voice_url} | Status Callback: {status_callback_url}")

    try:
        call = twilio_client.calls.create(
            to=raw_number,
            from_=US_PHONENUMBER,  # 발신자는 Twilio 구매 번호 (국제 발신 권한 확인 필요)
            url=voice_url,
            method="POST",
            status_callback=status_callback_url,
            status_callback_method='POST',
            status_callback_event=['initiated', 'ringing', 'answered', 'completed', 'busy', 'failed', 'no-answer', 'canceled'],
        )
        logger.info(f"Twilio 통화 생성 성공: sid={call.sid} to={raw_number}")
        conversation_history[call.sid] = [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."}]
        # 시나리오/콜 세부 로직은 agent call graph에서 관리 (여기서는 단순 발신)

        return CallResponse(status="success", call_sid=call.sid, message="전화 연결이 시작되었습니다.")
    except TwilioRestException as e:
        logger.error(f"Twilio API 오류 code={getattr(e, 'code', None)} msg={getattr(e, 'msg', str(e))}")
        detail = getattr(e, 'msg', str(e))
        raise HTTPException(status_code=400, detail=f"Twilio 오류: {detail}")
    except Exception as e:
        logger.error(f"통화 시작 중 예상치 못한 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")


@app.post("/voice/start")
async def handle_voice_start(request: Request, db: Session = Depends(get_db)):
    """통화 시작 시 초기 메시지를 재생하고 사용자 입력을 받습니다."""
    form = await request.form()
    call_sid = form.get('CallSid')
    logger.info(f"통화 시작됨 (SID: {call_sid})")
    if call_sid:
        # 초기 status 저장 (initiated)
        AgentServices(db).update_call_status(call_sid, 'initiated')
    
    greeting = "안녕하세요! 무엇을 도와드릴까요?"
    response = VoiceResponse()
    response.say(greeting, voice='Polly.Seoyeon', language='ko-KR')
    # 프론트엔드 실시간 표시를 위해 초기 에이전트 멘트를 Socket.IO로 전송
    if call_sid:
        # 대화 기록 초기화 (시나리오 진행도 포함)
        conversation_history.setdefault(call_sid, [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."}])
        conversation_history[call_sid].append({"role": "assistant", "content": greeting})
        # 대화 기록에 첫 greeting 저장 (시나리오면 이미 idx 0 소비)
        await sio.emit('ai_response_complete', { 'text': greeting, 'call_sid': call_sid })
    
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
async def process_speech(request: Request, db: Session = Depends(get_db)):
    """사용자 음성 입력을 처리하고 LLM 응답을 생성하여 반환합니다."""
    form = await request.form()
    call_sid = form.get('CallSid')
    user_speech = form.get('SpeechResult')
    
    logger.info(f"음성 수신 (SID: {call_sid}): {user_speech}")
    services = AgentServices(db)

    response = VoiceResponse()

    if user_speech:
        # 프론트엔드로 사용자 발화 전송 (call_sid 포함)
        await sio.emit('user_speech', {'text': user_speech, 'call_sid': call_sid})
        services.record_transcript_turn(call_sid, 'user', user_speech)

        # 대화 기록에 사용자 발화 추가
        if call_sid in conversation_history:
            conversation_history[call_sid].append({"role": "user", "content": user_speech})
        else:
            # 만약을 대비한 초기화
            conversation_history[call_sid] = [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."},
                                              {"role": "user", "content": user_speech}]

        
        try:
            # OpenAI 스트리밍 호출로 토큰 단위 전송
            logger.info(f"OpenAI 스트리밍 시작 (SID: {call_sid})")
            # 프론트가 이전 응답 누적을 초기화할 수 있도록 시작 이벤트 emit
            await sio.emit('ai_response_begin', {'call_sid': call_sid})
            stream = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=conversation_history[call_sid],
                max_tokens=180,
                temperature=0.7,
                stream=True,
            )
            full_chunks: List[str] = []
            for chunk in stream:
                delta = None
                try:
                    choice = chunk.choices[0]
                    raw_delta = getattr(choice, 'delta', None)
                    # 다양한 포맷 지원
                    if isinstance(raw_delta, dict):
                        content_val = raw_delta.get('content')
                        if isinstance(content_val, str):
                            delta = content_val
                        elif isinstance(content_val, list):
                            parts = []
                            for part in content_val:
                                if isinstance(part, dict):
                                    t = part.get('text') or part.get('content')
                                    if t: parts.append(t)
                                elif isinstance(part, str):
                                    parts.append(part)
                            if parts:
                                delta = ''.join(parts)
                    elif raw_delta and isinstance(raw_delta, str):
                        delta = raw_delta
                except Exception as parse_e:
                    logger.debug(f"스트리밍 델타 파싱 실패 (SID: {call_sid}): {parse_e}")
                    delta = None
                if delta:
                    full_chunks.append(delta)
                    await sio.emit('ai_response_text', {'text_delta': delta, 'call_sid': call_sid})
                    # --- Streaming transcript runtime flush (partial) ---
                    if call_sid:
                        buf = assistant_stream_buffers.get(call_sid, "") + delta
                        # Flush 조건: 길이 임계 또는 문장부호 종료
                        if len(buf) > 40 or any(buf.endswith(p) for p in [".", "?", "!", "요", "다", "."]):
                            # runtime transcript에 부분 turn 추가
                            services.record_transcript_turn(call_sid, 'assistant', buf.strip())
                            buf = ""
                        assistant_stream_buffers[call_sid] = buf
            ai_message = ''.join(full_chunks).strip()
            if not ai_message:
                logger.warning(f"스트리밍 델타가 비어있음. 폴백 단일 요청 수행 (SID: {call_sid})")
                try:
                    fallback = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=conversation_history[call_sid],
                        max_tokens=160,
                        temperature=0.7,
                        stream=False,
                    )
                    ai_message = fallback.choices[0].message.get('content') if fallback.choices else ''
                except Exception as fb_e:
                    logger.error(f"폴백 단일 요청 실패 (SID: {call_sid}): {fb_e}")
            logger.info(f"OpenAI 스트리밍 완료 (SID: {call_sid}) 길이={len(ai_message)}")

            # 최종 발화 내용 결정 (빈 문자열이면 사용자에게 들려준 사과 멘트 사용)
            final_text = ai_message if ai_message else "죄송합니다. 지금은 답을 제공할 수 없어요."

            # 남은 partial buffer 최종 turn으로 기록 (중복 방지: final_text가 이미 포함되면 스킵)
            if call_sid:
                pending_buf = assistant_stream_buffers.get(call_sid, "").strip()
                if pending_buf:
                    if pending_buf not in final_text:
                        services.record_transcript_turn(call_sid, 'assistant', pending_buf)
                # 최종 발화 전체가 마지막 partial과 다르면 한 번 더 전체 문장 기록
                if not ai_message.endswith(pending_buf):
                    services.record_transcript_turn(call_sid, 'assistant', final_text)
                assistant_stream_buffers[call_sid] = ""

            # 대화 기록 업데이트 (빈 응답이라도 실제 사용자에게 들린 문장 저장)
            conversation_history[call_sid].append({"role": "assistant", "content": final_text})

            # Twilio 음성 재생
            response.say(final_text, voice='Polly.Seoyeon', language='ko-KR')

            # 최종 응답 소켓 전송 (emit 시점을 Twilio say 이후로 이동해 UI와 음성 싱크 개선)
            await sio.emit('ai_response_complete', {'text': final_text, 'call_sid': call_sid})
            services.record_transcript_turn(call_sid, 'assistant', final_text)

        except StopIteration:
            # 시나리오 분기 정상 처리 - 아무 것도 하지 않고 다음 Gather 로 진행
            pass
        except Exception as e:
            logger.error(f"OpenAI/시나리오 처리 오류 (SID: {call_sid}): {e}", exc_info=True)
            error_text = "죄송합니다. 시스템에 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            await sio.emit('openai_error', {'error': str(e)})
            # 사용자에게 들리는 멘트를 UI에도 표시
            await sio.emit('ai_response_complete', {'text': error_text, 'call_sid': call_sid})
            services.record_transcript_turn(call_sid, 'assistant', error_text)
            conversation_history.setdefault(call_sid, [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다."}])
            conversation_history[call_sid].append({"role": "assistant", "content": error_text})
            response.say(error_text, voice='Polly.Seoyeon', language='ko-KR')
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
async def voice_status_callback(request: Request, db: Session = Depends(get_db)):
    """통화 상태 변경 시 호출되는 웹훅. 통화 종료 시 프론트엔드에 알림."""
    form = await request.form()
    call_sid = form.get('CallSid')
    call_status = form.get('CallStatus')
    error_code = form.get('ErrorCode')  # Twilio가 실패 사유 코드 제공 (https://www.twilio.com/docs/api/errors)
    to_number = form.get('To')
    from_number = form.get('From')

    
    logger.info(f"통화 상태 업데이트 (SID: {call_sid}) status={call_status} error_code={error_code} to={to_number} from={from_number}")
    services = AgentServices(db)
    if call_sid and call_status:
        services.update_call_status(call_sid, call_status)
    # 통화 종료 상태 목록
    final_statuses = ['completed', 'busy', 'failed', 'no-answer', 'canceled']

    # 실시간 상태 업데이트 이벤트 전송
    await sio.emit('call_status_update', {
        'call_sid': call_sid,
        'status': call_status,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'data': { 'error_code': error_code }
    })

    if call_status in final_statuses:
        logger.info(f"통화 종료됨 (SID: {call_sid}). 프론트엔드에 알림 전송.")
        # Socket.IO를 통해 프론트엔드에 이벤트 전송
        await sio.emit('call_ended', {'call_sid': call_sid})
        
        # 대화 기록 삭제
        if call_sid:
            if call_sid in conversation_history:
                del conversation_history[call_sid]
                logger.info(f"대화 기록 삭제 (SID: {call_sid})")
            # TODO: call_graph extraction이 끝났는지 확인 후 runtime cleanup (보류)

    return Response(status_code=200)

# --- 기존의 복잡한 WebSocket 및 미디어 스트리밍 관련 코드는 모두 제거 ---

# 어획량 API 라우터 등록
app.include_router(fishery_router)

# Socket.IO 앱 마운트 (realtime_server.py에서 가져옴)
from src.realtime_server import socket_app
app.mount("/socket.io", socket_app)


if __name__ == "__main__":
    import uvicorn
    from src.ssl_generator import generate_self_signed_cert
    import os
    
    # SSL 인증서 생성
    cert_file, key_file = generate_self_signed_cert()
    
    # HTTPS 사용 여부 환경변수로 제어 (기본값: True)
    use_ssl = os.getenv("USE_SSL", "true").lower() in ("true", "1", "yes")
    
    if use_ssl:
        print(f"Starting HTTPS server with SSL certificate: {cert_file}")
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=8000,
            ssl_keyfile=key_file,
            ssl_certfile=cert_file,
            ssl_version=3,  # TLS 1.2+
        )
    else:
        print("Starting HTTP server (SSL disabled)")
        uvicorn.run(app, host="0.0.0.0", port=8000)