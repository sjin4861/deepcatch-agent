export type ToolResult = {
    id: string;
    toolName?: string;
    title?: string;
    content: string;
    metadata?: Record<string, unknown> | null;
    receivedAt: string;
};

export type ToolResultPayload = {
    id?: string;
    toolName?: string;
    title?: string;
    content?: string;
    text?: string;
    output?: string;
    metadata?: Record<string, unknown> | null;
    createdAt?: string;
};

export type AgentChatResponse = {
    message: string;
    toolResults?: ToolResultPayload[];
    callSuggested?: boolean;
};

export type MapCoordinate = {
    name: string;
    label?: string;
    lat: number;
    lng: number;
    address?: string | null;
    phone?: string | null;
};

export type MapRouteMetadata = {
    departure: MapCoordinate & { label: string };
    arrival: MapCoordinate;
    businesses: MapCoordinate[];
    route?: {
        mode?: string;
        distance_km?: number;
        duration_minutes?: number;
        bounds?: {
            south: number;
            west: number;
            north: number;
            east: number;
        };
    };
};

export type FisheryCatchTopSpecies = {
    name: string;
    catch?: number;
    share?: number;
    averagePrice?: number | null;
};

export type FisheryCatchTimelinePoint = {
    date: string;
    [species: string]: number | string;
};

export type FisheryCatchMetadata = {
    analysisRange?: string;
    chartTimeline?: FisheryCatchTimelinePoint[];
    chartSeries?: Array<{
        species: string;
        points: Array<{ date: string; weight: number }>;
    }>;
    topSpecies?: FisheryCatchTopSpecies[];
    totalCatchKg?: number;
    summary?: string;
    dataSource?: string;
};
