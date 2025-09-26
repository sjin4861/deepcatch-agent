"""
OpenAI Realtime API 클라이언트

OpenAI의 실시간 음성-텍스트-음성 변환 API와 WebSocket을 통해 통신하고,
오디오 스트림을 전송하며, 실시간으로 결과를 수신합니다.
"""

import asyncio
import aiohttp
import json
from base64 import b64decode

from typing import Callable, Awaitable

from src.config import settings, logger
from src.realtime_server import broadcast_transcription, broadcast_ai_response_chunk

class OpenAIRealtimeClient:
    """OpenAI Realtime API와의 WebSocket 통신을 관리하는 클라이언트"""

    BASE_URL = "wss://api.openai.com/v1/audio/realtime/transcribe/stream"

    def __init__(self, call_sid: str, on_tts_chunk: Callable[[bytes], Awaitable[None]]):
        self.call_sid = call_sid
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._receiver_task: asyncio.Task | None = None
        self._on_tts_chunk = on_tts_chunk

    async def connect(self):
        """OpenAI Realtime API에 WebSocket 연결"""
        try:
            self._session = aiohttp.ClientSession()
            url = self._get_connection_url()
            logger.info(f"Connecting to OpenAI Realtime API at {url}")
            
            self._ws = await self._session.ws_connect(url)
            self._receiver_task = asyncio.create_task(self._receiver())
            
            logger.info("Successfully connected to OpenAI Realtime API.")

        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            await self.close()
            raise

    async def send_audio(self, audio_chunk: bytes):
        """오디오 청크를 WebSocket을 통해 전송"""
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_bytes(audio_chunk)
            except Exception as e:
                logger.error(f"Error sending audio to OpenAI: {e}")
        else:
            logger.warning("WebSocket is not connected. Cannot send audio.")

    async def _receiver(self):
        """WebSocket으로부터 메시지를 수신하고 처리"""
        while self._ws and not self._ws.closed:
            try:
                message = await self._ws.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(json.loads(message.data))
                elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
            except Exception as e:
                logger.error(f"Error receiving message from OpenAI: {e}")
                break
        logger.info("OpenAI receiver task finished.")

    async def _handle_message(self, data: dict):
        """수신된 메시지 유형에 따라 처리"""
        msg_type = data.get("message")

        if msg_type == "transcription":
            transcription = data.get("text", "")
            is_final = data.get("final", False)
            logger.debug(f"Transcription received: '{transcription}' (final: {is_final})")
            await broadcast_transcription(transcription, is_final)
        
        elif msg_type == "speech_synthesis_chunk":
            audio_chunk_b64 = data.get("audio")
            if audio_chunk_b64:
                audio_chunk = b64decode(audio_chunk_b64)
                await self._on_tts_chunk(audio_chunk)

        elif msg_type == "text_chunk":
            # AI 응답 텍스트 청크 처리
            text_chunk = data.get("text", "")
            logger.debug(f"AI response chunk: '{text_chunk}'")
            await broadcast_ai_response_chunk(text_chunk)

        elif msg_type == "error":
            logger.error(f"OpenAI API Error: {data.get('error')}")

    def _get_connection_url(self) -> str:
        """API 연결을 위한 URL 생성"""
        params = {
            "model": settings.openai_realtime_model,
            "voice": settings.openai_realtime_voice,
            "temperature": settings.openai_realtime_temperature,
            "encoding": "pcm_s16le",
            "sample_rate": 16000, # mulaw에서 변환 후 샘플 레이트
            "language": "ko",
            "api_key": settings.openai_api_key
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.BASE_URL}?{query_string}"

    async def close(self):
        """WebSocket 연결 종료"""
        if self._receiver_task:
            self._receiver_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("OpenAI Realtime client closed.")
