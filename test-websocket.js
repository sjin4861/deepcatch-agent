const WebSocket = require('ws');

// First, we need to create a call session via the API to put it in the new system
const https = require('https');

async function createCallSession() {
    return new Promise((resolve, reject) => {
        const data = JSON.stringify({
            phone_number: "+821021139911",
            welcome_message: "테스트 환영 메시지",
            silence_delay_seconds: 3
        });

        const options = {
            hostname: 'pityingly-overwily-dawna.ngrok-free.dev',
            port: 443,
            path: '/call/initiate',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': data.length
            }
        };

        const req = https.request(options, (res) => {
            let responseData = '';
            res.on('data', (chunk) => {
                responseData += chunk;
            });
            res.on('end', () => {
                try {
                    const response = JSON.parse(responseData);
                    resolve(response.call_sid);
                } catch (e) {
                    reject(e);
                }
            });
        });

        req.on('error', (e) => {
            reject(e);
        });

        req.write(data);
        req.end();
    });
}

async function testWebSocket() {
    console.log('1. 통화 세션 생성 중...');
    
    try {
        const callSid = await createCallSession();
        console.log('2. 통화 세션 생성됨:', callSid);
        
        const wsUrl = `wss://pityingly-overwily-dawna.ngrok-free.dev/voice/stream?call_sid=${callSid}`;
        console.log('3. WebSocket 연결 시도:', wsUrl);

        const ws = new WebSocket(wsUrl);

        ws.on('open', function open() {
            console.log('✅ WebSocket 연결 성공!');
            
            // Test message
            ws.send('Hello Server');
        });

        ws.on('message', function message(data) {
            console.log('📨 서버로부터 메시지:', data.toString());
        });

        ws.on('close', function close(code, reason) {
            console.log(`❌ 연결 종료: 코드=${code}, 이유=${reason.toString() || '없음'}`);
        });

        ws.on('error', function error(err) {
            console.log('🚨 WebSocket 오류:', err.message);
        });

        // 5초 후 연결 종료
        setTimeout(() => {
            console.log('테스트 완료, 연결 종료');
            ws.close();
        }, 5000);
        
    } catch (error) {
        console.log('통화 세션 생성 실패:', error.message);
    }
}

// Run the test
testWebSocket();