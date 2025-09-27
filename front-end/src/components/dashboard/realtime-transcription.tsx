'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Mic } from 'lucide-react';
import { useTranscription } from '@/context/transcription-context';
import type { TranscriptSegment } from '@/context/transcription-context';

const TYPING_INTERVAL_MS = 28;

export default function RealtimeTranscription() {
    const { segments, isLoading, error, refresh, isActive, isConnected, hasAttempted } = useTranscription();
    const scrollAreaRef = useRef<HTMLDivElement>(null);
    const typingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const [displayedSegments, setDisplayedSegments] = useState<TranscriptSegment[]>([]);
    const [segmentProgress, setSegmentProgress] = useState<number[]>([]);
    const segmentProgressRef = useRef<number[]>([]);
    const displayedSegmentsRef = useRef<TranscriptSegment[]>([]);
    const pendingSegmentsRef = useRef<TranscriptSegment[]>([]);
    const startNextSegmentRef = useRef<() => void>(() => {});

    useEffect(() => {
        if (scrollAreaRef.current) {
            const viewport = scrollAreaRef.current.querySelector('div');
            if (viewport) {
                viewport.scrollTop = viewport.scrollHeight;
            }
        }
    }, [displayedSegments.length, segmentProgress]);

    useEffect(() => {
        displayedSegmentsRef.current = displayedSegments;
    }, [displayedSegments]);

    useEffect(() => {
        segmentProgressRef.current = segmentProgress;
    }, [segmentProgress]);

    const stopTyping = useCallback(() => {
        if (typingTimerRef.current) {
            clearInterval(typingTimerRef.current);
            typingTimerRef.current = null;
        }
    }, []);

    const runTick = useCallback(() => {
        let shouldStartNext = false;

        setSegmentProgress(prev => {
            if (prev.length === 0) {
                stopTyping();
                return prev;
            }

            const next = [...prev];
            const lastIndex = next.length - 1;
            const currentSegment = displayedSegmentsRef.current[lastIndex];

            if (!currentSegment) {
                return prev;
            }

            const targetLength = currentSegment.text.length;
            if (next[lastIndex] < targetLength) {
                next[lastIndex] = Math.min(next[lastIndex] + 1, targetLength);
                return next;
            }

            shouldStartNext = true;
            return prev;
        });

        if (shouldStartNext) {
            if (pendingSegmentsRef.current.length > 0) {
                startNextSegmentRef.current();
            } else {
                stopTyping();
            }
        }
    }, [stopTyping]);

    const ensureTimer = useCallback(() => {
        if (!typingTimerRef.current) {
            typingTimerRef.current = setInterval(runTick, TYPING_INTERVAL_MS);
        }
    }, [runTick]);

    const startNextSegment = useCallback(() => {
        if (pendingSegmentsRef.current.length === 0) {
            return;
        }

        const segmentsList = displayedSegmentsRef.current;
        const progressList = segmentProgressRef.current;

        if (segmentsList.length > 0) {
            const lastIndex = segmentsList.length - 1;
            const lastSegment = segmentsList[lastIndex];
            const lastProgress = progressList[lastIndex] ?? 0;

            if (lastSegment && lastProgress < lastSegment.text.length) {
                return;
            }
        }

        const nextSegment = pendingSegmentsRef.current.shift();
        if (!nextSegment) {
            return;
        }

        setDisplayedSegments(prev => [...prev, nextSegment]);
        setSegmentProgress(prev => [...prev, 0]);
        ensureTimer();
    }, [ensureTimer]);

    useEffect(() => {
        startNextSegmentRef.current = startNextSegment;
    }, [startNextSegment]);

    useEffect(() => {
        if (segments.length === 0) {
            pendingSegmentsRef.current = [];
            setDisplayedSegments([]);
            setSegmentProgress([]);
            stopTyping();
            return;
        }

        const knownCount = displayedSegmentsRef.current.length + pendingSegmentsRef.current.length;
        if (segments.length > knownCount) {
            const newSegments = segments.slice(knownCount);
            pendingSegmentsRef.current.push(...newSegments);
            startNextSegment();
        }
    }, [segments, startNextSegment, stopTyping]);

    useEffect(() => () => stopTyping(), [stopTyping]);

    const showIdleState = !isActive && segments.length === 0 && !isLoading && !error;
    const showWaitingState = isActive && !isLoading && !error && segments.length === 0;

    return (
        <Card className="flex-1 flex flex-col min-h-[400px]">
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                    <Mic className="text-accent" />
                    Live Transcription
                </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 flex flex-col min-h-0">
                <ScrollArea className="flex-1 pr-4 -mr-4" ref={scrollAreaRef}>
                    <div className="space-y-4">
                        {hasAttempted && !isConnected && !error && (
                            <div className="flex items-center justify-center h-full text-muted-foreground">
                                <p>Connecting to call service…</p>
                            </div>
                        )}
                        {isLoading && (
                            <div className="flex items-center justify-center h-full text-muted-foreground">
                                <p>Dialing the charter…</p>
                            </div>
                        )}
                        {error && !isLoading && (
                            <div className="flex flex-col items-center justify-center gap-2 h-full text-destructive">
                                <p>Unable to fetch transcription.</p>
                                <button className="underline" onClick={() => refresh()}>
                                    Retry
                                </button>
                            </div>
                        )}
                        {showWaitingState && (
                            <div className="flex items-center justify-center h-full text-muted-foreground">
                                <p>Waiting for the other party to pick up…</p>
                            </div>
                        )}
                        {showIdleState && (
                            <div className="flex items-center justify-center h-full text-muted-foreground">
                                <p>Start a call to see the live conversation here.</p>
                            </div>
                        )}
                        {!isLoading && !error && displayedSegments.length > 0 && (
                            displayedSegments.map((line, index) => {
                                const visibleLength = Math.min(segmentProgress[index] ?? line.text.length, line.text.length);
                                const visibleText = line.text.slice(0, visibleLength);
                                return (
                                    <div key={`${line.speaker}-${index}`} className="flex flex-col">
                                        <span className={`font-bold ${line.speaker.toLowerCase() === 'agent' ? 'text-primary' : 'text-foreground'}`}>
                                            {line.speaker}
                                        </span>
                                        <p className="text-muted-foreground whitespace-pre-wrap">{visibleText}</p>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    );
}
