'use client';

import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, ChartLegendContent } from '@/components/ui/chart';
import { Anchor } from 'lucide-react';
import type { ChartConfig } from '@/components/ui/chart';
import { useLocale } from '@/context/locale-context';

const rawData = [
  { monthIndex: 0, mahi: 4000, wahoo: 2400 },
  { monthIndex: 1, mahi: 3000, wahoo: 1398 },
  { monthIndex: 2, mahi: 2000, wahoo: 9800 },
  { monthIndex: 3, mahi: 2780, wahoo: 3908 },
  { monthIndex: 4, mahi: 1890, wahoo: 4800 },
  { monthIndex: 5, mahi: 2390, wahoo: 3800 },
];

export default function FishingYieldChart() {
  const { t, locale } = useLocale();

  const monthFormatter = useMemo(
    () => new Intl.DateTimeFormat(locale, { month: 'short' }),
    [locale],
  );

  const chartData = useMemo(
    () => rawData.map(item => ({
      month: monthFormatter.format(new Date(2024, item.monthIndex, 1)),
      mahi: item.mahi,
      wahoo: item.wahoo,
    })),
    [monthFormatter],
  );

  const chartConfig = useMemo<ChartConfig>(() => ({
    mahi: {
      label: t('chart.fishingYield.series.mahi'),
      color: 'hsl(var(--primary))',
    },
    wahoo: {
      label: t('chart.fishingYield.series.wahoo'),
      color: 'hsl(var(--accent))',
    },
  }), [t]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Anchor className="text-accent"/>
          {t('chart.fishingYield.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="min-h-[200px] w-full">
          <BarChart data={chartData} accessibilityLayer>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="month"
              tickLine={false}
              tickMargin={10}
              axisLine={false}
              tickFormatter={(value) => value}
            />
            <YAxis />
            <ChartTooltip cursor={{ fill: 'hsl(var(--muted))' }} content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar dataKey="mahi" fill="var(--color-mahi)" radius={4} />
            <Bar dataKey="wahoo" fill="var(--color-wahoo)" radius={4} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
