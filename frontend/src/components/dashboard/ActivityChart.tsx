import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { generateActivityData } from '@/lib/mock-data';
import { useMemo } from 'react';

export function ActivityChart() {
  const data = useMemo(() => generateActivityData(), []);

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
      <h3 className="text-sm font-semibold text-foreground mb-4">Incident Activity — Last 24 Hours</h3>
      <ResponsiveContainer width="100%" height={256}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(218,43%,20%)" />
          <XAxis dataKey="hour" tick={{ fill: 'hsl(218,11%,46%)', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: 'hsl(218,11%,46%)', fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{
              backgroundColor: 'hsl(224,43%,11%)',
              border: '1px solid hsl(218,43%,20%)',
              borderRadius: '8px',
              color: 'hsl(213,31%,95%)',
              fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: 'hsl(218,11%,46%)' }} />
          <Area
            type="monotone"
            dataKey="autoResolved"
            name="Auto-Resolved"
            stroke="hsl(217,91%,60%)"
            fill="hsl(217,91%,60%)"
            fillOpacity={0.2}
            strokeWidth={2}
          />
          <Area
            type="monotone"
            dataKey="escalated"
            name="Escalated"
            stroke="hsl(38,92%,50%)"
            fill="hsl(38,92%,50%)"
            fillOpacity={0.2}
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
