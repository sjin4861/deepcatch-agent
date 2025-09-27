"""
OpenAI Realtime API 테스트 스크립트

이 스크립트는 OpenAI Realtime API 연결과 기본 기능들을 테스트합니다.
"""

import asyncio
import base64
import json
from src.openai_realtime import OpenAIRealtimeClient, RealtimeCallbacks
from src.config import settings, logger

class TestCallbacks:
    """테스트용 콜백 클래스"""
    
    def __init__(self):
        self.transcriptions = []
        self.ai_responses = []
        self.errors = []
        self.session_created = False
    
    async def on_transcription(self, text: str, is_final: bool):
        print(f"🎤 전사 ({'최종' if is_final else '임시'}): {text}")
        if is_final:
            self.transcriptions.append(text)
    
    async def on_ai_response_text(self, text_delta: str):
        print(f"🤖 AI 응답 델타: {text_delta}")
        
    async def on_ai_response_audio(self, audio_data: bytes):
        print(f"🔊 AI 오디오 수신: {len(audio_data)} bytes")
    
    async def on_ai_response_complete(self, full_text: str):
        print(f"✅ AI 응답 완료: {full_text}")
        self.ai_responses.append(full_text)
    
    async def on_session_created(self, session_data: dict):
        print(f"🔗 세션 생성: {session_data.get('session', {}).get('id')}")
        self.session_created = True
    
    async def on_error(self, error_msg: str):
        print(f"❌ 오류: {error_msg}")
        self.errors.append(error_msg)
    
    async def on_speech_started(self):
        print("🎙️ 음성 입력 시작")
    
    async def on_speech_stopped(self):
        print("🛑 음성 입력 종료")

async def generate_test_audio():
    """테스트용 오디오 데이터 생성 (무음)"""
    # 1초 분량의 16kHz PCM16 무음 데이터
    sample_rate = 16000
    duration = 1.0
    samples = int(sample_rate * duration)
    
    # 16-bit signed integer 무음 (0값들)
    silence = b'\x00\x00' * samples
    return silence

async def test_openai_realtime():
    """OpenAI Realtime API 테스트"""
    
    print("🚀 OpenAI Realtime API 테스트 시작")
    print(f"📋 사용 모델: {settings.openai_realtime_model}")
    print(f"🔑 API 키: {settings.openai_api_key[:10]}...")
    
    # 콜백 설정
    test_callbacks = TestCallbacks()
    callbacks = RealtimeCallbacks(
        on_transcription=test_callbacks.on_transcription,
        on_ai_response_text=test_callbacks.on_ai_response_text,
        on_ai_response_audio=test_callbacks.on_ai_response_audio,
        on_ai_response_complete=test_callbacks.on_ai_response_complete,
        on_session_created=test_callbacks.on_session_created,
        on_error=test_callbacks.on_error,
        on_speech_started=test_callbacks.on_speech_started,
        on_speech_stopped=test_callbacks.on_speech_stopped,
    )
    
    # 클라이언트 생성
    client = OpenAIRealtimeClient(
        api_key=settings.openai_api_key,
        callbacks=callbacks
    )
    
    try:
        # 1. 연결 테스트
        print("\n1️⃣ OpenAI Realtime API 연결 테스트...")
        connected = await client.connect()
        
        if not connected:
            print("❌ 연결 실패!")
            return
        
        print("✅ 연결 성공!")
        
        # 세션 생성 대기
        await asyncio.sleep(2)
        
        if not test_callbacks.session_created:
            print("❌ 세션 생성되지 않음!")
            return
        
        # 2. 텍스트 메시지 테스트
        print("\n2️⃣ 텍스트 메시지 테스트...")
        await client.send_text_message("안녕하세요! 낚시 예약 시스템 테스트입니다.")
        
        # AI 응답 대기
        print("⏳ AI 응답 대기 중...")
        await asyncio.sleep(5)
        
        # 3. 오디오 테스트 (무음 데이터)
        print("\n3️⃣ 오디오 스트리밍 테스트...")
        test_audio = await generate_test_audio()
        
        # 오디오 청크로 나누어 전송
        chunk_size = 1024
        for i in range(0, len(test_audio), chunk_size):
            chunk = test_audio[i:i+chunk_size]
            await client.send_audio_data(chunk)
            await asyncio.sleep(0.1)  # 100ms 간격
        
        # 오디오 버퍼 커밋
        await client.commit_audio_buffer()
        print("🎵 테스트 오디오 전송 완료")
        
        # 응답 대기
        await asyncio.sleep(3)
        
        # 4. 결과 요약
        print("\n📊 테스트 결과 요약:")
        print(f"✅ 세션 생성: {test_callbacks.session_created}")
        print(f"📝 전사 결과: {len(test_callbacks.transcriptions)}개")
        print(f"🤖 AI 응답: {len(test_callbacks.ai_responses)}개")
        print(f"❌ 오류: {len(test_callbacks.errors)}개")
        
        if test_callbacks.transcriptions:
            print("\n📝 전사 내용:")
            for i, text in enumerate(test_callbacks.transcriptions):
                print(f"  {i+1}. {text}")
        
        if test_callbacks.ai_responses:
            print("\n🤖 AI 응답:")
            for i, response in enumerate(test_callbacks.ai_responses):
                print(f"  {i+1}. {response}")
        
        if test_callbacks.errors:
            print("\n❌ 오류 내용:")
            for i, error in enumerate(test_callbacks.errors):
                print(f"  {i+1}. {error}")
    
    except Exception as e:
        print(f"❌ 테스트 중 오류 발생: {e}")
        logger.error(f"테스트 오류: {e}", exc_info=True)
    
    finally:
        # 연결 정리
        await client.disconnect()
        print("\n🧹 연결 정리 완료")

if __name__ == "__main__":
    print("=" * 50)
    print("OpenAI Realtime API 테스트")
    print("=" * 50)
    
    try:
        asyncio.run(test_openai_realtime())
    except KeyboardInterrupt:
        print("\n⚠️ 사용자에 의해 중단됨")
    except Exception as e:
        print(f"❌ 실행 오류: {e}")
    
    print("\n🏁 테스트 완료")