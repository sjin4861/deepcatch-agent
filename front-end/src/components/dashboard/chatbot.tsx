'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Loader2, PhoneCall, Send } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useTranscription } from '@/context/transcription-context';
import { API_BASE_URL } from '@/lib/config';
import { useToast } from '@/hooks/use-toast';
import { useAgentInsights } from '@/context/agent-insights-context';
import type { AgentChatResponse, ToolResult, ToolResultPayload } from '@/types/agent';

type Message = {
    id: string;
    sender: 'user' | 'bot';
    text?: string;
    status?: 'pending' | 'delivered';
    variant?: 'call-suggestion';
};

function resolveCallEndpoint() {
    // if (API_BASE_URL) {
    //     return `${API_BASE_URL.replace(/\/$/, '')}/call`;
    // }
    return '/api/mock/call';
}

function resolveChatEndpoint() {
    if (API_BASE_URL) {
        const end_point = `${API_BASE_URL.replace(/\/$/, '')}/chat`;
        console.log('Chat endpoint:', end_point);
        return end_point;
    }
    return '/api/mock/chat';
}

function normalizeToolResults(payloads: ToolResultPayload[] | undefined | null): ToolResult[] {
    if (!payloads || payloads.length === 0) {
        return [];
    }

    const normalized: ToolResult[] = [];

    for (const payload of payloads) {
        if (!payload) {
            continue;
        }
        const content = payload.content ?? payload.output ?? payload.text;
        if (!content || typeof content !== 'string') {
            continue;
        }

        const id = (payload.id && payload.id.trim().length > 0)
            ? payload.id
            : typeof crypto !== 'undefined' && 'randomUUID' in crypto
                ? crypto.randomUUID()
                : `tool-${Date.now()}-${Math.random().toString(16).slice(2)}`;

        const result: ToolResult = {
            id,
            toolName: payload.toolName,
            title: payload.title,
            content,
            metadata: payload.metadata ?? null,
            receivedAt: payload.createdAt ?? new Date().toISOString(),
        };

        normalized.push(result);
    }

    return normalized;
}

