"""
WebSocket 기반 실시간 통신 서버
FastAPI와 python-socketio를 사용하여 WebSocket 연결을 관리하고,
실시간으로 클라이언트와 데이터를 주고받습니다.
"""

import socketio
from fastapi import FastAPI
from typing import Dict, Any

from src.config import settings, logger

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
