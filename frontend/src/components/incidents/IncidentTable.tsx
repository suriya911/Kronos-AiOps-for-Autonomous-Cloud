import { formatDistanceToNow } from 'date-fns';
import { AlertTriangle } from 'lucide-react';
import type { Incident } from '@/lib/types';
import { StatusBadge, MethodBadge } from '@/components/incidents/IncidentBadges';

function ActionRequiredBadge() {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-destructive/15 text-destructive border border-destructive/30 animate-pulse">
      <AlertTriangle className="h-3 w-3" />
      Action Required
    </span>
  );
}

interface IncidentTableProps {
  incidents: Incident[];
  onRowClick: (incident: Incident) => void;
  compact?: boolean;
}

export function IncidentTable({ incidents, onRowClick, compact }: IncidentTableProps) {
  const items = compact ? incidents.slice(0, 10) : incidents;

  return (
    <div className="rounded-xl border border-border bg-card shadow-lg overflow-hidden">
      {compact && (
        <div className="px-5 py-3 border-b border-border">
          <h3 className="text-sm font-semibold text-foreground">Recent Incidents</h3>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-xs">
              <th className="text-left px-4 py-3 font-medium">Status</th>
              <th className="text-left px-4 py-3 font-medium">Type</th>
              <th className="text-left px-4 py-3 font-medium">Incident ID</th>
              <th className="text-left px-4 py-3 font-medium">Detected</th>
              {!compact && <th className="text-left px-4 py-3 font-medium">MTTR</th>}
              <th className="text-left px-4 py-3 font-medium">Method</th>
            </tr>
          </thead>
          <tbody>
            {items.map((inc) => {
              const needsAction =
                inc.severity === 'CRITICAL' &&
                (inc.status === 'OPEN' || inc.status === 'ESCALATED');
              return (
                <tr
                  key={inc.incidentId}
                  onClick={() => onRowClick(inc)}
                  className={`border-b border-border/50 hover:bg-accent/50 cursor-pointer transition-colors slide-in-row${needsAction ? ' bg-destructive/5' : ''}`}
                >
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      <StatusBadge status={inc.status} />
                      {needsAction && <ActionRequiredBadge />}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent text-foreground">
                      {inc.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {inc.incidentId.substring(0, 14)}…
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs" title={inc.detectedAt}>
                    {formatDistanceToNow(new Date(inc.detectedAt), { addSuffix: true })}
                  </td>
                  {!compact && (
                    <td className={`px-4 py-3 font-mono text-xs ${
                      inc.mttr && inc.mttr > 120 ? 'text-destructive' : 'text-foreground'
                    }`}>
                      {inc.mttr ? `${inc.mttr}s` : '—'}
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <MethodBadge method={inc.method} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
