# main.py - 낚시 예약 AI 에이전트
from fastapi import FastAPI, Request, Form, HTTPException, Response, WebSocket, WebSocketDisconnect
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
import openai
from src.realtime_server import sio

load_dotenv()
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
############################
# 시나리오 확장 지원      #
############################
SCENARIO_MODE = os.getenv("SCENARIO_MODE", "0").lower() in ("1", "true", "yes", "on")
from pathlib import Path

# 시나리오 디렉토리 해석 로직 개선: 실행 기준 디렉토리(server/)와 루트 혼동 방지
_raw_scenario_dir = os.getenv("SCENARIO_DIR")
_base_dir = Path(__file__).resolve().parent  # server/src
_project_root = _base_dir.parent  # server/

def _resolve_scenario_dir() -> str:
    candidates = []
    if _raw_scenario_dir:
        p = Path(_raw_scenario_dir)
        if not p.is_absolute():
            # 현재 working dir이 server/ 라면 'server/data/..' 는 중복 -> 정규화
            candidates.append((_project_root / p).resolve())
            # 사용자가 server/data/scenarios 로 넣었지만 실제는 data/scenarios 일 때
            if str(p).startswith('server/'):
                candidates.append((_project_root / str(p)[7:]).resolve())
        else:
            candidates.append(p)
    # 기본 후보: server/data/scenarios -> 실제 경로는 project_root/data/scenarios
    candidates.append((_project_root / 'data' / 'scenarios').resolve())
    for c in candidates:
        if c.exists() and c.is_dir():
            return str(c)
    # 마지막 fallback (첫 후보 반환)
    return str(candidates[-1])

SCENARIO_DIR = _resolve_scenario_dir()
DEFAULT_SCENARIO_ID = os.getenv("SCENARIO_ID", "scenario1")

# per-call 상태
scenario_progress: Dict[str, int] = {}          # 진행 인덱스
call_scenario_id: Dict[str, str] = {}            # call_sid -> scenario_id 매핑
scenario_library: Dict[str, List[str]] = {}      # scenario_id -> assistant_lines

def load_scenario_library() -> Dict[str, List[str]]:
    lib: Dict[str, List[str]] = {}
    if os.path.isdir(SCENARIO_DIR):
        for fname in os.listdir(SCENARIO_DIR):
            if not fname.lower().endswith('.json'): continue
            path = os.path.join(SCENARIO_DIR, fname)
            scenario_id = os.path.splitext(fname)[0]
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get('assistant_lines'), list):
                    lines = [str(x) for x in data['assistant_lines'] if isinstance(x, (str, int, float))]
                    if lines:
                        lib[scenario_id] = lines
                        logger.info(f"시나리오 로드: {scenario_id} ({len(lines)} lines)")
            except Exception as e:
                logger.warning(f"시나리오 파일 파싱 실패: {path} error={e}")
    else:
        logger.info(f"시나리오 디렉토리 없음: {SCENARIO_DIR} (내장 기본만 사용)")
    logger.info(f"시나리오 디렉토리 최종 경로: {SCENARIO_DIR}")
    # fallback: scenario1이 아예 없으면 임시 기본 생성
    if 'scenario1' not in lib:
        logger.warning("scenario1.json 을 찾지 못해 임시 기본 시나리오 사용")
        lib['scenario1'] = [
            "안녕하세요, 구룡포낚시프라자 맞으시죠? 내일 새벽 5시에 갯바위 원투 낚시 장비 대여 가능한지 확인해보고 싶습니다.",
            "4명인데, 초보자 2명, 경험자 2명이십니다.",
            "네, 청갯지렁이 2개랑 크릴 새우 2개로 준비 부탁드립니다. 가격은 얼마인가요?",
            "네, 알겠습니다. 확인해보고 다시 연락드리겠습니다. 좋은 하루 되세요. 감사합니다."
        ]
    logger.info(f"총 시나리오 수: {len(lib)} (ids={list(lib.keys())})")
    return lib

scenario_library = load_scenario_library()

def in_scenario() -> bool:
    return SCENARIO_MODE and len(scenario_library) > 0

