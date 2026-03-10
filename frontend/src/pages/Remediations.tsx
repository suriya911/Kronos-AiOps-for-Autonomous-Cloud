import { useMemo } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { useRemediations } from '@/hooks/use-remediations';

const statusColors: Record<string, string> = {
  SUCCESS: 'text-success bg-success/20',
  FAILED:  'text-destructive bg-destructive/20',
  SKIPPED: 'text-muted-foreground bg-muted',
};

const RemediationsPage = () => {
  const { data, isLoading } = useRemediations();
  const remediations = data?.remediations ?? [];

  // Compute KPI stats from real remediation data
  const stats = useMemo(() => {
    if (!remediations.length) return { successRate: 0, avgDuration: 0, todayCount: 0 };
    const successCount  = remediations.filter((r) => r.status === 'SUCCESS').length;
    const successRate   = Math.round((successCount / remediations.length) * 1000) / 10;
    const avgDurationMs = remediations.reduce((s, r) => s + r.durationMs, 0) / remediations.length;
    const avgDuration   = Math.round(avgDurationMs / 100) / 10; // ms → seconds, 1dp
    const todayStart    = new Date(); todayStart.setHours(0, 0, 0, 0);
    const todayCount    = remediations.filter((r) => new Date(r.executedAt) >= todayStart).length;
    return { successRate, avgDuration, todayCount };
  }, [remediations]);

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground">Auto-Remediation Success Rate</p>
          <p className="text-3xl font-bold text-success mt-1">{stats.successRate}%</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground">Average Remediation Time</p>
          <p className="text-3xl font-bold text-foreground mt-1">{stats.avgDuration}s</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground">Remediations Today</p>
          <p className="text-3xl font-bold text-primary mt-1">{stats.todayCount}</p>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-card shadow-lg overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
            Loading remediations…
          </div>
        ) : remediations.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
            No remediations recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground text-xs">
                  <th className="text-left px-4 py-3 font-medium">Incident ID</th>
                  <th className="text-left px-4 py-3 font-medium">Action</th>
                  <th className="text-left px-4 py-3 font-medium">Target</th>
                  <th className="text-left px-4 py-3 font-medium">Executed</th>
                  <th className="text-left px-4 py-3 font-medium">Duration</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-left px-4 py-3 font-medium">SSM Command</th>
                </tr>
              </thead>
              <tbody>
                {remediations.map((r) => (
                  <tr key={r.remediationId} className="border-b border-border/50 hover:bg-accent/50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{r.incidentId.substring(0, 14)}…</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent text-foreground">{r.actionType}</span>
                    </td>
                    <td className="px-4 py-3 text-foreground text-xs">{r.target}</td>
                    <td className="px-4 py-3 text-muted-foreground text-xs" title={r.executedAt}>
                      {formatDistanceToNow(new Date(r.executedAt), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-foreground">{r.durationMs}ms</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[r.status] ?? ''}`}>{r.status}</span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{r.ssmCommandId}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default RemediationsPage;
