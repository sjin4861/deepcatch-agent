"""
OpenAI Realtime API 통합 모듈

이 모듈은 OpenAI의 실시간 API를 사용하여 양방향 음성 대화를 처리합니다.
음성 인식(STT), AI 추론, 음성 합성(TTS)을 실시간으로 수행합니다.
"""

import asyncio
import json
import base64
import websockets
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from enum import Enum
import numpy as np

from src.config import settings, logger

class SessionEventType(str, Enum):
    """OpenAI Realtime API 세션 이벤트 타입"""
    # Client events
    SESSION_UPDATE = "session.update"
    INPUT_AUDIO_BUFFER_APPEND = "input_audio_buffer.append"
    INPUT_AUDIO_BUFFER_COMMIT = "input_audio_buffer.commit"
    INPUT_AUDIO_BUFFER_CLEAR = "input_audio_buffer.clear"
    CONVERSATION_ITEM_CREATE = "conversation.item.create"
    CONVERSATION_ITEM_DELETE = "conversation.item.delete"
    RESPONSE_CREATE = "response.create"
    RESPONSE_CANCEL = "response.cancel"
    
    # Server events
    ERROR = "error"
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    CONVERSATION_ITEM_CREATED = "conversation.item.created"
    CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
    CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_FAILED = "conversation.item.input_audio_transcription.failed"
    RESPONSE_CREATED = "response.created"
    RESPONSE_DONE = "response.done"
    RESPONSE_OUTPUT_ITEM_ADDED = "response.output_item.added"
    RESPONSE_OUTPUT_ITEM_DONE = "response.output_item.done"
    RESPONSE_CONTENT_PART_ADDED = "response.content_part.added"
    RESPONSE_CONTENT_PART_DONE = "response.content_part.done"
    RESPONSE_TEXT_DELTA = "response.text.delta"
    RESPONSE_TEXT_DONE = "response.text.done"
    RESPONSE_AUDIO_TRANSCRIPT_DELTA = "response.audio_transcript.delta"
    RESPONSE_AUDIO_TRANSCRIPT_DONE = "response.audio_transcript.done"
    RESPONSE_AUDIO_DELTA = "response.audio.delta"
    RESPONSE_AUDIO_DONE = "response.audio.done"
    RESPONSE_FUNCTION_CALL_ARGUMENTS_DELTA = "response.function_call_arguments.delta"
    RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE = "response.function_call_arguments.done"
    INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
    INPUT_AUDIO_BUFFER_CLEARED = "input_audio_buffer.cleared"
    INPUT_AUDIO_BUFFER_SPEECH_STARTED = "input_audio_buffer.speech_started"
    INPUT_AUDIO_BUFFER_SPEECH_STOPPED = "input_audio_buffer.speech_stopped"

@dataclass
class RealtimeCallbacks:
    """OpenAI Realtime API 콜백 함수들"""
    on_transcription: Optional[Callable[[str, bool], None]] = None  # (text, is_final)
    on_ai_response_text: Optional[Callable[[str], None]] = None  # (text_delta)
    on_ai_response_audio: Optional[Callable[[bytes], None]] = None  # (audio_data)
    on_ai_response_complete: Optional[Callable[[str], None]] = None  # (full_text)
    on_session_created: Optional[Callable[[Dict], None]] = None  # (session_data)
    on_error: Optional[Callable[[str], None]] = None  # (error_message)
    on_speech_started: Optional[Callable[[], None]] = None
    on_speech_stopped: Optional[Callable[[], None]] = None

