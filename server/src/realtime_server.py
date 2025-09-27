"""
WebSocket 기반 실시간 통신 서버
FastAPI와 python-socketio를 사용하여 WebSocket 연결을 관리하고,
실시간으로 클라이언트와 데이터를 주고받습니다.
"""

import socketio
from fastapi import FastAPI
from typing import Dict, Any, Optional

from src.config import settings, logger
from src.openai_realtime import OpenAIRealtimeClient, RealtimeCallbacks

# Socket.IO 비동기 서버 인스턴스 생성
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins_list,
    logger=True,
    engineio_logger=True,
)

# FastAPI 앱에 Socket.IO 연동
socket_app = socketio.ASGIApp(
    socketio_server=sio,
    socketio_path="socket.io"
)

# OpenAI Realtime 클라이언트 인스턴스 (전역)
openai_client: Optional[OpenAIRealtimeClient] = None
is_call_active = False

@sio.event
async def connect(sid: str, environ: Dict[str, Any]):
    """클라이언트 연결 시 호출되는 이벤트 핸들러"""
    logger.info(f"Socket.IO client connected: sid={sid}")
    await sio.emit('message', {'data': f'Welcome client {sid}'}, room=sid)

@sio.event
async def disconnect(sid: str):
    """클라이언트 연결 종료 시 호출되는 이벤트 핸들러"""
    logger.info(f"Socket.IO client disconnected: sid={sid}")

async def broadcast_call_status(status: str, call_sid: str, message: str):
    """통화 상태를 모든 클라이언트에게 브로드캐스트"""
    logger.debug(f"Broadcasting call status: {status} for call_sid: {call_sid}")
    await sio.emit('call_status', {
        'status': status,
        'call_sid': call_sid,
        'message': message
    })

async def broadcast_transcription(transcription: str, is_final: bool):
    """실시간 전사 결과를 브로드캐스트"""
    await sio.emit('transcription_update', {
        'transcription': transcription,
        'is_final': is_final
    })

async def broadcast_ai_response_chunk(chunk: str):
    """AI 응답의 일부(chunk)를 스트리밍"""
    await sio.emit('ai_response_chunk', {'chunk': chunk})

class SocketIOCallbacks:
    """Socket.IO를 통한 OpenAI Realtime API 콜백"""
    
    async def on_transcription(self, text: str, is_final: bool):
        """음성 인식 결과 처리"""
        logger.debug(f"Transcription: {text} (final: {is_final})")
        await sio.emit('transcription_update', {
            'text': text,
            'is_final': is_final
        })
    
    async def on_ai_response_text(self, text_delta: str):
        """AI 텍스트 응답 델타 처리"""
        logger.debug(f"AI text delta: {text_delta}")
        await sio.emit('ai_response_text', {'text_delta': text_delta})
    
    async def on_ai_response_audio(self, audio_data: bytes):
        """AI 오디오 응답 처리"""
        logger.debug(f"AI audio received: {len(audio_data)} bytes")
        await sio.emit('ai_response_audio', {'audio_length': len(audio_data)})
    
    async def on_ai_response_complete(self, full_text: str):
        """AI 응답 완료"""
        logger.info(f"AI response complete: {full_text}")
        await sio.emit('ai_response_complete', {'text': full_text})
    
    async def on_session_created(self, session_data: dict):
        """세션 생성 완료"""
        session_id = session_data.get('session', {}).get('id')
        logger.info(f"OpenAI session created: {session_id}")
        await sio.emit('session_created', {'session_id': session_id})
    
    async def on_error(self, error_msg: str):
        """오류 처리"""
        logger.error(f"OpenAI error: {error_msg}")
        await sio.emit('openai_error', {'error': error_msg})
    
    async def on_speech_started(self):
        """음성 입력 시작"""
        logger.debug("Speech started")
        await sio.emit('speech_started', {})
    
    async def on_speech_stopped(self):
        """음성 입력 종료"""
        logger.debug("Speech stopped")
        await sio.emit('speech_stopped', {})

