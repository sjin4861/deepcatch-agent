#!/usr/bin/env python3
"""
HTTPS 서버 실행 스크립트
uvicorn 명령어로도 HTTPS를 사용할 수 있도록 도와주는 스크립트
"""

import subprocess
import sys
import os
from pathlib import Path
from src.ssl_generator import generate_self_signed_cert

def main():
    # SSL 인증서 생성
    cert_file, key_file = generate_self_signed_cert()
    
    # uvicorn 명령어 구성
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "src.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--ssl-keyfile", key_file,
        "--ssl-certfile", cert_file,
        "--reload"
    ]
    
    print(f"🚀 Starting HTTPS server with SSL certificate...")
    print(f"📄 Certificate: {cert_file}")
    print(f"🔑 Private key: {key_file}")
    print(f"🌐 Server will be available at: https://localhost:8000")
    print(f"📋 Command: {' '.join(cmd)}")
    print()
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Server failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()