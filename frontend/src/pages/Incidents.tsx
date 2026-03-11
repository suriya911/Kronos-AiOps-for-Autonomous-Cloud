import { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import { useStore } from '@/lib/store';
import { api } from '@/lib/api';
import { useIncidents } from '@/hooks/use-incidents';
import { useQueryClient } from '@tanstack/react-query';
import { IncidentTable } from '@/components/incidents/IncidentTable';
import { IncidentDrawer } from '@/components/incidents/IncidentDrawer';
import type { Incident } from '@/lib/types';

const ITEMS_PER_PAGE = 25;

const IncidentsPage = () => {
  const { statusFilter, typeFilter, searchQuery, setStatusFilter, setTypeFilter, setSearchQuery, selectedIncident, isDrawerOpen, openDrawer, closeDrawer } = useStore();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);

  // Pass statusFilter to the API for server-side filtering; type + search are client-side
  const { data: incidentsData, isLoading } = useIncidents(statusFilter !== 'ALL' ? statusFilter : undefined);
  const incidents = incidentsData?.incidents ?? [];

  const filtered = useMemo(() => {
    return incidents.filter((inc) => {
      if (typeFilter !== 'ALL' && inc.type !== typeFilter) return false;
      if (searchQuery && !inc.incidentId.includes(searchQuery) && !inc.type.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      return true;
    });
  }, [incidents, typeFilter, searchQuery]);

  const totalPages = Math.ceil(filtered.length / ITEMS_PER_PAGE);
  const paginated = filtered.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  const handleRowClick = async (inc: Incident) => {
    try {
      const detail = await api.getIncident(inc.incidentId);
      openDrawer(detail);
    } catch (err) {
      console.error('[Incidents] Failed to load incident detail:', err);
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
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by incident ID or type..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setPage(1); }}
            className="w-full h-9 pl-9 pr-3 rounded-lg bg-accent border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="h-9 px-3 rounded-lg bg-accent border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="ALL">All Status</option>
          <option value="OPEN">Open</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="RESOLVED">Resolved</option>
          <option value="ESCALATED">Escalated</option>
          <option value="ERROR">Error</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
          className="h-9 px-3 rounded-lg bg-accent border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="ALL">All Types</option>
          <option value="CPU">CPU</option>
          <option value="MEMORY">Memory</option>
          <option value="DISK">Disk</option>
          <option value="LATENCY">Latency</option>
          <option value="UNKNOWN">Unknown</option>
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-40 rounded-xl border border-border bg-card text-muted-foreground text-sm">
          Loading incidents…
        </div>
      ) : (
        <IncidentTable incidents={paginated} onRowClick={handleRowClick} />
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-end gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm rounded-lg border border-border text-muted-foreground hover:bg-accent disabled:opacity-40"
          >
            Prev
          </button>
          {Array.from({ length: totalPages }, (_, i) => (
            <button
              key={i}
              onClick={() => setPage(i + 1)}
              className={`px-3 py-1.5 text-sm rounded-lg border ${
                page === i + 1 ? 'border-primary bg-primary/20 text-primary' : 'border-border text-muted-foreground hover:bg-accent'
              }`}
            >
              {i + 1}
            </button>
          ))}
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-sm rounded-lg border border-border text-muted-foreground hover:bg-accent disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      {selectedIncident && (
        <IncidentDrawer
          incident={selectedIncident}
          open={isDrawerOpen}
          onClose={closeDrawer}
          onResolved={() => queryClient.invalidateQueries({ queryKey: ['incidents'] })}
        />
      )}
    </div>
  );
};

export default IncidentsPage;
