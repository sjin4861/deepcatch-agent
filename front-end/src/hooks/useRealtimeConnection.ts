/**
 * 실시간 Socket.IO 연결을 관리하는 React Hook
 * 
 * 이 훅은 백엔드의 Socket.IO 서버와 연결하여 실시간 데이터를 주고받습니다.
 * 통화 상태, 전사 결과, AI 응답 등을 실시간으로 수신합니다.
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

// Socket.IO 이벤트 타입 정의
interface CallStatusUpdate {
  call_sid: string;
  status: string;
  timestamp: string;
  data: Record<string, any>;
}

interface TranscriptionUpdate {
  call_sid: string;
  text: string;
  is_final: boolean;
  speaker: string;
  timestamp: string;
}

interface AIResponseUpdate {
  call_sid: string;
  response: string;
  is_complete: boolean;
  timestamp: string;
}

interface ConversationStateUpdate {
  call_sid: string;
  state: Record<string, any>;
  timestamp: string;
}

interface ScenarioProgressUpdate {
  call_sid: string;
  scenario_id: string;
  consumed: number;
  total: number;
  is_complete: boolean;
}

// Hook의 반환 타입
interface UseRealtimeConnectionReturn {
  // 연결 상태
  isConnected: boolean;
  connectionError: string | null;
  
  // 통화 상태
  isCallActive: boolean;
  callError: string | null;
  
  // 데이터 상태
  callStatus: CallStatusUpdate | null;
  transcription: TranscriptionUpdate | null;
  aiResponse: string;
  conversationState: ConversationStateUpdate | null;
  sessionId: string | null;
  latestUserSpeech: string; // Twilio 사용자 발화 최신 텍스트
  conversation: ConversationTurn[]; // 멀티턴 대화 (실시간)
  scenarioProgress: ScenarioProgressUpdate | null;
  hasAIStreamingBegun: boolean;
  slots: Record<string, any> | null;
  callEnded: boolean;
  
  // 액션 함수들
  joinCallRoom: (callSid: string) => void;
  leaveCallRoom: (callSid: string) => void;
  clearData: () => void;
  startCall: () => void;
  stopCall: () => void;
  sendText: (text: string) => void;
}

// 멀티턴 대화 턴 타입
export interface ConversationTurn {
  id: string;
  role: 'user' | 'assistant';
  text: string; // 현재까지 누적(assistant 스트리밍 포함)
  isStreaming: boolean; // assistant 응답이 아직 진행 중인지 표시
}

// 환경변수에서 Socket.IO 서버 URL 가져오기
const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:8000';

export const useRealtimeConnection = (): UseRealtimeConnectionReturn => {
  // 상태 관리
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [isCallActive, setIsCallActive] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [callStatus, setCallStatus] = useState<CallStatusUpdate | null>(null);
  const [transcription, setTranscription] = useState<TranscriptionUpdate | null>(null);
  const [aiResponse, setAIResponse] = useState<string>('');
  const [latestUserSpeech, setLatestUserSpeech] = useState<string>('');
  const [conversationState, setConversationState] = useState<ConversationStateUpdate | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationTurn[]>([]);
  const [scenarioProgress, setScenarioProgress] = useState<ScenarioProgressUpdate | null>(null);
  const [hasAIStreamingBegun, setHasAIStreamingBegun] = useState(false);
  const [slots, setSlots] = useState<Record<string, any> | null>(null);
  const [callEnded, setCallEnded] = useState(false);
  
  // Socket 인스턴스 관리
  const socketRef = useRef<Socket | null>(null);
  const currentCallSidRef = useRef<string | null>(null);
  
  // Socket 연결 초기화
  useEffect(() => {
    console.log('🔌 Socket.IO 연결 초기화 시작:', SOCKET_URL);
    
    // Socket.IO 클라이언트 생성
    const socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
      timeout: 20000,
    });
    
    socketRef.current = socket;
    
    // 연결 이벤트 핸들러
    socket.on('connect', () => {
      console.log('✅ Socket.IO 연결 성공:', socket.id);
      setIsConnected(true);
      setConnectionError(null);
    });
    
    socket.on('disconnect', (reason) => {
      console.log('❌ Socket.IO 연결 해제:', reason);
      setIsConnected(false);
      if (reason === 'io server disconnect') {
        setConnectionError('서버에서 연결을 종료했습니다');
      }
    });
    
    socket.on('connect_error', (error) => {
      console.error('🚨 Socket.IO 연결 오류:', error);
      setConnectionError(`연결 오류: ${error.message}`);
      setIsConnected(false);
    });
    
    // 서버 확인 메시지
    socket.on('connection_confirmed', (data) => {
      console.log('✅ 서버 연결 확인:', data);
    });
    
    // 통화 상태 업데이트 수신
    socket.on('call_status_update', (data: CallStatusUpdate) => {
      console.log('📞 통화 상태 업데이트:', data);
      setCallStatus(data);
    });

    // Twilio: 사용자 발화 (server emits 'user_speech')
    socket.on('user_speech', (data: { text: string }) => {
      console.log('🗣️ 사용자 발화 수신 (Twilio):', data);
      setLatestUserSpeech(data.text);
      // transcription 상태에도 반영 (speaker 구분)
      setTranscription({
        call_sid: currentCallSidRef.current || 'twilio-call',
        text: data.text,
        is_final: true,
        speaker: 'user',
        timestamp: new Date().toISOString(),
      });
      // 멀티턴 대화 추가
      setConversation(prev => [...prev, {
        id: `user-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
        role: 'user',
        text: data.text,
        isStreaming: false,
      }]);
    });

    // Twilio: AI 응답 (server emits 'ai_response')
    socket.on('ai_response', (data: { text: string }) => {
      console.log('🤖 Twilio AI 응답 수신:', data);
      setAIResponse(data.text);
      setTranscription({
        call_sid: currentCallSidRef.current || 'twilio-call',
        text: data.text,
        is_final: true,
        speaker: 'assistant',
        timestamp: new Date().toISOString(),
      });
      // Twilio 단발 assistant 응답을 확정 턴으로 추가
      setConversation(prev => [...prev, {
        id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
        role: 'assistant',
        text: data.text,
        isStreaming: false,
      }]);
    });

    // Twilio: 통화 종료
    socket.on('call_ended', (data: { call_sid?: string }) => {
      console.log('📴 Twilio 통화 종료 이벤트 수신:', data);
      setIsCallActive(false);
      currentCallSidRef.current = null;
      setCallEnded(true);
    });
    
    // 실시간 전사 결과 수신
    socket.on('transcription_update', (data: TranscriptionUpdate) => {
      console.log('🎤 전사 업데이트:', data);
      setTranscription(data);
    });
    
    // AI 응답 스트리밍 수신
    socket.on('ai_response_update', (data: AIResponseUpdate) => {
      console.log('🤖 AI 응답 업데이트:', data);
      
      if (data.is_complete) {
        // 완료된 응답인 경우 전체 교체
        setAIResponse(data.response);
      } else {
        // 스트리밍 중인 경우 추가
        setAIResponse(prev => prev + data.response);
      }
    });
    
    // 대화 상태 업데이트 수신
    socket.on('conversation_state_update', (data: ConversationStateUpdate) => {
      console.log('💬 대화 상태 업데이트:', data);
      setConversationState(data);
    });
    
    // 룸 참여 확인
    socket.on('room_joined', (data) => {
      console.log('🏠 룸 참여 확인:', data);
    });

    // OpenAI 통화 시작 성공
    socket.on('call_started', (data) => {
      console.log('📞 통화 시작됨:', data);
      setIsCallActive(true);
      setCallError(null);
    });

    // OpenAI 통화 종료
    socket.on('call_stopped', (data) => {
      console.log('📞 통화 종료됨:', data);
      setIsCallActive(false);
      setCallError(null);
      setSessionId(null);
    });

    // OpenAI 통화 오류
    socket.on('call_error', (data) => {
      console.error('🚨 통화 오류:', data);
      setCallError(data.error);
      setIsCallActive(false);
    });

    // OpenAI 세션 생성
    socket.on('session_created', (data) => {
      console.log('🔗 OpenAI 세션 생성:', data);
      setSessionId(data.session_id);
    });

    // OpenAI 전사 업데이트 (새로운 형식)
    socket.on('transcription_update', (data: { text: string; is_final: boolean }) => {
      console.log('🎤 OpenAI 전사:', data);
      setTranscription({
        call_sid: 'openai-realtime',
        text: data.text,
        is_final: data.is_final,
        speaker: 'user',
        timestamp: new Date().toISOString(),
      });
    });

    // OpenAI AI 응답 텍스트 델타
    socket.on('ai_response_text', (data: { text_delta: string }) => {
      console.log('🤖 AI 텍스트 델타:', data);
      setAIResponse(prev => prev + data.text_delta);
      setHasAIStreamingBegun(true);
      setConversation(prev => {
        const delta = data.text_delta ?? '';
        const trimmed = delta.replace(/\r?\n/g, '');
        // 비어있는 델타(공백/UI에 보이지 않는)면 기존 스트리밍 턴 없을 때만 placeholder 턴 생성
        if (prev.length > 0) {
          const last = prev[prev.length - 1];
          if (last.role === 'assistant' && last.isStreaming) {
            if (delta.length === 0) return prev; // 아무 변화 없음
            const updated = { ...last, text: last.text + delta };
            return [...prev.slice(0, -1), updated];
          }
        }
        if (trimmed.length === 0) {
          // placeholder 턴 (나중에 complete에서 교체 가능)
          return [...prev, {
            id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
            role: 'assistant',
            text: '',
            isStreaming: true,
          }];
        }
        return [...prev, {
          id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
          role: 'assistant',
          text: delta,
          isStreaming: true,
        }];
      });
    });

    // OpenAI AI 응답 완료
    socket.on('ai_response_complete', (data: { text: string }) => {
      console.log('✅ AI 응답 완료:', data);
      setAIResponse(data.text);
      setConversation(prev => {
        if (prev.length === 0) {
          // 초기 인사 (greeting) 케이스
          return [{
            id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
            role: 'assistant',
            text: data.text,
            isStreaming: false,
          }];
        }
        const last = prev[prev.length - 1];
        if (last.role === 'assistant') {
          const updated = { ...last, text: data.text, isStreaming: false };
          return [...prev.slice(0, -1), updated];
        }
        return [...prev, {
          id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
          role: 'assistant',
          text: data.text,
          isStreaming: false,
        }];
      });
    });

    // OpenAI 오디오 응답
    socket.on('ai_response_audio', (data: { audio_length: number }) => {
      console.log('🔊 AI 오디오 수신:', data);
    });

    // OpenAI 음성 시작/종료
    socket.on('speech_started', () => {
      console.log('🎙️ 음성 입력 시작');
    });

    socket.on('speech_stopped', () => {
      console.log('🛑 음성 입력 종료');
    });

    // OpenAI 오류
    socket.on('openai_error', (data: { error: string }) => {
      console.error('🚨 OpenAI 오류:', data);
      setCallError(data.error);
    });

    // 시나리오 진행 상황
    socket.on('scenario_progress', (data: ScenarioProgressUpdate) => {
      console.log('📊 시나리오 진행:', data);
      setScenarioProgress(data);
    });

    // AI 응답 시작 (시나리오/스트리밍 공통 프리앰블)
    socket.on('ai_response_begin', (data: { call_sid?: string }) => {
      console.log('🚧 AI 응답 시작 이벤트:', data);
      // 직전 assistant 스트리밍이 완료되지 않았다면 그대로 두고, 모두 완료된 상태면 새 placeholder 생성
      setAIResponse('');
      setHasAIStreamingBegun(true);
      setConversation(prev => {
        if (prev.length > 0) {
          const last = prev[prev.length - 1];
          if (last.role === 'assistant' && last.isStreaming) {
            // 이미 스트리밍 중이면 중복 생성 방지
            return prev;
          }
        }
        return [...prev, {
          id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
          role: 'assistant',
          text: '',
          isStreaming: true,
        }];
      });
    });

    // 슬롯 추출 완료
    socket.on('call_slots_extracted', (data: { call_sid?: string; slots: Record<string, any> }) => {
      console.log('🎯 슬롯 추출 완료:', data);
      setSlots(data.slots || {});
    });

    socket.on('call_slots_error', (data: { call_sid?: string; error: string }) => {
      console.warn('⚠️ 슬롯 추출 오류:', data);
    });
    
    // 정리 함수
    return () => {
      console.log('🧹 Socket.IO 연결 정리');
      socket.disconnect();
    };
  }, []);
  
  // 통화 룸 참여
  const joinCallRoom = useCallback((callSid: string) => {
    if (!socketRef.current) {
      console.warn('⚠️ Socket이 연결되지 않음');
      return;
    }
    
    console.log('🚪 통화 룸 참여:', callSid);
    currentCallSidRef.current = callSid;
    
    socketRef.current.emit('join_call_room', { call_sid: callSid });
  }, []);
  
  // 통화 룸 나가기
  const leaveCallRoom = useCallback((callSid: string) => {
    if (!socketRef.current) {
      console.warn('⚠️ Socket이 연결되지 않음');
      return;
    }
    
    console.log('🚪 통화 룸 나가기:', callSid);
    currentCallSidRef.current = null;
    
    socketRef.current.emit('leave_call_room', { call_sid: callSid });
  }, []);
  
  // 데이터 초기화
  const clearData = useCallback(() => {
    console.log('🧹 실시간 데이터 초기화');
    setCallStatus(null);
    setTranscription(null);
    setAIResponse('');
    setConversation([]);
    setConversationState(null);
    setCallError(null);
    setSessionId(null);
    setHasAIStreamingBegun(false);
    setSlots(null);
    setCallEnded(false);
  }, []);

  // OpenAI 통화 시작
  const startCall = useCallback(() => {
    if (!socketRef.current) {
      console.warn('⚠️ Socket이 연결되지 않음');
      setCallError('Socket 연결이 필요합니다');
      return;
    }

    if (isCallActive) {
      console.warn('⚠️ 이미 통화가 활성화됨');
      return;
    }

    console.log('📞 OpenAI 통화 시작 요청');
    setCallError(null);
    socketRef.current.emit('start_call');
  }, [isCallActive]);

  // OpenAI 통화 종료
  const stopCall = useCallback(() => {
    if (!socketRef.current) {
      console.warn('⚠️ Socket이 연결되지 않음');
      return;
    }

    if (!isCallActive) {
      console.warn('⚠️ 활성화된 통화가 없음');
      return;
    }

    console.log('📞 OpenAI 통화 종료 요청');
    socketRef.current.emit('stop_call');
  }, [isCallActive]);

  // 텍스트 메시지 전송
  const sendText = useCallback((text: string) => {
    if (!socketRef.current) {
      console.warn('⚠️ Socket이 연결되지 않음');
      setCallError('Socket 연결이 필요합니다');
      return;
    }

    if (!isCallActive) {
      console.warn('⚠️ 활성화된 통화가 없음');
      setCallError('통화가 활성화되지 않았습니다');
      return;
    }

    console.log('📝 텍스트 메시지 전송:', text);
    socketRef.current.emit('send_text', { text });
  }, [isCallActive]);
  
  return {
    isConnected,
    connectionError,
    isCallActive,
    callError,
    callStatus,
    transcription,
    aiResponse,
    conversationState,
    sessionId,
    // 추가 노출: 최근 사용자 발화 (Twilio)
    latestUserSpeech,
    joinCallRoom,
    leaveCallRoom,
    clearData,
    startCall,
    stopCall,
    sendText,
    conversation,
    scenarioProgress,
    hasAIStreamingBegun,
    slots,
    callEnded,
  };
};