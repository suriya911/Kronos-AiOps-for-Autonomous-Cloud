export type IncidentStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'ESCALATED' | 'ERROR';
export type IncidentType = 'CPU' | 'MEMORY' | 'DISK' | 'LATENCY' | 'UNKNOWN';
export type IncidentSeverity = 'CRITICAL' | 'WARNING' | 'INFO';
export type IncidentMethod = 'AUTO' | 'MANUAL' | 'ESCALATED';
export type RemediationAction = 'RESTART_SERVICE' | 'CLEAR_DISK' | 'SCALE_OUT' | 'CUSTOM';
export type RemediationStatus = 'SUCCESS' | 'FAILED' | 'SKIPPED';
export type WsStatus = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'ERROR';

export interface Incident {
  incidentId: string;
  type: IncidentType;
  status: IncidentStatus;
  severity: IncidentSeverity;
  detectedAt: string;
  resolvedAt?: string;
  mttr?: number;
  method: IncidentMethod;
  alarmName: string;
  metricValue: number;
  zScore: number;
  executionArn?: string;
  remediationId?: string;
}

export interface IncidentDetail extends Incident {
  triageAt?: string;
  diagnosedAt?: string;
  guardrailCheckedAt?: string;
  remediationStartedAt?: string;
  resourceId: string;
  ewmaValue: number;
  metricHistory: number[];
  rootCause: string;
  diagnosis: {
    topErrors: string[];
    logInsightsQuery: string;
  };
  remediation?: {
    remediationId: string;
    actionType: RemediationAction;
    target: string;
    ssmCommandId: string;
    status: RemediationStatus;
    durationMs: number;
    log: Array<{ ts: string; msg: string }>;
  };
  timeline: Array<{
    state: string;
    ts: string;
    durationMs?: number;
  }>;
}

export interface KPIData {
  mttr: { value: number; unit: string; changeVsBaseline: number; trend: string };
  autoResolutionRate: { value: number; unit: string; period: string };
  openIncidents: { total: number; critical: number; warning: number };
  detectionLatency: { value: number; unit: string };
}

export interface MetricData {
  current: number;
  min: number;
  max: number;
  avg: number;
  unit: string;
  threshold: number | null;
  dataPoints: Array<{ ts: string; value: number }>;
}

export interface MetricsResponse {
  range: string;
  cpu: MetricData;
  memory: MetricData;
  disk: MetricData;
  latency: MetricData;
}

export interface Remediation {
  remediationId: string;
  incidentId: string;
  actionType: RemediationAction;
  target: string;
  executedAt: string;
  durationMs: number;
  status: RemediationStatus;
  ssmCommandId: string;
}

export interface GuardrailConfig {
  type: IncidentType;
  autoRemediate: boolean;
}

export interface ThresholdConfig {
  zScoreThreshold: number;
  ewmaAlpha: number;
  minDataPoints: number;
}
