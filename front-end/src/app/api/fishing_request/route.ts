import { NextRequest, NextResponse } from 'next/server';

// Helper function to parse the fishing request string.
// This is a simple implementation and might need to be more robust.
function parseFishingRequest(request: string): { date: string; time: string; people_count: number } {
    // Example request: "내일 오전 6시부터 바다낚시 예약하고 싶습니다. 4명이서 가려고 하는데 가능한지 확인해주세요."
    
    // This is a very basic parser.
    const peopleMatch = request.match(/(\d+)명/);
    const timeMatch = request.match(/(오전|오후)?\s*(\d+시)/);

    // A very naive date parser
    let date = new Date();
    if (request.includes('내일')) {
        date.setDate(date.getDate() + 1);
    }
    const dateString = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

    let hour = 12;
    if (timeMatch) {
        hour = parseInt(timeMatch[2]);
        if (timeMatch[1] === '오후' && hour < 12) {
            hour += 12;
        }
    }
    const timeString = `${String(hour).padStart(2, '0')}:00`;

    return {
        date: dateString,
        time: timeString,
        people_count: peopleMatch ? parseInt(peopleMatch[1]) : 1,
    };
}

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();
        const { to_phone, business_name, fishing_request } = body;

        if (!to_phone || !business_name || !fishing_request) {
            return NextResponse.json({ message: 'Missing required fields' }, { status: 400 });
        }

        const parsedRequest = parseFishingRequest(fishing_request);

        const backendRequestBody = {
            to_number: to_phone,
            business_name: business_name,
            fishing_request: {
                ...parsedRequest,
                fishing_type: "바다낚시", // Assuming default
            }
        };

        const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/call/initiate`;

        const backendResponse = await fetch(backendUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(backendRequestBody),
        });

        const responseData = await backendResponse.json();

        if (!backendResponse.ok) {
            return NextResponse.json(responseData, { status: backendResponse.status });
        }

        return NextResponse.json(responseData);

    } catch (error) {
        console.error('Error in /api/fishing_request:', error);
        return NextResponse.json({ message: 'Internal Server Error' }, { status: 500 });
    }
}
