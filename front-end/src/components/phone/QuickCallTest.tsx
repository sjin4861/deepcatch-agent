'use client';

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useRealtimeConnection } from '@/hooks/useRealtimeConnection';

/**
 * QuickCallTest
 * - 페이지 로드 후 바로 한 번에 테스트 콜을 눌러 스트리밍 흐름 검증하기 위한 최소 UI
 * - 환경변수 NEXT_PUBLIC_TEST_PHONE_NUMBER 없으면 입력창 제공
 * - 나중에 쉽게 제거 가능 (단일 파일 + page.tsx import 한 줄)
 */
export default function QuickCallTest() {
  const envNumber = process.env.NEXT_PUBLIC_TEST_PHONE_NUMBER || '';
  const [phone, setPhone] = useState(envNumber);
  const [loading, setLoading] = useState(false);
  const [callSid, setCallSid] = useState<string | null>(null);
  const { transcription, aiResponse, isConnected, latestUserSpeech, scenarioProgress } = useRealtimeConnection();
  const [scenarioId, setScenarioId] = useState<string>('scenario1');
  const [autoTriggered, setAutoTriggered] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string>('준비됨');

  // 자동 실행 옵션: env 에 NEXT_PUBLIC_AUTO_CALL === 'true'
  useEffect(() => {
    if (!autoTriggered && process.env.NEXT_PUBLIC_AUTO_CALL === 'true' && envNumber) {
      setAutoTriggered(true);
      void handleCall();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [envNumber, autoTriggered]);

  const handleCall = async () => {
    if (!phone.trim()) {
      setError('전화번호가 필요합니다.');
      return;
    }
    setError(null);
    setLoading(true);
    setStatusMsg('통화 요청 중...');
    try {
      const body = {
        to_phone: phone.trim(),
        business_name: 'QuickTest',
        fishing_request: '테스트 통화입니다. 시스템 스트리밍 검증.',
        scenario_id: scenarioId,
      };
      const res = await fetch('/api/fishing_request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || '실패');
      }
      setCallSid(data.call_sid || null);
      setStatusMsg('통화 연결 시도 중 (Twilio)...');
    } catch (e:any) {
      setError(e.message);
      setStatusMsg('오류 발생');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-sm md:text-base">
          🚀 빠른 콜 스트리밍 테스트
          <span className={`px-2 py-0.5 rounded text-xs ${isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>Socket {isConnected ? 'OK' : 'OFF'}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex gap-2 flex-wrap">
          {!envNumber && (
            <input
              value={phone}
              onChange={e=>setPhone(e.target.value)}
              placeholder="+8210..."
              className="flex-1 border rounded px-2 py-1 text-xs"
            />
          )}
          <select
            value={scenarioId}
            onChange={e=>setScenarioId(e.target.value)}
            className="border rounded px-2 py-1 text-xs bg-background"
          >
            <option value="scenario1">Scenario 1 (기본)</option>
            <option value="scenario2">Scenario 2 (추석 선상 문의)</option>
            <option value="scenario3">Scenario 3 (예약 확정)</option>
          </select>
          <Button disabled={loading || !phone} onClick={()=>void handleCall()} className="text-xs">
            {loading ? '요청 중...' : '테스트 Call'}
          </Button>
        </div>
        {callSid && <p className="text-xs text-gray-600">call_sid: {callSid}</p>}
        <p className="text-xs">상태: {statusMsg}</p>
        {error && <p className="text-xs text-red-600">에러: {error}</p>}
        <div className="border rounded p-2 bg-muted/30">
          <p className="font-medium mb-1">실시간 사용자 발화</p>
          <div className="text-xs whitespace-pre-wrap min-h-[32px]">{latestUserSpeech || '(대기 중)'}</div>
        </div>
        <div className="border rounded p-2 bg-muted/30">
          <p className="font-medium mb-1">AI 스트리밍 (누적)</p>
          <div className="text-xs whitespace-pre-wrap min-h-[48px]">{aiResponse || '(대기 중)'}</div>
        </div>
        {scenarioProgress && (
          <div className="border rounded p-2 bg-muted/20 flex items-center justify-between">
            <div className="text-[11px]">시나리오: {scenarioProgress.scenario_id}</div>
            <div className="text-[11px]">진행: {scenarioProgress.consumed}/{scenarioProgress.total} {scenarioProgress.is_complete && '(완료)'}</div>
          </div>
        )}
        {transcription && (
          <div className="border rounded p-2 bg-muted/20">
            <p className="font-medium mb-1">최근 전사 객체</p>
            <pre className="text-[10px] overflow-auto max-h-32">{JSON.stringify(transcription, null, 2)}</pre>
          </div>
        )}
        <p className="text-[10px] text-gray-400">※ 이 컴포넌트는 임시 테스트용입니다. 안정화 후 제거하세요.</p>
      </CardContent>
    </Card>
  );
}
