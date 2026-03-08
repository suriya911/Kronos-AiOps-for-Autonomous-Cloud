import type { IncidentStatus, IncidentMethod } from '@/lib/types';

const statusConfig: Record<IncidentStatus, { color: string; label: string }> = {
  RESOLVED: { color: 'bg-success/20 text-success', label: 'Resolved' },
  IN_PROGRESS: { color: 'bg-primary/20 text-primary pulse-status', label: 'In Progress' },
  OPEN: { color: 'bg-warning/20 text-warning', label: 'Open' },
  ESCALATED: { color: 'bg-warning/20 text-warning', label: 'Escalated' },
  ERROR: { color: 'bg-destructive/20 text-destructive', label: 'Error' },
};

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const cfg = statusConfig[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.color}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${
        status === 'RESOLVED' ? 'bg-success' :
        status === 'IN_PROGRESS' ? 'bg-primary' :
        status === 'ESCALATED' || status === 'OPEN' ? 'bg-warning' :
        'bg-destructive'
      }`} />
      {cfg.label}
    </span>
  );
}

const methodConfig: Record<IncidentMethod, { icon: string; color: string; label: string }> = {
  AUTO: { icon: '⚡', color: 'text-primary', label: 'Auto' },
  MANUAL: { icon: '👤', color: 'text-muted-foreground', label: 'Manual' },
  ESCALATED: { icon: '📧', color: 'text-warning', label: 'Escalated' },
};

export function MethodBadge({ method }: { method: IncidentMethod }) {
  const cfg = methodConfig[method];
  return (
    <span className={`text-xs font-medium ${cfg.color}`}>
      {cfg.icon} {cfg.label}
    </span>
  );
}
