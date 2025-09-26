'use client';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, ChartLegendContent } from '@/components/ui/chart';
import { Anchor } from 'lucide-react';
import type { ChartConfig } from '@/components/ui/chart';

const chartData = [
  { month: 'January', "Mahi-mahi": 4000, Wahoo: 2400 },
  { month: 'February', "Mahi-mahi": 3000, Wahoo: 1398 },
  { month: 'March', "Mahi-mahi": 2000, Wahoo: 9800 },
  { month: 'April', "Mahi-mahi": 2780, Wahoo: 3908 },
  { month: 'May', "Mahi-mahi": 1890, Wahoo: 4800 },
  { month: 'June', "Mahi-mahi": 2390, Wahoo: 3800 },
];

const chartConfig = {
  "Mahi-mahi": {
    label: "Mahi-mahi",
    color: "hsl(var(--primary))",
  },
  Wahoo: {
    label: "Wahoo",
    color: "hsl(var(--accent))",
  },
} satisfies ChartConfig;

export default function FishingYieldChart() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Anchor className="text-accent"/>
          Fishing Yields (lbs)
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
              tickFormatter={(value) => value.slice(0, 3)}
            />
            <YAxis />
            <ChartTooltip cursor={{ fill: 'hsl(var(--muted))' }} content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar dataKey="Mahi-mahi" fill="var(--color-Mahi-mahi)" radius={4} />
            <Bar dataKey="Wahoo" fill="var(--color-Wahoo)" radius={4} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
