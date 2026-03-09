import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { GuardrailConfig, ThresholdConfig } from '@/lib/types';

/**
 * Fetch guardrails + thresholds from SSM Parameter Store.
 * Cached for 5 minutes — settings change infrequently.
 */
export function useSettings() {
  return useQuery({
    queryKey:  ['settings'],
    queryFn:   api.getSettings,
    staleTime: 5 * 60_000,
  });
}

/** Save updated guardrails array to SSM and invalidate the settings cache. */
export function useUpdateGuardrails() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (guardrails: GuardrailConfig[]) => api.updateGuardrails(guardrails),
    onSuccess:  () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  });
}

/** Save updated threshold config to SSM and invalidate the settings cache. */
export function useUpdateThresholds() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (thresholds: ThresholdConfig) => api.updateThresholds(thresholds),
    onSuccess:  () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  });
}
