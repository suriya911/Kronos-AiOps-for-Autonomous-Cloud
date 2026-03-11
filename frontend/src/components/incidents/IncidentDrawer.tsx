import { X, CheckCircle2, Loader2 } from 'lucide-react';
import { useState } from 'react';
import type { IncidentDetail } from '@/lib/types';
import { StatusBadge } from './IncidentBadges';
import { TimelineTab } from './TimelineTab';
import { MetricsTab } from './MetricsTab';
import { RemediationLogTab } from './RemediationLogTab';
import { api } from '@/lib/api';

interface IncidentDrawerProps {
  incident:    IncidentDetail;
  open:        boolean;
  onClose:     () => void;
  onResolved?: () => void;
}

export function IncidentDrawer({ incident, open, onClose, onResolved }: IncidentDrawerProps) {
  const [activeTab, setActiveTab]   = useState<'timeline' | 'metrics' | 'remediation'>('timeline');
  const [resolving, setResolving]   = useState(false);
  const [resolveErr, setResolveErr] = useState('');

  if (!open) return null;

  const canResolve = incident.status === 'OPEN' || incident.status === 'ESCALATED' || incident.status === 'ERROR';

  const handleResolve = async () => {
    setResolving(true);
    setResolveErr('');
    try {
      await api.resolveIncident(incident.incidentId);
      onResolved?.();
      onClose();
    } catch (err) {
      setResolveErr(err instanceof Error ? err.message : 'Failed to resolve incident.');
    } finally {
      setResolving(false);
    }
  };

  const tabs = [
    { id: 'timeline' as const,    label: 'Timeline' },
    { id: 'metrics' as const,     label: 'Metrics' },
    { id: 'remediation' as const, label: 'Remediation Log' },
  ];

  return (
    <>
      <div className="fixed inset-0 bg-background/60 backdrop-blur-sm z-50" onClick={onClose} />
      <div className="fixed right-0 top-0 h-screen w-full max-w-[560px] bg-card border-l border-border z-50 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="p-5 border-b border-border">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-lg font-semibold text-foreground">{incident.incidentId}</span>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={incident.status} />
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-accent text-foreground">{incident.type}</span>
          </div>
          <p className="text-xs text-muted-foreground mt-2 font-mono">Detected: {incident.detectedAt}</p>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'text-primary border-b-2 border-primary'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {activeTab === 'timeline'    && <TimelineTab timeline={incident.timeline} />}
          {activeTab === 'metrics'     && <MetricsTab incident={incident} />}
          {activeTab === 'remediation' && <RemediationLogTab incident={incident} />}
        </div>

        {/* Footer — Human-Assisted Resolution */}
        {canResolve && (
          <div className="p-4 border-t border-border">
            <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">Human-Assisted Resolution</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Mark this incident as resolved after manual intervention. This records it as a
                human-assisted resolution in the audit log.
              </p>
              {resolveErr && (
                <p className="text-xs text-destructive">{resolveErr}</p>
              )}
              <button
                onClick={handleResolve}
                disabled={resolving}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-success/90 hover:bg-success text-white text-sm font-medium transition-colors disabled:opacity-60"
              >
                {resolving ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Resolving…</>
                ) : (
                  <><CheckCircle2 className="h-4 w-4" /> Mark as Resolved</>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