def assign_scenario_for_call(call_sid: str, requested_id: Optional[str]) -> str:
    chosen = requested_id or DEFAULT_SCENARIO_ID
    if chosen not in scenario_library:
        logger.warning(f"요청된 시나리오 {chosen} 가 라이브러리에 없음. 기본 scenario1 사용")
        chosen = "scenario1"
    call_scenario_id[call_sid] = chosen
    scenario_progress[call_sid] = 0
    logger.info(f"통화 {call_sid} 시나리오 할당: {chosen}")
    return chosen

def get_current_line(call_sid: str) -> Tuple[Optional[str], int, int]:
    sid = call_scenario_id.get(call_sid)
    if not sid: return (None, 0, 0)
    lines = scenario_library.get(sid, [])
    idx = scenario_progress.get(call_sid, 0)
    if idx < len(lines):
        return (lines[idx], idx, len(lines))
    return (None, idx, len(lines))

def advance_scenario(call_sid: str):
    scenario_progress[call_sid] = scenario_progress.get(call_sid, 0) + 1

async def emit_scenario_progress(call_sid: str):
    """시나리오 진행 상황을 클라이언트에 브로드캐스트"""
    if call_sid not in call_scenario_id:
        return
    sid = call_scenario_id[call_sid]
    lines = scenario_library.get(sid, [])
    idx = scenario_progress.get(call_sid, 0)  # 이미 advance 된 상태 (소비한 개수)
    total = len(lines)
    await sio.emit('scenario_progress', {
        'call_sid': call_sid,
        'scenario_id': sid,
        'consumed': idx,          # 소비된(보낸) assistant 라인 수
        'total': total,
        'is_complete': idx >= total
    })

############################
# 기존 함수 in_scenario 재정의 완료
############################


class CallRequest(BaseModel):
    # 선택적으로 번호를 받되, 없으면 KO_PHONENUMBER -> US_PHONENUMBER 순으로 fallback
    to_number: Optional[str] = Field(None, description="전화를 받을 상대방 번호 (E.164 형식, 없으면 환경변수 KO_PHONENUMBER 사용)")
    scenario_id: Optional[str] = Field(None, description="선택 실행할 시나리오 ID (scenario2, scenario3 등). SCENARIO_MODE=true 일 때만 적용")

class CallResponse(BaseModel):
    status: str
    call_sid: Optional[str] = None
    message: str


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
        # 시나리오 모드면 시나리오 할당 (call_scenario_id, scenario_progress)
        if in_scenario():
            assign_scenario_for_call(call.sid, req.scenario_id)

        return CallResponse(status="success", call_sid=call.sid, message="전화 연결이 시작되었습니다.")
    except TwilioRestException as e:
        logger.error(f"Twilio API 오류 code={getattr(e, 'code', None)} msg={getattr(e, 'msg', str(e))}")
        detail = getattr(e, 'msg', str(e))
        raise HTTPException(status_code=400, detail=f"Twilio 오류: {detail}")
    except Exception as e:
        logger.error(f"통화 시작 중 예상치 못한 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")


