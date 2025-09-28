'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Workflow, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranscription } from '@/context/transcription-context';
import { useAgentInsights } from '@/context/agent-insights-context';
import type {
    MapRouteMetadata,
    ToolResult,
    FisheryCatchMetadata,
    FisheryCatchTopSpecies,
    FisheryCatchTimelinePoint,
    WeatherToolMetadata,
    WeatherHolidayOverview,
} from '@/types/agent';
import MapRoutePreview from './map-route-preview';
import { useLocale } from '@/context/locale-context';
import FisherySeasonChart from './fishery-season-chart';
import HolidayWeatherWidget from './holiday-weather-widget';

function formatTimestamp(value: string | undefined, locale: string) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return null;
    }
    return new Intl.DateTimeFormat(locale || undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    }).format(date);
}

function renderMetadataValue(value: unknown): string {
    if (value == null) {
        return '—';
    }
    if (typeof value === 'string') {
        return value;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
        return String(value);
    }
    if (Array.isArray(value)) {
        return value.map(item => renderMetadataValue(item)).join(', ');
    }
    try {
        return JSON.stringify(value);
    } catch {
        return String(value);
    }
}

export default function InformationSummary() {
    const { isLoading, error, refresh, isActive, hasAttempted } = useTranscription();
    const { toolResults } = useAgentInsights();
    const { t, locale } = useLocale();
    const [activeIndex, setActiveIndex] = useState(0);
    const previousCountRef = useRef(0);

    useEffect(() => {
        const nextCount = toolResults.length;

        if (nextCount === 0) {
            previousCountRef.current = 0;
            setActiveIndex(0);
            return;
        }

        if (nextCount !== previousCountRef.current) {
            previousCountRef.current = nextCount;
            setActiveIndex(nextCount - 1);
        } else if (activeIndex > nextCount - 1) {
            setActiveIndex(nextCount - 1);
        }
    }, [toolResults, activeIndex]);

    const activeResult: ToolResult | null = useMemo(() => {
        return toolResults[activeIndex] ?? null;
    }, [toolResults, activeIndex]);

    const mapMetadata = useMemo(() => {
        if (!activeResult?.metadata || typeof activeResult.metadata !== 'object') {
            return null;
        }
        const mapValue = (activeResult.metadata as Record<string, unknown>).map;
        if (
            mapValue &&
            typeof mapValue === 'object' &&
            'departure' in mapValue &&
            'arrival' in mapValue
        ) {
            return mapValue as MapRouteMetadata;
        }
        return null;
    }, [activeResult]);

    const metadataEntries = useMemo(() => {
        if (!activeResult?.metadata || typeof activeResult.metadata !== 'object') {
            return [] as Array<[string, unknown]>;
        }
        const hiddenKeys = new Set(['map', 'chartTimeline', 'chartSeries', 'records']);
        if (activeResult.toolName === 'weather_tide') {
            [
                'holidayOverview',
                'holiday_range',
                'holiday_days',
                'holiday_chart',
                'holiday_best',
                'holiday_advisories',
                'holiday_source',
                'target_date',
                'sunrise',
                'wind',
                'tide',
                'best_window',
                'summary',
                'tide_phase',
                'moon_age',
            ].forEach(key => hiddenKeys.add(key));
        }
        return Object.entries(activeResult.metadata).filter(([key]) => !hiddenKeys.has(key));
    }, [activeResult]);

    const fisheryChartData = useMemo(() => {
        if (!activeResult || activeResult.toolName !== 'fishery_catch') {
            return null;
        }

        const metadata = activeResult.metadata as FisheryCatchMetadata | null | undefined;
        if (!metadata) {
            return null;
        }

        const timeline = Array.isArray(metadata.chartTimeline)
            ? (metadata.chartTimeline as FisheryCatchTimelinePoint[])
            : [];
        if (timeline.length === 0) {
            return null;
        }

        const topSpecies = Array.isArray(metadata.topSpecies)
            ? (metadata.topSpecies as FisheryCatchTopSpecies[])
            : [];

        return {
            analysisRange: typeof metadata.analysisRange === 'string' ? metadata.analysisRange : undefined,
            timeline,
            topSpecies,
        };
    }, [activeResult]);

    const weatherOverview = useMemo(() => {
        if (!activeResult || activeResult.toolName !== 'weather_tide') {
            return null;
        }

        const metadata = activeResult.metadata as WeatherToolMetadata | null | undefined;
        if (!metadata || typeof metadata !== 'object') {
            return null;
        }

        const overviewRaw = metadata.holidayOverview;
        if (!overviewRaw || typeof overviewRaw !== 'object') {
            return null;
        }

        const overviewObject = overviewRaw as WeatherHolidayOverview;
        const overview: WeatherHolidayOverview = {
            rangeLabel: typeof overviewObject.rangeLabel === 'string' ? overviewObject.rangeLabel : null,
            days: Array.isArray(overviewObject.days) ? overviewObject.days : [],
            chart: Array.isArray(overviewObject.chart) ? overviewObject.chart : [],
            best: overviewObject.best ?? undefined,
            advisories: Array.isArray(overviewObject.advisories)
                ? overviewObject.advisories.filter((note): note is string => typeof note === 'string')
                : [],
            source: typeof overviewObject.source === 'string' ? overviewObject.source : null,
        };

        return {
            overview,
            targetDate: typeof metadata.target_date === 'string' ? metadata.target_date : undefined,
            sunrise: typeof metadata.sunrise === 'string' ? metadata.sunrise : undefined,
            wind: typeof metadata.wind === 'string' ? metadata.wind : undefined,
            tide: typeof metadata.tide === 'string' ? metadata.tide : undefined,
            tidePhase: typeof metadata.tide_phase === 'string' ? metadata.tide_phase : undefined,
            moonAge: typeof metadata.moon_age === 'number' ? metadata.moon_age : undefined,
            bestWindow: typeof metadata.best_window === 'string' ? metadata.best_window : undefined,
            summary: typeof metadata.summary === 'string' ? metadata.summary : undefined,
        };
    }, [activeResult]);

    const hasResults = toolResults.length > 0;

    const showIdleState = !hasAttempted && !hasResults;
    const showAwaitingState = hasAttempted && isActive && !hasResults && !error;

    const handlePrev = () => {
        setActiveIndex(index => Math.max(0, index - 1));
    };

    const handleNext = () => {
        setActiveIndex(index => Math.min(toolResults.length - 1, index + 1));
    };

    const receivedAtLabel = useMemo(() => {
        if (!activeResult) {
            return null;
        }
        const formatted = formatTimestamp(activeResult.receivedAt, locale);
        if (!formatted) {
            return null;
        }
        return t('information.receivedAt', { time: formatted });
    }, [activeResult, locale, t]);

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Workflow className="text-accent" />
                    {t('information.title')}
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {error && (
                    <div className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-md p-3">
                        {t('information.error')}
                        {' '}
                        <button className="underline" onClick={() => refresh()}>
                            {t('information.retry')}
                        </button>
                    </div>
                )}

                {showIdleState && (
                    <p className="text-sm text-muted-foreground">
                        {t('information.idle')}
                    </p>
                )}

                {showAwaitingState && (
                    <p className="text-sm text-muted-foreground">
                        {t('information.awaiting')}
                    </p>
                )}

                {!isLoading && !error && !showIdleState && !hasResults && !showAwaitingState && (
                    <p className="text-sm text-muted-foreground">
                        {t('information.empty')}
                    </p>
                )}

                {hasResults && activeResult && (
                    <div className="space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                                {activeResult.toolName && (
                                    <Badge variant="outline" className="bg-secondary/50">
                                        {activeResult.toolName}
                                    </Badge>
                                )}
                                {activeResult.title && (
                                    <span className="text-sm font-medium text-foreground/80">
                                        {activeResult.title}
                                    </span>
                                )}
                            </div>
                            <span className="text-xs uppercase tracking-wide text-muted-foreground">
                                {activeIndex + 1} / {toolResults.length}
                            </span>
                        </div>

                        <div className="space-y-3 rounded-2xl border border-border/60 bg-secondary/40 p-4">
                            {receivedAtLabel && (
                                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                    {receivedAtLabel}
                                </span>
                            )}
                            <p className="whitespace-pre-wrap text-sm leading-relaxed text-secondary-foreground">
                                {activeResult.content}
                            </p>
                            {weatherOverview && (
                                <HolidayWeatherWidget
                                    overview={weatherOverview.overview}
                                    targetDate={weatherOverview.targetDate}
                                    sunrise={weatherOverview.sunrise}
                                    wind={weatherOverview.wind}
                                    tide={weatherOverview.tide}
                                    tidePhase={weatherOverview.tidePhase}
                                    moonAge={weatherOverview.moonAge}
                                    bestWindow={weatherOverview.bestWindow}
                                    summary={weatherOverview.summary}
                                />
                            )}
                            {mapMetadata && (
                                <MapRoutePreview metadata={mapMetadata} />
                            )}
                            {fisheryChartData && (
                                <FisherySeasonChart
                                    analysisRange={fisheryChartData.analysisRange}
                                    timeline={fisheryChartData.timeline}
                                    topSpecies={fisheryChartData.topSpecies}
                                />
                            )}
                        </div>

                        <div className="flex items-center justify-between gap-3">
                            <Button
                                variant="outline"
                                onClick={handlePrev}
                                disabled={activeIndex === 0}
                                className="flex-1"
                            >
                                <ChevronLeft className="mr-2 h-4 w-4" />
                                {t('information.previous')}
                            </Button>
                            <Button
                                variant="outline"
                                onClick={handleNext}
                                disabled={activeIndex >= toolResults.length - 1}
                                className="flex-1"
                            >
                                {t('information.next')}
                                <ChevronRight className="ml-2 h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