function createMessageId(prefix: 'user' | 'bot') {
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

export default function Chatbot() {
    const [messages, setMessages] = useState<Message[]>([
        { id: createMessageId('bot'), text: 'Hello! How can I assist you today?', sender: 'bot', status: 'delivered' },
    ]);
    const [inputValue, setInputValue] = useState('');
    const [isCalling, setIsCalling] = useState(false);
    const [isSending, setIsSending] = useState(false);
    const { start, isActive, hasAttempted } = useTranscription();
    const { toast } = useToast();
    const { recordToolResults } = useAgentInsights();
    const scrollAreaRef = useRef<HTMLDivElement>(null);

    const handleSendMessage = useCallback(async () => {
        const text = inputValue.trim();
        if (!text || isSending) {
            return;
        }

        const userMessage: Message = {
            id: createMessageId('user'),
            text,
            sender: 'user',
            status: 'delivered',
        };

        setMessages(prev => [...prev, userMessage, { id: 'agent-pending', text: 'Thinking…', sender: 'bot', status: 'pending' }]);
        setInputValue('');
        setIsSending(true);

        try {
            const response = await fetch(resolveChatEndpoint(), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: text }),
            });

            if (!response.ok) {
                throw new Error(`Agent request failed (${response.status})`);
            }

            const payload: AgentChatResponse = await response.json();

            const normalizedResults = normalizeToolResults(payload.toolResults);
            if (normalizedResults.length > 0) {
                recordToolResults(normalizedResults);
            }

            setMessages(prev => {
                const next = prev.slice(0, -1); // remove pending placeholder
                if (payload.message) {
                    next.push({
                        id: createMessageId('bot'),
                        text: payload.message,
                        sender: 'bot',
                        status: 'delivered',
                    });
                }

                if (payload.callSuggested) {
                    const hasCallSuggestion = next.some(message => message.variant === 'call-suggestion');
                    if (!hasCallSuggestion) {
                        next.push({
                            id: createMessageId('bot'),
                            sender: 'bot',
                            status: 'delivered',
                            variant: 'call-suggestion',
                        });
                    }
                }

                return next;
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to fetch agent response.';
            toast({
                variant: 'destructive',
                title: 'Message failed',
                description: message,
            });
            setMessages(prev => prev.filter(message => message.id !== 'agent-pending'));
        } finally {
            setIsSending(false);
        }
    }, [inputValue, isSending, recordToolResults, toast]);

    const handleStartCall = async () => {
        setIsCalling(true);
        try {
            const response = await fetch(resolveCallEndpoint(), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ source: 'dashboard' }),
            });

            if (!response.ok) {
                throw new Error(`Failed to start call (${response.status})`);
            }

            await start();
            toast({
                title: 'Call started',
                description: 'Streaming live transcription from the charter call.',
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to start the call.';
            toast({
                variant: 'destructive',
                title: 'Call Failed',
                description: message,
            });
        } finally {
            setIsCalling(false);
        }
    };

    useEffect(() => {
        if (scrollAreaRef.current) {
            const viewport = scrollAreaRef.current.querySelector('div');
            if (viewport) {
                viewport.scrollTop = viewport.scrollHeight;
            }
        }
    }, [messages]);

    return (
        <Card className="flex flex-col h-full min-h-[80vh]">
            <CardContent className="flex-1 flex flex-col p-4 gap-4 overflow-hidden">
                <ScrollArea className="h-[80vh] pr-4 -mr-4" ref={scrollAreaRef}>
                    <div className="space-y-4">
                        {messages.map((message, index) => {
                            const isUser = message.sender === 'user';
                            const isPending = message.status === 'pending';
                            const isCallSuggestion = message.variant === 'call-suggestion';
                            const bubbleColor = isCallSuggestion
                                ? 'bg-accent/20 text-foreground border border-accent/40'
                                : isUser
                                    ? 'bg-primary text-primary-foreground'
                                    : 'bg-secondary';
                            return (
                                <div key={message.id ?? index} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                                    <div
                                        className={`max-w-xs lg:max-w-md rounded-lg px-4 py-2 shadow-sm ${bubbleColor}`}
                                    >
                                        {isPending ? (
                                            <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                                {message.text ?? 'Thinking…'}
                                            </span>
                                        ) : isCallSuggestion ? (
                                            <div className="space-y-3 text-sm">
                                                <div className="font-medium text-foreground">
                                                    Ready to confirm availability?
                                                </div>
                                                <p className="text-muted-foreground">
                                                    I can connect with the charter and stream the conversation live. Start the call whenever you&apos;re ready.
                                                </p>
                                                <Button
                                                    onClick={handleStartCall}
                                                    disabled={isCalling || isActive}
                                                    className="w-fit flex items-center gap-2"
                                                >
                                                    {isCalling ? (
                                                        <>
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                            Dialing...
                                                        </>
                                                    ) : (
                                                        <>
                                                            <PhoneCall className="h-4 w-4" />
                                                            {isActive
                                                                ? 'Call in Progress'
                                                                : hasAttempted
                                                                    ? 'Restart Call'
                                                                    : 'Start Call'}
                                                        </>
                                                    )}
                                                </Button>
                                                {isActive && (
                                                    <p className="text-xs text-muted-foreground">
                                                        Live transcription is flowing to the panel on the right.
                                                    </p>
                                                )}
                                            </div>
                                        ) : (
                                            <span className="whitespace-pre-line break-words">{message.text}</span>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    </ScrollArea>
                <div className="flex gap-2">
                    <Input
                        placeholder="Type a message..."
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                void handleSendMessage();
                            }
                        }}
                        aria-label="Chat message input"
                        disabled={isSending}
                    />
                    <Button onClick={() => void handleSendMessage()} aria-label="Send message" disabled={isSending}>
                        {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
