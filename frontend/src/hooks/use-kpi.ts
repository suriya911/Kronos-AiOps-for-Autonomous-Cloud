import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

/**
 * Fetch KPI summary (MTTR, autoResolutionRate, openIncidents, detectionLatency).
 * The WebSocketManager invalidates this key on every incident event so the
 * dashboard cards refresh automatically within seconds.
 */
export function useKPI() {
  return useQuery({
    queryKey:  ['kpi'],
    queryFn:   api.getKPI,
    staleTime: 60_000,
  });
}
