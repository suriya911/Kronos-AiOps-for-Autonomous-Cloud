import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

/**
 * Fetch the incident list, optionally filtered by status.
 * Re-fetches every 30 s and whenever the WebSocket invalidates the cache.
 */
export function useIncidents(statusFilter?: string) {
  return useQuery({
    queryKey:             ['incidents', statusFilter ?? 'ALL'],
    queryFn:              () => api.getIncidents(statusFilter),
    staleTime:            10_000,
    refetchInterval:      10_000,
    refetchOnWindowFocus: true,
  });
}

/**
 * Fetch the full detail for a single incident (drawer).
 * Only runs when `id` is non-empty.
 */
export function useIncident(id: string) {
  return useQuery({
    queryKey: ['incident', id],
    queryFn:  () => api.getIncident(id),
    enabled:  !!id,
    staleTime: 60_000,
  });
}
