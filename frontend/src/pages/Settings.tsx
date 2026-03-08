import { useState } from 'react';
import { mockGuardrails } from '@/lib/mock-data';
import type { GuardrailConfig } from '@/lib/types';
import { toast } from 'sonner';

const SettingsPage = () => {
  const [activeTab, setActiveTab] = useState<'guardrails' | 'thresholds' | 'notifications'>('guardrails');
  const [guardrails, setGuardrails] = useState<GuardrailConfig[]>(mockGuardrails);
  const [zScore, setZScore] = useState(3.0);
  const [ewmaAlpha, setEwmaAlpha] = useState(0.3);
  const [minDataPoints, setMinDataPoints] = useState(60);
  const [email, setEmail] = useState('ops-team@company.com');
  const [slack, setSlack] = useState('');

  const tabs = [
    { id: 'guardrails' as const, label: 'Guardrails' },
    { id: 'thresholds' as const, label: 'Thresholds' },
    { id: 'notifications' as const, label: 'Notifications' },
  ];

  const toggleGuardrail = (type: string) => {
    setGuardrails((g) => g.map((r) => r.type === type ? { ...r, autoRemediate: !r.autoRemediate } : r));
  };

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-primary border-b-2 border-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'guardrails' && (
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg">
          <p className="text-sm text-muted-foreground mb-4">Control which incident types are auto-remediated</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-xs">
                <th className="text-left px-4 py-3 font-medium">Incident Type</th>
                <th className="text-left px-4 py-3 font-medium">Auto-Remediate</th>
                <th className="text-right px-4 py-3 font-medium">Toggle</th>
              </tr>
            </thead>
            <tbody>
              {guardrails.map((g) => (
                <tr key={g.type} className="border-b border-border/50">
                  <td className="px-4 py-3 text-foreground">{g.type}</td>
                  <td className="px-4 py-3 text-muted-foreground">{g.autoRemediate ? '✓' : '✗'}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => toggleGuardrail(g.type)}
                      className={`relative w-10 h-5 rounded-full transition-colors ${
                        g.autoRemediate ? 'bg-primary' : 'bg-muted'
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 h-4 w-4 rounded-full bg-foreground transition-transform ${
                          g.autoRemediate ? 'translate-x-5' : 'translate-x-0.5'
                        }`}
                      />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4 flex justify-end">
            <button
              onClick={() => toast.success('Guardrails saved')}
              className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90"
            >
              Save Changes
            </button>
          </div>
        </div>
      )}

      {activeTab === 'thresholds' && (
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg space-y-6">
          <div>
            <label className="text-sm text-foreground font-medium">Z-Score Threshold: {zScore.toFixed(1)}</label>
            <input type="range" min="1" max="5" step="0.1" value={zScore} onChange={(e) => setZScore(+e.target.value)}
              className="w-full mt-2 accent-primary" />
            <div className="flex justify-between text-xs text-muted-foreground"><span>1.0</span><span>5.0</span></div>
          </div>
          <div>
            <label className="text-sm text-foreground font-medium">EWMA Alpha: {ewmaAlpha.toFixed(2)}</label>
            <input type="range" min="0.1" max="0.9" step="0.05" value={ewmaAlpha} onChange={(e) => setEwmaAlpha(+e.target.value)}
              className="w-full mt-2 accent-primary" />
            <div className="flex justify-between text-xs text-muted-foreground"><span>0.1</span><span>0.9</span></div>
          </div>
          <div>
            <label className="text-sm text-foreground font-medium">Min Data Points: {minDataPoints}</label>
            <input type="range" min="10" max="120" step="10" value={minDataPoints} onChange={(e) => setMinDataPoints(+e.target.value)}
              className="w-full mt-2 accent-primary" />
            <div className="flex justify-between text-xs text-muted-foreground"><span>10</span><span>120</span></div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={() => toast.success('Thresholds saved')}
              className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90"
            >
              Save Changes
            </button>
          </div>
        </div>
      )}

      {activeTab === 'notifications' && (
        <div className="rounded-xl border border-border bg-card p-5 shadow-lg space-y-4">
          <div>
            <label className="text-sm text-foreground font-medium block mb-1.5">SNS Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full h-9 px-3 rounded-lg bg-accent border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div>
            <label className="text-sm text-foreground font-medium block mb-1.5">Slack Webhook (optional)</label>
            <input type="url" value={slack} onChange={(e) => setSlack(e.target.value)} placeholder="https://hooks.slack.com/..."
              className="w-full h-9 px-3 rounded-lg bg-accent border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => toast.success('Test notification sent')}
              className="px-4 py-2 text-sm rounded-lg border border-border text-foreground font-medium hover:bg-accent"
            >
              Send Test Alert
            </button>
            <button
              onClick={() => toast.success('Notification settings saved')}
              className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SettingsPage;
