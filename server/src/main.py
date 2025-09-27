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
# NOTE: run_call_flow / call_runtime 기능을 main 내부로 통합하기 위한 준비.
# 기존 별도 유틸 (.agent.call_test_flow, .agent.call_runtime) 사용을 단계적으로 축소.
# 아래 TODO 섹션 참조.
from .agent.conversation_models import FishingPlanDetails
from .agent.scenario_loader import load_scenario_steps, ScenarioState

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
    # 비즈니스 데이터 시드 (이미 존재하면 skip)
    try:
        seed_businesses_if_needed()
    except Exception:
        logger.exception("비즈니스 시드 중 오류 발생")

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
_scenario_sessions: Dict[str, ScenarioState] = {}  # call_sid -> ScenarioState

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
    """플래너 결과를 기반으로 비즈니스(낚시점)에 즉시 전화를 발신하거나 시뮬레이션.

    - Planner 필수 키가 비어있으면 400 반환
    - simulate=True: Twilio 미호출, 가짜 SID 생성 후 즉시 completed 상태로 반환
    - simulate=False: Twilio outbound (start_reservation_call 경유) 수행
    - WebSocket 이벤트: call_started, call_failed
    """
    services = AgentServices(db)
    snapshot = services.load_plan()
    plan_details = snapshot.details
    missing = plan_details.missing_keys()
    if missing:
        return CallTestResponse(result={
            'state': 'failed',
            'error': f'플랜 필수 정보 부족: {", ".join(missing)}',
            'missing': missing,
            'simulated': req.simulate,
        })

    # 비즈니스 선택
    selection = services.pick_business(details=plan_details, preferred_name=req.shop_name)
    business = selection.business
    if not business:
        await sio.emit('call_failed', {'reason': 'no_business', 'shop_name': req.shop_name})
        return CallTestResponse(result={
            'state': 'failed',
            'error': '연결 가능한 비즈니스가 없습니다.',
            'simulated': req.simulate,
        })

    # 시뮬레이션 분기
    if req.simulate:
        call_sid = f"SIM-{uuid4().hex[:10]}"
        services.update_call_status(call_sid, 'completed')
        conversation_history[call_sid] = [
            {"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."}
        ]
        await sio.emit('call_started', {
            'call_sid': call_sid,
            'business': business.name,
            'phone': business.phone,
            'simulated': True,
        })
        return CallTestResponse(result={
            'state': 'completed',
            'call_sid': call_sid,
            'shop_name': business.name,
            'phone': business.phone,
            'simulated': True,
            'transcript_len': 0,
            'transcript_preview': [],
            'slots': {},
        })

    # 실전화: 기존 start_reservation_call 로 Twilio 호출 (Webhook /voice/start → /voice/process-speech 흐름)
    summary = services.start_reservation_call(details=plan_details, preferred_name=req.shop_name)
    if not summary.success or not summary.sid:
        await sio.emit('call_failed', {
            'business': business.name,
            'phone': business.phone,
            'error': summary.message,
        })
        return CallTestResponse(result={
            'state': 'failed',
            'error': summary.message,
            'shop_name': business.name,
        })

    call_sid = summary.sid
    conversation_history[call_sid] = [
        {"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."}
    ]
    await sio.emit('call_started', {
        'call_sid': call_sid,
        'business': business.name,
        'phone': business.phone,
        'simulated': False,
    })
    return CallTestResponse(result={
        'state': 'initiated',
        'call_sid': call_sid,
        'shop_name': business.name,
        'phone': business.phone,
        'simulated': False,
    })

    # NOTE: 통합 후 예상 반환 형식 (초안)
    # return CallTestResponse(result={
    #   'state': 'completed',
    #   'call_sid': call_sid,
    #   'shop_name': shop_name,
    #   'started_at': started_iso,
    #   'ended_at': ended_iso,
    #   'transcript_len': len(transcript),
    #   'transcript_preview': transcript[:6],
    #   'slots': slots.to_dict(),
    #   'error': None,
    #   'simulated': simulate,
    #   'candidate_count': len(candidates)
    # })


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
    """[Deprecated]
    런타임에 저장된 통화 상태 & 최근 transcript 일부 반환 (Swagger 테스트/백업 용).
    프런트엔드는 WebSocket 이벤트(call_started, call_status_update, ai_response_*, call_ended 등)
    기반으로 상태를 구성해야 하며 일반 흐름에서는 이 엔드포인트를 폴링하지 않습니다.
    재연결 후 state 복구가 필요한 극히 예외적인 경우만 1회 호출하십시오.
    """
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
    
    response = VoiceResponse()
    first_line = "안녕하세요! 무엇을 도와드릴까요?"  # 기본
    scenario_used = False
    if settings.scenario_mode and call_sid:
        steps = load_scenario_steps(settings.scenario_id)
        if steps:
            st = ScenarioState(steps)
            _scenario_sessions[call_sid] = st
            line = st.next_assistant_line()
            if line:
                first_line = line
                scenario_used = True
    response.say(first_line, voice='Polly.Seoyeon', language='ko-KR')
    if call_sid:
        conversation_history.setdefault(call_sid, [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."}])
        conversation_history[call_sid].append({"role": "assistant", "content": first_line})
        await sio.emit('ai_response_complete', { 'text': first_line, 'call_sid': call_sid, 'scenario': scenario_used })
    
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
            # (시나리오 모드) 다음 assistant scripted line 우선 제공
            scenario_state = _scenario_sessions.get(call_sid) if call_sid else None
            if settings.scenario_mode and scenario_state:
                next_line = scenario_state.next_assistant_line()
                if next_line:
                    conversation_history[call_sid].append({"role": "assistant", "content": next_line})
                    services.record_transcript_turn(call_sid, 'assistant', next_line)
                    response.say(next_line, voice='Polly.Seoyeon', language='ko-KR')
                    await sio.emit('ai_response_complete', {'text': next_line, 'call_sid': call_sid, 'scenario': True})
                    # 시나리오 라인만 재생 후 바로 다음 사용자 입력 대기 (LLM 호출 생략)
                    gather = Gather(input='speech', action='/voice/process-speech', method='POST', speech_timeout='auto', speech_model='experimental_conversations', language='ko-KR')
                    response.append(gather)
                    response.redirect('/voice/process-speech', method='POST')
                    return Response(content=str(response), media_type='application/xml')
                else:
                    # 시나리오 종료 후 일반 LLM 전환 알림 한번만
                    await sio.emit('scenario_finished', {'call_sid': call_sid})
                    del _scenario_sessions[call_sid]
            # OpenAI 스트리밍 호출로 토큰 단위 전송 (일반 모드)
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
        
        # ---- 슬롯 추출 & Plan.status 업데이트 (Item #1) ----
        if call_sid:
            try:
                # 1) transcript 수집 (call_runtime 내부 저장 형태: list[dict])
                raw_turns = call_runtime._transcripts.get(call_sid, [])  # type: ignore[attr-defined]
                # services.extract_slots_from_transcript 는 turn.text 속성을 기대 → 간단 래퍼 생성
                class _Wrap:
                    def __init__(self, text: str):
                        self.text = text
                wrapped = [_Wrap(t.get('text', '')) for t in raw_turns]
                slots = services.extract_slots_from_transcript(wrapped)

                # 2) 기존 Plan.status 로드 → slots 병합하여 재저장
                snapshot = services.load_plan()
                plan_obj = snapshot.record
                details = snapshot.details
                stage = snapshot.stage
                # 기존 status JSON 파싱
                call_payload = None
                try:
                    if plan_obj.status:
                        current_payload = json.loads(plan_obj.status)
                        call_payload = current_payload.get('call') if isinstance(current_payload, dict) else None
                except Exception:
                    logger.warning("plan.status JSON 파싱 실패 → 재생성")
                payload: Dict[str, Any] = {
                    'stage': stage,
                    'plan': details.to_dict(),
                }
                if call_payload:
                    payload['call'] = call_payload
                else:
                    # 최소 call 요약 (business_name 추론)
                    business_name = call_payload.get('business_name') if call_payload else '(unknown)'
                    payload['call'] = {
                        'success': call_status == 'completed',
                        'business_name': business_name,
                        'status': call_status,
                        'sid': call_sid,
                        'message': f'통화 종료 상태: {call_status}',
                    }
                payload['slots'] = slots.to_dict()
                plan_obj.status = json.dumps(payload, ensure_ascii=False)
                services.db.add(plan_obj)
                services.db.commit()
                logger.info(f"슬롯 저장 완료 call_sid={call_sid} slots={payload['slots']}")
                # 슬롯 저장 완료 이벤트
                await sio.emit('call_slots_extracted', {
                    'call_sid': call_sid,
                    'slots': payload['slots'],
                })
            except Exception as exc:
                logger.error(f"슬롯 추출/저장 실패 call_sid={call_sid}: {exc}", exc_info=True)
                await sio.emit('call_slots_error', {
                    'call_sid': call_sid,
                    'error': str(exc),
                })

            # 3) 대화 기록 및 runtime cleanup
            if call_sid in conversation_history:
                del conversation_history[call_sid]
                logger.info(f"대화 기록 삭제 (SID: {call_sid})")
            try:
                call_runtime.cleanup(call_sid)  # type: ignore[attr-defined]
            except Exception:
                pass
            # TODO(Scenario Progress): scenario_finished 상태면 별도 summary 이벤트 push 고려

############################
# Planner Agent 구조 반영 / 통합 콜 플로우 개선을 위한 TODO 모음 (High-level)
############################
# 1. Planner → Call 연계: 현재 PlannerAgent 결과(plan_details)와 별개로 /call 이 독립 실행.
#    - 목표: /chat 상에서 call 요청 감지 시 plan_details(snapshot)를 기반으로 /call 호출 or 직접 서비스 호출.
#    - compose_response_node 에 callSuggested 로직 존재. tool_runner_node 의 call tool 과 충돌 여부 점검 필요.
# 2. FishingPlanDetails 필드 차이: 과거 participants_adults/children → 단일 participants 로 수렴됨.
#    - 과거 seed/시뮬레이션 코드(build_minimal_plan 등) 정리 필요.
# 3. PlanSnapshot.persist 구조: plan.status JSON { stage, plan, call } 형식 유지.
#    - 통화 완료 시 call_summary + slots 추가 확장: { stage, plan, call, slots } 고려.
# 4. Scenario 모드: main 의 /voice/start 에서 greeting 고정 → scenario 첫 assistant_lines 선재생 필요.
#    - scenario_loader 로드 + per-call state 저장(dict: scenario_cursor).
# 5. 실시간 Transcript: assistant_stream_buffers flush 로직과 call_runtime 중복 turn 기록 정리 (중복 최소화).
# 6. Slot Extraction 시점: 현재 call_graph.extract_node 또는 /voice/status 종료 시점 중 선택.
#    - 음성 통화의 경우 종료 webhook(/voice/status)에서 transcript snapshot 후 extract 호출 권장.
# 7. Error Handling: OpenAI 스트림 실패 시 fallback, Twilio 실패 시 HTTP 400. 재시도 정책 정의 필요.
# 8. Simulation Path: /call simulate=True 와 /call/initiate 차이 통합 -> mode flag + twilio inactive fallback.
# 9. Websocket Events 표준화: ai_response_begin/text/complete vs scenario_line 이벤트 구분.
# 10. Cleanup Strategy: call_runtime + conversation_history + scenario_state 모두 종료 이벤트에서 일괄 정리.
# 11. PlannerAgent missing_keys 있을 때 call 요청 방지 (사전 검증) → /call 진입 시 guard.
# 12. Tool Integration: call tool 실행 시 /call API 호출 대신 내부 Python 함수 직접 호출 고려.
# 13. Observability: 통화 lifecycle 로그 ID(call_sid) prefix 통일, timing metrics (started→ended) 계산.
# 14. Config Flags: settings.scenario_mode, scenario_auto_feed_all 사용 여부 재정의 및 문서화.
# 15. Tests: test_api.py 확장 - /call happy path + simulate path + slot extraction edge cases.


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