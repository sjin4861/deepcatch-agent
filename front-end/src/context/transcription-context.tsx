'use client';

import {
    createContext,
    type ReactNode,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from 'react';
import { useSocketIO } from '@/lib/socket-io-client';

export type TranscriptSegment = { speaker: string; text: string; timestamp?: string };
export type TranscriptionContextValue = {
  segments: TranscriptSegment[];
  transcript: string;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  start: () => Promise<void>;
  stop: () => void;
  isActive: boolean;
  isConnected: boolean;
  hasAttempted: boolean; // 유지 (호환성)
};

const TranscriptionContext = createContext<TranscriptionContextValue | null>(null);

export function TranscriptionProvider({
    children,
}: {
    children: ReactNode;
}) {
    const [isActive, setIsActive] = useState(false);
    const [hasCompleted, setHasCompleted] = useState(false);
    const [hasAttempted, setHasAttempted] = useState(false);
    const isMountedRef = useRef(true);

    const { connected, segments: rawSegments, error, isCalling, startCall, stopCall } = useSocketIO();

    // rawSegments (assistant/user) → 기존 형태(speaker) 매핑
    const segments = useMemo<TranscriptSegment[]>(() => {
        return rawSegments.map((s) => ({ speaker: s.role, text: s.text }));
    }, [rawSegments]);

    const start = useCallback(async () => {
        if (!isMountedRef.current) return;
        setHasCompleted(false);
        setIsActive(true);
        setHasAttempted(true);
        startCall();
    }, [startCall]);

    const stop = useCallback(() => {
        if (!isMountedRef.current) return;
        setIsActive(false);
        setHasCompleted(true);
        stopCall();
    }, [stopCall]);

    const refresh = useCallback(async () => {
        if (!isMountedRef.current) return;
        setHasCompleted(false);
        setIsActive(true);
        startCall();
    }, [startCall]);

    useEffect(() => {
        if (!isCalling && isActive && segments.length > 0) {
            setIsActive(false);
            setHasCompleted(true);
        }
    }, [isCalling, isActive, segments.length]);

    useEffect(() => {
        if (error) {
            setIsActive(false);
            setHasCompleted(true);
        }
    }, [error]);

    useEffect(() => () => { isMountedRef.current = false; }, []);

    const value = useMemo<TranscriptionContextValue>(() => {
        const transcript = segments.map(seg => `${seg.speaker}: ${seg.text}`).join('\n');
        const isLoading = isActive && segments.length === 0 && !hasCompleted && !error;
        return { segments, transcript, isLoading, error, refresh, start, stop, isActive, isConnected: connected, hasAttempted };
    }, [segments, isActive, hasCompleted, error, refresh, start, stop, connected, hasAttempted]);

    return <TranscriptionContext.Provider value={value}>{children}</TranscriptionContext.Provider>;
}

export function useTranscription() {
    const ctx = useContext(TranscriptionContext);
    if (!ctx) throw new Error('useTranscription must be used within a TranscriptionProvider');
    return ctx;
}
