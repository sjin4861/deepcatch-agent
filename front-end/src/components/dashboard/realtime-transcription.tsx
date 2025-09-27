'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Mic } from 'lucide-react';
// 기존 context 기반 로직 + Socket 실시간 이벤트 통합
import { useTranscription } from '@/context/transcription-context';
import { useRealtimeConnection } from '@/hooks/useRealtimeConnection';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const TYPING_INTERVAL_MS = 28;

export default function RealtimeTranscription() {
    const [dialing, setDialing] = useState(false);
    const [dialError, setDialError] = useState<string | null>(null);
    const [lastCallSid, setLastCallSid] = useState<string | null>(null);
    const DEFAULT_TARGET = process.env.NEXT_PUBLIC_DEFAULT_CALL_TARGET || process.env.NEXT_PUBLIC_TEST_PHONE_NUMBER || '';
    // 시나리오 선택 (테스트용)
    const [scenarioId, setScenarioId] = useState<'scenario1' | 'scenario2' | 'scenario3'>('scenario1');
    const { isLoading, error, refresh, isActive, hasAttempted } = useTranscription();
    const {
        aiResponse,
        latestUserSpeech,
        isConnected: socketConnected,
        callStatus,
        startCall,
        stopCall,
        isCallActive,
        callError,
        conversation,
        scenarioProgress,
    } = useRealtimeConnection();
    const scrollAreaRef = useRef<HTMLDivElement>(null);
    // 글자 단위 출력 상태: 각 conversation turn 별 현재 출력된 길이
    const [charProgress, setCharProgress] = useState<Record<string, number>>({});
    const progressRef = useRef<Record<string, number>>({});
    const typingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const lastConversationLengthRef = useRef(0);
    // 통화 타이머
    const [callStartTime, setCallStartTime] = useState<number | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    // 시나리오 모드 여부 (서버 환경변수 반영 가정 - 브라우저 빌드 시 expose 필요 시 NEXT_PUBLIC_SCENARIO_MODE 사용)
    const scenarioMode = (process.env.NEXT_PUBLIC_SCENARIO_MODE || '').toLowerCase() === 'true';

    useEffect(() => {
        if (scrollAreaRef.current) {
            const viewport = scrollAreaRef.current.querySelector('div');
            if (viewport) {
                viewport.scrollTop = viewport.scrollHeight;
            }
        }
    }, [conversation, charProgress]);

    const stopTyping = useCallback(() => {
        if (typingTimerRef.current) {
            clearInterval(typingTimerRef.current);
            typingTimerRef.current = null;
        }
    }, []);

    // 새 turn 추가되면 charProgress 초기화
    useEffect(() => {
        const len = conversation.length;
        if (len === lastConversationLengthRef.current) return;
        const newTurns = conversation.slice(lastConversationLengthRef.current);
        setCharProgress(prev => {
            const copy = { ...prev };
            newTurns.forEach(turn => {
                if (!(turn.id in copy)) copy[turn.id] = 0;
            });
            return copy;
        });
        lastConversationLengthRef.current = len;
        if (!typingTimerRef.current) {
            typingTimerRef.current = setInterval(() => {
                setCharProgress(prev => {
                    const updated: Record<string, number> = { ...prev };
                    let anyActive = false;
                    for (const turn of conversation) {
                        const full = turn.text.length;
                        const current = updated[turn.id] ?? 0;
                        if (current < full) {
                            updated[turn.id] = Math.min(current + 1, full);
                            anyActive = true;
                            break; // 한 tick에 한 글자만 → 더 실시간 느낌
                        }
                    }
                    if (!anyActive) {
                        stopTyping();
                    }
                    progressRef.current = updated;
                    return updated;
                });
            }, TYPING_INTERVAL_MS);
        }
    }, [conversation, stopTyping]);

    // 스트리밍 assistant turn 텍스트 길이 증가 반영
    useEffect(() => {
        if (!typingTimerRef.current && conversation.some(t => t.isStreaming)) {
            typingTimerRef.current = setInterval(() => {
                setCharProgress(prev => {
                    const updated: Record<string, number> = { ...prev };
                    let anyActive = false;
                    for (const turn of conversation) {
                        const full = turn.text.length;
                        const current = updated[turn.id] ?? 0;
                        if (current < full) {
                            updated[turn.id] = Math.min(current + 1, full);
                            anyActive = true;
                            break;
                        }
                    }
                    if (!anyActive) stopTyping();
                    progressRef.current = updated;
                    return updated;
                });
            }, TYPING_INTERVAL_MS);
        }
    }, [conversation, stopTyping]);

    useEffect(() => () => stopTyping(), [stopTyping]);

    // 표시용 상태 판단 (소켓 단일 진행 중 전사 또는 기존 segments 기준)
    const hasAnyContent = conversation.length > 0;
    const showIdleState = !isCallActive && !hasAnyContent && !isLoading && !error;
    const showWaitingState = isCallActive && !isLoading && !error && !hasAnyContent;

    // callStatus 감시하여 타이머 갱신
    useEffect(() => {
        if (!callStatus) return;
        const st = (callStatus.status || '').toLowerCase();
        const activeStatuses = ['in-progress', 'answered'];
        if (!callStartTime && activeStatuses.includes(st)) {
            const start = Date.now();
            setCallStartTime(start);
            timerRef.current && clearInterval(timerRef.current);
            timerRef.current = setInterval(() => {
                setElapsed(Math.floor((Date.now() - start) / 1000));
            }, 1000);
        }
        const endStatuses = ['completed','busy','failed','no-answer','canceled'];
        if (callStartTime && endStatuses.includes(st)) {
            timerRef.current && clearInterval(timerRef.current);
            timerRef.current = null;
        }
    }, [callStatus, callStartTime]);

    useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

    const formatElapsed = (sec: number) => {
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        return `${m}:${s.toString().padStart(2,'0')}`;
    };

    return (
        <Card className="flex-1 flex flex-col min-h-[400px]">
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                    <Mic className="text-accent" />
                    Live Transcription
                    {scenarioMode && <Badge variant="outline" className="text-[10px]">Scenario</Badge>}
                </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 flex flex-col min-h-0">
                <ScrollArea className="flex-1 pr-4 -mr-4" ref={scrollAreaRef}>
                    <div className="space-y-4">
                        {hasAttempted && !socketConnected && !error && (
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
                        {!isLoading && !error && conversation.length > 0 && (
                            conversation.map(turn => {
                                const shown = charProgress[turn.id] ?? 0;
                                const visible = turn.text.slice(0, shown);
                                const isAssistant = turn.role === 'assistant';
                                return (
                                    <div key={turn.id} className="flex flex-col">
                                        <span className={`font-bold ${isAssistant ? 'text-primary' : 'text-foreground'}`}>{isAssistant ? 'Agent' : 'User'}</span>
                                        <p className="text-muted-foreground whitespace-pre-wrap">
                                            {visible}
                                            {turn.isStreaming && shown >= visible.length && <span className="animate-pulse">▍</span>}
                                        </p>
                                    </div>
                                );
                            })
                        )}
                        {/* 보조 패널 제거: conversation에 통합됨 */}
                        {callError && (
                            <div className="text-xs text-destructive">Call Error: {callError}</div>
                        )}
                    </div>
                </ScrollArea>
                <div className="mt-3 flex flex-wrap gap-2 justify-end">
                    {/* 시나리오 토글 */}
                    <div className="flex gap-1 items-center border rounded px-2 py-1 bg-muted/40">
                        {(['scenario1','scenario2','scenario3'] as const).map(s => (
                            <button
                                key={s}
                                type="button"
                                onClick={()=>setScenarioId(s)}
                                className={`text-[11px] px-2 py-0.5 rounded border transition-colors ${scenarioId===s ? 'bg-primary text-primary-foreground border-primary' : 'bg-background hover:bg-muted border-border'}`}
                            >
                                {s.replace('scenario','S')}
                            </button>
                        ))}
                        {scenarioProgress && (
                            <span className="ml-2 text-[10px] text-muted-foreground">
                                {scenarioProgress.consumed}/{scenarioProgress.total}{scenarioProgress.is_complete && ' ✓'}
                            </span>
                        )}
                    </div>
                    <Button
                        size="sm"
                        variant="default"
                        disabled={dialing || !DEFAULT_TARGET}
                        onClick={async () => {
                            try {
                                setDialError(null);
                                setDialing(true);
                                const resp = await fetch('/api/fishing_request', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({
                                        to_phone: DEFAULT_TARGET,
                                        business_name: '테스트 낚시집',
                                        fishing_request: '내일 오전 6시 3명 바다낚시 예약 가능한가요?',
                                        scenario_id: scenarioId,
                                    }),
                                });
                                const data = await resp.json();
                                if (!resp.ok) {
                                    setDialError(data.message || 'Call initiate failed');
                                } else {
                                    setLastCallSid(data.call_sid || null);
                                }
                            } catch (e: any) {
                                setDialError(e.message || 'Unknown error');
                            } finally {
                                setDialing(false);
                            }
                        }}
                    >
                        {dialing ? 'Dialing…' : 'Test Call'}
                    </Button>
                </div>
                {callStatus && (
                    <div className="mt-2 text-[10px] text-muted-foreground">Twilio Status: {callStatus.status}</div>
                )}
                {/* 통화 진행 바 */}
                <div className="mt-2">
                    <div className="w-full rounded border px-3 py-1.5 flex flex-wrap gap-3 items-center bg-muted/40">
                        <span className="text-[11px] font-medium">{callStatus ? `Call: ${callStatus.status}` : 'Call: idle'}</span>
                        <span className="text-[11px] text-muted-foreground">Elapsed: {callStartTime ? formatElapsed(elapsed) : '0:00'}</span>
                        {callStatus?.data?.error_code && (
                            <span className="text-[11px] text-destructive">Err: {callStatus.data.error_code}</span>
                        )}
                        {!callStartTime && callStatus && (
                            <span className="text-[11px] text-muted-foreground">Waiting answer…</span>
                        )}
                    </div>
                </div>
                {lastCallSid && (
                    <div className="mt-1 text-[10px] text-muted-foreground">Call SID: {lastCallSid}</div>
                )}
                {dialError && (
                    <div className="mt-1 text-[10px] text-destructive">Dial Error: {dialError}</div>
                )}
            </CardContent>
        </Card>
    );
}
