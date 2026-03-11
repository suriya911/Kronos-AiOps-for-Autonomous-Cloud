import { LayoutDashboard, AlertTriangle, Activity, Wrench, Settings, ChevronLeft, ChevronRight } from 'lucide-react';
import { NavLink } from '@/components/NavLink';
import { useStore } from '@/lib/store';

const navItems = [
  { title: 'Dashboard', url: '/', icon: LayoutDashboard },
  { title: 'Incidents', url: '/incidents', icon: AlertTriangle },
  { title: 'Metrics', url: '/metrics', icon: Activity },
  { title: 'Remediations', url: '/remediations', icon: Wrench },
  { title: 'Settings', url: '/settings', icon: Settings },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, wsStatus } = useStore();

  return (
    <aside
      className={`fixed left-0 top-0 h-screen bg-card border-r border-border flex flex-col z-50 transition-all duration-300 ${
        sidebarCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-border">
        <img src="/kronos-logo.svg" alt="Kronos" className="h-7 w-7 shrink-0" />
        {!sidebarCollapsed && (
          <>
            <span className="ml-2 text-primary font-bold text-xl tracking-tight">KRONOS</span>
            <span className="ml-2 text-xs text-muted-foreground">AIOps Platform</span>
          </>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {navItems.map((item) => (
          <NavLink
            key={item.url}
            to={item.url}
            end={item.url === '/'}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            activeClassName="bg-accent text-primary font-medium"
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {!sidebarCollapsed && <span>{item.title}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Bottom */}
      <div className="px-4 py-3 border-t border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              wsStatus === 'CONNECTED' ? 'bg-success pulse-live' : 'bg-muted-foreground'
            }`}
          />
          {!sidebarCollapsed && (
            <span className="text-xs text-muted-foreground">
              {wsStatus === 'CONNECTED' ? 'LIVE' : wsStatus}
            </span>
          )}
        </div>
        <button
          onClick={toggleSidebar}
          className="p-1 rounded hover:bg-accent text-muted-foreground"
        >
          {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
    </aside>
  );
}
