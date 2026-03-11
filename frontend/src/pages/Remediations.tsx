import { useMemo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Bot, UserCheck } from 'lucide-react';
import { useRemediations } from '@/hooks/use-remediations';

// Action types that indicate automated SSM-driven remediation
const AUTO_ACTIONS = new Set([
  'RESTART_SERVICE', 'CLEAR_CACHE', 'ROTATE_LOGS', 'SCALE_OUT',
  'SCALE_IN', 'REBOOT', 'FLUSH_QUEUE', 'ROLLBACK',
]);

const statusColors: Record<string, string> = {
  SUCCESS: 'text-success bg-success/20',
  FAILED:  'text-destructive bg-destructive/20',
  SKIPPED: 'text-muted-foreground bg-muted',
};

type Tab = 'autonomous' | 'human';

const RemediationsPage = () => {
  const { data, isLoading } = useRemediations();
  const [activeTab, setActiveTab] = useState<Tab>('autonomous');
  const remediations = data?.remediations ?? [];

  const { autonomous, humanAssisted } = useMemo(() => {
    const autonomous    = remediations.filter((r) => AUTO_ACTIONS.has(r.actionType) && r.status === 'SUCCESS');
    const humanAssisted = remediations.filter((r) => !AUTO_ACTIONS.has(r.actionType) || r.status !== 'SUCCESS');
    return { autonomous, humanAssisted };
  }, [remediations]);

  // KPI stats across all
  const stats = useMemo(() => {
    if (!remediations.length) return { successRate: 0, avgDuration: 0, totalAuto: 0, totalHuman: 0 };
    const successCount  = remediations.filter((r) => r.status === 'SUCCESS').length;
    const successRate   = Math.round((successCount / remediations.length) * 1000) / 10;
    const avgDurationMs = remediations.reduce((s, r) => s + r.durationMs, 0) / remediations.length;
    const avgDuration   = Math.round(avgDurationMs / 100) / 10;
    return { successRate, avgDuration, totalAuto: autonomous.length, totalHuman: humanAssisted.length };
  }, [remediations, autonomous, humanAssisted]);

  const displayed = activeTab === 'autonomous' ? autonomous : humanAssisted;

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground">Success Rate</p>
          <p className="text-3xl font-bold text-success mt-1">{stats.successRate}%</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground">Avg. Resolution Time</p>
          <p className="text-3xl font-bold text-foreground mt-1">{stats.avgDuration}s</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5" /> Autonomous
          </p>
          <p className="text-3xl font-bold text-primary mt-1">{stats.totalAuto}</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground flex items-center gap-1.5">
            <UserCheck className="h-3.5 w-3.5" /> Human-Assisted
          </p>
          <p className="text-3xl font-bold text-foreground mt-1">{stats.totalHuman}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="rounded-xl border border-border bg-card shadow-lg overflow-hidden">
        <div className="flex border-b border-border">
          <button
            onClick={() => setActiveTab('autonomous')}
            className={`flex items-center gap-2 flex-1 py-3.5 text-sm font-medium transition-colors ${
              activeTab === 'autonomous'
                ? 'text-primary border-b-2 border-primary bg-primary/5'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
            }`}
          >
            <Bot className="h-4 w-4" />
            Autonomous Remediation
            <span className="ml-1 px-1.5 py-0.5 rounded-full text-xs bg-primary/20 text-primary font-mono">
              {autonomous.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('human')}
            className={`flex items-center gap-2 flex-1 py-3.5 text-sm font-medium transition-colors ${
              activeTab === 'human'
                ? 'text-primary border-b-2 border-primary bg-primary/5'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
            }`}
          >
            <UserCheck className="h-4 w-4" />
            Human-Assisted Resolution
            <span className="ml-1 px-1.5 py-0.5 rounded-full text-xs bg-muted text-muted-foreground font-mono">
              {humanAssisted.length}
            </span>
          </button>
        </div>

        {/* Tab description */}
        <div className="px-4 py-2.5 bg-muted/20 border-b border-border text-xs text-muted-foreground">
          {activeTab === 'autonomous'
            ? 'Actions executed automatically by the AIOps engine via SSM Run Command without human intervention.'
            : 'Incidents that required operator involvement — escalated cases or manual closures by on-call engineers.'}
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
            Loading remediations…
          </div>
        ) : displayed.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
            {activeTab === 'autonomous'
              ? 'No autonomous remediations recorded yet.'
              : 'No human-assisted resolutions recorded yet.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground text-xs">
                  <th className="text-left px-4 py-3 font-medium">Incident ID</th>
                  <th className="text-left px-4 py-3 font-medium">
                    {activeTab === 'autonomous' ? 'Action Executed' : 'Resolution Type'}
                  </th>
                  <th className="text-left px-4 py-3 font-medium">Target Resource</th>
                  <th className="text-left px-4 py-3 font-medium">Executed</th>
                  <th className="text-left px-4 py-3 font-medium">Duration</th>
                  <th className="text-left px-4 py-3 font-medium">Outcome</th>
                  {activeTab === 'autonomous' && (
                    <th className="text-left px-4 py-3 font-medium">SSM Command</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {displayed.map((r) => (
                  <tr key={r.remediationId} className="border-b border-border/50 hover:bg-accent/50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {r.incidentId.substring(0, 14)}…
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent text-foreground">
                        {r.actionType || (activeTab === 'human' ? 'MANUAL_CLOSURE' : '—')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground text-xs">{r.target || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground text-xs" title={r.executedAt}>
                      {formatDistanceToNow(new Date(r.executedAt), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-foreground">{r.durationMs}ms</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[r.status] ?? ''}`}>
                        {r.status}
                      </span>
                    </td>
                    {activeTab === 'autonomous' && (
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {r.ssmCommandId || '—'}
                      </td>
                    )}
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
