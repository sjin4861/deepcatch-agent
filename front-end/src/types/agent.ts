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

export type WeatherHolidayTideEvent = {
    time: string;
    height: number;
};

export type WeatherHolidayDay = {
    date: string;
    label?: string;
    weekday?: string;
    condition?: string;
    summary?: string;
    tempMin?: number;
    tempMax?: number;
    windSpeed?: number;
    windDirection?: string;
    waveHeight?: number;
    precipitationChance?: number;
    tidePhase?: string;
    moonAge?: number;
    sunrise?: string;
    sunset?: string;
    bestWindow?: string;
    cautionWindow?: string | null;
    highTides?: WeatherHolidayTideEvent[];
    lowTides?: WeatherHolidayTideEvent[];
    comfortScore?: number;
};

export type WeatherHolidayChartPoint = {
    date: string;
    label?: string;
    windSpeed?: number;
    waveHeight?: number;
    tempMin?: number;
    tempMax?: number;
    precipitationChance?: number;
    comfortScore?: number;
};

export type WeatherHolidayBest = {
    date?: string;
    label?: string;
    reason?: string;
    score?: number;
};

export type WeatherHolidayOverview = {
    rangeLabel?: string | null;
    days?: WeatherHolidayDay[];
    chart?: WeatherHolidayChartPoint[];
    best?: WeatherHolidayBest | null;
    advisories?: string[];
    source?: string | null;
};

export type WeatherToolMetadata = {
    target_date?: string;
    sunrise?: string;
    wind?: string;
    tide?: string;
    best_window?: string;
    summary?: string;
    tide_phase?: string | null;
    moon_age?: number | null;
    holidayOverview?: WeatherHolidayOverview | null;
};
