'use client';

import { useMemo } from 'react';
import { Line, LineChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import {
    ChartContainer,
    ChartTooltip,
    ChartTooltipContent,
    ChartLegend,
    ChartLegendContent,
} from '@/components/ui/chart';
import type { ChartConfig } from '@/components/ui/chart';
import type {
    FisheryCatchTimelinePoint,
    FisheryCatchTopSpecies,
} from '@/types/agent';
import { useLocale } from '@/context/locale-context';

const COLOR_PALETTE = [
    'hsl(var(--chart-1))',
    'hsl(var(--chart-2))',
    'hsl(var(--chart-3))',
    'hsl(var(--chart-4))',
    'hsl(var(--chart-5))',
];

type ChartSeriesInfo = {
    name: string;
    key: string;
    color: string;
};

type FisherySeasonChartProps = {
    analysisRange?: string;
    timeline: FisheryCatchTimelinePoint[];
    topSpecies: FisheryCatchTopSpecies[];
};

export default function FisherySeasonChart({ analysisRange, timeline, topSpecies }: FisherySeasonChartProps) {
    const { locale } = useLocale();

    const speciesSeries = useMemo<ChartSeriesInfo[]>(() => {
        const timelineSpecies = new Set<string>();
        timeline.forEach(row => {
            Object.keys(row).forEach(key => {
                if (key !== 'date') {
                    timelineSpecies.add(key);
                }
            });
        });

        const preferredOrder = topSpecies.map(item => item.name);
        const allSpecies = Array.from(new Set([...preferredOrder, ...timelineSpecies])).slice(0, 5);

        return allSpecies.map((name, index) => ({
            name,
            key: `series_${index}`,
            color: COLOR_PALETTE[index % COLOR_PALETTE.length],
        }));
    }, [timeline, topSpecies]);

    const chartConfig = useMemo<ChartConfig>(() => {
        return speciesSeries.reduce((config, series) => {
            config[series.key] = {
                label: series.name,
                color: series.color,
            };
            return config;
        }, {} as ChartConfig);
    }, [speciesSeries]);

    const dateFormatter = useMemo(() => new Intl.DateTimeFormat(locale || undefined, {
        month: '2-digit',
        day: '2-digit',
    }), [locale]);

    const chartData = useMemo(() => {
        return timeline.map(row => {
            const rawDate = typeof row.date === 'string' ? row.date : '';
            const parsedDate = rawDate ? new Date(`${rawDate}T00:00:00`) : null;
            const dateLabel = parsedDate && !Number.isNaN(parsedDate.getTime())
                ? dateFormatter.format(parsedDate)
                : rawDate;

            const entry: Record<string, number | string> = {
                date: rawDate,
                dateLabel,
            };

            speciesSeries.forEach(series => {
                const value = row[series.name];
                entry[series.key] = typeof value === 'number'
                    ? Number(value.toFixed(2))
                    : Number.parseFloat(String(value ?? 0)) || 0;
            });

            return entry;
        });
    }, [timeline, speciesSeries, dateFormatter]);

    if (!chartData.length || !speciesSeries.length) {
        return null;
    }

    return (
        <div className="space-y-2">
            {analysisRange && (
                <p className="text-xs font-medium text-muted-foreground">
                    분석 기간: {analysisRange}
                </p>
            )}
            <ChartContainer config={chartConfig} className="min-h-[220px] w-full">
                <LineChart data={chartData} accessibilityLayer>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis
                        dataKey="dateLabel"
                        tickLine={false}
                        axisLine={false}
                        tickMargin={10}
                    />
                    <YAxis tickLine={false} axisLine={false} width={48} />
                    <ChartTooltip
                        content={(
                            <ChartTooltipContent
                                labelKey="dateLabel"
                                formatter={(value) =>
                                    `${Number(value ?? 0).toLocaleString(locale)} kg`
                                }
                            />
                        )}
                    />
                    <ChartLegend content={<ChartLegendContent />} />
                    {speciesSeries.map(series => (
                        <Line
                            key={series.key}
                            type="monotone"
                            dataKey={series.key}
                            name={series.name}
                            stroke={`var(--color-${series.key})`}
                            strokeWidth={2}
                            dot={false}
                            isAnimationActive={false}
                        />
                    ))}
                </LineChart>
            </ChartContainer>
        </div>
    );
}
