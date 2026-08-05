export { fetchHealth, fetchTraceIds, fetchSota, fetchStdoutRange, stdoutUrl, submitUserInteraction, uploadTask } from '../services/rdagent-api'
export type { HealthCheck } from '../services/rdagent-api'
export { controlTask, fetchTrace, fetchTraceStatuses } from '../services/rdagent-api'
export type { TraceStatusItem } from '../services/rdagent-api'

// ── Artifact Aggregation API ──

export async function fetchAlphaLab(traceId: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await fetch(`/traces/${encodeURIComponent(traceId)}/alpha-lab`, { signal })
  if (!response.ok) throw new Error(`Alpha Lab API failed: ${response.status}`)
  return response.json()
}

export async function fetchModelLab(traceId: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await fetch(`/traces/${encodeURIComponent(traceId)}/model-lab`, { signal })
  if (!response.ok) throw new Error(`Model Lab API failed: ${response.status}`)
  return response.json()
}

export async function fetchStrategyDashboard(traceId: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await fetch(`/traces/${encodeURIComponent(traceId)}/strategy`, { signal })
  if (!response.ok) throw new Error(`Strategy API failed: ${response.status}`)
  return response.json()
}

export async function fetchReport(traceId: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await fetch(`/traces/${encodeURIComponent(traceId)}/report`, { signal })
  if (!response.ok) throw new Error(`Report API failed: ${response.status}`)
  return response.json()
}
