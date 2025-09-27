from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    resp.say("안녕하세요, 낚시집 데모 전화를 테스트하고 있습니다. 영업 시간이 어떻게 되나요?", language="ko-KR")
    resp.record(max_length=30, action="/handle-recording", transcribe=True)
    return Response(str(resp), mimetype="text/xml")

@app.route("/handle-recording", methods=["POST"])
def handle_recording():
    recording_url = request.form.get("RecordingUrl")
    transcription_text = request.form.get("TranscriptionText")
    print("녹음된 음성:", recording_url)
    print("자동 전사 결과:", transcription_text)
    resp = VoiceResponse()
    resp.say("답변해주셔서 감사합니다. 좋은 하루 보내세요.", language="ko-KR")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
