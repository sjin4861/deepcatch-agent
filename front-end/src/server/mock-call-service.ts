import { WebSocketServer, WebSocket as WS } from 'ws';
import type { WebSocket } from 'ws';

export type TranscriptSegment = {
    speaker: string;
    text: string;
    timestamp?: string;
};

type PendingStream = {
    segments: TranscriptSegment[];
    intervalMs: number;
    initialDelayMs: number;
};

type MockCallState = {
    wss: WebSocketServer;
    clients: Set<WebSocket>;
    isStreaming: boolean;
    pendingStream: PendingStream | null;
    currentTimer: NodeJS.Timeout | null;
};

declare global {
    // eslint-disable-next-line no-var
    var __mockCallState: MockCallState | undefined;
}

export const DEFAULT_SEGMENTS: TranscriptSegment[] = [
    { speaker: 'Agent', text: 'Thank you for calling Aqua Adventures, this is Sarah.' },
    { speaker: 'Caller', text: "Hi Sarah, I'm looking to book a deep-sea fishing trip." },
    { speaker: 'Agent', text: 'Great! The mahi-mahi bite has been fantastic. Are you thinking half or full day?' },
    { speaker: 'Caller', text: 'Let’s do a full-day trip. What does that include?' },
    { speaker: 'Agent', text: 'It’s $1,200 for up to four guests, captain, gear, bait, and licenses included.' },
    { speaker: 'Caller', text: 'Perfect. Could we schedule it for next Saturday?' },
    { speaker: 'Agent', text: 'Absolutely. May I have your name and callback number?' },
    { speaker: 'Caller', text: 'John Doe, 555-123-4567.' },
    { speaker: 'Agent', text: 'Thanks, John. I’ll send the confirmation shortly.' },
];

const DEFAULT_INTERVAL = 1500;
const DEFAULT_INITIAL_DELAY = 900;
const PORT = Number(process.env.MOCK_WS_PORT ?? process.env.NEXT_PUBLIC_SOCKET_PORT ?? 9003);

function getGlobalState(): MockCallState {
    if (!globalThis.__mockCallState) {
        const wss = new WebSocketServer({ port: PORT });
        const clients = new Set<WebSocket>();
        const state: MockCallState = {
            wss,
            clients,
            isStreaming: false,
            pendingStream: null,
            currentTimer: null,
        };

        const broadcastStatus = (status: string) => {
            broadcast(state, { type: 'status', status });
        };

        wss.on('connection', socket => {
            clients.add(socket);
            socket.send(JSON.stringify({ type: 'status', status: 'ready' }));

            socket.on('close', () => {
                clients.delete(socket);
                if (clients.size === 0) {
                    stopStream(state, { sendStoppedStatus: false });
                }
            });

            socket.on('message', raw => {
                try {
                    const payload = JSON.parse(raw.toString());
                    if (payload?.type === 'start_call') {
                        if (!state.isStreaming) {
                            startStream(state, state.pendingStream ?? createPendingStream());
                        }
                    } else if (payload?.type === 'stop_call') {
                        stopStream(state, { sendStoppedStatus: true });
                    }
                } catch (error) {
                    console.error('[mock-call] failed to parse websocket message', error);
                }
            });

            if (state.pendingStream && !state.isStreaming) {
                broadcastStatus('queued');
            }
        });

        wss.on('listening', () => {
            console.info(`[mock-call] mock websocket server listening on ws://localhost:${PORT}`);
        });

        wss.on('error', error => {
            console.error('[mock-call] websocket server error', error);
        });

        globalThis.__mockCallState = state;
    }

    return globalThis.__mockCallState;
}

function createPendingStream(
    segments: TranscriptSegment[] = DEFAULT_SEGMENTS,
    intervalMs = DEFAULT_INTERVAL,
    initialDelayMs = DEFAULT_INITIAL_DELAY,
): PendingStream {
    return {
        segments: segments.map(segment => ({ ...segment })),
        intervalMs,
        initialDelayMs,
    };
}

function broadcast(state: MockCallState, message: unknown) {
    const payload = JSON.stringify(message);
    for (const client of state.clients) {
        if (client.readyState === WS.OPEN) {
            client.send(payload);
        }
    }
}

function stopStream(state: MockCallState, options: { sendStoppedStatus?: boolean } = {}) {
    const { sendStoppedStatus = false } = options;
    if (state.currentTimer) {
        clearTimeout(state.currentTimer);
        state.currentTimer = null;
    }
    if (state.isStreaming) {
        state.isStreaming = false;
        if (sendStoppedStatus) {
            broadcast(state, { type: 'status', status: 'stopped' });
        }
    }
    if (sendStoppedStatus) {
        state.pendingStream = null;
    }
}

function startStream(state: MockCallState, pending: PendingStream) {
    stopStream(state);
    state.isStreaming = true;
    state.pendingStream = null;

    const { segments, intervalMs, initialDelayMs } = pending;
    let index = 0;

    const sendNext = () => {
        if (!state.isStreaming) {
            return;
        }
        if (index >= segments.length) {
            broadcast(state, { type: 'transcription_done' });
            state.isStreaming = false;
            state.currentTimer = null;
            return;
        }

        const segment = segments[index];
        broadcast(state, {
            type: 'transcription_segment',
            segment,
            index,
            done: index === segments.length - 1,
        });
        index += 1;
        state.currentTimer = setTimeout(sendNext, intervalMs);
    };

    state.currentTimer = setTimeout(sendNext, Math.max(initialDelayMs, 0));
}

export function queueMockCall(options?: { segments?: TranscriptSegment[]; intervalMs?: number; initialDelayMs?: number }) {
    const state = getGlobalState();
    if (options?.segments && options.segments.length === 0) {
        throw new Error('segments must contain at least one entry when provided');
    }

    const pending = createPendingStream(
        options?.segments ?? DEFAULT_SEGMENTS,
        options?.intervalMs ?? DEFAULT_INTERVAL,
        options?.initialDelayMs ?? DEFAULT_INITIAL_DELAY,
    );

    state.pendingStream = pending;

    if (state.clients.size > 0) {
        broadcast(state, { type: 'status', status: 'queued' });
    }

    // If there are active clients and we are not waiting for an explicit start_call message,
    // begin streaming automatically.
    if (state.clients.size > 0) {
        startStream(state, pending);
    }
}

export function ensureMockServer() {
    return getGlobalState();
}

export function getMockServerInfo() {
    const state = getGlobalState();
    return {
        port: PORT,
        clientCount: state.clients.size,
        isStreaming: state.isStreaming,
        hasPendingStream: Boolean(state.pendingStream),
    };
}
