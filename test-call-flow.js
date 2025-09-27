const https = require('https');

async function simulateCallFlow() {
    console.log('1. 실제 Twilio 통화 생성...');
    
    // Create a real call using the initiate endpoint
    const callData = JSON.stringify({
        to_number: "+821021139911",
        business_name: "테스트 업체",
        fishing_request: {
            date: "2024-01-01",
            time: "10:00",
            people_count: 1,
            fishing_type: "테스트"
        }
    });

    const options = {
        hostname: 'pityingly-overwily-dawna.ngrok-free.dev',
        port: 443,
        path: '/call/initiate',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': callData.length
        }
    };

    return new Promise((resolve, reject) => {
        const req = https.request(options, (res) => {
            let responseData = '';
            res.on('data', (chunk) => {
                responseData += chunk;
            });
            res.on('end', () => {
                try {
                    const response = JSON.parse(responseData);
                    console.log('2. 통화 생성 응답:', response);
                    
                    if (response.call_sid) {
                        // Now test the voice/start endpoint with this call_sid
                        testVoiceStart(response.call_sid);
                    }
                    resolve(response);
                } catch (e) {
                    reject(e);
                }
            });
        });

        req.on('error', (e) => {
            reject(e);
        });

        req.write(callData);
        req.end();
    });
}

function testVoiceStart(callSid) {
    console.log('3. voice/start 엔드포인트 테스트:', callSid);
    
    const postData = `CallSid=${callSid}&From=%2B14472881918&To=%2B821021139911`;
    
    const options = {
        hostname: 'pityingly-overwily-dawna.ngrok-free.dev',
        port: 443,
        path: '/voice/start',
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Content-Length': postData.length
        }
    };

    const req = https.request(options, (res) => {
        let responseData = '';
        res.on('data', (chunk) => {
            responseData += chunk;
        });
        res.on('end', () => {
            console.log('4. TwiML 응답:');
            console.log(responseData);
        });
    });

    req.on('error', (e) => {
        console.log('voice/start 요청 오류:', e.message);
    });

    req.write(postData);
    req.end();
}

simulateCallFlow().catch(console.error);