async def create_openai_client():
    """OpenAI Realtime 클라이언트 생성"""
    global openai_client
    
    if openai_client is not None:
        logger.warning("OpenAI client already exists")
        return openai_client
    
    # 콜백 설정
    callbacks = SocketIOCallbacks()
    realtime_callbacks = RealtimeCallbacks(
        on_transcription=callbacks.on_transcription,
        on_ai_response_text=callbacks.on_ai_response_text,
        on_ai_response_audio=callbacks.on_ai_response_audio,
        on_ai_response_complete=callbacks.on_ai_response_complete,
        on_session_created=callbacks.on_session_created,
        on_error=callbacks.on_error,
        on_speech_started=callbacks.on_speech_started,
        on_speech_stopped=callbacks.on_speech_stopped,
    )
    
    # 클라이언트 생성
    openai_client = OpenAIRealtimeClient(
        api_key=settings.openai_api_key,
        callbacks=realtime_callbacks
    )
    
    logger.info("OpenAI Realtime client created")
    return openai_client

@sio.event
async def start_call(sid: str):
    """통화 시작 이벤트 핸들러"""
    global is_call_active, openai_client
    
    try:
        if is_call_active:
            await sio.emit('call_error', {'error': 'Call already active'}, room=sid)
            return
        
        logger.info(f"Starting call for client {sid}")
        
        # OpenAI 클라이언트 생성 및 연결
        openai_client = await create_openai_client()
        connected = await openai_client.connect()
        
        if not connected:
            await sio.emit('call_error', {'error': 'Failed to connect to OpenAI'}, room=sid)
            return
        
        is_call_active = True
        logger.info("Call started successfully")
        
        # 클라이언트에게 성공 알림
        await sio.emit('call_started', {
            'status': 'connected',
            'message': 'OpenAI Realtime API connected'
        }, room=sid)
        
    except Exception as e:
        logger.error(f"Error starting call: {e}")
        await sio.emit('call_error', {'error': str(e)}, room=sid)

@sio.event
async def stop_call(sid: str):
    """통화 종료 이벤트 핸들러"""
    global is_call_active, openai_client
    
    try:
        if not is_call_active:
            await sio.emit('call_error', {'error': 'No active call'}, room=sid)
            return
        
        logger.info(f"Stopping call for client {sid}")
        
        # OpenAI 연결 종료
        if openai_client:
            await openai_client.disconnect()
            openai_client = None
        
        is_call_active = False
        logger.info("Call stopped successfully")
        
        # 클라이언트에게 종료 알림
        await sio.emit('call_stopped', {
            'status': 'disconnected',
            'message': 'Call ended'
        }, room=sid)
        
    except Exception as e:
        logger.error(f"Error stopping call: {e}")
        await sio.emit('call_error', {'error': str(e)}, room=sid)

@sio.event
async def send_audio(sid: str, data: dict):
    """오디오 데이터 전송 이벤트 핸들러"""
    global openai_client
    
    try:
        if not is_call_active or not openai_client:
            await sio.emit('call_error', {'error': 'No active call'}, room=sid)
            return
        
        audio_data = data.get('audio_data')
        if audio_data:
            # Base64 디코딩 후 OpenAI로 전송
            import base64
            audio_bytes = base64.b64decode(audio_data)
            await openai_client.send_audio_data(audio_bytes)
            logger.debug(f"Audio data sent: {len(audio_bytes)} bytes")
        
    except Exception as e:
        logger.error(f"Error sending audio: {e}")
        await sio.emit('call_error', {'error': str(e)}, room=sid)

@sio.event
async def send_text(sid: str, data: dict):
    """텍스트 메시지 전송 이벤트 핸들러"""
    global openai_client
    
    try:
        if not is_call_active or not openai_client:
            await sio.emit('call_error', {'error': 'No active call'}, room=sid)
            return
        
        text = data.get('text')
        if text:
            await openai_client.send_text_message(text)
            logger.debug(f"Text message sent: {text}")
        
    except Exception as e:
        logger.error(f"Error sending text: {e}")
        await sio.emit('call_error', {'error': str(e)}, room=sid)

