#!/usr/bin/env python3
"""
SSL 인증서 생성 스크립트
자체 서명된 SSL 인증서를 생성하여 HTTPS 개발 서버를 실행할 수 있도록 합니다.
"""

from src.ssl_generator import generate_self_signed_cert
import sys

def main():
    try:
        cert_file, key_file = generate_self_signed_cert()
        print("\n✅ SSL 인증서가 성공적으로 생성되었습니다!")
        print(f"📄 인증서: {cert_file}")
        print(f"🔑 개인키: {key_file}")
        print("\n🌐 서버를 HTTPS로 시작하려면:")
        print("   python src/main.py")
        print("\n🔧 HTTP로 시작하려면 환경변수를 설정하세요:")
        print("   USE_SSL=false python src/main.py")
        print("\n⚠️  자체 서명된 인증서이므로 브라우저에서 보안 경고가 표시될 수 있습니다.")
        print("   개발 목적으로만 사용하세요.")
    except Exception as e:
        print(f"❌ SSL 인증서 생성 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()