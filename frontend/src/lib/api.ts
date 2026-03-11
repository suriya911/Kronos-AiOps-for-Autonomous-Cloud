// ─── Kronos AIOps — API client + WebSocketManager ────────────────────────────
//
// Single module for ALL backend communication:
//   • apiFetch<T>()     — typed fetch wrapper with error handling
//   • api.*             — typed API functions (incidents, kpi, metrics, settings)
//   • WebSocketManager  — auto-reconnecting WS with exponential backoff
//
// Set VITE_USE_MOCK=true to fall back to local mock data (offline dev).
// ─────────────────────────────────────────────────────────────────────────────

import type {
  Incident,
  IncidentDetail,
  KPIData,
  MetricsResponse,
  Remediation,
  GuardrailConfig,
  ThresholdConfig,
  RemediationAction,
  RemediationStatus,
} from './types';
// ─── Environment ──────────────────────────────────────────────────────────────

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const USE_MOCK  = import.meta.env.VITE_USE_MOCK === 'true';

// ─── Backend → Frontend value maps ───────────────────────────────────────────
//
// DynamoDB stores raw Step-Functions / Lambda strings; the frontend expects
// the shorter UI labels defined in types.ts.

const METHOD_MAP: Record<string, Incident['method']> = {
  AUTO_REMEDIATED: 'AUTO',
  HUMAN_REQUIRED:  'ESCALATED',
};

const STATUS_MAP: Record<string, Incident['status']> = {
  REMEDIATION_FAILED: 'ERROR',
};

// ─── Fetch wrapper ────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API ${res.status} ${res.statusText}: ${text}`);
  }

  return res.json() as Promise<T>;
}

// ─── Transform helpers ────────────────────────────────────────────────────────

function transformMethod(raw: unknown): Incident['method'] {
  if (raw == null) return 'MANUAL';
  return METHOD_MAP[String(raw)] ?? (raw as Incident['method']);
}

