import { format } from 'date-fns';

interface TimelineEntry {
  state: string;
  ts: string;
  durationMs?: number;
}

const stateLabels: Record<string, string> = {
  ALARM_TRIGGERED: 'Alarm Triggered',
  TRIAGE_COMPLETE: 'Triage Complete',
  DIAGNOSIS_DONE: 'Diagnosis Done',
  GUARDRAIL_CHECKED: 'Guardrail Check',
  REMEDIATION_DONE: 'Auto-Remediated',
  INCIDENT_CLOSED: 'Incident Closed',
};

const stateColors: Record<string, string> = {
  ALARM_TRIGGERED: 'bg-muted-foreground',
  TRIAGE_COMPLETE: 'bg-primary',
  DIAGNOSIS_DONE: 'bg-primary',
  GUARDRAIL_CHECKED: 'bg-primary',
  REMEDIATION_DONE: 'bg-success',
  INCIDENT_CLOSED: 'bg-success',
};

export function TimelineTab({ timeline }: { timeline: TimelineEntry[] }) {
  return (
    <div className="relative">
      <div className="absolute left-3 top-3 bottom-3 w-px bg-border" />
      <div className="space-y-6">
        {timeline.map((step, i) => (
          <div key={i} className="flex items-start gap-4 relative">
            <div className={`h-6 w-6 rounded-full border-2 border-card ${stateColors[step.state] || 'bg-muted-foreground'} shrink-0 z-10 flex items-center justify-center`}>
              <span className="h-2 w-2 rounded-full bg-card" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground">
                {stateLabels[step.state] || step.state}
              </p>
              <p className="text-xs font-mono text-muted-foreground mt-0.5">
                {format(new Date(step.ts), 'HH:mm:ss.SSS')}
              </p>
              {step.durationMs !== undefined && step.durationMs > 0 && (
                <span className="text-xs text-primary mt-1 inline-block">
                  +{step.durationMs >= 1000 ? `${(step.durationMs / 1000).toFixed(1)}s` : `${step.durationMs}ms`}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
