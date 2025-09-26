"""
Twilio Media Stream과 OpenAI Realtime API 간의 브릿지

Twilio로부터 수신한 Media Stream(WebSocket)을 처리하고, 
오디오 포맷을 변환하여 OpenAI Realtime API로 전달합니다.
"""

import asyncio
import json
import audioop
from base64 import b64decode, b64encode
from fastapi import WebSocket, WebSocketDisconnect

from src.config import logger
from src.openai_realtime import OpenAIRealtimeClient


class MediaBridge:
    """Twilio Media Stream을 OpenAI와 연결하는 브릿지 클래스"""

    def __init__(self, websocket: WebSocket):
        self.twilio_ws = websocket
        self.call_sid: str | None = None
        self.stream_sid: str | None = None
        self.openai_client: OpenAIRealtimeClient | None = None
        self.ratecv_state = None
        self.downsample_ratecv_state = None

    async def handle_connection(self):
        """Twilio WebSocket 연결을 수락하고 메시지 루프 시작"""
        await self.twilio_ws.accept()
        logger.info("Twilio Media Stream connected.")
        try:
            while True:
                message = await self.twilio_ws.receive_text()
                await self._process_message(message)
        except WebSocketDisconnect:
            logger.info("Twilio Media Stream disconnected.")
            if self.openai_client:
                await self.openai_client.close()

    async def _process_message(self, message: str):
        """Twilio로부터 받은 메시지를 파싱하고 처리"""
        data = json.loads(message)
        event = data.get("event")

        if event == "start":
            self.stream_sid = data["start"]["streamSid"]
            self.call_sid = data["start"]["callSid"]
            logger.info(f"Media stream {self.stream_sid} started for call: {self.call_sid}")
            self.openai_client = OpenAIRealtimeClient(self.call_sid, self._handle_tts_chunk)
            await self.openai_client.connect()

        elif event == "media":
            if self.openai_client:
                payload = data["media"]["payload"]
                audio_chunk_mulaw = b64decode(payload)
                
                # mulaw -> 16-bit linear PCM 변환
                audio_chunk_pcm_8k = audioop.ulaw2lin(audio_chunk_mulaw, 2)
                
                # OpenAI에 맞게 8kHz -> 16kHz로 업샘플링
                audio_chunk_pcm_16k, self.ratecv_state = audioop.ratecv(audio_chunk_pcm_8k, 2, 1, 8000, 16000, self.ratecv_state)

                await self.openai_client.send_audio(audio_chunk_pcm_16k)

        elif event == "stop":
            logger.info(f"Media stream stopped for call: {self.call_sid}")
            if self.openai_client:
                await self.openai_client.close()

    async def _handle_tts_chunk(self, pcm_24k_chunk: bytes):
        """OpenAI TTS 오디오 청크를 받아 처리하고 Twilio로 전송"""
        # 24kHz PCM -> 8kHz PCM로 다운샘플링
        pcm_8k_chunk, self.downsample_ratecv_state = audioop.ratecv(
            pcm_24k_chunk, 2, 1, 24000, 8000, self.downsample_ratecv_state
        )

        # 16-bit linear PCM -> 8-bit mulaw 변환
        mulaw_chunk = audioop.lin2ulaw(pcm_8k_chunk, 2)

        # Base64 인코딩
        payload = b64encode(mulaw_chunk).decode("utf-8")

        # Twilio로 전송할 media 메시지 생성
        message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": payload
            }
        }

        # WebSocket을 통해 Twilio로 메시지 전송
        await self.twilio_ws.send_text(json.dumps(message))


async def twilio_media_stream_handler(websocket: WebSocket):
    """FastAPI WebSocket 엔드포인트 핸들러"""
    bridge = MediaBridge(websocket)
    await bridge.handle_connection()