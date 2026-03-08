import { format } from 'date-fns';
import type { IncidentDetail } from '@/lib/types';

export function RemediationLogTab({ incident }: { incident: IncidentDetail }) {
  if (!incident.remediation) {
    return <p className="text-sm text-muted-foreground">No remediation data available.</p>;
  }

  const { remediation } = incident;

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <div className="rounded-lg bg-accent px-3 py-2">
          <p className="text-xs text-muted-foreground">Action</p>
          <p className="text-sm font-medium text-foreground">{remediation.actionType}</p>
        </div>
        <div className="rounded-lg bg-accent px-3 py-2">
          <p className="text-xs text-muted-foreground">Target</p>
          <p className="text-sm font-medium text-foreground">{remediation.target}</p>
        </div>
        <div className="rounded-lg bg-accent px-3 py-2">
          <p className="text-xs text-muted-foreground">Duration</p>
          <p className="text-sm font-medium text-foreground">{(remediation.durationMs / 1000).toFixed(1)}s</p>
        </div>
      </div>

      <div className="rounded-lg bg-background border border-border p-4 font-mono text-xs space-y-1.5 overflow-x-auto">
        {remediation.log.map((entry, i) => (
          <p key={i} className="text-muted-foreground">
            <span className="text-primary">[{format(new Date(entry.ts), 'HH:mm:ss')}]</span>{' '}
            {entry.msg}
          </p>
        ))}
      </div>

      <div className="mt-4 rounded-lg bg-accent px-3 py-2">
        <p className="text-xs text-muted-foreground">SSM Command ID</p>
        <p className="text-xs font-mono text-foreground">{remediation.ssmCommandId}</p>
      </div>
    </div>
  );
}
