import { X } from 'lucide-react';
import { useState } from 'react';
import type { IncidentDetail } from '@/lib/types';
import { StatusBadge } from './IncidentBadges';
import { TimelineTab } from './TimelineTab';
import { MetricsTab } from './MetricsTab';
import { RemediationLogTab } from './RemediationLogTab';

interface IncidentDrawerProps {
  incident: IncidentDetail;
  open: boolean;
  onClose: () => void;
}

export function IncidentDrawer({ incident, open, onClose }: IncidentDrawerProps) {
  const [activeTab, setActiveTab] = useState<'timeline' | 'metrics' | 'remediation'>('timeline');

  if (!open) return null;

  const tabs = [
    { id: 'timeline' as const, label: 'Timeline' },
    { id: 'metrics' as const, label: 'Metrics' },
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
          {activeTab === 'timeline' && <TimelineTab timeline={incident.timeline} />}
          {activeTab === 'metrics' && <MetricsTab incident={incident} />}
          {activeTab === 'remediation' && <RemediationLogTab incident={incident} />}
        </div>

        {/* Manual Override */}
        {incident.status === 'IN_PROGRESS' && (
          <div className="p-4 border-t border-border">
            <div className="bg-warning/10 border border-warning/30 rounded-lg p-4">
              <p className="text-sm text-warning font-medium mb-3">⚠ Awaiting Manual Approval</p>
              <div className="flex gap-2">
                <button className="flex-1 py-2 rounded-lg bg-success text-success-foreground text-sm font-medium hover:opacity-90">
                  ✓ Approve Remediation
                </button>
                <button className="flex-1 py-2 rounded-lg border border-destructive text-destructive text-sm font-medium hover:bg-destructive/10">
                  ✕ Reject & Escalate
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
