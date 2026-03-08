import { useEffect } from 'react';
import { useStore } from '@/lib/store';
import { mockIncidents, mockKPI, getMockIncidentDetail } from '@/lib/mock-data';
import { KPICards } from '@/components/dashboard/KPICards';
import { ActivityChart } from '@/components/dashboard/ActivityChart';
import { SystemHealthPanel } from '@/components/dashboard/SystemHealthPanel';
import { IncidentTable } from '@/components/incidents/IncidentTable';
import { IncidentDrawer } from '@/components/incidents/IncidentDrawer';
import type { Incident } from '@/lib/types';

const Dashboard = () => {
  const { incidents, setIncidents, kpi, setKpi, selectedIncident, isDrawerOpen, openDrawer, closeDrawer } = useStore();

  useEffect(() => {
    if (incidents.length === 0) setIncidents(mockIncidents);
    if (!kpi) setKpi(mockKPI);
  }, []);

  const handleRowClick = (inc: Incident) => {
    openDrawer(getMockIncidentDetail(inc.incidentId));
  };

  return (
    <div className="space-y-6">
      {kpi && <KPICards kpi={kpi} />}
      <ActivityChart />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <IncidentTable incidents={incidents} onRowClick={handleRowClick} compact />
        <SystemHealthPanel />
      </div>
      {selectedIncident && (
        <IncidentDrawer incident={selectedIncident} open={isDrawerOpen} onClose={closeDrawer} />
      )}
    </div>
  );
};

export default Dashboard;
