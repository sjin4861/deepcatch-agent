import { NextResponse } from 'next/server';
import type { AgentChatResponse } from '@/types/agent';

const MOCK_AGENT_RESPONSES: AgentChatResponse[] = [
    {
        message: 'Great! I pulled your trip preferences — warm offshore waters targeting mahi-mahi for a party of four. I can keep tracking bait availability and seasonal catches as you plan.',
        toolResults: [
            {
                id: 'trip-overview',
                toolName: 'trip_planner',
                title: 'Trip Preferences Identified',
                content: 'Target species: mahi-mahi\nGuests: 4 anglers\nPreferred window: next 2 weeks\nNotes: captain-provided gear requested',
                metadata: {
                    species: 'Mahi-mahi',
                    guests: 4,
                    window: 'Next 2 weeks',
                    gear: 'captain-provided',
                },
                createdAt: new Date().toISOString(),
            },
        ],
    },
    {
        message: 'Conditions look favorable — seas around 2-3 ft with light northeast winds. I also checked the charter docks: two of our partner captains have early morning departures available for full-day runs.',
        toolResults: [
            {
                id: 'weather-brief',
                toolName: 'marine_weather',
                title: 'Marine Forecast • Key West',
                content: 'Saturday: NE winds 10-12 kts, seas 2-3 ft. Sunrise 6:45 AM, best bite expected mid-morning on the edge.',
                metadata: {
                    location: 'Key West, FL',
                    wind: '10-12 kts NE',
                    seas: '2-3 ft',
                },
                createdAt: new Date(Date.now() + 2 * 60 * 1000).toISOString(),
            },
            {
                id: 'availability-scan',
                toolName: 'charter_lookup',
                title: 'Partner Charter Openings',
                content: 'Pelagic Pursuit: 6:30 AM departure • $1,200\nReel Current: 7:00 AM departure • $1,250 (includes upgraded tackle)',
                metadata: {
                    operators: ['Pelagic Pursuit', 'Reel Current'],
                },
                createdAt: new Date(Date.now() + 3 * 60 * 1000).toISOString(),
            },
        ],
    },
    {
        message: 'Want me to lock in the charter while those slots are open? I can hop on a quick call with the captain, confirm the details, and loop you in live.',
        toolResults: [
            {
                id: 'call-script',
                toolName: 'call_preparation',
                title: 'Call Preparation Notes',
                content: 'Confirm: party of 4, full-day, next Saturday. Mention bait preference for mahi and that guests need licenses included.',
                metadata: {
                    duration: 'Full day',
                    guests: 4,
                    targetDate: 'Upcoming Saturday',
                },
                createdAt: new Date(Date.now() + 4 * 60 * 1000).toISOString(),
            },
        ],
        callSuggested: true,
    },
];

let responseIndex = 0;

export async function POST(request: Request) {
    try {
        const payload = await request.json().catch(() => null);
        const userMessage = typeof payload?.message === 'string' ? payload.message.trim() : '';
        if (!userMessage) {
            return NextResponse.json({
                message: 'Let me know how I can help and I\'ll start pulling the latest charter intel.',
            } satisfies AgentChatResponse);
        }

        const response = MOCK_AGENT_RESPONSES[responseIndex] ?? MOCK_AGENT_RESPONSES[MOCK_AGENT_RESPONSES.length - 1];
        responseIndex = (responseIndex + 1) % MOCK_AGENT_RESPONSES.length;

        console.info('[mock-chat] responding to message', { userMessage, response });

        return NextResponse.json(response satisfies AgentChatResponse);
    } catch (error) {
        console.error('[mock-chat] failed to generate response', error);
        return NextResponse.json({
            message: 'Something went wrong fetching insights. Try again in a moment.',
        } satisfies AgentChatResponse, { status: 500 });
    }
}
