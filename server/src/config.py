"""
환경 변수 설정 및 애플리케이션 구성 관리

이 모듈은 .env 파일에서 설정을 로드하고 애플리케이션 전체에서 사용할 수 있도록 
구성 클래스를 제공합니다.
"""

import os
import logging
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Settings(BaseSettings):
    """애플리케이션 설정 클래스"""
    
    # 기본 설정
    log_level: str = "DEBUG"
    
    # Twilio 설정
    account_sid: str
    auth_token: str 
    us_phonenumber: str
    ko_phonenumber: str | None = None
    
    # OpenAI 설정
    openai_api_key: str
    openai_realtime_model: str = "gpt-4o-realtime-preview-2024-10-01"
    openai_realtime_voice: str = "alloy"
    openai_realtime_temperature: float = 0.7
    
    # WebSocket 서버 설정
    websocket_host: str = "0.0.0.0"
    websocket_port: int = 8001
    cors_origins: str = "http://localhost:3000,http://localhost:9002,null"
    
    # Twilio Media Stream 설정
    twilio_webhook_url: str = os.getenv("TWILIO_WEBHOOK_URL", "https://your-domain.ngrok.io")
    twilio_sample_rate: int = 8000
    twilio_encoding: str = "mulaw"
    
    # 오디오 처리 설정
    audio_chunk_size: int = 1024
    audio_buffer_size: int = 4096

    # 시나리오 설정 (옵션)
    scenario_mode: bool | None = None  # SCENARIO_MODE
    scenario_dir: str | None = None    # SCENARIO_DIR
    scenario_id: str | None = None     # SCENARIO_ID
    
    # 외부 API 설정 
    dpg_service_key: str | None = None  # DPG_SERVICE_KEY 
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 환경변수명을 소문자로 변환하지 않음
        case_sensitive = False
    
    @property
    def cors_origins_list(self) -> List[str]:
        """CORS origins를 리스트로 변환"""
        return [origin.strip() for origin in self.cors_origins.split(",")]

# 전역 설정 인스턴스
settings = Settings()

def setup_logging() -> logging.Logger:
    """로깅 설정을 초기화하고 logger 반환"""
    
    # 로그 레벨 설정
    log_level = getattr(logging, settings.log_level.upper(), logging.DEBUG)
    
    # 로거 설정
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    logger = logging.getLogger("deepcatch-agent")
    logger.setLevel(log_level)
    
    logger.debug(f"로깅 초기화 완료. 레벨: {settings.log_level}")
    logger.debug(f"WebSocket 서버: {settings.websocket_host}:{settings.websocket_port}")
    logger.debug(f"CORS Origins: {settings.cors_origins_list}")
    
    return logger

# 글로벌 로거 인스턴스
logger = setup_logging()