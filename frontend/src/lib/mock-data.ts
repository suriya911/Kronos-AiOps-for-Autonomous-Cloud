import type { Incident, IncidentDetail, KPIData, MetricsResponse, Remediation, GuardrailConfig } from './types';
import { subHours, subMinutes, subSeconds, formatISO } from 'date-fns';

const now = new Date();
const ts = (hoursAgo: number, minAgo = 0, secAgo = 0) =>
  formatISO(subSeconds(subMinutes(subHours(now, hoursAgo), minAgo), secAgo));

const incidentTypes = ['CPU', 'MEMORY', 'DISK', 'LATENCY', 'UNKNOWN'] as const;
const statuses = ['RESOLVED', 'RESOLVED', 'RESOLVED', 'IN_PROGRESS', 'ESCALATED', 'OPEN', 'RESOLVED', 'RESOLVED', 'ERROR', 'RESOLVED'] as const;
const severities = ['CRITICAL', 'WARNING', 'INFO'] as const;
const methods = ['AUTO', 'AUTO', 'AUTO', 'MANUAL', 'ESCALATED'] as const;

function randomId() {
  return 'inc_' + Math.random().toString(36).substring(2, 14);
}

export const mockIncidents: Incident[] = Array.from({ length: 20 }, (_, i) => {
  const status = statuses[i % statuses.length];
  const type = incidentTypes[i % incidentTypes.length];
  const detectedAt = ts(Math.random() * 48, Math.floor(Math.random() * 60));
  const mttr = status === 'RESOLVED' ? Math.floor(10 + Math.random() * 120) : undefined;
  const resolvedAt = mttr ? formatISO(new Date(new Date(detectedAt).getTime() + mttr * 1000)) : undefined;

  return {
    incidentId: randomId(),
    type,
    status: status as Incident['status'],
    severity: severities[i % severities.length],
    detectedAt,
    resolvedAt,
    mttr,
    method: methods[i % methods.length],
    alarmName: `High${type.charAt(0) + type.slice(1).toLowerCase()}Utilization`,
    metricValue: 50 + Math.random() * 45,
    zScore: 2 + Math.random() * 4,
    remediationId: status === 'RESOLVED' ? 'rem_' + Math.random().toString(36).substring(2, 8) : undefined,
  };
}).sort((a, b) => new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime());

export function getMockIncidentDetail(id: string): IncidentDetail {
  const inc = mockIncidents.find(i => i.incidentId === id) || mockIncidents[0];
  const detected = new Date(inc.detectedAt);
  const mkTs = (ms: number) => formatISO(new Date(detected.getTime() + ms));

  return {
    ...inc,
    triageAt: mkTs(1700),
    diagnosedAt: mkTs(3100),
    guardrailCheckedAt: mkTs(3300),
    remediationStartedAt: mkTs(3500),
    resourceId: 'i-0abc' + Math.random().toString(36).substring(2, 10),
    ewmaValue: 55 + Math.random() * 15,
    metricHistory: Array.from({ length: 60 }, () => 30 + Math.random() * 65),
    rootCause: `${inc.type} spike triggered by runaway process PID ${Math.floor(1000 + Math.random() * 9000)}`,
    diagnosis: {
      topErrors: ['OutOfMemoryError in app.log', 'Thread pool exhausted', 'Connection timeout at db:5432'],
      logInsightsQuery: 'fields @timestamp, @message | filter @message like /ERROR/',
    },
    remediation: inc.remediationId ? {
      remediationId: inc.remediationId,
      actionType: 'RESTART_SERVICE',
      target: 'app-service',
      ssmCommandId: 'cmd-' + Math.random().toString(36).substring(2, 10),
      status: 'SUCCESS',
      durationMs: 2000 + Math.floor(Math.random() * 5000),
      log: [
        { ts: mkTs(3500), msg: 'Checking service state...' },
        { ts: mkTs(3800), msg: 'Service found: running' },
        { ts: mkTs(4000), msg: 'Action: restart_service' },
        { ts: mkTs(4200), msg: 'SSM Run Command sent: cmd-0abc123' },
        { ts: mkTs(6000), msg: 'Command status: SUCCESS' },
        { ts: mkTs(6200), msg: 'Incident closed. Resolution written to DynamoDB.' },
      ],
    } : undefined,
    timeline: [
      { state: 'ALARM_TRIGGERED', ts: inc.detectedAt },
      { state: 'TRIAGE_COMPLETE', ts: mkTs(1700), durationMs: 1700 },
      { state: 'DIAGNOSIS_DONE', ts: mkTs(3100), durationMs: 1400 },
      { state: 'GUARDRAIL_CHECKED', ts: mkTs(3300), durationMs: 200 },
      { state: 'REMEDIATION_DONE', ts: mkTs((inc.mttr || 30) * 1000), durationMs: ((inc.mttr || 30) * 1000) - 3300 },
      { state: 'INCIDENT_CLOSED', ts: inc.resolvedAt || mkTs(60000), durationMs: 0 },
    ],
  };
}