function transformStatus(raw: unknown): Incident['status'] {
  if (raw == null) return 'OPEN';
  return STATUS_MAP[String(raw)] ?? (raw as Incident['status']);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function transformIncident(raw: Record<string, any>): Incident {
  return {
    incidentId:    String(raw.incidentId  ?? ''),
    type:          (raw.type as Incident['type']) ?? 'UNKNOWN',
    status:        transformStatus(raw.status),
    severity:      (raw.severity as Incident['severity']) ?? 'INFO',
    detectedAt:    String(raw.detectedAt  ?? ''),
    resolvedAt:    raw.resolvedAt     ? String(raw.resolvedAt)    : undefined,
    mttr:          raw.mttr     != null ? Number(raw.mttr)        : undefined,
    method:        transformMethod(raw.method),
    alarmName:     String(raw.alarmName   ?? ''),
    metricValue:   Number(raw.metricValue ?? 0),
    zScore:        Number(raw.zScore      ?? 0),
    executionArn:  raw.executionArn   ? String(raw.executionArn)  : undefined,
    remediationId: raw.remediationId  ? String(raw.remediationId) : undefined,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function transformIncidentDetail(raw: Record<string, any>): IncidentDetail {
  const base     = transformIncident(raw);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const diag     = (raw.diagnosis ?? {}) as Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rem      = raw.remediation as Record<string, any> | undefined;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const timeline = (raw.timeline as Array<Record<string, any>>) ?? [];

  return {
    ...base,
    triageAt:              raw.triageAt              ? String(raw.triageAt)              : undefined,
    diagnosedAt:           raw.diagnosedAt           ? String(raw.diagnosedAt)           : undefined,
    guardrailCheckedAt:    raw.guardrailCheckedAt    ? String(raw.guardrailCheckedAt)    : undefined,
    remediationStartedAt:  raw.remediationStartedAt  ? String(raw.remediationStartedAt)  : undefined,
    resourceId:    String(raw.resourceId  ?? ''),
    ewmaValue:     Number(raw.ewmaValue   ?? 0),
    metricHistory: (raw.metricHistory as number[]) ?? [],
    rootCause:     String(raw.rootCause   ?? ''),
    diagnosis: {
      topErrors:         (diag.topErrors as string[]) ?? [],
      logInsightsQuery:  String(diag.logInsightsQuery ?? ''),
    },
    remediation: rem
      ? {
          remediationId: String(rem.remediationId ?? ''),
          actionType:    (rem.actionType as RemediationAction),
          target:        String(rem.target        ?? ''),
          ssmCommandId:  String(rem.ssmCommandId  ?? ''),
          status:        (rem.status as RemediationStatus),
          durationMs:    Number(rem.durationMs    ?? 0),
          log:           (rem.log as Array<{ ts: string; msg: string }>) ?? [],
        }
      : undefined,
    timeline: timeline.map((t) => ({
      state:      String(t.state ?? ''),
      ts:         String(t.ts    ?? ''),
      durationMs: t.durationMs != null ? Number(t.durationMs) : undefined,
    })),
  };
}

// ─── Public API object ────────────────────────────────────────────────────────

export const api = {

  async getIncidents(statusFilter?: string): Promise<{ incidents: Incident[]; count: number }> {
    if (USE_MOCK) {
      const { mockIncidents } = await import('./mock-data');
      return { incidents: mockIncidents, count: mockIncidents.length };
    }
    const qs  = statusFilter && statusFilter !== 'ALL' ? `?status=${statusFilter}` : '';
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = await apiFetch<{ incidents: any[]; count: number }>(`/incidents${qs}`);
    return {
      incidents: raw.incidents.map(transformIncident),
      count:     raw.count,
    };
  },

  async getIncident(id: string): Promise<IncidentDetail> {
    if (USE_MOCK) {
      const { getMockIncidentDetail } = await import('./mock-data');
      return getMockIncidentDetail(id);
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = await apiFetch<Record<string, any>>(`/incidents/${id}`);
    return transformIncidentDetail(raw);
  },

  async getKPI(): Promise<KPIData> {
    if (USE_MOCK) {
      const { mockKPI } = await import('./mock-data');
      return mockKPI;
    }
    return apiFetch<KPIData>('/kpi');
  },

  async getMetrics(range: string): Promise<MetricsResponse> {
    if (USE_MOCK) {
      const { getMockMetrics } = await import('./mock-data');
      return getMockMetrics(range);
    }
    return apiFetch<MetricsResponse>(`/metrics?range=${range}`);
  },

  async getRemediations(): Promise<{ remediations: Remediation[]; count: number }> {
    if (USE_MOCK) {
      const { mockRemediations } = await import('./mock-data');
      return { remediations: mockRemediations, count: mockRemediations.length };
    }
    return apiFetch<{ remediations: Remediation[]; count: number }>('/remediations');
  },

  async getSettings(): Promise<{ guardrails: GuardrailConfig[]; thresholds: ThresholdConfig }> {
    if (USE_MOCK) {
      const { mockGuardrails } = await import('./mock-data');
      return {
        guardrails:  mockGuardrails,
        thresholds:  { zScoreThreshold: 3.0, ewmaAlpha: 0.3, minDataPoints: 60 },
      };
    }
    return apiFetch<{ guardrails: GuardrailConfig[]; thresholds: ThresholdConfig }>('/settings');
  },

  async updateGuardrails(guardrails: GuardrailConfig[]): Promise<void> {
    if (USE_MOCK) return;
    await apiFetch('/settings/guardrails', {
      method: 'PATCH',
      body:   JSON.stringify({ guardrails }),
    });
  },

  async updateThresholds(thresholds: ThresholdConfig): Promise<void> {
    if (USE_MOCK) return;
    await apiFetch('/settings/thresholds', {
      method: 'PATCH',
      body:   JSON.stringify(thresholds),
    });
  },

  async resolveIncident(id: string, notes?: string): Promise<{ resolved: boolean; resolvedAt: string }> {
    if (USE_MOCK) return { resolved: true, resolvedAt: new Date().toISOString() };
    return apiFetch(`/incidents/${id}`, {
      method: 'PATCH',
      body:   JSON.stringify({ notes: notes ?? '' }),
    });
  },

  async triggerDemo(type: string, severity: string): Promise<{ triggered: boolean; message: string; alarmName: string }> {
    if (USE_MOCK) {
      return {
        triggered: true,
        message:   `Mock demo triggered: ${severity} ${type} incident. It will appear on the dashboard shortly.`,
        alarmName: `aiops-demo-${type.toLowerCase()}`,
      };
    }
    return apiFetch('/demo/trigger', {
      method: 'POST',
      body:   JSON.stringify({ type, severity }),
    });
  },
};

// ─── WebSocketManager ─────────────────────────────────────────────────────────
//
// Manages one WebSocket connection with:
//   • Automatic reconnection with exponential backoff (1s → 2s → 4s → … → 30s)
//   • Query cache invalidation on every incident event
//   • Status propagation to Zustand store (for the Topbar indicator)

export interface BackendWsEvent {
  event: string;
  incidentId?: string;
  [key: string]: unknown;
}

/** Minimal store interface required by WebSocketManager */
type WsStore = {
  setWsStatus: (status: 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'ERROR') => void;
};

/** Minimal QueryClient interface (compatible with @tanstack/react-query QueryClient) */
type QueryClientLike = {
  invalidateQueries: (filters: { queryKey: unknown[] }) => void | Promise<void>;
};

export class WebSocketManager {
  private ws:              WebSocket | null                  = null;
  private reconnectTimer:  ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay:  number = 1_000;
  private readonly maxDelay: number = 30_000;
  private closed:          boolean = false;

  constructor(
    private readonly wsUrl:        string,
    private readonly store:        WsStore,
    private readonly queryClient:  QueryClientLike,
  ) {}

  connect(): void {
    if (this.closed) return;

    this.store.setWsStatus('CONNECTING');

    try {
      this.ws = new WebSocket(this.wsUrl);
    } catch (err) {
      console.error('[WS] Failed to create WebSocket:', err);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log('[WS] Connected');
      this.store.setWsStatus('CONNECTED');
      this.reconnectDelay = 1_000; // reset exponential backoff
    };

    this.ws.onmessage = (evt: MessageEvent) => {
      try {
        const data: BackendWsEvent = JSON.parse(evt.data as string);
        this.handleMessage(data);
      } catch (err) {
        console.warn('[WS] Failed to parse message:', err);
      }
    };

    this.ws.onclose = (evt: CloseEvent) => {
      console.log(`[WS] Closed (code=${evt.code})`);
      this.store.setWsStatus('DISCONNECTED');
      if (!this.closed) this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      console.error('[WS] Error');
      this.store.setWsStatus('ERROR');
    };
  }

  private handleMessage(data: BackendWsEvent): void {
    const { event } = data;

    switch (event) {
      case 'INCIDENT_CREATED':
      case 'INCIDENT_UPDATED':
      case 'INCIDENT_RESOLVED':
      case 'INCIDENT_ESCALATED':
        // Invalidate React Query cache → pages auto-refetch with fresh data
        void this.queryClient.invalidateQueries({ queryKey: ['incidents'] });
        void this.queryClient.invalidateQueries({ queryKey: ['kpi'] });
        break;

      default:
        console.log('[WS] Unknown event type:', event);
    }
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    console.log(`[WS] Reconnecting in ${this.reconnectDelay}ms…`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxDelay);
      this.connect();
    }, this.reconnectDelay);
  }

  disconnect(): void {
    this.closed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
