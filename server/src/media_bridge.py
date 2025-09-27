"""
Twilio Media Streams와 OpenAI Realtime API를 연결하는 브릿지 모듈

이 모듈은 Twilio에서 실시간으로 수신되는 오디오 데이터를 OpenAI Realtime API로 전송하고,
OpenAI에서 생성된 응답 오디오를 다시 Twilio로 전송하는 양방향 브릿지 역할을 합니다.
"""

import asyncio
import json
import base64
import websockets
from typing import Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
import weakref

from src.config import settings, logger
from src.openai_realtime import OpenAIRealtimeClient, RealtimeCallbacks, convert_mulaw_to_pcm16, convert_pcm16_to_mulaw, resample_pcm16
from src.realtime_server import broadcast_transcription, broadcast_ai_response_chunk, broadcast_call_status

class TwilioMediaStreamHandler:
    """Twilio Media Stream과 OpenAI Realtime API를 연결하는 핸들러"""
    
    def __init__(self):
        """핸들러 초기화"""
        self.active_connections: Dict[str, Dict[str, Any]] = {}
        self.openai_clients: Dict[str, OpenAIRealtimeClient] = {}
        
        # 오디오 버퍼 설정
        self.audio_chunk_size = settings.audio_chunk_size
        self.sample_rate = settings.twilio_sample_rate
        
        logger.info("Twilio Media Stream 핸들러 초기화 완료")

    
    async def handle_media_stream(self, websocket: WebSocket, call_sid: str):
        """
        Twilio Media Stream WebSocket 연결 처리
        
        Args:
            websocket: Twilio에서 연결된 WebSocket
            call_sid: 통화 ID
        """
        
        logger.info(f"Media Stream 연결 시작: {call_sid}")
        
        try:
            # WebSocket 연결 수락
            await websocket.accept()
            logger.info(f"WebSocket 연결 수락 완료: {call_sid}")
            
            # call_sid가 "pending"인 경우 첫 번째 메시지에서 실제 call_sid 추출
            if call_sid == "pending":
                logger.info("call_sid가 pending 상태, 첫 번째 메시지에서 call_sid 추출 시도...")
                first_message = await websocket.receive_text()
                logger.info(f"첫 번째 메시지 수신: {first_message}")
                
                try:
                    import json
                    message_data = json.loads(first_message)
                    logger.info(f"첫 번째 메시지 전체 내용: {message_data}")
                    
                    # Twilio Media Stream에서 가능한 모든 call_sid 필드들 확인
                    possible_fields = ['call_sid', 'callSid', 'call-sid', 'CallSid', 'streamSid', 'stream_sid']
                    actual_call_sid = None
                    
                    for field in possible_fields:
                        if field in message_data:
                            actual_call_sid = message_data[field]
                            logger.info(f"call_sid를 {field} 필드에서 발견: {actual_call_sid}")
                            break
                    
                    if actual_call_sid:
                        call_sid = actual_call_sid
                        logger.info(f"첫 번째 메시지에서 call_sid 추출 성공: {actual_call_sid}")
                    else:
                        logger.error(f"첫 번째 메시지에서 call_sid를 찾을 수 없음")
                        logger.error(f"사용 가능한 필드들: {list(message_data.keys())}")
                        
                        # twilio_call_sessions에서 활성 세션 찾기
                        from src.main import twilio_call_sessions
                        if len(twilio_call_sessions) == 1:
                            # 활성 세션이 하나뿐이면 그것을 사용
                            actual_call_sid = list(twilio_call_sessions.keys())[0]
                            call_sid = actual_call_sid
                            logger.info(f"활성 세션에서 call_sid 추출: {actual_call_sid}")
                        else:
                            # 임시로 타임스탬프 기반 call_sid 생성
                            import time
                            call_sid = f"unknown_{int(time.time())}"
                            logger.warning(f"임시 call_sid 생성: {call_sid}")
                            
                except json.JSONDecodeError:
                    logger.error(f"첫 번째 메시지 JSON 파싱 실패: {first_message}")
                    
                    # twilio_call_sessions에서 활성 세션 찾기
                    from src.main import twilio_call_sessions
                    if len(twilio_call_sessions) == 1:
                        actual_call_sid = list(twilio_call_sessions.keys())[0]
                        call_sid = actual_call_sid
                        logger.info(f"JSON 파싱 실패 시 활성 세션에서 call_sid 추출: {actual_call_sid}")
                    else:
                        import time
                        call_sid = f"unknown_{int(time.time())}"
                        logger.warning(f"JSON 파싱 실패 시 임시 call_sid 생성: {call_sid}")
            
            # 연결 정보 저장
            self.active_connections[call_sid] = {
                "websocket": websocket,
                "call_sid": call_sid,
                "stream_sid": None,
                "is_connected": True,
                "audio_buffer": bytearray(),
                "accumulated_text": "",
                "ai_response_buffer": bytearray()
            }
            
            logger.info(f"연결 정보 저장 완료: {call_sid}")
            
            # 새로운 시스템인지 확인
            from src.main import twilio_call_sessions
            is_new_system = call_sid in twilio_call_sessions
            
            if not is_new_system:
                # 기존 시스템: OpenAI Realtime 클라이언트 생성 및 연결
                logger.info(f"기존 시스템 사용 - OpenAI Realtime 클라이언트 설정: {call_sid}")
                await self._setup_openai_client(call_sid)
            else:
                # 새로운 시스템: OpenAI 클라이언트 설정 생략
                logger.info(f"새로운 시스템 감지 - 실시간 STT/LLM/TTS 사용: {call_sid}")
            
            # 통화 상태 브로드캐스트
            await broadcast_call_status("media_connected", call_sid, "미디어 스트림 연결됨")
            
            # 메시지 처리 루프 (시스템에 따라 다른 처리)
            if is_new_system:
                await self._new_system_message_loop(websocket, call_sid)
            else:
                await self._message_loop(websocket, call_sid)
            
        except WebSocketDisconnect:
            logger.info(f"Media Stream 연결 해제: {call_sid}")
        except Exception as e:
            logger.error(f"Media Stream 처리 오류 [{call_sid}]: {e}", exc_info=True)
        finally:
            await self._cleanup_connection(call_sid)
            
        return call_sid  # 실제 call_sid 반환 (pending에서 변경되었을 수 있음)
    
    async def _new_system_message_loop(self, websocket: WebSocket, call_sid: str):
        """새로운 시스템용 Twilio Media Stream 메시지 처리 루프"""
        
        connection = self.active_connections[call_sid]
        logger.info(f"새로운 시스템 메시지 루프 시작: {call_sid}")
        
        # 새로운 시스템 세션 가져오기
        from src.main import twilio_call_sessions
        session = twilio_call_sessions.get(call_sid)
        
        if not session:
            logger.error(f"새로운 시스템 세션을 찾을 수 없음: {call_sid}")
            return
            
        # 환영 메시지는 TwiML에서 이미 처리됨
        logger.info(f"환영 메시지는 TwiML에서 처리됨: {session.welcome_message}")
        
        try:
            while connection["is_connected"]:
                # Twilio에서 메시지 수신
                message = await websocket.receive_text()
                data = json.loads(message)
                
                await self._process_new_system_message(call_sid, data, session)
                
        except WebSocketDisconnect:
            logger.info(f"새로운 시스템 WebSocket 연결 해제: {call_sid}")
            connection["is_connected"] = False
            
            # 세션도 정리
            from src.main import twilio_call_sessions
            if call_sid in twilio_call_sessions:
                del twilio_call_sessions[call_sid]
                logger.info(f"Twilio 세션 정리됨: {call_sid}")
                
        except Exception as e:
            logger.error(f"새로운 시스템 메시지 루프 오류 [{call_sid}]: {e}", exc_info=True)
            connection["is_connected"] = False
            
            # 오류 시에도 세션 정리
            from src.main import twilio_call_sessions
            if call_sid in twilio_call_sessions:
                del twilio_call_sessions[call_sid]
                logger.info(f"오류로 인한 Twilio 세션 정리: {call_sid}")
    
    async def _process_new_system_message(self, call_sid: str, data: dict, session):
        """새로운 시스템용 Twilio 메시지 처리"""
        
        message_type = data.get("event")
        
        if message_type == "connected":
            logger.info(f"Twilio Media Stream 연결됨: {call_sid}")
            
        elif message_type == "start":
            # Stream 시작
            start_data = data.get("start", {})
            stream_sid = start_data.get("streamSid")
            logger.info(f"Stream 시작 데이터 [{call_sid}]: {start_data}")
            
            self.active_connections[call_sid]["stream_sid"] = stream_sid
            logger.info(f"Media Stream 시작: {call_sid}, StreamSID: {stream_sid}")
            
            # 연결 상태 재확인
            connection = self.active_connections[call_sid]
            logger.info(f"연결 정보 업데이트 [{call_sid}]: {connection}")
            
        elif message_type == "media":
            # 오디오 데이터 수신
            media_data = data.get("media", {})
            audio_payload = media_data.get("payload", "")
            
            if audio_payload:
                # μ-law 오디오를 PCM16으로 변환
                try:
                    audio_bytes = base64.b64decode(audio_payload)
                    pcm16_audio = convert_mulaw_to_pcm16(audio_bytes)
                    
                    # 음성 활동 감지 (단순한 방법: 0이 아닌 값의 비율)
                    audio_activity = self._detect_voice_activity(pcm16_audio)
                    
                    # 오디오 버퍼에 추가
                    session.audio_buffer.extend(pcm16_audio)
                    
                    # 음성 활동이 있으면 타이머 리셋
                    if audio_activity:
                        session.last_activity_time = __import__('time').time()
                        logger.debug(f"음성 활동 감지 [{call_sid}]: 버퍼 크기 {len(session.audio_buffer)}")
                        
                        # 부분 STT 수행 (일정 크기 이상일 때만)
                        if len(session.audio_buffer) >= 16000:  # 2초 분량
                            await self._process_partial_stt(call_sid, session)
                    
                    # 침묵 감지: 일정 시간 동안 음성 활동이 없으면 STT 처리
                    current_time = __import__('time').time()
                    silence_duration = current_time - session.last_activity_time
                    
                    # 최소 음성 길이와 침묵 시간 조건 확인
                    min_audio_length = 4000  # 0.5초 분량 (8kHz) - 더 빠른 반응
                    has_enough_audio = len(session.audio_buffer) >= min_audio_length
                    
                    if silence_duration >= session.silence_timeout and has_enough_audio:
                        logger.info(f"🔇 침묵 감지 [{call_sid}]: {silence_duration:.1f}초, 버퍼: {len(session.audio_buffer)} bytes, STT 처리 시작")
                        await self._process_audio_chunk(call_sid, session)
                        
                except Exception as e:
                    logger.error(f"오디오 처리 오류 [{call_sid}]: {e}")
                    
        elif message_type == "stop":
            logger.info(f"Media Stream 종료: {call_sid}")
            
            # 연결 상태 업데이트
            if call_sid in self.active_connections:
                self.active_connections[call_sid]["is_connected"] = False
            
            # 세션 정리
            from src.main import twilio_call_sessions
            if call_sid in twilio_call_sessions:
                del twilio_call_sessions[call_sid]
                logger.info(f"Media Stream 종료로 인한 세션 정리: {call_sid}")
            
        else:
            logger.debug(f"알 수 없는 메시지 타입 [{call_sid}]: {message_type}")
    
    def _detect_voice_activity(self, pcm16_audio: bytes) -> bool:
        """음성 활동 감지 (간단한 방법)"""
        try:
            # PCM16 데이터를 16비트 정수로 변환
            import struct
            samples = struct.unpack(f'<{len(pcm16_audio)//2}h', pcm16_audio)
            
            # RMS (Root Mean Square) 계산
            if len(samples) == 0:
                return False
                
            rms = sum(sample * sample for sample in samples) / len(samples)
            rms = rms ** 0.5
            
            # 임계값 설정 (로그를 보니 18-27 수준이므로 낮게 조정)
            threshold = 50  # 훨씬 낮은 임계값으로 조정
            is_active = rms > threshold
            
            # 디버깅용 로그 (음성 활동이 있을 때만)
            if is_active:
                logger.info(f"🎙️ 음성 활동 감지: RMS={rms:.0f}, 임계값={threshold}")
            elif random.random() < 0.05:  # 5% 확률로 침묵 상태도 로그
                logger.debug(f"침묵: RMS={rms:.0f}, 임계값={threshold}")
            
            return is_active
            
        except Exception as e:
            logger.error(f"음성 활동 감지 오류: {e}")
            return False
    
    async def _process_audio_chunk(self, call_sid: str, session):
        """오디오 청크를 STT로 처리"""
        
        if len(session.audio_buffer) == 0:
            return
            
        # 연결 상태 확인
        if call_sid not in self.active_connections:
            logger.warning(f"연결이 없어서 STT 처리 중단: {call_sid}")
            session.audio_buffer.clear()
            return
            
        connection = self.active_connections[call_sid]
        if not connection["is_connected"]:
            logger.warning(f"연결이 비활성화되어 STT 처리 중단: {call_sid}")
            session.audio_buffer.clear()
            return
            
        try:
            # 오디오 버퍼를 WAV 형태로 변환
            import io
            import wave
            
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # 모노
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(8000)  # 8kHz (Twilio default)
                wav_file.writeframes(bytes(session.audio_buffer))
            
            wav_buffer.seek(0)
            wav_buffer.name = "audio.wav"  # 파일명 설정 필요
            
            # OpenAI Whisper STT 호출
            import openai
            client = openai.AsyncOpenAI()
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=wav_buffer,
                language="ko"
            )
            
            if transcript.text.strip():
                logger.info(f"STT 결과 [{call_sid}]: {transcript.text}")
                session.last_transcript = transcript.text
                
                # STT 결과를 브라우저에 실시간 표시
                try:
                    from src.realtime_server import broadcast_transcription
                    await broadcast_transcription(transcript.text, True)  # is_final=True
                    logger.info(f"STT 결과 브라우저 전송 완료 [{call_sid}]: {transcript.text}")
                except Exception as broadcast_error:
                    logger.error(f"STT 브라우저 전송 실패 [{call_sid}]: {broadcast_error}")
                
                # LLM 처리
                await self._process_llm_response(call_sid, transcript.text, session)
            
            # 버퍼 클리어
            session.audio_buffer.clear()
            
        except Exception as e:
            logger.error(f"STT 처리 오류 [{call_sid}]: {e}")
            session.audio_buffer.clear()
    
    async def _process_llm_response(self, call_sid: str, text: str, session):
        """LLM 응답 생성 및 TTS 전송"""
        
        # 연결 상태 확인
        if call_sid not in self.active_connections:
            logger.warning(f"연결이 없어서 LLM 처리 중단: {call_sid}")
            return
            
        connection = self.active_connections[call_sid]
        if not connection["is_connected"]:
            logger.warning(f"연결이 비활성화되어 LLM 처리 중단: {call_sid}")
            return
        
        if session.is_processing_llm:
            logger.info(f"LLM 처리 중이므로 요청 무시: {call_sid}")
            return
            
        session.is_processing_llm = True
        
        try:
            # 대화 히스토리에 추가
            session.conversation_history.append({"role": "user", "content": text})
            
            # OpenAI GPT 호출
            import openai
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 친절한 한국어 AI 어시스턴트입니다. 간단하고 명확하게 대답해주세요."},
                    *session.conversation_history
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            logger.info(f"LLM 응답 [{call_sid}]: {ai_response}")
            
            # 대화 히스토리에 추가
            session.conversation_history.append({"role": "assistant", "content": ai_response})
            
            # TTS로 변환 및 전송
            await self._send_tts_response(call_sid, ai_response)
            
        except Exception as e:
            logger.error(f"LLM 처리 오류 [{call_sid}]: {e}")
        finally:
            session.is_processing_llm = False
    
    async def _send_tts_response(self, call_sid: str, text: str):
        """TTS 응답 전송"""
        
        logger.info(f"TTS 응답 전송 시작 [{call_sid}]: {text}")
        
        # 연결 상태 재확인
        if call_sid not in self.active_connections:
            logger.warning(f"연결이 없어서 TTS 전송 중단: {call_sid}")
            return
            
        connection = self.active_connections[call_sid]
        if not connection["is_connected"]:
            logger.warning(f"연결이 비활성화되어 TTS 전송 중단: {call_sid}")
            return
        
        try:
            # 1. 브라우저로 텍스트 전송
            from src.realtime_server import broadcast_ai_response_chunk
            await broadcast_ai_response_chunk(text)
            logger.info(f"AI 응답 브라우저 전송 완료 [{call_sid}]: {text}")
            
            # 2. Twilio Say를 사용해서 텍스트 직접 읽어주기
            try:
                from twilio.rest import Client
                from twilio.twiml.voice_response import VoiceResponse
                import os
                
                # Twilio 클라이언트 생성
                client = Client(os.getenv('ACCOUNT_SID'), os.getenv('AUTH_TOKEN'))
                
                # TwiML 생성 - Say로 텍스트 읽기
                twiml = VoiceResponse()
                twiml.say(text, voice='Polly.Seoyeon', language='ko-KR')
                
                # Media Stream을 계속 유지하기 위해 Connect 추가
                websocket_url = f"wss://pityingly-overwily-dawna.ngrok-free.dev/voice/stream?call_sid={call_sid}"
                connect = twiml.connect()
                connect.stream(url=websocket_url)
                
                # 통화 업데이트
                logger.info(f"Twilio Say 전송 시작 [{call_sid}]: {text}")
                client.calls(call_sid).update(twiml=str(twiml))
                logger.info(f"Twilio Say 전송 완료 [{call_sid}]: {text}")
                
            except Exception as tts_error:
                logger.error(f"Twilio Say 전송 실패 [{call_sid}]: {tts_error}")
            
        except Exception as e:
            logger.error(f"AI 응답 처리 오류 [{call_sid}]: {e}", exc_info=True)
    
    async def _send_audio_to_twilio(self, call_sid: str, wav_audio: bytes):
        """WAV 오디오를 Twilio Media Stream으로 전송"""
        
        logger.info(f"오디오 전송 함수 시작 [{call_sid}]: WAV 크기 {len(wav_audio)} bytes")
        
        connection = self.active_connections.get(call_sid)
        if not connection:
            logger.error(f"연결 정보 없음: {call_sid}")
            logger.error(f"활성 연결들: {list(self.active_connections.keys())}")
            return
            
        websocket = connection["websocket"]
        stream_sid = connection.get("stream_sid")
        
        logger.info(f"연결 상태 확인 [{call_sid}]: WebSocket={websocket is not None}, StreamSID={stream_sid}")
        
        if not websocket or not stream_sid:
            logger.error(f"WebSocket 또는 StreamSID 없음 [{call_sid}]: WS={websocket is not None}, SID={stream_sid}")
            return
            
        try:
            # WAV를 μ-law로 변환
            import wave
            import io
            
            logger.info(f"WAV 변환 시작 [{call_sid}]")
            
            # WAV 파일 읽기
            wav_buffer = io.BytesIO(wav_audio)
            with wave.open(wav_buffer, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                logger.info(f"WAV 정보 [{call_sid}]: 프레임={frames}, 샘플레이트={sample_rate}, 채널={channels}")
                
                pcm16_data = wav_file.readframes(frames)
            
            logger.info(f"PCM16 데이터 크기 [{call_sid}]: {len(pcm16_data)} bytes")
            
            # 샘플레이트가 8kHz가 아니면 리샘플링
            if sample_rate != 8000:
                logger.info(f"리샘플링 시작 [{call_sid}]: {sample_rate}Hz → 8000Hz")
                pcm16_data = resample_pcm16(pcm16_data, sample_rate, 8000)
                logger.info(f"리샘플링 완료 [{call_sid}]: {len(pcm16_data)} bytes")
            
            # PCM16을 μ-law로 변환
            mulaw_data = convert_pcm16_to_mulaw(pcm16_data)
            logger.info(f"μ-law 변환 완료 [{call_sid}]: {len(mulaw_data)} bytes")
            
            # 오디오를 작은 청크로 나누어 전송 (160 bytes per chunk for 8kHz)
            chunk_size = 160  # 20ms at 8kHz μ-law
            total_chunks = len(mulaw_data) // chunk_size
            logger.info(f"오디오 청크 분할 [{call_sid}]: {len(mulaw_data)} bytes → {total_chunks} chunks")
            
            import base64
            
            for i in range(0, len(mulaw_data), chunk_size):
                chunk = mulaw_data[i:i + chunk_size]
                
                # 마지막 청크가 너무 작으면 무음으로 패딩 (μ-law 무음은 0x7F)
                if len(chunk) < chunk_size:
                    chunk = chunk + b'\x7f' * (chunk_size - len(chunk))
                
                payload = base64.b64encode(chunk).decode('utf-8')
                
                # Twilio Media message 생성
                media_message = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": payload
                    }
                }
                
                await websocket.send_text(json.dumps(media_message))
                
                # 청크 간 작은 지연
                await asyncio.sleep(0.02)  # 20ms delay
            
            logger.info(f"오디오 전송 완료 [{call_sid}]: {total_chunks} chunks 전송됨")
            
        except Exception as e:
            logger.error(f"오디오 전송 오류 [{call_sid}]: {e}", exc_info=True)
    
    async def _setup_openai_client(self, call_sid: str):
        """OpenAI Realtime 클라이언트 설정"""
        
        # 콜백 함수 정의
        callbacks = RealtimeCallbacks(
            on_transcription=lambda text, is_final: asyncio.create_task(
                self._handle_transcription(call_sid, text, is_final)
            ),
            on_ai_response_text=lambda text_delta: asyncio.create_task(
                self._handle_ai_text_response(call_sid, text_delta)
            ),
            on_ai_response_audio=lambda audio_data: asyncio.create_task(
                self._handle_ai_audio_response(call_sid, audio_data)
            ),
            on_ai_response_complete=lambda full_text: asyncio.create_task(
                self._handle_ai_response_complete(call_sid, full_text)
            ),
            on_session_created=lambda session_data: asyncio.create_task(
                self._handle_session_created(call_sid, session_data)
            ),
            on_error=lambda error_msg: asyncio.create_task(
                self._handle_openai_error(call_sid, error_msg)
            ),
            on_speech_started=lambda: asyncio.create_task(
                self._handle_speech_started(call_sid)
            ),
            on_speech_stopped=lambda: asyncio.create_task(
                self._handle_speech_stopped(call_sid)
            )
        )
        
        # OpenAI 클라이언트 생성
        client = OpenAIRealtimeClient(
            api_key=settings.openai_api_key,
            callbacks=callbacks
        )
        
        # OpenAI API 연결
        success = await client.connect()
        if success:
            self.openai_clients[call_sid] = client
            logger.info(f"OpenAI Realtime 클라이언트 연결 성공: {call_sid}")
        else:
            logger.error(f"OpenAI Realtime 클라이언트 연결 실패: {call_sid}")
            raise Exception("OpenAI Realtime API 연결 실패")
    
    async def _message_loop(self, websocket: WebSocket, call_sid: str):
        """Twilio Media Stream 메시지 처리 루프"""
        
        connection = self.active_connections[call_sid]
        
        try:
            while connection["is_connected"]:
                # Twilio에서 메시지 수신
                message = await websocket.receive_text()
                data = json.loads(message)
                
                await self._process_twilio_message(call_sid, data)
                
        except WebSocketDisconnect:
            logger.info(f"Twilio WebSocket 연결 해제: {call_sid}")
            connection["is_connected"] = False
        except Exception as e:
            logger.error(f"메시지 루프 오류 [{call_sid}]: {e}", exc_info=True)
            connection["is_connected"] = False
    
    async def _process_twilio_message(self, call_sid: str, data: Dict[str, Any]):
        """Twilio에서 수신된 메시지 처리"""
        
        event_type = data.get("event")
        connection = self.active_connections.get(call_sid)
        
        if not connection:
            logger.warning(f"연결 정보를 찾을 수 없음: {call_sid}")
            return
        
        if event_type == "connected":
            # 스트림 연결 확인
            logger.debug(f"Twilio 스트림 연결됨: {call_sid}")
            
        elif event_type == "start":
            # 스트림 시작
            stream_sid = data.get("start", {}).get("streamSid")
            connection["stream_sid"] = stream_sid
            logger.info(f"미디어 스트림 시작: {call_sid}, Stream SID: {stream_sid}")
            
            # 새로운 시스템인지 확인하고 환영 메시지 전송
            from src.main import twilio_call_sessions, send_tts_to_twilio
            import asyncio
            if call_sid in twilio_call_sessions:
                # 새로운 시스템: 세션 설정에 따라 환영 메시지 전송
                session = twilio_call_sessions[call_sid]
                logger.info(f"새로운 시스템 감지 - 환영 메시지 예약: {call_sid}, 지연: {session.welcome_delay}초")
                asyncio.create_task(self._send_welcome_message_delayed(call_sid))
            
            # 스트림 시작 알림
            await broadcast_call_status("stream_started", call_sid, "음성 스트림 시작됨")
            
        elif event_type == "media":
            # 오디오 데이터 수신
            await self._process_audio_data(call_sid, data)
            
        elif event_type == "stop":
            # 스트림 종료
            logger.info(f"미디어 스트림 종료: {call_sid}")
            connection["is_connected"] = False
            
        else:
            logger.debug(f"처리되지 않은 Twilio 이벤트: {event_type}")
    
    async def _process_audio_data(self, call_sid: str, data: Dict[str, Any]):
        """Twilio에서 수신된 오디오 데이터 처리"""
        
        try:
            # Base64로 인코딩된 μ-law 오디오 데이터 추출
            media = data.get("media", {})
            payload = media.get("payload")
            
            if not payload:
                return
            
            # Base64 디코딩
            mulaw_data = base64.b64decode(payload)
            
            # 새로운 Twilio 통화 세션이 있으면 우선 처리
            from src.main import twilio_call_sessions, handle_twilio_media_chunk
            if call_sid in twilio_call_sessions:
                await handle_twilio_media_chunk(call_sid, mulaw_data)
                return
            
            # 기존 OpenAI Realtime API 처리
            # μ-law를 PCM16으로 변환
            pcm16_data = convert_mulaw_to_pcm16(mulaw_data)
            
            # OpenAI Realtime API로 전송
            openai_client = self.openai_clients.get(call_sid)
            if openai_client and openai_client.is_connected:
                await openai_client.send_audio_data(pcm16_data)
            
            # 오디오 버퍼에 추가 (디버깅용)
            connection = self.active_connections[call_sid]
            connection["audio_buffer"].extend(pcm16_data)
            
            # 버퍼 크기 제한
            if len(connection["audio_buffer"]) > self.audio_chunk_size * 10:
                connection["audio_buffer"] = connection["audio_buffer"][-self.audio_chunk_size * 5:]
            
        except Exception as e:
            logger.error(f"오디오 데이터 처리 오류 [{call_sid}]: {e}")
    
    async def _handle_transcription(self, call_sid: str, text: str, is_final: bool):
        """음성 인식 결과 처리"""
        
        logger.debug(f"전사 결과 [{call_sid}]: {'최종' if is_final else '임시'} - {text}")
        
        # 실시간으로 전사 결과 브로드캐스트
        await broadcast_transcription(text, is_final)
        
        # 누적 텍스트 업데이트
        connection = self.active_connections.get(call_sid)
        if connection and is_final:
            if connection["accumulated_text"]:
                connection["accumulated_text"] += " " + text
            else:
                connection["accumulated_text"] = text
    
    async def _handle_ai_text_response(self, call_sid: str, text_delta: str):
        """AI 텍스트 응답 스트리밍 처리"""
        
        logger.debug(f"AI 텍스트 델타 [{call_sid}]: {text_delta}")
        
        # 실시간으로 AI 응답 브로드캐스트
        await broadcast_ai_response_chunk(text_delta)
    
    async def _handle_ai_audio_response(self, call_sid: str, audio_data: bytes):
        """AI 오디오 응답 처리"""
        
        try:
            # OpenAI 응답(24kHz)을 Twilio(8kHz)에 맞게 리샘플링
            resampled_audio = resample_pcm16(audio_data, from_rate=24000, to_rate=8000)

            # PCM16을 μ-law로 변환
            mulaw_data = convert_pcm16_to_mulaw(resampled_audio)
            
            # Base64로 인코딩
            payload = base64.b64encode(mulaw_data).decode('utf-8')
            
            # Twilio로 오디오 전송
            connection = self.active_connections.get(call_sid)
            if connection and connection["is_connected"]:
                websocket = connection["websocket"]
                
                # Twilio Media 메시지 형식으로 전송
                message = {
                    "event": "media",
                    "streamSid": connection.get("stream_sid"),
                    "media": {
                        "payload": payload
                    }
                }
                
                await websocket.send_text(json.dumps(message))
                
                logger.debug(f"AI 오디오 응답 전송 [{call_sid}]: {len(audio_data)} bytes (resampled to {len(resampled_audio)})")
        
        except Exception as e:
            logger.error(f"AI 오디오 응답 처리 오류 [{call_sid}]: {e}")
    
    async def _handle_ai_response_complete(self, call_sid: str, full_text: str):
        """AI 응답 완료 처리"""
        
        logger.info(f"AI 응답 완료 [{call_sid}]: {full_text}")
        
        # 완료된 응답을 통화 상태에 저장
        await broadcast_call_status("ai_response_complete", call_sid, full_text)
    
    async def _handle_session_created(self, call_sid: str, session_data: Dict[str, Any]):
        """OpenAI 세션 생성 처리"""
        
        session_id = session_data.get("session", {}).get("id")
        logger.info(f"OpenAI 세션 생성됨 [{call_sid}]: {session_id}")
        
        await broadcast_call_status("openai_session_created", call_sid, f"OpenAI 세션: {session_id}")
    
    async def _handle_openai_error(self, call_sid: str, error_msg: str):
        """OpenAI 오류 처리"""
        
        logger.error(f"OpenAI 오류 [{call_sid}]: {error_msg}")
        
        await broadcast_call_status("openai_error", call_sid, f"OpenAI 오류: {error_msg}")
    
    async def _handle_speech_started(self, call_sid: str):
        """음성 입력 시작 처리"""
        
        logger.debug(f"음성 입력 시작 [{call_sid}]")
        
        await broadcast_call_status("speech_started", call_sid, "음성 입력 시작")
    
    async def _handle_speech_stopped(self, call_sid: str):
        """음성 입력 종료 처리"""
        
        logger.debug(f"음성 입력 종료 [{call_sid}]")
        
        await broadcast_call_status("speech_stopped", call_sid, "음성 입력 종료")
    
    async def _send_welcome_message_delayed(self, call_sid: str, message: str = None, delay: float = None):
        """지연된 환영 메시지 전송"""
        try:
            from src.main import twilio_call_sessions, send_tts_to_twilio
            
            # 매개변수가 제공되지 않으면 세션에서 가져오기
            if message is None or delay is None:
                if call_sid not in twilio_call_sessions:
                    logger.warning(f"환영 메시지 전송 시도했지만 세션이 없음: {call_sid}")
                    return
                    
                session = twilio_call_sessions[call_sid]
                welcome_message = message or session.welcome_message
                welcome_delay = delay if delay is not None else session.welcome_delay
            else:
                welcome_message = message
                welcome_delay = delay
            
            # 설정된 지연 시간만큼 대기
            logger.info(f"환영 메시지 지연 대기 시작: {call_sid}, {welcome_delay}초")
            await asyncio.sleep(welcome_delay)
            
            # 연결이 아직 활성인지 확인
            if call_sid not in self.active_connections:
                logger.warning(f"환영 메시지 전송 시도했지만 연결이 없음: {call_sid}")
                return
                
            connection = self.active_connections[call_sid]
            if not connection["is_connected"]:
                logger.warning(f"환영 메시지 전송 시도했지만 연결이 비활성: {call_sid}")
                return
            
            # 환영 메시지가 빈 문자열이면 전송하지 않음
            if not welcome_message or welcome_message.strip() == "":
                logger.info(f"환영 메시지가 비어있어 전송하지 않음: {call_sid}")
                return
            
            logger.info(f"환영 메시지 전송 시작: {call_sid}, 메시지: {welcome_message}")
            
            # 실시간 서버로 환영 메시지 브로드캐스트
            from src.realtime_server import broadcast_ai_response_chunk
            await broadcast_ai_response_chunk(welcome_message)
            logger.info(f"환영 메시지 브로드캐스트 완료: {call_sid}")
            
        except Exception as e:
            logger.error(f"환영 메시지 전송 오류 [{call_sid}]: {e}")