class OpenAIRealtimeClient:
    """OpenAI Realtime API 클라이언트"""
    
    # OpenAI Realtime API URL
    REALTIME_API_URL = "wss://api.openai.com/v1/realtime"
    
    def __init__(self, api_key: str, callbacks: RealtimeCallbacks):
        """
        OpenAI Realtime 클라이언트 초기화
        
        Args:
            api_key: OpenAI API 키
            callbacks: 이벤트 콜백 함수들
        """
        self.api_key = api_key
        self.callbacks = callbacks
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.session_id: Optional[str] = None
        self.is_connected = False
        self.conversation_items: List[Dict] = []
        
        # 설정값들
        self.model = settings.openai_realtime_model
        self.voice = settings.openai_realtime_voice
        self.temperature = settings.openai_realtime_temperature
        
        # 오디오 버퍼 관리
        self.audio_buffer_size = settings.audio_buffer_size
        self.accumulated_audio = bytearray()
        
        logger.info(f"OpenAI Realtime 클라이언트 초기화 - 모델: {self.model}, 음성: {self.voice}")
    
    async def connect(self) -> bool:
        """OpenAI Realtime API에 연결"""
        try:
            # WebSocket 연결 설정
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            url = f"{self.REALTIME_API_URL}?model={self.model}"
            
            logger.debug(f"OpenAI Realtime API 연결 시도: {url}")
            
            self.websocket = await websockets.connect(
                url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            self.is_connected = True
            logger.info("OpenAI Realtime API 연결 성공")
            
            # 세션 업데이트 요청
            await self._send_session_update()
            
            # 메시지 수신 루프 시작
            asyncio.create_task(self._message_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"OpenAI Realtime API 연결 실패: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """연결 해제"""
        if self.websocket:
            try:
                # websockets 13.0+ 에서는 close() 호출 전 상태 확인 불필요
                await self.websocket.close()
            except Exception as e:
                logger.debug(f"웹소켓 닫기 중 오류 (무시): {e}")
        self.is_connected = False
        logger.info("OpenAI Realtime API 연결 해제")
    
    async def _send_session_update(self):
        """세션 설정 업데이트"""
        session_config = {
            "type": SessionEventType.SESSION_UPDATE,
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self._get_system_instructions(),
                "voice": self.voice,
                "input_audio_format": {
                    "type": "pcm",
                    "encoding": "s16le",
                    "sample_rate": 8000,
                    "channels": 1
                },
                "output_audio_format": {
                    "type": "pcm",
                    "encoding": "s16le",
                    "sample_rate": 24000,
                    "channels": 1
                },
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                },
                "tools": [],
                "tool_choice": "auto",
                "temperature": self.temperature,
                "max_response_output_tokens": 4096
            }
        }
        
        await self._send_message(session_config)
        logger.debug("세션 설정 업데이트 전송")
    
    def _get_system_instructions(self) -> str:
        """시스템 지시사항 반환"""
        return """당신은 한국의 낚시집 예약을 도와주는 AI 어시스턴트입니다.

역할:
- 고객의 낚시 예약 요청을 받아 낚시집 업체와 전화로 예약을 진행합니다.
- 정중하고 친근한 톤으로 대화합니다.
- 필요한 정보를 명확하게 확인합니다.

주요 확인 사항:
1. 예약 날짜와 시간
2. 인원수
3. 낚시 종류 (바다낚시, 민물낚시 등)
4. 가격 및 포함 사항
5. 대안 날짜 (원하는 날짜가 불가능한 경우)

대화 방식:
- 한국어로 자연스럽게 대화합니다.
- 상대방의 답변을 잘 듣고 적절히 반응합니다.
- 예약이 어려운 경우 대안을 제시합니다.
- 통화를 정중하게 마무리합니다."""
    
    async def send_audio_data(self, audio_data: bytes):
        """오디오 데이터 전송 (PCM16 형식)"""
        if not self.is_connected or not self.websocket:
            logger.warning("연결되지 않은 상태에서 오디오 전송 시도")
            return
        
        try:
            # 오디오 데이터를 base64로 인코딩
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            message = {
                "type": SessionEventType.INPUT_AUDIO_BUFFER_APPEND,
                "audio": audio_base64
            }
            
            await self._send_message(message)
            
        except Exception as e:
            logger.error(f"오디오 데이터 전송 실패: {e}")
    
    async def commit_audio_buffer(self):
        """오디오 버퍼 커밋 (음성 인식 시작)"""
        if not self.is_connected:
            return
        
        message = {
            "type": SessionEventType.INPUT_AUDIO_BUFFER_COMMIT
        }
        
        await self._send_message(message)
        logger.debug("오디오 버퍼 커밋")
    
    async def clear_audio_buffer(self):
        """오디오 버퍼 클리어"""
        if not self.is_connected:
            return
        
        message = {
            "type": SessionEventType.INPUT_AUDIO_BUFFER_CLEAR
        }
        
        await self._send_message(message)
        logger.debug("오디오 버퍼 클리어")
    
    async def send_text_message(self, text: str):
        """텍스트 메시지 전송"""
        if not self.is_connected:
            return
        
        item = {
            "type": SessionEventType.CONVERSATION_ITEM_CREATE,
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text
                    }
                ]
            }
        }
        
        await self._send_message(item)
        
        # 응답 생성 요청
        response_request = {
            "type": SessionEventType.RESPONSE_CREATE
        }
        
        await self._send_message(response_request)
        logger.debug(f"텍스트 메시지 전송: {text}")
    
    async def _send_message(self, message: Dict[str, Any]):
        """WebSocket으로 메시지 전송"""
        if not self.websocket or not self.is_connected:
            logger.warning("WebSocket이 연결되지 않아 메시지 전송 불가")
            return
        
        try:
            await self.websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
            self.is_connected = False
    
    async def _message_loop(self):
        """메시지 수신 루프"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 파싱 오류: {e}")
                except Exception as e:
                    logger.error(f"메시지 처리 오류: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("OpenAI Realtime API 연결이 종료됨")
        except Exception as e:
            logger.error(f"메시지 루프 오류: {e}")
        finally:
            self.is_connected = False
    
    async def _handle_message(self, data: Dict[str, Any]):
        """수신된 메시지 처리"""
        event_type = data.get("type")
        
        if event_type == SessionEventType.SESSION_CREATED:
            self.session_id = data.get("session", {}).get("id")
            logger.info(f"세션 생성됨: {self.session_id}")
            if self.callbacks.on_session_created:
                await self.callbacks.on_session_created(data)
        
        elif event_type == SessionEventType.SESSION_UPDATED:
            logger.debug("세션 업데이트됨")
        
        elif event_type == SessionEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            logger.debug("음성 입력 시작")
            if self.callbacks.on_speech_started:
                await self.callbacks.on_speech_started()
        
        elif event_type == SessionEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            logger.debug("음성 입력 종료")
            if self.callbacks.on_speech_stopped:
                await self.callbacks.on_speech_stopped()
        
        elif event_type == SessionEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            # 음성 인식 완료
            transcript = data.get("transcript", "")
            logger.debug(f"음성 인식 완료: {transcript}")
            if self.callbacks.on_transcription:
                await self.callbacks.on_transcription(transcript, True)
        
        elif event_type == SessionEventType.RESPONSE_TEXT_DELTA:
            # AI 응답 텍스트 스트리밍
            text_delta = data.get("delta", "")
            if self.callbacks.on_ai_response_text:
                await self.callbacks.on_ai_response_text(text_delta)
        
        elif event_type == SessionEventType.RESPONSE_TEXT_DONE:
            # AI 응답 텍스트 완료
            text = data.get("text", "")
            logger.debug(f"AI 텍스트 응답 완료: {text}")
            if self.callbacks.on_ai_response_complete:
                await self.callbacks.on_ai_response_complete(text)
        
        elif event_type == SessionEventType.RESPONSE_AUDIO_DELTA:
            # AI 응답 오디오 스트리밍
            audio_delta = data.get("delta")
            if audio_delta and self.callbacks.on_ai_response_audio:
                try:
                    audio_bytes = base64.b64decode(audio_delta)
                    await self.callbacks.on_ai_response_audio(audio_bytes)
                except Exception as e:
                    logger.error(f"오디오 델타 처리 오류: {e}")
        
        elif event_type == SessionEventType.RESPONSE_AUDIO_DONE:
            logger.debug("AI 오디오 응답 완료")
        
        elif event_type == SessionEventType.ERROR:
            error_msg = data.get("error", {}).get("message", "알 수 없는 오류")
            logger.error(f"OpenAI Realtime API 오류: {error_msg}")
            if self.callbacks.on_error:
                await self.callbacks.on_error(error_msg)
        
        else:
            logger.debug(f"처리되지 않은 이벤트: {event_type}")

# 유틸리티 함수들
def convert_mulaw_to_pcm16(mulaw_data: bytes) -> bytes:
    """μ-law 오디오를 PCM16으로 변환"""
    try:
        # μ-law 디코딩 테이블
        mulaw_table = np.array([
            -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
            -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
            -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
            -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
            -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
            -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
            -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
            -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
            -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
            -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
            -876, -844, -812, -780, -748, -716, -684, -652,
            -620, -588, -556, -524, -492, -460, -428, -396,
            -372, -356, -340, -324, -308, -292, -276, -260,
            -244, -228, -212, -196, -180, -164, -148, -132,
            -120, -112, -104, -96, -88, -80, -72, -64,
            -56, -48, -40, -32, -24, -16, -8, 0,
            32124, 31100, 30076, 29052, 28028, 27004, 25980, 24956,
            23932, 22908, 21884, 20860, 19836, 18812, 17788, 16764,
            15996, 15484, 14972, 14460, 13948, 13436, 12924, 12412,
            11900, 11388, 10876, 10364, 9852, 9340, 8828, 8316,
            7932, 7676, 7420, 7164, 6908, 6652, 6396, 6140,
            5884, 5628, 5372, 5116, 4860, 4604, 4348, 4092,
            3900, 3772, 3644, 3516, 3388, 3260, 3132, 3004,
            2876, 2748, 2620, 2492, 2364, 2236, 2108, 1980,
            1884, 1820, 1756, 1692, 1628, 1564, 1500, 1436,
            1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
            -876, -844, -812, -780, -748, -716, -684, -652,
            -620, -588, -556, -524, -492, -460, -428, -396,
            -372, -356, -340, -324, -308, -292, -276, -260,
            -244, -228, -212, -196, -180, -164, -148, -132,
            -120, -112, -104, -96, -88, -80, -72, -64,
            -56, -48, -40, -32, -24, -16, -8, 0
        ], dtype=np.int16)
        
        # μ-law 바이트를 인덱스로 사용하여 PCM16 값 조회
        mulaw_array = np.frombuffer(mulaw_data, dtype=np.uint8)
        pcm16_array = mulaw_table[mulaw_array]
        
        return pcm16_array.tobytes()
        
    except Exception as e:
        logger.error(f"μ-law to PCM16 변환 오류: {e}")
        return b''

def convert_pcm16_to_mulaw(pcm16_data: bytes) -> bytes:
    """PCM16 오디오를 μ-law로 변환"""
    try:
        # PCM16 데이터를 numpy 배열로 변환
        pcm16_array = np.frombuffer(pcm16_data, dtype=np.int16)
        
        # μ-law 인코딩
        # 부호 비트 추출
        sign = (pcm16_array < 0).astype(np.uint8)
        
        # 절댓값 계산
        abs_pcm = np.abs(pcm16_array.astype(np.int32))
        
        # 압축된 값 계산
        compressed = np.zeros_like(abs_pcm, dtype=np.uint8)
        
        # 각 샘플에 대해 μ-law 인코딩 수행
        for i, val in enumerate(abs_pcm):
            val = min(val, 32767)  # 클리핑
            val += 132  # 바이어스 추가
            
            if val >= 16384:
                compressed[i] = 0x70 | ((val >> 10) & 0x0F)
            elif val >= 8192:
                compressed[i] = 0x60 | ((val >> 9) & 0x0F)
            elif val >= 4096:
                compressed[i] = 0x50 | ((val >> 8) & 0x0F)
            elif val >= 2048:
                compressed[i] = 0x40 | ((val >> 7) & 0x0F)
            elif val >= 1024:
                compressed[i] = 0x30 | ((val >> 6) & 0x0F)
            elif val >= 512:
                compressed[i] = 0x20 | ((val >> 5) & 0x0F)
            elif val >= 256:
                compressed[i] = 0x10 | ((val >> 4) & 0x0F)
            else:
                compressed[i] = (val >> 4) & 0x0F
        
        # 부호 비트 적용
        mulaw = compressed ^ (sign << 7) ^ 0x55
        
        return mulaw.tobytes()
        
    except Exception as e:
        logger.error(f"PCM16 to μ-law 변환 오류: {e}")
        return b''

def resample_pcm16(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    """PCM16 오디오 데이터 리샘플링"""
    if from_rate == to_rate:
        return audio_data
    
    try:
        from_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # 리샘플링 비율 계산
        resample_ratio = to_rate / from_rate
        
        # 새 배열 길이 계산
        to_length = int(len(from_array) * resample_ratio)
        
        # 새 인덱스 생성
        to_indices = np.linspace(0, len(from_array) - 1, to_length)
        
        # 선형 보간을 사용하여 리샘플링
        resampled_array = np.interp(to_indices, np.arange(len(from_array)), from_array).astype(np.int16)
        
        return resampled_array.tobytes()
        
    except Exception as e:
        logger.error(f"오디오 리샘플링 오류 ({from_rate}Hz -> {to_rate}Hz): {e}")
        return b''