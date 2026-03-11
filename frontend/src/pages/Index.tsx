import { useStore } from '@/lib/store';
import { api } from '@/lib/api';
import { useIncidents } from '@/hooks/use-incidents';
import { useKPI } from '@/hooks/use-kpi';
import { KPICards } from '@/components/dashboard/KPICards';
import { ActivityChart } from '@/components/dashboard/ActivityChart';
import { SystemHealthPanel } from '@/components/dashboard/SystemHealthPanel';
import { DemoTrigger } from '@/components/dashboard/DemoTrigger';
import { IncidentTable } from '@/components/incidents/IncidentTable';
import { IncidentDrawer } from '@/components/incidents/IncidentDrawer';
import type { Incident } from '@/lib/types';

const Dashboard = () => {
  const { selectedIncident, isDrawerOpen, openDrawer, closeDrawer } = useStore();

  // Real data via React Query — auto-refetches every 30 s + on WebSocket events
  const { data: incidentsData, isLoading: incidentsLoading } = useIncidents();
  const { data: kpi } = useKPI();

  const incidents = incidentsData?.incidents ?? [];

  // Fetch full incident detail from the HTTP API then open the side-drawer
  const handleRowClick = async (inc: Incident) => {
    try {
      const detail = await api.getIncident(inc.incidentId);
      openDrawer(detail);
    } catch (err) {
      console.error('[Dashboard] Failed to load incident detail:', err);
      // Fallback: open with partial data so the UX does not break
      openDrawer({
        ...inc,
        resourceId:    '',
        ewmaValue:     0,
        metricHistory: [],
        rootCause:     'Detail unavailable — check CloudWatch logs.',
        diagnosis:     { topErrors: [], logInsightsQuery: '' },
        timeline:      [],
      });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Dashboard</h1>
        <DemoTrigger />
      </div>
      {kpi && <KPICards kpi={kpi} />}
      <ActivityChart />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {incidentsLoading ? (
          <div className="flex items-center justify-center h-40 rounded-xl border border-border bg-card text-muted-foreground text-sm">
            Loading incidents…
          </div>
        ) : (
          <IncidentTable incidents={incidents.slice(0, 10)} onRowClick={handleRowClick} compact />
        )}
        <SystemHealthPanel />
      </div>
      {selectedIncident && (
        <IncidentDrawer incident={selectedIncident} open={isDrawerOpen} onClose={closeDrawer} />
      )}
    </div>
  );
};

export default Dashboard;
