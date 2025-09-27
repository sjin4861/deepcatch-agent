// Simple WebSocket client for use in Next.js front-end
// Usage: import { useCallSocket } from '@/lib/socket-client';
import { useEffect, useRef, useState, useCallback } from 'react';

export type TranscriptSegment = {
    speaker: string;
    text: string;
    timestamp?: string;
};

export type CallSocketState = {
    connected: boolean;
    hasAttempted: boolean;
    segments: TranscriptSegment[];
    isCalling: boolean;
    error: string | null;
    startCall: () => void;
    stopCall: () => void;
    reset: () => void;
};

type SocketMessage =
    | { type: 'ready' }
    | { type: 'transcription_segment'; segment: TranscriptSegment; index?: number; done?: boolean }
    | { type: 'transcription_done' }
    | { type: 'error'; message: string }
    | { type: 'status'; status: string };

const WS_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'ws://localhost:9003';
const isBrowser = typeof window !== 'undefined';

export function useCallSocket(): CallSocketState {
    const [connected, setConnected] = useState(false);
    const [hasAttempted, setHasAttempted] = useState(false);
    const [segments, setSegments] = useState<TranscriptSegment[]>([]);
    const [isCalling, setIsCalling] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const pendingMessagesRef = useRef<string[]>([]);
    const closingRef = useRef(false);

    const flushPendingMessages = useCallback(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            while (pendingMessagesRef.current.length > 0) {
                const payload = pendingMessagesRef.current.shift();
                if (payload) {
                    wsRef.current.send(payload);
                }
            }
        }
    }, []);

    const cleanupSocket = useCallback((options: { close?: boolean; resetAttempt?: boolean } = {}) => {
        const { close = false, resetAttempt = false } = options;
        closingRef.current = close;
        if (wsRef.current) {
            if (close && wsRef.current.readyState === WebSocket.OPEN) {
                wsRef.current.close();
            }
            wsRef.current = null;
        }
        setConnected(false);
        setIsCalling(false);
        if (resetAttempt) {
            setHasAttempted(false);
        }
        pendingMessagesRef.current = [];
    }, []);

    const handleSocketError = useCallback((message = 'WebSocket error') => {
        setError(message);
        setIsCalling(false);
    }, []);

    const handleMessage = useCallback((event: MessageEvent) => {
        try {
            const parsed = typeof event.data === 'string' ? event.data : event.data.toString();
            const data: SocketMessage = JSON.parse(parsed);
            switch (data.type) {
                case 'transcription_segment':
                    setSegments(prev => [...prev, data.segment]);
                    break;
                case 'transcription_done':
                    setIsCalling(false);
                    break;
                case 'status':
                    if (data.status === 'ready') {
                        setConnected(true);
                        setError(null);
                    }
                    break;
                case 'error':
                    handleSocketError(data.message ?? 'Socket error');
                    break;
                case 'ready':
                    setConnected(true);
                    setError(null);
                    break;
                default:
                    break;
            }
        } catch (err) {
            handleSocketError('Malformed message from call service');
        }
    }, [handleSocketError]);

    const ensureSocket = useCallback(() => {
        if (!isBrowser) {
            return;
        }
        if (wsRef.current) {
            const state = wsRef.current.readyState;
            if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) {
                return;
            }
        }

        try {
            const ws = new WebSocket(WS_URL);
            wsRef.current = ws;

            ws.onopen = () => {
                setConnected(true);
                setError(null);
                flushPendingMessages();
            };

            ws.onclose = () => {
                const wasClosing = closingRef.current;
                cleanupSocket();
                closingRef.current = false;
                if (!wasClosing && hasAttempted) {
                    handleSocketError('Call service disconnected');
                }
            };

            ws.onerror = () => {
                handleSocketError();
                cleanupSocket();
            };

            ws.onmessage = handleMessage;
        } catch (err) {
            handleSocketError('Failed to connect to call service');
        }
    }, [cleanupSocket, flushPendingMessages, handleMessage, handleSocketError, hasAttempted]);

    useEffect(() => {
        return () => {
            cleanupSocket({ close: true, resetAttempt: true });
        };
    }, [cleanupSocket]);

    const queueMessage = useCallback((payload: unknown) => {
        const message = JSON.stringify(payload);
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(message);
        } else {
            pendingMessagesRef.current.push(message);
            ensureSocket();
        }
    }, [ensureSocket]);

    const startCall = useCallback(() => {
        setSegments([]);
        setIsCalling(true);
        setError(null);
        setHasAttempted(true);
        ensureSocket();
        queueMessage({ type: 'start_call' });
    }, [ensureSocket, queueMessage]);

    const reset = useCallback(() => {
        setSegments([]);
        setIsCalling(false);
        setError(null);
        setHasAttempted(false);
    }, []);

    const stopCall = useCallback(() => {
        setIsCalling(false);
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'stop_call' }));
        }
    }, []);

    return {
        connected,
        hasAttempted,
        segments,
        isCalling,
        error,
        startCall,
        stopCall,
        reset,
    };
}
