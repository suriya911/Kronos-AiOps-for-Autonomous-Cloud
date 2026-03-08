import { useLocation } from 'react-router-dom';
import { format } from 'date-fns';
import { useStore } from '@/lib/store';

const pageTitles: Record<string, string> = {
  '/': 'Dashboard',
  '/incidents': 'Incidents',
  '/metrics': 'Metrics',
  '/remediations': 'Remediations',
  '/settings': 'Settings',
};

export function Topbar() {
  const { pathname } = useLocation();
  const wsStatus = useStore((s) => s.wsStatus);
  const title = pageTitles[pathname] || 'Dashboard';

  return (
    <header className="sticky top-0 z-40 h-14 border-b border-border bg-background/80 backdrop-blur-sm flex items-center justify-between px-6">
      <h1 className="text-lg font-semibold tracking-tight text-foreground">{title}</h1>
      <div className="flex items-center gap-4">
        <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs border ${
          wsStatus === 'CONNECTED'
            ? 'border-success/30 text-success'
            : 'border-muted text-muted-foreground'
        }`}>
          <span className={`h-1.5 w-1.5 rounded-full ${
            wsStatus === 'CONNECTED' ? 'bg-success pulse-live' : 'bg-muted-foreground'
          }`} />
          {wsStatus === 'CONNECTED' ? 'System Operational' : 'Connecting...'}
        </div>
        <span className="text-xs font-mono text-muted-foreground">
          {format(new Date(), 'MMM dd, HH:mm:ss')}
        </span>
      </div>
    </header>
  );
}
