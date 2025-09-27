import { NextResponse } from 'next/server';
import {
    DEFAULT_SEGMENTS,
    ensureMockServer,
    getMockServerInfo,
    queueMockCall,
    type TranscriptSegment,
} from '@/server/mock-call-service';

export const runtime = 'nodejs';

type MockCallRequest = {
    segments?: unknown;
    script?: unknown;
    transcript?: unknown;
    intervalMs?: unknown;
    initialDelayMs?: unknown;
};

function sanitizeSegments(value: unknown): TranscriptSegment[] | null {
    if (!Array.isArray(value)) {
        return null;
    }

    const segments: TranscriptSegment[] = [];
    for (const entry of value) {
        if (!entry || typeof entry !== 'object') {
            continue;
        }

        const speaker = 'speaker' in entry ? String((entry as { speaker: unknown }).speaker ?? '') : '';
        const text = 'text' in entry ? String((entry as { text: unknown }).text ?? '') : '';

        if (!speaker.trim() || !text.trim()) {
            continue;
        }

        const segment: TranscriptSegment = {
            speaker: speaker.trim(),
            text: text.trim(),
        };

        if ('timestamp' in entry && (entry as { timestamp?: unknown }).timestamp != null) {
            segment.timestamp = String((entry as { timestamp?: unknown }).timestamp);
        }

        segments.push(segment);
    }

    return segments.length > 0 ? segments : null;
}

function parseTranscriptLines(value: unknown): string[] | null {
    if (typeof value === 'string') {
        return value
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean);
    }

    if (Array.isArray(value)) {
        return value
            .map(line => (typeof line === 'string' ? line.trim() : ''))
            .filter(Boolean);
    }

    return null;
}

function transcriptToSegments(lines: string[]): TranscriptSegment[] {
    return lines.map((text, index) => ({
        speaker: index % 2 === 0 ? 'Agent' : 'Caller',
        text,
    }));
}

function parseOptionalNumber(value: unknown): number | undefined {
    if (value === undefined || value === null) {
        return undefined;
    }

    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) {
        return undefined;
    }

    return parsed;
}

export async function POST(request: Request) {
    try {
        ensureMockServer();

        const body = (await request.json().catch(() => ({}))) as MockCallRequest;
        console.info('[mock-call] received request', body);

        const segmentsCandidate =
            sanitizeSegments(body.segments) ??
            sanitizeSegments(body.script) ??
            null;

        const transcriptLines = segmentsCandidate ? null : parseTranscriptLines(body.transcript);
        const segments = segmentsCandidate ?? (transcriptLines ? transcriptToSegments(transcriptLines) : undefined);

        const intervalMs = parseOptionalNumber(body.intervalMs);
        const initialDelayMs = parseOptionalNumber(body.initialDelayMs);

        queueMockCall({ segments, intervalMs, initialDelayMs });

        const info = getMockServerInfo();

        return NextResponse.json({
            status: 'dialing',
            mock: true,
            queuedSegments: (segments ?? DEFAULT_SEGMENTS).length,
            socket: {
                port: info.port,
                clientCount: info.clientCount,
            },
        });
    } catch (error) {
        console.error('[mock-call] error handling request', error);
        return NextResponse.json({ error: 'Failed to start mock call' }, { status: 500 });
    }
}
