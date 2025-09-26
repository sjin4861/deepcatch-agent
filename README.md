# deepcatch-agent
🎣 포항 구룡포 낚시 관광객을 위한 AI 전화 예약 에이전트

---

## 🚀 실행 방법

### 1. 프로젝트 클론 및 환경 세팅
```bash
git clone https://github.com/사용자명/deepcatch-agent.git
cd deepcatch-agent
un sync
```

### 2. 환경 변수 설정
.env 파일을 프로젝트 루트에 생성하고 내용을 입력합니다.
Twilio가 로컬 Flask 서버에 접근하려면 [ngrok](https://ngrok.com/download)을 사용합니다.

#### ngrok 다운로드
- [macOS](https://ngrok.com/download)
- [Windows](https://ngrok.com/download)
- [Linux](https://ngrok.com/download)

설치 후 터미널에서 실행:
```bash
ngrok http 5000
### 3. Flask 서버 실행
```bash
uv run src/app.py
ngrok http 5000
# 성공하면 다음과 같이 URL이 출력됩니다:
Forwarding    https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:5000
# 이 URL을 복사해서 Python 코드에 있는 URL 변수에 넣어줍니다:
URL = "https://xxxx-xx-xx-xx-xx.ngrok-free.app/voice"
# 이후 다른 터미널에서 다음을 실행하세요:
un run src/call.py
```