async def send_simple_test_audio(call_sid: str):
    """간단한 테스트 오디오 전송 (톤 신호)"""
    try:
        import struct
        import math
        
        # 1초간 440Hz 톤 생성 (8kHz, 모노, 16-bit PCM)
        sample_rate = 8000
        frequency = 440
        duration = 1.0
        
        samples = []
        for i in range(int(sample_rate * duration)):
            value = int(32767 * 0.3 * math.sin(2 * math.pi * frequency * i / sample_rate))
            samples.append(struct.pack('<h', value))
        
        pcm_data = b''.join(samples)
        
        # PCM을 μ-law로 변환
        from src.openai_realtime import convert_pcm16_to_mulaw
        mulaw_data = convert_pcm16_to_mulaw(pcm_data)
        
        # Twilio로 전송
        from src.media_bridge import media_handler
        if call_sid in media_handler.active_connections:
            connection = media_handler.active_connections[call_sid]
            websocket = connection["websocket"]
            stream_sid = connection.get("stream_sid")
            
            if websocket and stream_sid:
                chunk_size = 160
                for i in range(0, len(mulaw_data), chunk_size):
                    chunk = mulaw_data[i:i + chunk_size]
                    
                    import base64, json
                    payload = base64.b64encode(chunk).decode('utf-8')
                    
                    message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": payload
                        }
                    }
                    
                    await websocket.send_text(json.dumps(message))
                    await asyncio.sleep(0.02)
                
                logger.info(f"테스트 톤 전송 완료: {call_sid}")
            else:
                logger.warning(f"테스트 톤 전송 실패 - 연결 없음: {call_sid}")
        
    except Exception as e:
        logger.error(f"테스트 톤 전송 오류: {e}")

    async def _cleanup_connection(self, call_sid: str):
        """연결 정리"""
        
        logger.info(f"연결 정리 시작: {call_sid}")
        
        # OpenAI 클라이언트 정리
        if call_sid in self.openai_clients:
            client = self.openai_clients[call_sid]
            await client.disconnect()
            del self.openai_clients[call_sid]
            logger.debug(f"OpenAI 클라이언트 정리 완료: {call_sid}")
        
        # 연결 정보 정리
        if call_sid in self.active_connections:
            connection = self.active_connections[call_sid]
            connection["is_connected"] = False
            del self.active_connections[call_sid]
            logger.debug(f"연결 정보 정리 완료: {call_sid}")
        
        # Twilio 세션 정리
        from src.main import twilio_call_sessions
        if call_sid in twilio_call_sessions:
            del twilio_call_sessions[call_sid]
            logger.info(f"Twilio 세션 정리 완료: {call_sid}")
        
        # 통화 종료 알림
        await broadcast_call_status("media_disconnected", call_sid, "미디어 스트림 연결 해제됨")
        
        logger.info(f"연결 정리 완료: {call_sid}")
    
    def get_connection_status(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """연결 상태 조회"""
        
        connection = self.active_connections.get(call_sid)
        if not connection:
            return None
        
        openai_client = self.openai_clients.get(call_sid)
        
        return {
            "call_sid": call_sid,
            "stream_sid": connection.get("stream_sid"),
            "is_connected": connection["is_connected"],
            "openai_connected": openai_client.is_connected if openai_client else False,
            "accumulated_text": connection["accumulated_text"],
            "audio_buffer_size": len(connection["audio_buffer"])
        }
    
    def get_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """모든 연결 상태 조회"""
        
        return {
            call_sid: self.get_connection_status(call_sid)
            for call_sid in self.active_connections.keys()
        }

# 글로벌 핸들러 인스턴스
media_handler = TwilioMediaStreamHandler()

async def twilio_media_stream_handler(websocket: WebSocket):
    """
    Twilio Media Stream WebSocket 엔드포인트 핸들러
    
    이 함수는 FastAPI WebSocket 엔드포인트로 사용됩니다.
    """
    
    # Query parameter에서 call_sid 추출
    call_sid = websocket.query_params.get("call_sid")
    
    if not call_sid:
        logger.error("call_sid가 제공되지 않음")
        await websocket.close(code=4000, reason="call_sid required")
        return
    
    logger.info(f"새로운 미디어 스트림 연결 요청: {call_sid}")
    
    # 핸들러로 처리 위임
    await media_handler.handle_media_stream(websocket, call_sid)