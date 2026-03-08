import { LineChart, Line, XAxis, YAxis, ReferenceLine, ResponsiveContainer, Tooltip } from 'recharts';
import type { IncidentDetail } from '@/lib/types';

export function MetricsTab({ incident }: { incident: IncidentDetail }) {
  const data = incident.metricHistory.map((value, i) => ({ index: i, value }));
  const threshold = incident.type === 'CPU' ? 80 : incident.type === 'MEMORY' ? 85 : incident.type === 'LATENCY' ? 200 : null;

  return (
    <div>
      <div className="mb-4">
        <ResponsiveContainer width="100%" height={192}>
          <LineChart data={data}>
            <XAxis dataKey="index" tick={{ fill: 'hsl(218,11%,46%)', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: 'hsl(218,11%,46%)', fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(224,43%,11%)',
                border: '1px solid hsl(218,43%,20%)',
                borderRadius: '8px',
                color: 'hsl(213,31%,95%)',
                fontSize: 12,
              }}
            />
            <Line type="monotone" dataKey="value" stroke="hsl(217,91%,60%)" dot={false} strokeWidth={2} />
            {threshold && (
              <ReferenceLine y={threshold} stroke="hsl(0,72%,51%)" strokeDasharray="5 5" label={{ value: 'Threshold', fill: 'hsl(0,72%,51%)', fontSize: 10, position: 'right' }} />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="flex gap-3">
        <div className="flex-1 rounded-lg bg-accent p-3 text-center">
          <p className="text-xs text-muted-foreground">Z-Score</p>
          <p className="text-lg font-bold text-foreground">{incident.zScore.toFixed(2)}</p>
        </div>
        <div className="flex-1 rounded-lg bg-accent p-3 text-center">
          <p className="text-xs text-muted-foreground">EWMA</p>
          <p className="text-lg font-bold text-foreground">{incident.ewmaValue.toFixed(1)}</p>
        </div>
        <div className="flex-1 rounded-lg bg-accent p-3 text-center">
          <p className="text-xs text-muted-foreground">Peak Value</p>
          <p className="text-lg font-bold text-foreground">{incident.metricValue.toFixed(1)}</p>
        </div>
      </div>
    </div>
  );
}
