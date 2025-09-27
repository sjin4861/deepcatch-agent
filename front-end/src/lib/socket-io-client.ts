import { useEffect, useRef, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';

export interface AIStreamSegment {
  role: 'user' | 'assistant';
  text: string;
  final?: boolean;
  ts?: string;
}

export interface UseSocketIOOptions {
  url?: string;
  path?: string;
}

export function useSocketIO(options: UseSocketIOOptions = {}) {
  const { url = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:8000', path = '/socket.io' } = options;
  const socketRef = useRef<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [segments, setSegments] = useState<AIStreamSegment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isCalling, setIsCalling] = useState(false);
  const pendingAssistantRef = useRef<string>('');

  useEffect(() => {
    const s = io(url, { path, transports: ['websocket'] });
    socketRef.current = s;

    s.on('connect', () => { setConnected(true); setError(null); });
    s.on('disconnect', () => { setConnected(false); setIsCalling(false); });

    s.on('call_started', (_d) => { setIsCalling(true); });
    s.on('call_stopped', () => { setIsCalling(false); });

    s.on('user_speech', (d) => {
      if (d?.text) {
        setSegments(prev => [...prev, { role: 'user', text: d.text, ts: d.timestamp }]);
      }
    });
    // 스트리밍 델타
    s.on('ai_response_text', (d) => {
      const delta: string | undefined = d?.text_delta;
      if (!delta) return;
      pendingAssistantRef.current += delta;
      // UI 재렌더 (마지막 segment를 덮어쓰기 대신 별도 가상 segment 유지)
      setSegments(prev => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last && last.role === 'assistant' && !last.final) {
          last.text = pendingAssistantRef.current;
          return copy;
        }
        copy.push({ role: 'assistant', text: pendingAssistantRef.current });
        return copy;
      });
    });
    s.on('ai_response_complete', (d) => {
      const full = d?.text || pendingAssistantRef.current;
      setSegments(prev => [...prev.filter(seg => !(seg.role === 'assistant' && !seg.final && seg.text === pendingAssistantRef.current)), { role: 'assistant', text: full, final: true }]);
      pendingAssistantRef.current = '';
    });
    s.on('openai_error', (d) => { setError(d?.error || 'openai_error'); });
    s.on('call_error', (d) => { setError(d?.error || 'call_error'); setIsCalling(false); });

    return () => { s.disconnect(); };
  }, [url, path]);

  const startCall = useCallback(() => {
    if (!socketRef.current) return;
    if (isCalling) return; // already
    socketRef.current.emit('start_call');
  }, [isCalling]);

  const stopCall = useCallback(() => {
    if (!socketRef.current) return;
    socketRef.current.emit('stop_call');
  }, []);

  const sendUserText = useCallback((text: string) => {
    if (!socketRef.current) return;
    socketRef.current.emit('send_text', { text });
    setSegments(prev => [...prev, { role: 'user', text }]);
  }, []);

  return { connected, segments, error, isCalling, startCall, stopCall, sendUserText };
}
