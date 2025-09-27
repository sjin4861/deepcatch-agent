"""
자체 서명된 SSL 인증서 생성 유틸리티
"""

import os
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from datetime import datetime, timedelta
import ipaddress
from pathlib import Path

def generate_self_signed_cert(cert_dir: str = "certs"):
    """자체 서명된 SSL 인증서 생성"""
    
    # 인증서 디렉토리 생성
    cert_path = Path(cert_dir)
    cert_path.mkdir(exist_ok=True)
    
    cert_file = cert_path / "server.crt"
    key_file = cert_path / "server.key"
    
    # 이미 인증서가 존재하면 재사용
    if cert_file.exists() and key_file.exists():
        print(f"Using existing certificate: {cert_file}")
        return str(cert_file), str(key_file)
    
    print("Generating new self-signed SSL certificate...")
    
    # 개인키 생성
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Subject 및 Issuer 이름 설정
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Seoul"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Seoul"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "DeepCatch Agent"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    # 인증서 생성
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=365)  # 1년간 유효
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.IPAddress(ipaddress.IPv6Address("::1")),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256())
    
    # 인증서 파일로 저장
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    # 개인키 파일로 저장
    with open(key_file, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    print(f"Certificate saved to: {cert_file}")
    print(f"Private key saved to: {key_file}")
    
    return str(cert_file), str(key_file)

if __name__ == "__main__":
    cert_file, key_file = generate_self_signed_cert()
    print(f"SSL certificate generated successfully!")
    print(f"Certificate: {cert_file}")
    print(f"Private key: {key_file}")