@app.post("/voice/start")
async def handle_voice_start(request: Request):
    """통화 시작 시 초기 메시지를 재생하고 사용자 입력을 받습니다."""
    form = await request.form()
    call_sid = form.get('CallSid')
    logger.info(f"통화 시작됨 (SID: {call_sid})")
    
    # 시나리오 모드면 진행 인덱스 0의 라인을 greeting 으로 사용
    if in_scenario() and call_sid and call_sid in call_scenario_id:
        line, idx, total = get_current_line(call_sid)
        greeting = line or "안녕하세요! 무엇을 도와드릴까요?"
        # 0번 라인 소비
        advance_scenario(call_sid)
        if call_sid:
            # 진행률 이벤트 전송 (greeting 포함 1개 소비 후 상태)
            await emit_scenario_progress(call_sid)
            # 만약 시나리오가 단 한 줄로 구성되어 이미 완료되었다면 즉시 종료
            _, consumed_idx, total_lines = get_current_line(call_sid)
            # get_current_line 은 아직 남은 라인 반환. 종료 판단은 scenario_progress 사용
            if scenario_progress.get(call_sid, 0) >= total_lines:
                # 바로 종료 (Hangup)
                response.say(greeting, voice='Polly.Seoyeon', language='ko-KR')
                response.hangup()
                await sio.emit('ai_response_complete', { 'text': greeting, 'call_sid': call_sid })
                return Response(content=str(response), media_type="application/xml")
    else:
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
async def process_speech(request: Request):
    """사용자 음성 입력을 처리하고 LLM 응답을 생성하여 반환합니다."""
    form = await request.form()
    call_sid = form.get('CallSid')
    user_speech = form.get('SpeechResult')
    
    logger.info(f"음성 수신 (SID: {call_sid}): {user_speech}")

    response = VoiceResponse()

    if user_speech:
        # 프론트엔드로 사용자 발화 전송 (call_sid 포함)
        await sio.emit('user_speech', {'text': user_speech, 'call_sid': call_sid})

        # 대화 기록에 사용자 발화 추가
        if call_sid in conversation_history:
            conversation_history[call_sid].append({"role": "user", "content": user_speech})
        else:
            # 만약을 대비한 초기화
            conversation_history[call_sid] = [{"role": "system", "content": "당신은 친절한 AI 전화 상담원입니다. 한국어로 간결하고 명확하게 답변해주세요."},
                                              {"role": "user", "content": user_speech}]

        
        try:
            # --- 시나리오 모드 처리: OpenAI 호출 전에 조기 분기 ---
            if in_scenario() and call_sid in call_scenario_id:
                line, idx, total = get_current_line(call_sid)
                if line is not None:  # 아직 남은 라인 있음
                    logger.info(f"시나리오 assistant 응답 (idx={idx}/{total}) (SID: {call_sid})")
                    # 스트리밍 UX 일관성을 위해 begin 이벤트 먼저 전송
                    await sio.emit('ai_response_begin', {'call_sid': call_sid})
                    conversation_history[call_sid].append({"role": "assistant", "content": line})
                    await sio.emit('ai_response_complete', {'text': line, 'call_sid': call_sid})
                    response.say(line, voice='Polly.Seoyeon', language='ko-KR')
                    advance_scenario(call_sid)
                    await emit_scenario_progress(call_sid)
                    # 모든 시나리오 라인을 소비했으면 Hangup 후 즉시 반환
                    if scenario_progress.get(call_sid, 0) >= total:
                        response.hangup()
                        return Response(content=str(response), media_type="application/xml")
                    raise StopIteration

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

            # 대화 기록 업데이트 (빈 응답이라도 실제 사용자에게 들린 문장 저장)
            conversation_history[call_sid].append({"role": "assistant", "content": final_text})

            # Twilio 음성 재생
            response.say(final_text, voice='Polly.Seoyeon', language='ko-KR')

            # 최종 응답 소켓 전송 (emit 시점을 Twilio say 이후로 이동해 UI와 음성 싱크 개선)
            await sio.emit('ai_response_complete', {'text': final_text, 'call_sid': call_sid})

        except StopIteration:
            # 시나리오 분기 정상 처리 - 아무 것도 하지 않고 다음 Gather 로 진행
            pass
        except Exception as e:
            logger.error(f"OpenAI/시나리오 처리 오류 (SID: {call_sid}): {e}", exc_info=True)
            error_text = "죄송합니다. 시스템에 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            await sio.emit('openai_error', {'error': str(e)})
            # 사용자에게 들리는 멘트를 UI에도 표시
            await sio.emit('ai_response_complete', {'text': error_text, 'call_sid': call_sid})
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
async def voice_status_callback(request: Request):
    """통화 상태 변경 시 호출되는 웹훅. 통화 종료 시 프론트엔드에 알림."""
    form = await request.form()
    call_sid = form.get('CallSid')
    call_status = form.get('CallStatus')
    error_code = form.get('ErrorCode')  # Twilio가 실패 사유 코드 제공 (https://www.twilio.com/docs/api/errors)
    to_number = form.get('To')
    from_number = form.get('From')

    
    logger.info(f"통화 상태 업데이트 (SID: {call_sid}) status={call_status} error_code={error_code} to={to_number} from={from_number}")
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
            if call_sid in scenario_progress:
                del scenario_progress[call_sid]
                logger.info(f"시나리오 진행 상태 삭제 (SID: {call_sid})")
            if call_sid in call_scenario_id:
                del call_scenario_id[call_sid]
                logger.info(f"시나리오 ID 매핑 삭제 (SID: {call_sid})")

    return Response(status_code=200)

# --- 기존의 복잡한 WebSocket 및 미디어 스트리밍 관련 코드는 모두 제거 ---

# Socket.IO 앱 마운트 (realtime_server.py에서 가져옴)
from src.realtime_server import socket_app
app.mount("/socket.io", socket_app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)