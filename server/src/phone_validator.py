"""
전화번호 유효성 검증 모듈

이 모듈은 Twilio API에서 사용할 수 있는 올바른 형식의 전화번호인지 검증합니다.
E.164 형식을 준수하고 Twilio에서 지원하는 국가의 번호인지 확인합니다.
"""

import re
from typing import Optional, Tuple
from src.config import logger

class PhoneValidator:
    """전화번호 유효성 검증 클래스"""
    
    # E.164 형식 정규식 패턴
    E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$')
    
    # 지원하는 국가 코드와 번호 형식
    SUPPORTED_COUNTRIES = {
        # 미국/캐나다 (+1)
        '1': {
            'name': '미국/캐나다',
            'pattern': re.compile(r'^\+1[2-9]\d{2}[2-9]\d{6}$'),
            'example': '+12345551234'
        },
        # 한국 (+82)
        '82': {
            'name': '한국',
            'pattern': re.compile(r'^\+82(10|11|16|17|18|19)\d{7,8}$'),
            'example': '+821012345678'
        },
        # 일본 (+81)
        '81': {
            'name': '일본',
            'pattern': re.compile(r'^\+81[789]0\d{8}$'),
            'example': '+819012345678'
        }
    }
    
    @classmethod
    def normalize_phone_number(cls, phone: str) -> str:
        """전화번호를 E.164 형식으로 정규화"""
        
        # 공백, 하이픈, 괄호 제거
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        
        # + 기호가 없으면 추가
        if not cleaned.startswith('+'):
            # 한국 번호인 경우 (010으로 시작)
            if cleaned.startswith('010'):
                cleaned = '+82' + cleaned[1:]  # 010 -> +8210
            # 미국 번호인 경우 (11자리)
            elif len(cleaned) == 11 and cleaned.startswith('1'):
                cleaned = '+' + cleaned
            # 10자리 미국 번호
            elif len(cleaned) == 10:
                cleaned = '+1' + cleaned
            else:
                # 기본적으로 + 추가
                cleaned = '+' + cleaned
        
        logger.debug(f"전화번호 정규화: {phone} -> {cleaned}")
        return cleaned
    
    @classmethod
    def validate_phone_number(cls, phone: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        전화번호 유효성 검증
        
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: 
            (유효성, 정규화된 번호, 오류 메시지)
        """
        
        if not phone:
            return False, None, "전화번호가 비어있습니다"
        
        # 정규화
        normalized = cls.normalize_phone_number(phone)
        
        # E.164 형식 검증
        if not cls.E164_PATTERN.match(normalized):
            return False, None, f"E.164 형식이 아닙니다: {normalized}"
        
        # 국가 코드 추출
        country_code = cls._extract_country_code(normalized)
        if not country_code:
            return False, None, f"지원하지 않는 국가 코드입니다: {normalized}"
        
        # 국가별 상세 검증
        country_info = cls.SUPPORTED_COUNTRIES.get(country_code)
        if not country_info:
            return False, None, f"지원하지 않는 국가입니다: +{country_code}"
        
        # 국가별 패턴 검증
        if not country_info['pattern'].match(normalized):
            return False, None, (
                f"{country_info['name']} 번호 형식이 올바르지 않습니다. "
                f"예시: {country_info['example']}"
            )
        
        logger.debug(f"전화번호 검증 성공: {normalized} ({country_info['name']})")
        return True, normalized, None
    
    @classmethod
    def _extract_country_code(cls, phone: str) -> Optional[str]:
        """E.164 형식 번호에서 국가 코드 추출"""
        
        if not phone.startswith('+'):
            return None
        
        # 국가 코드는 1-3자리
        for length in [1, 2, 3]:
            code = phone[1:1+length]
            if code in cls.SUPPORTED_COUNTRIES:
                return code
        
        return None
    
    @classmethod
    def is_twilio_verified_number(cls, phone: str) -> bool:
        """
        Twilio에서 인증된 번호인지 확인 (Trial 계정용)
        
        Trial 계정에서는 인증된 번호로만 전화를 걸 수 있습니다.
        실제 프로덕션에서는 이 함수를 제거하거나 수정해야 합니다.
        """
        
        # 환경변수에서 인증된 번호 목록을 가져올 수 있도록 설계
        # 현재는 기본적으로 True 반환 (유료 계정 가정)
        
        verified_numbers = [
            # 여기에 Twilio에서 인증한 번호들을 추가
            # 예: "+821012345678", "+12345551234"
        ]
        
        # Trial 계정이 아닌 경우 모든 번호 허용
        if not verified_numbers:
            return True
        
        return phone in verified_numbers
    
    @classmethod
    def get_validation_error_message(cls, phone: str) -> str:
        """사용자 친화적인 오류 메시지 생성"""
        
        is_valid, normalized, error = cls.validate_phone_number(phone)
        
        if is_valid:
            return ""
        
        return f"전화번호 오류: {error}. 올바른 형식으로 입력해주세요."

# 전역 유틸리티 함수들
def validate_and_normalize_phone(phone: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """전화번호 검증 및 정규화 유틸리티 함수"""
    return PhoneValidator.validate_phone_number(phone)

def is_valid_phone_number(phone: str) -> bool:
    """간단한 전화번호 유효성 검증"""
    is_valid, _, _ = PhoneValidator.validate_phone_number(phone)
    return is_valid