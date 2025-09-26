from twilio.rest import Client
from dotenv import load_dotenv
import os
load_dotenv()

# Twilio 인증 정보 (환경변수에 저장하는 걸 권장)
ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
US_PHONENUMBER = os.getenv("US_PHONENUMBER")
KO_PHONENUMBER = os.getenv("KO_PHONENUMBER")  # 한국 번호 예시
URL = os.getenv("URL")  # Flask 서버가 외부에서 접근 가능한 URL
client = Client(ACCOUNT_SID, AUTH_TOKEN)

call = client.calls.create(
    to=KO_PHONENUMBER,  # 수신자 번호 (데모 시 본인 번호 추천)
    from_=US_PHONENUMBER,  # 발신자 번호 (Twilio 콘솔에서 받은 번호)
    url=URL  # Flask 서버가 외부에서 접근 가능한 URL
)

print("전화 발신 중... Call SID:", call.sid)
