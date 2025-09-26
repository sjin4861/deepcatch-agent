// Simple mock WebSocket server for local dev (Node.js only)
// Usage: `node src/mocks/socket-mock-server.ts` (run separately from Next.js)
import { WebSocketServer } from 'ws';
import type { WebSocket, RawData } from 'ws';

const PORT = 9003;
const wss = new WebSocketServer({ port: PORT });

const TEMPLATE_TRANSCRIPTION = [
    { speaker: 'Agent', text: 'Thank you for calling Aqua Adventures, this is Sarah.' },
    { speaker: 'Caller', text: 'Hi Sarah, I want to book a deep-sea fishing trip.' },
    { speaker: 'Agent', text: 'Great! Mahi-mahi and Wahoo are biting now. Half or full-day?' },
    { speaker: 'Caller', text: 'Full-day. What does it cost?' },
    { speaker: 'Agent', text: 'It\'s $1200 for up to 4 people, all gear included.' },
    { speaker: 'Caller', text: 'Book for next Saturday, please.' },
    { speaker: 'Agent', text: 'May I have your name and number?' },
    { speaker: 'Caller', text: 'John Doe, 555-123-4567.' },
    { speaker: 'Agent', text: 'You\'re all set! Confirmation email coming soon.' },
];

wss.on('connection', (ws: WebSocket) => {
    console.log('Mock WebSocket client connected');
    let idx = 0;
    const sendNext = () => {
        if (idx < TEMPLATE_TRANSCRIPTION.length) {
            ws.send(JSON.stringify({
                type: 'transcription_segment',
                segment: TEMPLATE_TRANSCRIPTION[idx],
                index: idx,
                done: idx === TEMPLATE_TRANSCRIPTION.length - 1,
            }));
            idx++;
            setTimeout(sendNext, 1500);
        } else {
            ws.send(JSON.stringify({ type: 'transcription_done' }));
        }
    };
    ws.on('message', (msg: RawData) => {
        const data = JSON.parse(msg.toString());
        if (data.type === 'start_call') {
            idx = 0;
            sendNext();
        }
    });
    ws.send(JSON.stringify({ type: 'ready' }));
});

console.log(`Mock WebSocket server running on ws://localhost:${PORT}`);
