'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Mic, Bot, AlertCircle } from 'lucide-react';
import { useRealtimeConnection } from '@/hooks/useRealtimeConnection';

// 대화 기록 타입 정의
interface ConversationEntry {
  speaker: 'user' | 'ai';
  text: string;
  timestamp: string;
  is_final: boolean;
}

// 화자별 스타일 설정
const speakerDetails = {
  user: {
    name: 'Caller',
    style: 'text-blue-600',
    icon: Mic,
  },
  ai: {
    name: 'AI Agent',
    style: 'text-green-600',
    icon: Bot,
  },
};

export default function RealtimeTranscription() {
  // 실시간 연결 Hook 사용
  const { 
    isConnected, 
    connectionError, 
    transcription, 
    aiResponse,
    callStatus 
  } = useRealtimeConnection();
  
  // 대화 기록 상태 관리
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // 전사 결과가 업데이트될 때 대화 기록에 추가
  useEffect(() => {
    if (transcription && transcription.is_final) {
      const newEntry: ConversationEntry = {
        speaker: 'user',
        text: transcription.text,
        timestamp: transcription.timestamp,
        is_final: true,
      };
      
      setConversation(prev => [...prev, newEntry]);
    }
  }, [transcription]);

  // AI 응답이 완료될 때 대화 기록에 추가
  useEffect(() => {
    if (aiResponse && aiResponse.trim()) {
      // AI 응답 중복 방지를 위해 마지막 항목이 AI인지 확인
      setConversation(prev => {
        const lastEntry = prev[prev.length - 1];
        if (lastEntry && lastEntry.speaker === 'ai') {
          // 마지막 AI 응답 업데이트
          return prev.map((entry, index) => 
            index === prev.length - 1 
              ? { ...entry, text: aiResponse }
              : entry
          );
        } else {
          // 새로운 AI 응답 추가
          const newEntry: ConversationEntry = {
            speaker: 'ai',
            text: aiResponse,
            timestamp: new Date().toISOString(),
            is_final: true,
          };
          return [...prev, newEntry];
        }
      });
    }
  }, [aiResponse]);

  // 자동 스크롤
  useEffect(() => {
    if (scrollAreaRef.current) {
      const viewport = scrollAreaRef.current.querySelector('div');
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
      }
    }
  }, [conversation, transcription]);

  // 상태 메시지 렌더링
  const renderStatus = () => {
    if (connectionError) {
      return (
        <div className="flex items-center justify-center h-full text-red-500">
          <AlertCircle className="w-5 h-5 mr-2" />
          <p>연결 오류: {connectionError}</p>
        </div>
      );
    }
    
    if (!isConnected) {
      return (
        <div className="flex items-center justify-center h-full text-muted-foreground">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-gray-900 mr-2"></div>
          <p>실시간 서버에 연결 중...</p>
        </div>
      );
    }
    
    if (!callStatus || callStatus.status === 'initiated') {
      return (
        <div className="flex items-center justify-center h-full text-muted-foreground">
          <p>통화 시작을 기다리는 중...</p>
        </div>
      );
    }
    
    if (conversation.length === 0) {
      return (
        <div className="flex items-center justify-center h-full text-muted-foreground">
          <p>대화 내용이 여기에 실시간으로 표시됩니다...</p>
        </div>
      );
    }
    
    return null;
  };

  const status = renderStatus();

  return (
    <Card className="flex-1 flex flex-col min-h-[400px]">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Mic className="text-accent" />
          실시간 전사
        </CardTitle>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span className="text-sm text-muted-foreground">
            {isConnected ? '연결됨' : '연결 해제됨'}
          </span>
          {callStatus && (
            <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
              {callStatus.status}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col min-h-0">
        <ScrollArea className="flex-1 pr-4 -mr-4" ref={scrollAreaRef}>
          <div className="space-y-4">
            {status ? (
              status
            ) : (
              <>
                {/* 확정된 대화 기록 */}
                {conversation.map((entry, index) => {
                  const SpeakerIcon = speakerDetails[entry.speaker].icon;
                  return (
                    <div key={index} className="flex flex-col space-y-1">
                      <div className="flex items-center gap-2">
                        <SpeakerIcon className="w-4 h-4" />
                        <span className={`font-medium ${speakerDetails[entry.speaker].style}`}>
                          {speakerDetails[entry.speaker].name}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(entry.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-foreground pl-6 whitespace-pre-wrap">
                        {entry.text}
                      </p>
                    </div>
                  );
                })}
                
                {/* 실시간 전사 진행 중 (임시) */}
                {transcription && !transcription.is_final && (
                  <div className="flex flex-col space-y-1 opacity-70">
                    <div className="flex items-center gap-2">
                      <Mic className="w-4 h-4" />
                      <span className="font-medium text-blue-600">
                        Caller (실시간)
                      </span>
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                    </div>
                    <p className="text-foreground pl-6 italic">
                      {transcription.text}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
