import { Clock, Zap, AlertTriangle, Activity } from 'lucide-react';
import type { KPIData } from '@/lib/types';

interface KPICardsProps {
  kpi: KPIData;
}

export function KPICards({ kpi }: KPICardsProps) {
  const cards = [
    {
      icon: Clock,
      iconColor: 'text-primary',
      value: `${kpi.mttr.value}s`,
      label: 'Mean Time To Resolve',
      subtext: `↓ ${Math.abs(kpi.mttr.changeVsBaseline)}% vs manual baseline`,
      subtextColor: 'text-success',
    },
    {
      icon: Zap,
      iconColor: 'text-success',
      value: `${kpi.autoResolutionRate.value}%`,
      valueColor: 'text-success',
      label: 'Auto-Resolution Rate',
      subtext: `Last ${kpi.autoResolutionRate.period}`,
      subtextColor: 'text-muted-foreground',
    },
    {
      icon: AlertTriangle,
      iconColor: kpi.openIncidents.total > 0 ? 'text-destructive' : 'text-success',
      value: String(kpi.openIncidents.total),
      valueColor: kpi.openIncidents.total > 0 ? 'text-destructive' : 'text-success',
      label: 'Open Incidents',
      subtext: `${kpi.openIncidents.critical} critical, ${kpi.openIncidents.warning} warning`,
      subtextColor: 'text-muted-foreground',
    },
    {
      icon: Activity,
      iconColor: 'text-primary',
      value: `${kpi.detectionLatency.value}s`,
      valueColor: 'text-primary',
      label: 'Detection Latency',
      subtext: 'Alarm → triage',
      subtextColor: 'text-muted-foreground',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-xl border border-border bg-card p-5 shadow-lg glow-blue"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-accent">
              <card.icon className={`h-5 w-5 ${card.iconColor}`} />
            </div>
          </div>
          <p className={`text-3xl font-bold tracking-tight ${card.valueColor || 'text-foreground'}`}>
            {card.value}
          </p>
          <p className="text-sm text-muted-foreground mt-1">{card.label}</p>
          <p className={`text-xs mt-2 ${card.subtextColor}`}>{card.subtext}</p>
        </div>
      ))}
    </div>
  );
}
