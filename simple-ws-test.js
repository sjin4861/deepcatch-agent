const WebSocket = require('ws');

const wsUrl = 'wss://pityingly-overwily-dawna.ngrok-free.dev/voice/stream?call_sid=debug_test_456';

console.log('WebSocket 연결 시도:', wsUrl);

const ws = new WebSocket(wsUrl);

ws.on('open', function open() {
    console.log('✅ WebSocket 연결 성공!');
});

ws.on('message', function message(data) {
    console.log('📨 서버로부터 메시지:', data.toString());
});

ws.on('close', function close(code, reason) {
    console.log(`❌ 연결 종료: 코드=${code}, 이유=${reason.toString() || '없음'}`);
    process.exit();
});

ws.on('error', function error(err) {
    console.log('🚨 WebSocket 오류:', err.message);
    process.exit();
});

// 10초 후 연결 종료
setTimeout(() => {
    console.log('테스트 완료, 연결 종료');
    ws.close();
}, 10000);