/**
 * Socket.IO 연결 디버그 컴포넌트
 * 실시간 연결 상태와 수신된 이벤트들을 확인할 수 있습니다.
 */

'use client';

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useRealtimeConnection } from '@/hooks/useRealtimeConnection';

export default function SocketDebug() {
  const { 
    isConnected, 
    connectionError, 
    isCallActive,
    callError,
    callStatus, 
    transcription, 
    aiResponse,
    conversationState,
    sessionId,
    joinCallRoom, 
    leaveCallRoom, 
    clearData,
    startCall,
    stopCall,
    sendText
  } = useRealtimeConnection();

  const [testCallSid] = useState('test-call-12345');
  const [events, setEvents] = useState<string[]>([]);
  const [testMessage, setTestMessage] = useState('안녕하세요! 낚시 예약 도움이 필요합니다.');

  // 이벤트 로그 추가
  useEffect(() => {
    if (callStatus) {
      setEvents(prev => [...prev, `📞 Call Status: ${callStatus.status} - ${callStatus.data || ''}`]);
    }
  }, [callStatus]);

  useEffect(() => {
    if (transcription) {
      setEvents(prev => [...prev, `🎤 Transcription (${transcription.is_final ? 'final' : 'partial'}): ${transcription.text}`]);
    }
  }, [transcription]);

  useEffect(() => {
    if (aiResponse) {
      setEvents(prev => [...prev, `🤖 AI Response: ${aiResponse.slice(0, 50)}...`]);
    }
  }, [aiResponse]);

  useEffect(() => {
    if (isCallActive) {
      setEvents(prev => [...prev, `📞 OpenAI Call Started`]);
    } else {
      setEvents(prev => [...prev, `📞 OpenAI Call Stopped`]);
    }
  }, [isCallActive]);

  useEffect(() => {
    if (callError) {
      setEvents(prev => [...prev, `❌ Call Error: ${callError}`]);
    }
  }, [callError]);

  useEffect(() => {
    if (sessionId) {
      setEvents(prev => [...prev, `🔗 Session Created: ${sessionId}`]);
    }
  }, [sessionId]);

  const handleJoinRoom = () => {
    joinCallRoom(testCallSid);
    setEvents(prev => [...prev, `🚪 Joining room: ${testCallSid}`]);
  };

  const handleLeaveRoom = () => {
    leaveCallRoom(testCallSid);
    setEvents(prev => [...prev, `🚪 Leaving room: ${testCallSid}`]);
  };

  const handleClearData = () => {
    clearData();
    setEvents([]);
  };

  const handleStartCall = () => {
    startCall();
    setEvents(prev => [...prev, `📞 Starting OpenAI Call...`]);
  };

  const handleStopCall = () => {
    stopCall();
    setEvents(prev => [...prev, `📞 Stopping OpenAI Call...`]);
  };

  const handleSendText = () => {
    if (testMessage.trim()) {
      sendText(testMessage);
      setEvents(prev => [...prev, `📝 Sent text: ${testMessage}`]);
    }
  };

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          Socket.IO 디버그 패널
          <div className="flex gap-2">
            <div className={`px-2 py-1 rounded text-sm ${
              isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
            }`}>
              {isConnected ? '연결됨' : '연결 해제됨'}
            </div>
            <div className={`px-2 py-1 rounded text-sm ${
              isCallActive ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'
            }`}>
              {isCallActive ? '통화 중' : '통화 대기'}
            </div>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 연결 상태 */}
        <div className="space-y-2">
          <h3 className="font-medium">연결 상태</h3>
          <div className="p-3 bg-gray-50 rounded">
            <p><strong>Socket 연결:</strong> {isConnected ? '✅ 연결됨' : '❌ 연결 해제됨'}</p>
            <p><strong>OpenAI 통화:</strong> {isCallActive ? '✅ 활성화됨' : '❌ 비활성화됨'}</p>
            {sessionId && (
              <p><strong>세션 ID:</strong> {sessionId}</p>
            )}
            {connectionError && (
              <p className="text-red-600"><strong>연결 오류:</strong> {connectionError}</p>
            )}
            {callError && (
              <p className="text-red-600"><strong>통화 오류:</strong> {callError}</p>
            )}
          </div>
        </div>

        {/* OpenAI 통화 제어 */}
        <div className="space-y-2">
          <h3 className="font-medium">OpenAI 통화 제어</h3>
          <div className="flex gap-2 flex-wrap">
            <Button 
              onClick={handleStartCall} 
              disabled={!isConnected || isCallActive}
              className="bg-green-600 hover:bg-green-700"
            >
              🔊 Activate Call
            </Button>
            <Button 
              onClick={handleStopCall} 
              disabled={!isConnected || !isCallActive}
              variant="destructive"
            >
              🛑 Stop Call
            </Button>
          </div>
        </div>

        {/* 텍스트 메시지 테스트 */}
        <div className="space-y-2">
          <h3 className="font-medium">텍스트 메시지 테스트</h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={testMessage}
              onChange={(e) => setTestMessage(e.target.value)}
              placeholder="테스트 메시지 입력..."
              className="flex-1 px-3 py-2 border rounded"
              disabled={!isCallActive}
            />
            <Button 
              onClick={handleSendText}
              disabled={!isConnected || !isCallActive || !testMessage.trim()}
            >
              📝 전송
            </Button>
          </div>
        </div>

        {/* 기타 테스트 버튼들 */}
        <div className="space-y-2">
          <h3 className="font-medium">기타 테스트</h3>
          <div className="flex gap-2">
            <Button onClick={handleJoinRoom} disabled={!isConnected} variant="outline">
              테스트 룸 참여
            </Button>
            <Button onClick={handleLeaveRoom} disabled={!isConnected} variant="outline">
              룸 나가기
            </Button>
            <Button onClick={handleClearData} variant="outline">
              데이터 초기화
            </Button>
          </div>
        </div>

        {/* 현재 데이터 상태 */}
        <div className="space-y-2">
          <h3 className="font-medium">현재 데이터</h3>
          <div className="p-3 bg-gray-50 rounded space-y-1 text-sm">
            <p><strong>Call Status:</strong> {callStatus?.status || 'None'}</p>
            <p><strong>Transcription:</strong> {transcription?.text || 'None'}</p>
            <p><strong>AI Response:</strong> {aiResponse ? `${aiResponse.slice(0, 30)}...` : 'None'}</p>
            <p><strong>Conversation State:</strong> {conversationState ? JSON.stringify(conversationState.state).slice(0, 30) + '...' : 'None'}</p>
          </div>
        </div>

        {/* 이벤트 로그 */}
        <div className="space-y-2">
          <h3 className="font-medium">이벤트 로그</h3>
          <div className="h-40 overflow-y-auto p-3 bg-gray-50 rounded text-sm">
            {events.length === 0 ? (
              <p className="text-gray-500">이벤트가 없습니다</p>
            ) : (
              events.map((event, index) => (
                <div key={index} className="py-1 border-b border-gray-200">
                  {event}
                </div>
              ))
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}