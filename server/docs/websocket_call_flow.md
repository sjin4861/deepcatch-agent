# WebSocket Call Flow & Event Specification

본 문서는 프런트엔드가 `/call/status` 폴링 없이 **Socket.IO(WebSocket)** 이벤트만으로 통화 UI 상태를 구성하기 위한 규격을 정의합니다.

## 1. 연결 및 네임스페이스
- 엔드포인트: `/socket.io`
- 연결 직후 클라이언트는 별도 인증 절차가 없다면 즉시 이벤트 수신 가능.

## 2. 이벤트 목록 요약
| 이벤트 | 발생 시점 | 페이로드 필드 | 설명 |
|--------|-----------|---------------|------|
| `call_started` | /call API 성공 (simulate 또는 실제 Twilio) | `call_sid, business, phone, simulated` | 통화 세션 생성/발신 시작. simulate=true 시 즉시 completed 전환될 수 있음. |
| `call_failed` | /call API 비즈니스 선택 실패, Twilio 실패 | `business?, phone?, error?, reason?` | 발신 시도 실패. UI는 오류 메시지 표시 후 대기 상태로 복귀. |
| `ai_response_begin` | LLM 스트리밍 시작 직전 | `call_sid` | 새 어시스턴트 응답 스트림 시작. 기존 partial 메시지 버퍼 초기화. |
| `ai_response_text` | LLM 스트리밍 중 토큰/청크 단위 | `call_sid, text_delta` | 부분 텍스트 누적 후 UI 실시간 업데이트. |
| `ai_response_complete` | LLM 응답(또는 시나리오 한 줄) 완료 | `call_sid, text, scenario?` | 최종 문장 확정. scenario=true면 스크립트 출처. |
| `user_speech` | 사용자 음성 인식 결과 수신 | `call_sid, text` | 사용자 발화 turn 확정. |
| `call_status_update` | Twilio Voice Status 콜백 | `call_sid, status, timestamp, data.error_code?` | Twilio 상태 변화를 UI에 반영 (ringing, answered 등). |
| `call_ended` | 최종 종료 상태 도달 | `call_sid` | UI는 종료 표시 & 후처리 (슬롯/요약 패널). |
| `call_slots_extracted` | 종료 후 슬롯 추출 성공 | `call_sid, slots` | 가격/인원/출발시간 등 추출 결과 표시. |
| `call_slots_error` | 슬롯 추출 실패 | `call_sid, error` | 추출 실패 알림 (재시도 버튼 노출 가능). |
| `scenario_finished` | 시나리오 스크립트 마지막 줄 소비 | `call_sid` | 이후부터 일반 LLM 모드 전환. |
| `openai_error` | LLM 호출 예외 발생 | `call_sid?, error` | 어시스턴트 응답 실패 안내. |

## 3. 상태 머신 (프런트 재구성)
프런트는 이벤트 기반으로 아래와 같이 상태를 구성할 수 있습니다.

```
IDLE ──(call_started)──> OUTBOUND
OUTBOUND ──(call_status_update: ringing)──> RINGING
RINGING ──(call_status_update: answered)──> IN_PROGRESS
IN_PROGRESS ──(ai_response_begin / user_speech 반복)──> IN_PROGRESS
IN_PROGRESS ──(call_ended)──> ENDED
```
추가로 simulate=true 시:
```
IDLE ──(call_started[simulated=true])──> ENDED (즉시)
```

## 4. 재연결 복구 전략
- 기본은 서버 폴링 불필요. 단, 브라우저 새로고침 등으로 상태 유실 시 `/call/status/{call_sid}` 1회 호출 후:
  - 최근 transcript preview → 이미 종료 여부 판단
  - 종료된 세션이면 추가 WebSocket listen 중단
- 향후 별도 `session_sync` 이벤트 필요 시 확장 가능.

## 5. 시나리오 모드 처리
- 첫 줄: `ai_response_complete` (scenario=true)
- 사용자 발화 이후 또 다른 시나리오 라인이 있으면 동일 이벤트 반복.
- 모든 라인 소비 후 `scenario_finished` 발행 → 이후부터 LLM 경로 (`ai_response_begin`→`ai_response_text`→`ai_response_complete`).

## 6. UI 권장 렌더링 로직
1. `call_started` 수신 시 패널 활성화, business/phone 표기.
2. `call_status_update`:
   - ringing: 진행 인디케이터
   - answered/in-progress: 통화 타이머 시작
3. `user_speech` → transcript 리스트에 사용자 turn append.
4. `ai_response_text` → 현재 진행중 assistant turn streaming 표시.
5. `ai_response_complete` → streaming turn 확정, scenario flag 표시(스크립트 아이콘 등).
6. `scenario_finished` → “스크립트 완료, 실시간 응답 전환” 배지 1회 노출.
7. `call_ended` → 타이머 중지, 상태 ‘종료’ 표시.
8. `call_slots_extracted` → Side panel 에 슬롯 강조 (가격, 인원, 출발시간).
9. `openai_error` → 재시도/안내 배너 표시.

## 7. 예시 이벤트 payload
```jsonc
// call_started
{"call_sid":"CAxxx","business":"구룡포 낚시프라자","phone":"+8210...","simulated":false}

// ai_response_text
{"call_sid":"CAxxx","text_delta":"네, 가능합니다."}

// ai_response_complete (scenario)
{"call_sid":"CAxxx","text":"안녕하세요 구룡포 낚시프라자 맞으신가요?","scenario":true}

// user_speech
{"call_sid":"CAxxx","text":"네 말씀하세요"}

// call_status_update
{"call_sid":"CAxxx","status":"ringing","timestamp":"2025-09-27T10:00:00Z"}

// call_slots_extracted
{"call_sid":"CAxxx","slots":{"price_quote":"15만원","capacity_confirmed":4,"departure_time":"5시 00분","conditions_notes":null}}
```

## 8. 폴백 (/call/status) 사용 권고 범위
- WebSocket 연결 실패 시(네트워크 차단) 혹은 새로고침 직후 마지막 세션 복구 필요할 때만 단발성 호출.
- 장기 폴링 절대 금지 (성능/서버 자원 낭비).

## 9. 버전 및 변경 로그
- v1 (현재): 기본 이벤트 세트 정의, 시나리오 지원, 슬롯 추출 이벤트 포함.
- 예정: 대화 turn id 제공, partial token rate metric, AI latency metric.

---
문의/확장 필요 사항은 server/src/main.py TODO 섹션을 참고하거나 신규 이슈로 등록하세요.
