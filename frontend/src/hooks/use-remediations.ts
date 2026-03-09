import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

/**
 * Fetch the remediation log from DynamoDB.
 * Refetches every 60 s (remediations don't change as often as incidents).
 */
export function useRemediations() {
  return useQuery({
    queryKey:        ['remediations'],
    queryFn:         api.getRemediations,
    staleTime:       30_000,
    refetchInterval: 60_000,
  });
}
