import { create } from 'zustand';
import type { Incident, IncidentDetail, KPIData, WsStatus } from './types';

interface AIOpsStore {
  incidents: Incident[];
  setIncidents: (incidents: Incident[]) => void;
  selectedIncident: IncidentDetail | null;
  isDrawerOpen: boolean;
  setSelectedIncident: (incident: IncidentDetail | null) => void;
  openDrawer: (incident: IncidentDetail) => void;
  closeDrawer: () => void;

  kpi: KPIData | null;
  setKpi: (kpi: KPIData) => void;

  wsStatus: WsStatus;
  setWsStatus: (status: WsStatus) => void;

  handleIncidentCreated: (incident: Incident) => void;
  handleIncidentUpdated: (incident: Partial<Incident> & { incidentId: string }) => void;

  statusFilter: string;
  typeFilter: string;
  searchQuery: string;
  setStatusFilter: (s: string) => void;
  setTypeFilter: (s: string) => void;
  setSearchQuery: (q: string) => void;

  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useStore = create<AIOpsStore>((set) => ({
  incidents: [],
  setIncidents: (incidents) => set({ incidents }),
  selectedIncident: null,
  isDrawerOpen: false,
  setSelectedIncident: (incident) => set({ selectedIncident: incident }),
  openDrawer: (incident) => set({ selectedIncident: incident, isDrawerOpen: true }),
  closeDrawer: () => set({ isDrawerOpen: false, selectedIncident: null }),

  kpi: null,
  setKpi: (kpi) => set({ kpi }),

  wsStatus: 'DISCONNECTED',
  setWsStatus: (wsStatus) => set({ wsStatus }),

  handleIncidentCreated: (incident) =>
    set((state) => ({ incidents: [incident, ...state.incidents] })),
  handleIncidentUpdated: (update) =>
    set((state) => ({
      incidents: state.incidents.map((i) =>
        i.incidentId === update.incidentId ? { ...i, ...update } : i
      ),
    })),

  statusFilter: 'ALL',
  typeFilter: 'ALL',
  searchQuery: '',
  setStatusFilter: (statusFilter) => set({ statusFilter }),
  setTypeFilter: (typeFilter) => set({ typeFilter }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),

  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
