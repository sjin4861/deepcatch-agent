'use client';

import { useMemo, type ComponentType } from 'react';
import { CalendarDays, Clock, MoonStar, Sun, ThermometerSun, Waves, Wind } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart';
import type { ChartConfig } from '@/components/ui/chart';
import type {
    WeatherHolidayBest,
    WeatherHolidayDay,
    WeatherHolidayOverview,
    WeatherHolidayTideEvent,
} from '@/types/agent';
import { cn } from '@/lib/utils';

const CHART_CONFIG: ChartConfig = {
    windSpeed: {
        label: '풍속 (m/s)',
        color: 'hsl(var(--chart-1))',
    },
    waveHeight: {
        label: '파고 (m)',
        color: 'hsl(var(--chart-2))',
    },
    precipitation: {
        label: '강수확률 (%)',
        color: 'hsl(var(--chart-3))',
    },
};

type HolidayWeatherWidgetProps = {
    overview: WeatherHolidayOverview;
    targetDate?: string;
    sunrise?: string;
    wind?: string;
    tide?: string;
    tidePhase?: string | null;
    moonAge?: number | null;
    bestWindow?: string;
    summary?: string;
};

export default function HolidayWeatherWidget({
    overview,
    targetDate,
    sunrise,
    wind,
    tide,
    tidePhase,
    moonAge,
    bestWindow,
    summary,
}: HolidayWeatherWidgetProps) {
    const days = useMemo<WeatherHolidayDay[]>(() => Array.isArray(overview.days) ? overview.days : [], [overview.days]);
    const chartPoints = useMemo(() => Array.isArray(overview.chart) ? overview.chart : [], [overview.chart]);
    const advisories = useMemo(() => Array.isArray(overview.advisories) ? overview.advisories.filter((note): note is string => typeof note === 'string' && note.trim().length > 0) : [], [overview.advisories]);
    const best = useMemo<WeatherHolidayBest | null>(() => (overview.best && typeof overview.best === 'object') ? overview.best : null, [overview.best]);

    const highlightedDay = useMemo<WeatherHolidayDay | null>(() => {
        if (!days.length) {
            return null;
        }
        if (best?.date) {
            const match = days.find(day => day.date === best.date);
            if (match) {
                return match;
            }
        }
        return days[0];
    }, [days, best]);

    const chartData = useMemo(() => {
        return chartPoints
            .map(point => {
                if (!point || typeof point !== 'object') {
                    return null;
                }
                const windValue = typeof point.windSpeed === 'number' ? Number(point.windSpeed.toFixed(1)) : null;
                const waveValue = typeof point.waveHeight === 'number' ? Number(point.waveHeight.toFixed(2)) : null;
                const precipitationValue = typeof point.precipitationChance === 'number'
                    ? Math.max(0, Math.min(100, Math.round(point.precipitationChance)))
                    : null;

                return {
                    date: point.date,
                    label: point.label || point.date,
                    windSpeed: windValue,
                    waveHeight: waveValue,
                    precipitation: precipitationValue,
                };
            })
            .filter((entry): entry is { date: string; label: string; windSpeed: number | null; waveHeight: number | null; precipitation: number | null } =>
                Boolean(entry && entry.date)
            );
    }, [chartPoints]);

    const detailItems = useMemo(() => {
        const items: Array<{ icon: ComponentType<{ className?: string }>; label: string; value?: string }> = [];
        if (targetDate) {
            items.push({ icon: CalendarDays, label: '일자', value: targetDate });
        }
        if (sunrise) {
            items.push({ icon: Sun, label: '일출', value: sunrise });
        }
        if (bestWindow) {
            items.push({ icon: Clock, label: '추천 시간대', value: bestWindow });
        }
        if (wind) {
            items.push({ icon: Wind, label: '바람', value: wind });
        }
        if (tide) {
            items.push({ icon: Waves, label: '물때', value: tide });
        }
        if (tidePhase) {
            const label = moonAge != null ? `${tidePhase} · 음력 ${moonAge.toFixed(1)}일` : tidePhase;
            items.push({ icon: MoonStar, label: '물때 단계', value: label });
        }
        if (summary) {
            items.push({ icon: ThermometerSun, label: '요약', value: summary });
        }
        return items;
    }, [targetDate, sunrise, bestWindow, wind, tide, tidePhase, moonAge, summary]);

    const highlightMetrics = useMemo(() => {
        if (!highlightedDay) {
            return [] as Array<{ label: string; value: string | null; icon: ComponentType<{ className?: string }> }>;
        }
        const metrics: Array<{ label: string; value: string | null; icon: ComponentType<{ className?: string }> }> = [];
        if (typeof highlightedDay.tempMin === 'number' || typeof highlightedDay.tempMax === 'number') {
            const min = highlightedDay.tempMin != null ? `${Math.round(highlightedDay.tempMin)}°` : null;
            const max = highlightedDay.tempMax != null ? `${Math.round(highlightedDay.tempMax)}°` : null;
            metrics.push({
                label: '기온',
                value: min && max ? `${min} / ${max}` : min ?? max,
                icon: ThermometerSun,
            });
        }
        if (typeof highlightedDay.windSpeed === 'number') {
            const direction = highlightedDay.windDirection ? ` (${highlightedDay.windDirection})` : '';
            metrics.push({
                label: '평균 풍속',
                value: `${highlightedDay.windSpeed.toFixed(1)} m/s${direction}`,
                icon: Wind,
            });
        }
        if (typeof highlightedDay.waveHeight === 'number') {
            metrics.push({
                label: '평균 파고',
                value: `${highlightedDay.waveHeight.toFixed(1)} m`,
                icon: Waves,
            });
        }
        if (highlightedDay.bestWindow) {
            metrics.push({
                label: '권장 시간대',
                value: highlightedDay.bestWindow,
                icon: Clock,
            });
        }
        if (highlightedDay.cautionWindow) {
            metrics.push({
                label: '주의 시간대',
                value: highlightedDay.cautionWindow,
                icon: Clock,
            });
        }
        const tidePhaseValue = highlightedDay.tidePhase ? highlightedDay.tidePhase : null;
        if (tidePhaseValue) {
            const moon = highlightedDay.moonAge != null ? ` · 음력 ${highlightedDay.moonAge.toFixed(1)}일` : '';
            metrics.push({
                label: '물때 단계',
                value: `${tidePhaseValue}${moon}`,
                icon: MoonStar,
            });
        }
        const highTideText = formatTideEvents(highlightedDay.highTides);
        if (highTideText) {
            metrics.push({
                label: '만조',
                value: highTideText,
                icon: Waves,
            });
        }
        const lowTideText = formatTideEvents(highlightedDay.lowTides);
        if (lowTideText) {
            metrics.push({
                label: '간조',
                value: lowTideText,
                icon: Waves,
            });
        }
        return metrics;
    }, [highlightedDay]);

    if (!overview.rangeLabel && !days.length) {
        return null;
    }

    return (
        <div className="space-y-4">
            {overview.rangeLabel && (
                <div className="space-y-2">
                    <p className="text-sm font-semibold text-foreground">
                        {overview.rangeLabel}
                    </p>
                    {detailItems.length > 0 && (
                        <div className="grid gap-2 sm:grid-cols-2">
                            {detailItems.map(item => (
                                <div
                                    key={`${item.label}-${item.value}`}
                                    className="flex items-start gap-2 rounded-lg border border-border/40 bg-background/50 p-2"
                                >
                                    <item.icon className="mt-0.5 h-4 w-4 text-muted-foreground" />
                                    <div className="text-xs">
                                        <p className="font-medium text-muted-foreground/80">{item.label}</p>
                                        <p className="text-foreground/90">{item.value}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {highlightedDay && (
                <div className="space-y-3 rounded-xl border border-primary/40 bg-primary/5 p-4 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-1">
                            <div className="flex items-center gap-2">
                                <Badge variant="secondary" className="bg-primary text-primary-foreground">
                                    추천 일정
                                </Badge>
                                <p className="text-sm font-semibold text-foreground">
                                    {highlightedDay.label || highlightedDay.date}
                                </p>
                            </div>
                            <p className="text-xs text-muted-foreground">
                                {highlightedDay.date}
                                {highlightedDay.weekday ? ` (${highlightedDay.weekday})` : ''}
                            </p>
                        </div>
                        {best?.score != null && (
                            <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                                적합도 {Math.round(best.score)}점
                            </span>
                        )}
                    </div>
                    {(best?.reason || highlightedDay.summary) && (
                        <p className="text-sm leading-relaxed text-foreground/80">
                            {best?.reason || highlightedDay.summary}
                        </p>
                    )}
                    {highlightMetrics.length > 0 && (
                        <div className="grid gap-2 sm:grid-cols-2">
                            {highlightMetrics.map(metric => (
                                metric.value ? (
                                    <div
                                        key={`${metric.label}-${metric.value}`}
                                        className="flex items-start gap-2 rounded-lg border border-border/30 bg-background/60 p-2"
                                    >
                                        <metric.icon className="mt-0.5 h-4 w-4 text-muted-foreground" />
                                        <div className="text-xs">
                                            <p className="font-medium text-muted-foreground/80">{metric.label}</p>
                                            <p className="text-foreground/90">{metric.value}</p>
                                        </div>
                                    </div>
                                ) : null
                            ))}
                        </div>
                    )}
                </div>
            )}

            {chartData.length > 0 && (
                <div className="space-y-2 rounded-xl border border-border/60 bg-background/50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        연휴별 핵심 지표
                    </p>
                    <ChartContainer config={CHART_CONFIG} className="min-h-[220px] w-full">
                        <ComposedChart data={chartData} accessibilityLayer>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={10} />
                            <YAxis yAxisId="left" tickLine={false} axisLine={false} width={42} />
                            <YAxis yAxisId="right" orientation="right" tickLine={false} axisLine={false} width={42} domain={[0, 100]} />
                            <ChartTooltip
                                content={(
                                    <ChartTooltipContent
                                        labelKey="label"
                                        formatter={(value, name, item) => {
                                            if (item?.dataKey === 'windSpeed') {
                                                return `${value} m/s`;
                                            }
                                            if (item?.dataKey === 'waveHeight') {
                                                return `${value} m`;
                                            }
                                            if (item?.dataKey === 'precipitation') {
                                                return `${value}%`;
                                            }
                                            return String(value ?? '');
                                        }}
                                    />
                                )}
                            />
                            <ChartLegend content={<ChartLegendContent />} />
                            <Bar
                                yAxisId="right"
                                dataKey="precipitation"
                                name="강수확률 (%)"
                                fill="var(--color-precipitation)"
                                radius={[4, 4, 0, 0]}
                                barSize={24}
                            />
                            <Line
                                yAxisId="left"
                                dataKey="windSpeed"
                                name="풍속 (m/s)"
                                stroke="var(--color-windSpeed)"
                                strokeWidth={2}
                                dot={{ r: 3 }}
                                isAnimationActive={false}
                            />
                            <Line
                                yAxisId="left"
                                dataKey="waveHeight"
                                name="파고 (m)"
                                stroke="var(--color-waveHeight)"
                                strokeWidth={2}
                                dot={{ r: 3 }}
                                strokeDasharray="4 4"
                                isAnimationActive={false}
                            />
                        </ComposedChart>
                    </ChartContainer>
                </div>
            )}

            {days.length > 0 && (
                <div className="grid gap-3 md:grid-cols-2">
                    {days.map(day => (
                        <div
                            key={day.date}
                            className={cn(
                                'space-y-2 rounded-xl border border-border/60 bg-muted/10 p-4',
                                highlightedDay && day.date === highlightedDay.date && 'border-primary/70 bg-primary/5'
                            )}
                        >
                            <div className="flex items-start justify-between gap-2">
                                <div>
                                    <p className="text-sm font-semibold text-foreground">{day.label || day.date}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {day.date}
                                        {day.weekday ? ` (${day.weekday})` : ''}
                                    </p>
                                </div>
                                {typeof day.comfortScore === 'number' && (
                                    <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-xs font-medium text-foreground/80">
                                        적합도 {Math.round(day.comfortScore)}점
                                    </span>
                                )}
                            </div>
                            {day.summary && (
                                <p className="text-sm text-muted-foreground">
                                    {day.summary}
                                </p>
                            )}
                            <div className="grid gap-2 text-xs md:grid-cols-2">
                                {renderDayMetric('온도', formatTemperatureRange(day.tempMin, day.tempMax))}
                                {renderDayMetric('풍속', formatWind(day.windSpeed, day.windDirection))}
                                {renderDayMetric('파고', day.waveHeight != null ? `${day.waveHeight.toFixed(1)} m` : null)}
                                {renderDayMetric('권장 시간대', day.bestWindow ?? null)}
                                {renderDayMetric('주의 시간대', day.cautionWindow ?? null)}
                                {renderDayMetric('물때', day.tidePhase ?? null)}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {advisories.length > 0 && (
                <div className="space-y-2 rounded-xl border border-border/60 bg-background/40 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        참고 사항
                    </p>
                    <ul className="space-y-1.5 text-sm text-muted-foreground">
                        {advisories.map(note => (
                            <li key={note} className="leading-relaxed">
                                {note}
                            </li>
                        ))}
                    </ul>
                    {overview.source && (
                        <p className="text-[11px] text-muted-foreground/70">
                            출처: {overview.source}
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}

function formatTideEvents(events?: WeatherHolidayTideEvent[] | null) {
    if (!Array.isArray(events) || events.length === 0) {
        return null;
    }
    return events
        .filter(event => event && typeof event.time === 'string')
        .map(event => {
            const height = typeof event.height === 'number' ? `${event.height.toFixed(2)}m` : '';
            return `${event.time}${height ? ` (${height})` : ''}`;
        })
        .join(', ');
}

function formatTemperatureRange(min?: number, max?: number) {
    if (min == null && max == null) {
        return null;
    }
    const minText = min != null ? `${Math.round(min)}°` : null;
    const maxText = max != null ? `${Math.round(max)}°` : null;
    if (minText && maxText) {
        return `${minText} / ${maxText}`;
    }
    return minText ?? maxText;
}

function formatWind(speed?: number, direction?: string) {
    if (speed == null && !direction) {
        return null;
    }
    const base = speed != null ? `${speed.toFixed(1)} m/s` : '';
    if (direction) {
        return `${base}${base ? ' · ' : ''}${direction}`;
    }
    return base || direction || null;
}

function renderDayMetric(label: string, value: string | null) {
    if (!value) {
        return null;
    }
    return (
        <div className="rounded-lg border border-border/40 bg-background/60 p-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground/80">{label}</p>
            <p className="text-sm text-foreground/90">{value}</p>
        </div>
    );
}
