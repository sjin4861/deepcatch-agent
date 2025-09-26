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
import { useCallSocket, type TranscriptSegment } from '@/lib/socket-client';

export type { TranscriptSegment } from '@/lib/socket-client';

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
    hasAttempted: boolean;
};

const TranscriptionContext = createContext<TranscriptionContextValue | null>(null);

type ProviderProps = {
    children: ReactNode;
};

export function TranscriptionProvider({
    children,
}: ProviderProps) {
    const [isActive, setIsActive] = useState(false);
    const [hasCompleted, setHasCompleted] = useState(false);
    const isMountedRef = useRef(true);

    const {
        connected,
        hasAttempted,
        segments,
        isCalling,
        error,
        startCall,
        stopCall,
        reset,
    } = useCallSocket();

    const start = useCallback(async () => {
        if (!isMountedRef.current) return;
        setHasCompleted(false);
        setIsActive(true);
        startCall();
    }, [startCall]);

    const stop = useCallback(() => {
        if (!isMountedRef.current) return;
        setIsActive(false);
        setHasCompleted(true);
        stopCall();
        reset();
    }, [reset, stopCall]);

    const refresh = useCallback(async () => {
        if (!isMountedRef.current) return;
        reset();
        setHasCompleted(false);
        setIsActive(true);
        startCall();
    }, [reset, startCall]);

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

    useEffect(() => {
        return () => {
            isMountedRef.current = false;
            reset();
        };
    }, [reset]);

    const value = useMemo<TranscriptionContextValue>(() => {
        const transcript = segments
            .map(segment => `${segment.speaker}: ${segment.text}`)
            .join('\n');
        const isLoading = isActive && segments.length === 0 && !hasCompleted && !error;
        return {
            segments,
            transcript,
            isLoading,
            error,
            refresh,
            start,
            stop,
            isActive,
            isConnected: connected,
            hasAttempted,
        };
    }, [segments, isActive, hasCompleted, error, refresh, start, stop, connected, hasAttempted]);

    return (
        <TranscriptionContext.Provider value={value}>
            {children}
        </TranscriptionContext.Provider>
    );
}

export function useTranscription() {
    const context = useContext(TranscriptionContext);
    if (!context) {
        throw new Error('useTranscription must be used within a TranscriptionProvider');
    }
    return context;
}
