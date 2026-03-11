import { useState } from 'react';
import { Zap, ChevronDown, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

const INCIDENT_TYPES = [
  { value: 'CPU',     label: 'CPU Spike',        desc: 'Runaway process / CPU saturation' },
  { value: 'MEMORY',  label: 'Memory Leak',       desc: 'Heap exhaustion / OOM pressure' },
  { value: 'DISK',    label: 'Disk Full',          desc: 'Log partition filling up' },
  { value: 'LATENCY', label: 'API Latency',        desc: 'Response time degradation' },
];

const SEVERITIES = [
  { value: 'CRITICAL', label: 'Critical', color: 'text-destructive' },
  { value: 'WARNING',  label: 'Warning',  color: 'text-yellow-400' },
];

type TriggerState = 'idle' | 'loading' | 'success' | 'error';

export function DemoTrigger() {
  const queryClient             = useQueryClient();
  const [open, setOpen]         = useState(false);
  const [type, setType]         = useState('CPU');
  const [severity, setSeverity] = useState('CRITICAL');
  const [state, setState]       = useState<TriggerState>('idle');
  const [message, setMessage]   = useState('');

  const selectedType     = INCIDENT_TYPES.find(t => t.value === type)!;
  const selectedSeverity = SEVERITIES.find(s => s.value === severity)!;

  const handleTrigger = async () => {
    setState('loading');
    setMessage('');
    try {
      const result = await api.triggerDemo(type, severity);
      setState('success');
      setMessage(result.message);
      // Immediately refresh incident list and KPIs, then again after 8s and 20s
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['kpi'] });
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['incidents'] });
        queryClient.invalidateQueries({ queryKey: ['kpi'] });
      }, 8_000);
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['incidents'] });
        queryClient.invalidateQueries({ queryKey: ['kpi'] });
      }, 20_000);
    } catch (err) {
      setState('error');
      setMessage(err instanceof Error ? err.message : 'Failed to trigger demo incident.');
    }
  };

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      // Reset state when dialog closes
      setTimeout(() => { setState('idle'); setMessage(''); }, 200);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2 border-primary/40 text-primary hover:bg-primary/10">
          <Zap className="h-4 w-4" />
          Trigger Live Demo
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            Trigger Live Demo Incident
          </DialogTitle>
          <DialogDescription>
            Fire a real CloudWatch alarm event to demonstrate the full AIOps pipeline —
            detection → diagnosis → auto-remediation → resolution.
          </DialogDescription>
        </DialogHeader>

        {state === 'idle' || state === 'loading' ? (
          <div className="space-y-4 py-2">
            {/* Incident Type */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">Incident Type</label>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className="w-full justify-between">
                    <span className="flex flex-col items-start">
                      <span className="font-medium">{selectedType.label}</span>
                      <span className="text-xs text-muted-foreground">{selectedType.desc}</span>
                    </span>
                    <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-64">
                  {INCIDENT_TYPES.map(t => (
                    <DropdownMenuItem
                      key={t.value}
                      onClick={() => setType(t.value)}
                      className="flex flex-col items-start gap-0.5 py-2"
                    >
                      <span className="font-medium">{t.label}</span>
                      <span className="text-xs text-muted-foreground">{t.desc}</span>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Severity */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">Severity</label>
              <div className="flex gap-2">
                {SEVERITIES.map(s => (
                  <button
                    key={s.value}
                    onClick={() => setSeverity(s.value)}
                    className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                      severity === s.value
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Preview */}
            <div className="rounded-md bg-muted/40 border border-border p-3 text-sm space-y-1">
              <div className="flex items-center gap-2 text-muted-foreground">
                <span>This will trigger:</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={selectedSeverity.color}>
                  {selectedSeverity.label}
                </Badge>
                <span className="font-medium">{selectedType.label}</span>
                <span className="text-muted-foreground">incident</span>
              </div>
              <p className="text-xs text-muted-foreground pt-1">
                Incident will appear on the dashboard within ~10 seconds and flow
                through the full detection → remediation pipeline.
              </p>
            </div>
          </div>
        ) : state === 'success' ? (
          <div className="py-4 space-y-3">
            <div className="flex items-center gap-3 text-success">
              <CheckCircle2 className="h-6 w-6 shrink-0" />
              <span className="font-medium">Demo incident triggered!</span>
            </div>
            <p className="text-sm text-muted-foreground">{message}</p>
          </div>
        ) : (
          <div className="py-4 space-y-3">
            <div className="flex items-center gap-3 text-destructive">
              <XCircle className="h-6 w-6 shrink-0" />
              <span className="font-medium">Trigger failed</span>
            </div>
            <p className="text-sm text-muted-foreground">{message}</p>
          </div>
        )}

        <DialogFooter>
          {state === 'idle' || state === 'loading' ? (
            <>
              <Button variant="ghost" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleTrigger}
                disabled={state === 'loading'}
                className="gap-2"
              >
                {state === 'loading' ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Triggering…</>
                ) : (
                  <><Zap className="h-4 w-4" /> Fire Incident</>
                )}
              </Button>
            </>
          ) : (
            <Button onClick={() => handleOpenChange(false)}>Close</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
