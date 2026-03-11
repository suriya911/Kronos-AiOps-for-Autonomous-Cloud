import { useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import { Info } from 'lucide-react';
import { useMetrics } from '@/hooks/use-metrics';

const ranges = ['1h', '6h', '24h', '7d', '30d'] as const;

const chartConfig = [
  { key: 'cpu' as const, title: 'CPU Utilization', color: 'hsl(217,91%,60%)', fill: 'hsl(217,91%,60%)' },
  { key: 'memory' as const, title: 'Memory Usage', color: 'hsl(270,70%,60%)', fill: 'hsl(270,70%,60%)' },
  { key: 'disk' as const, title: 'Disk I/O', color: 'hsl(173,80%,40%)', fill: 'hsl(173,80%,40%)' },
  { key: 'latency' as const, title: 'Network Latency', color: 'hsl(25,95%,53%)', fill: 'hsl(25,95%,53%)' },
];

const MetricsPage = () => {
  const [range, setRange] = useState<string>('1h');
  const { data, isLoading } = useMetrics(range);

  // Check if any metric has isSimulated flag (backend sets it when CW has no data)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const isSimulated = data && (data as any).cpu?.isSimulated === true;

  return (
    <div className="space-y-6">
      {isSimulated && (
        <div className="flex items-start gap-2.5 rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          <Info className="h-4 w-4 shrink-0 mt-0.5 text-primary" />
          <span>
            <span className="font-medium text-foreground">Simulated data</span> — No active EC2 instances are emitting
            CloudWatch metrics. Charts show representative demo data. Connect real infrastructure to see live telemetry.
          </span>
        </div>
      )}
      <div className="flex justify-end gap-1">
        {ranges.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
              range === r ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64 rounded-xl border border-border bg-card text-muted-foreground text-sm">
          Loading metrics…
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {chartConfig.map((cfg) => {
            const metric = data?.[cfg.key];
            if (!metric) return null;

            // In dev environments without real EC2 the Lambda returns empty dataPoints
            const hasData = metric.dataPoints.length > 0;

            return (
              <div key={cfg.key} className="rounded-xl border border-border bg-card p-5 shadow-lg">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="text-sm font-semibold text-foreground">{cfg.title}</h3>
                  <span className="text-2xl font-bold text-foreground">
                    {metric.current}<span className="text-sm text-muted-foreground ml-1">{metric.unit}</span>
                  </span>
                </div>

                {hasData ? (
                  <>
                    <ResponsiveContainer width="100%" height={256}>
                      <AreaChart data={metric.dataPoints}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(218,43%,20%)" />
                        <XAxis dataKey="ts" tick={false} axisLine={false} />
                        <YAxis tick={{ fill: 'hsl(218,11%,46%)', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: 'hsl(224,43%,11%)',
                            border: '1px solid hsl(218,43%,20%)',
                            borderRadius: '8px',
                            color: 'hsl(213,31%,95%)',
                            fontSize: 12,
                          }}
                          labelFormatter={() => ''}
                          formatter={(value: number) => [`${value.toFixed(1)} ${metric.unit}`, cfg.title]}
                        />
                        <Area type="monotone" dataKey="value" stroke={cfg.color} fill={cfg.fill} fillOpacity={0.15} strokeWidth={2} />
                        {metric.threshold && (
                          <ReferenceLine y={metric.threshold} stroke="hsl(0,72%,51%)" strokeDasharray="5 5" />
                        )}
                      </AreaChart>
                    </ResponsiveContainer>
                    <div className="flex gap-4 mt-3 text-xs text-muted-foreground">
                      <span>Min: <span className="text-foreground font-medium">{metric.min}{metric.unit}</span></span>
                      <span>Max: <span className="text-foreground font-medium">{metric.max}{metric.unit}</span></span>
                      <span>Avg: <span className="text-foreground font-medium">{metric.avg}{metric.unit}</span></span>
                    </div>
                  </>
                ) : (
                  <div className="flex items-center justify-center h-64 text-muted-foreground text-xs text-center">
                    No data available for this range.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default MetricsPage;