export const mockKPI: KPIData = {
  mttr: { value: 47, unit: 'seconds', changeVsBaseline: -84, trend: 'down' },
  autoResolutionRate: { value: 94.2, unit: '%', period: '30d' },
  openIncidents: {
    total: mockIncidents.filter(i => i.status === 'OPEN' || i.status === 'IN_PROGRESS').length,
    critical: mockIncidents.filter(i => (i.status === 'OPEN' || i.status === 'IN_PROGRESS') && i.severity === 'CRITICAL').length,
    warning: mockIncidents.filter(i => (i.status === 'OPEN' || i.status === 'IN_PROGRESS') && i.severity === 'WARNING').length,
  },
  detectionLatency: { value: 2.3, unit: 'seconds' },
};

function generateMetricPoints(hours: number, baseValue: number, variance: number) {
  const points: Array<{ ts: string; value: number }> = [];
  const count = Math.min(hours * 12, 360);
  for (let i = count; i >= 0; i--) {
    points.push({
      ts: formatISO(subMinutes(now, i * 5)),
      value: Math.max(0, baseValue + (Math.random() - 0.5) * variance * 2),
    });
  }
  return points;
}

export function getMockMetrics(range = '1h'): MetricsResponse {
  const hours = range === '1h' ? 1 : range === '6h' ? 6 : range === '24h' ? 24 : range === '7d' ? 168 : 720;
  const cpuPoints = generateMetricPoints(hours, 58, 20);
  const memPoints = generateMetricPoints(hours, 43, 15);
  const diskPoints = generateMetricPoints(hours, 12, 8);
  const latPoints = generateMetricPoints(hours, 45, 30);

  const stats = (pts: Array<{ value: number }>) => ({
    min: Math.round(Math.min(...pts.map(p => p.value)) * 10) / 10,
    max: Math.round(Math.max(...pts.map(p => p.value)) * 10) / 10,
    avg: Math.round(pts.reduce((s, p) => s + p.value, 0) / pts.length * 10) / 10,
  });

  return {
    range,
    cpu: { current: 67.4, ...stats(cpuPoints), unit: '%', threshold: 80, dataPoints: cpuPoints },
    memory: { current: 43.2, ...stats(memPoints), unit: '%', threshold: 85, dataPoints: memPoints },
    disk: { current: 12.1, ...stats(diskPoints), unit: 'MB/s', threshold: null, dataPoints: diskPoints },
    latency: { current: 8, ...stats(latPoints), unit: 'ms', threshold: 200, dataPoints: latPoints },
  };
}

export const mockRemediations: Remediation[] = mockIncidents
  .filter(i => i.remediationId)
  .map(i => ({
    remediationId: i.remediationId!,
    incidentId: i.incidentId,
    actionType: (['RESTART_SERVICE', 'CLEAR_DISK', 'SCALE_OUT', 'CUSTOM'] as const)[Math.floor(Math.random() * 4)],
    target: ['app-service', 'web-server', 'db-primary', 'cache-node'][Math.floor(Math.random() * 4)],
    executedAt: i.detectedAt,
    durationMs: 2000 + Math.floor(Math.random() * 8000),
    status: (['SUCCESS', 'SUCCESS', 'SUCCESS', 'FAILED', 'SKIPPED'] as const)[Math.floor(Math.random() * 5)],
    ssmCommandId: 'cmd-' + Math.random().toString(36).substring(2, 10),
  }));

export const mockGuardrails: GuardrailConfig[] = [
  { type: 'CPU', autoRemediate: true },
  { type: 'MEMORY', autoRemediate: true },
  { type: 'DISK', autoRemediate: true },
  { type: 'LATENCY', autoRemediate: false },
  { type: 'UNKNOWN', autoRemediate: false },
];

export function generateActivityData() {
  return Array.from({ length: 24 }, (_, i) => ({
    hour: `${String(23 - i).padStart(2, '0')}:00`,
    autoResolved: Math.floor(Math.random() * 8),
    escalated: Math.floor(Math.random() * 3),
  })).reverse();
}
