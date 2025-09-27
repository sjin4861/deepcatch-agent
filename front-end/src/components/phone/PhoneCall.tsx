/**
 * 실제 전화 발신 컴포넌트
 * Twilio를 통해 실제 전화번호로 통화를 시작합니다.
 */

'use client';

import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useRealtimeConnection } from '@/hooks/useRealtimeConnection';

interface FishingRequest {
  to_phone: string;
  business_name: string;
  fishing_request: string;
}

interface CallResponse {
  status: string;
  call_sid?: string;
  message: string;
}

export default function PhoneCall() {
  const [phoneNumber, setPhoneNumber] = useState('+821012345678');
  const [businessName, setBusinessName] = useState('해맞이 낚시터');
  const [fishingRequest, setFishingRequest] = useState('내일 오전 6시부터 바다낚시 예약하고 싶습니다. 4명이서 가려고 하는데 가능한지 확인해주세요.');
  const [isLoading, setIsLoading] = useState(false);
  const [callResponse, setCallResponse] = useState<CallResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 시나리오 선택 (테스트 용)
  const [scenarioId, setScenarioId] = useState<'scenario1' | 'scenario2' | 'scenario3'>('scenario1');

  const { 
    isConnected,
    callStatus,
    transcription,
    aiResponse,
    latestUserSpeech,
    joinCallRoom,
    scenarioProgress
  } = useRealtimeConnection();

  const handleMakeCall = async () => {
    if (!phoneNumber.trim() || !businessName.trim() || !fishingRequest.trim()) {
      setError('모든 필드를 입력해주세요.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setCallResponse(null);

    try {
      const requestData: FishingRequest = {
        to_phone: phoneNumber.trim(),
        business_name: businessName.trim(),
        fishing_request: fishingRequest.trim()
      };

      // scenario_id를 request body에 추가 (백엔드에서 선택된 시나리오 강제 적용)
      const extendedBody = { ...requestData, scenario_id: scenarioId };

      console.log('전화 발신 요청:', requestData);

      const response = await fetch('/api/fishing_request', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(extendedBody)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || '전화 발신에 실패했습니다.');
      }

      const data: CallResponse = await response.json();
      setCallResponse(data);
      
      console.log('전화 발신 성공:', data);
      if (data.call_sid) {
        // Socket.IO 룸 참여 -> Twilio에서 call_sid별 이벤트 분리 가능 시 확장
        joinCallRoom(data.call_sid);
      }

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      setError(errorMessage);
      console.error('전화 발신 오류:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const formatPhoneNumber = (value: string) => {
    // E.164 형식 유지하면서 입력 도움
    let cleaned = value.replace(/[^\d+]/g, '');
    if (!cleaned.startsWith('+')) {
      cleaned = '+' + cleaned;
    }
    return cleaned;
  };

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          📞 실제 전화 발신
          <div className={`px-2 py-1 rounded text-sm ${
            isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            Socket: {isConnected ? '연결됨' : '연결 해제됨'}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 전화번호 입력 */}
        <div className="space-y-2">
          <Label htmlFor="phone">전화번호 (E.164 형식)</Label>
          <Input
            id="phone"
            type="tel"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(formatPhoneNumber(e.target.value))}
            placeholder="+821012345678"
            className="font-mono"
          />
          <p className="text-sm text-gray-500">
            예: +821012345678 (한국), +81312345678 (일본), +16175551234 (미국)
          </p>
        </div>

        {/* 업체명 입력 */}
        <div className="space-y-2">
          <Label htmlFor="business">낚시터/업체명</Label>
          <Input
            id="business"
            type="text"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            placeholder="해맞이 낚시터"
          />
        </div>

        {/* 예약 요청 내용 */}
        <div className="space-y-2">
          <Label htmlFor="request">예약 요청 내용</Label>
          <Textarea
            id="request"
            value={fishingRequest}
            onChange={(e) => setFishingRequest(e.target.value)}
            placeholder="예약하고 싶은 날짜, 시간, 인원수 등을 입력해주세요."
            rows={4}
            className="resize-none"
          />
        </div>

        {/* 시나리오 토글 (테스트 전용) */}
        <div className="space-y-2">
          <Label>테스트 시나리오 선택</Label>
          <div className="flex gap-2 flex-wrap">
            {(['scenario1','scenario2','scenario3'] as const).map(s => (
              <button
                key={s}
                type="button"
                onClick={()=>setScenarioId(s)}
                className={`px-3 py-1 rounded border text-sm transition-colors ${
                  scenarioId === s
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white hover:bg-blue-50 border-gray-300'
                }`}
              >
                {s === 'scenario1' && 'Scenario 1'}
                {s === 'scenario2' && 'Scenario 2'}
                {s === 'scenario3' && 'Scenario 3'}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-500">시나리오 모드가 활성화된 경우 선택된 스크립트로 진행됩니다.</p>
          {scenarioProgress && (
            <div className="text-xs text-gray-600 flex items-center gap-2">
              <span>진행: {scenarioProgress.consumed}/{scenarioProgress.total}</span>
              {scenarioProgress.is_complete && <span className="text-green-600">(완료)</span>}
            </div>
          )}
        </div>

        {/* 전화 발신 버튼 */}
        <Button 
          onClick={handleMakeCall}
          disabled={isLoading || !phoneNumber.trim() || !businessName.trim() || !fishingRequest.trim()}
          className="w-full bg-blue-600 hover:bg-blue-700"
        >
          {isLoading ? (
            <>
              <span className="animate-spin mr-2">⏳</span>
              전화 연결 중...
            </>
          ) : (
            <>
              📞 전화 걸기
            </>
          )}
        </Button>

        {/* 응답 결과 */}
        {callResponse && (
          <div className="p-4 bg-green-50 border border-green-200 rounded">
            <h4 className="font-medium text-green-800 mb-2">✅ 전화 발신 성공</h4>
            <p className="text-sm text-green-700">{callResponse.message}</p>
            {callResponse.call_sid && (
              <p className="text-xs text-green-600 mt-1">통화 ID: {callResponse.call_sid}</p>
            )}
          </div>
        )}

        {/* 오류 메시지 */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded">
            <h4 className="font-medium text-red-800 mb-2">❌ 전화 발신 실패</h4>
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* 실시간 통화 상태 */}
        {callStatus && (
          <div className="p-4 bg-blue-50 border border-blue-200 rounded">
            <h4 className="font-medium text-blue-800 mb-2">📊 통화 상태</h4>
            <p className="text-sm text-blue-700">
              <strong>상태:</strong> {callStatus.status}
            </p>
            <p className="text-sm text-blue-700">
              <strong>시간:</strong> {new Date(callStatus.timestamp).toLocaleTimeString()}
            </p>
          </div>
        )}

        {/* 실시간 전사 */}
        {transcription && (
          <div className="p-4 bg-yellow-50 border border-yellow-200 rounded">
            <h4 className="font-medium text-yellow-800 mb-2">🎤 실시간 전사</h4>
            <p className="text-sm text-yellow-700">
              <strong>{transcription.speaker}:</strong> {transcription.text}
              <span className="ml-2 text-xs">
                ({transcription.is_final ? '최종' : '임시'})
              </span>
            </p>
            {latestUserSpeech && (
              <p className="text-xs text-gray-600 mt-2">최근 사용자: {latestUserSpeech}</p>
            )}
          </div>
        )}

        {/* AI 응답 */}
        {aiResponse && (
          <div className="p-4 bg-purple-50 border border-purple-200 rounded">
            <h4 className="font-medium text-purple-800 mb-2">🤖 AI 응답</h4>
            <p className="text-sm text-purple-700 whitespace-pre-wrap">{aiResponse}</p>
          </div>
        )}

        {/* 사용 안내 */}
        <div className="p-4 bg-gray-50 border border-gray-200 rounded">
          <h4 className="font-medium text-gray-800 mb-2">📋 사용 안내</h4>
          <ul className="text-sm text-gray-600 space-y-1">
            <li>• 전화번호는 E.164 형식(+국가코드+번호)으로 입력해주세요</li>
            <li>• Twilio Trial 계정에서는 인증된 번호로만 발신 가능합니다</li>
            <li>• 실제 전화가 연결되면 AI가 자동으로 예약을 진행합니다</li>
            <li>• 통화 내용은 실시간으로 전사되어 표시됩니다</li>
            <li>• 선택된 Scenario가 있다면 해당 스크립트를 순서대로 재생 후 자동 종료됩니다</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}