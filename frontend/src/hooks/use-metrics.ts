import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

/**
 * Fetch CloudWatch metric data for the given time range.
 * Returns CPU / memory / disk / latency with dataPoints arrays.
 * In dev environments without real EC2 instances the Lambda returns
 * `dataAvailable: false` and an empty dataPoints array — the Metrics
 * page guards against this.
 */
export function useMetrics(range: string) {
  return useQuery({
    queryKey:  ['metrics', range],
    queryFn:   () => api.getMetrics(range),
    staleTime: 60_000,
  });
}
