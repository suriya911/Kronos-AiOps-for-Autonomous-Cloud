import { Cpu, MemoryStick, HardDrive, Wifi } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import { getMockMetrics } from '@/lib/mock-data';
import { useMemo } from 'react';

const metrics = [
  { key: 'cpu' as const, label: 'CPU Utilization', icon: Cpu, color: 'hsl(217,91%,60%)' },
  { key: 'memory' as const, label: 'Memory Usage', icon: MemoryStick, color: 'hsl(270,70%,60%)' },
  { key: 'disk' as const, label: 'Disk I/O', icon: HardDrive, color: 'hsl(173,80%,40%)' },
  { key: 'latency' as const, label: 'Network Latency', icon: Wifi, color: 'hsl(25,95%,53%)' },
];

function getStatusColor(value: number, threshold: number | null) {
  if (!threshold) return 'bg-success';
  if (value >= threshold) return 'bg-destructive';
  if (value >= threshold * 0.8) return 'bg-warning';
  return 'bg-success';
}

export function SystemHealthPanel() {
  const data = useMemo(() => getMockMetrics('1h'), []);

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
      <h3 className="text-sm font-semibold text-foreground mb-4">System Health</h3>
      <div className="space-y-4">
        {metrics.map((m) => {
          const metric = data[m.key];
          return (
            <div key={m.key} className="flex items-center gap-3">
              <span className={`h-2 w-2 rounded-full shrink-0 ${getStatusColor(metric.current, metric.threshold)}`} />
              <m.icon className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="text-sm text-muted-foreground flex-1">{m.label}</span>
              <div className="w-24 h-8">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={metric.dataPoints.slice(-20)}>
                    <Line type="monotone" dataKey="value" stroke={m.color} dot={false} strokeWidth={1.5} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <span className="text-sm font-mono font-medium text-foreground w-16 text-right">
                {metric.current}{metric.unit}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
