export interface TraceMessage {
  tag: string
  timestamp?: string
  loop_id?: string | number | null
  content: unknown
}

export interface TraceRequest { id: string; all: boolean; reset: boolean; cursor?: number }

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly payload?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'error' in payload ? String(payload.error) : ''
    throw new ApiError(detail || `请求失败 (${response.status})`, response.status, payload)
  }
  return payload as T
}

export const fetchTraceIds = (signal?: AbortSignal) => fetch('/traces', { signal }).then(response => parseResponse<string[]>(response))

export interface TraceStatusItem {
  id: string
  status: 'running' | 'done' | 'error' | 'idle'
  loops: number[]
  created_at: string | null
  updated_at: string | null
  has_chart: boolean
}

/** C1 catalog: 批量获取所有 trace 状态（替代 N+1 全量拉取） */
export const fetchTraceStatuses = (signal?: AbortSignal) =>
  fetch('/traces/status', { signal }).then(response => parseResponse<TraceStatusItem[]>(response))
export const fetchTrace = (data: TraceRequest, signal?: AbortSignal) => fetch('/trace', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal }).then(response => parseResponse<TraceMessage[]>(response))
export const uploadTask = (data: FormData, signal?: AbortSignal) => fetch('/upload', { method: 'POST', body: data, signal }).then(response => parseResponse<{ id?: string; error?: string }>(response))
export const pollUploadReady = (id: string, signal?: AbortSignal) => fetch(`/upload/poll?${new URLSearchParams({ id })}`, { signal }).then(response => parseResponse<{ ready: boolean }>(response))
export const controlTask = (id: string, action: string, signal?: AbortSignal) => fetch('/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, action }), signal }).then(response => parseResponse<unknown>(response))
export const submitUserInteraction = (data: { id: string; payload: unknown }, signal?: AbortSignal) => fetch('/user_interaction/submit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal }).then(response => parseResponse<unknown>(response))
export const fetchSota = (traceId: string, signal?: AbortSignal) => fetch(`/traces/${encodeURIComponent(traceId)}/sota`, { signal }).then(response => parseResponse<Record<string, unknown>>(response))
export interface HealthCheck { overall: string; checks: Array<{ name: string; icon: string; status: 'pass' | 'warn' | 'fail'; detail: string }> }
export const fetchHealth = (signal?: AbortSignal) => fetch('/health', { signal }).then(response => parseResponse<HealthCheck>(response))
export const stdoutUrl = (id: string) => `/stdout?${new URLSearchParams({ id }).toString()}`
export const logStreamUrl = (id: string) => `/logs/sse?${new URLSearchParams({ trace: id }).toString()}`

/**
 * Range-incremental fetch on /stdout. Returns the new bytes (as string) and the
 * next offset (end + 1 of the returned range). Backend is Flask send_file which
 * natively supports HTTP Range.
 *
 * Responses:
 *   206 with Content-Range "bytes start-end/total" - normal incremental slice
 *   416 with Content-Range "bytes star-slash-total" - offset at or beyond EOF:
 *       total >= offset: file has not grown (waiting for LLM); keep offset, no data
 *       total <  offset: file was truncated/rewritten; reset offset to 0, full body
 *   200 (no Range handling) - full file fallback; next offset is total length
 *
 * First call should pass offset=0.
 */
export interface StdoutRangeResult { text: string; nextOffset: number }
export async function fetchStdoutRange(id: string, offset: number, signal?: AbortSignal): Promise<StdoutRangeResult> {
  const headers: Record<string, string> = offset > 0 ? { Range: `bytes=${offset}-` } : {}
  const response = await fetch(stdoutUrl(id), { headers, signal })
  if (!response.ok && response.status !== 416) {
    const payload = await response.json().catch(() => null)
    const detail = payload && typeof payload === 'object' && 'error' in payload ? String(payload.error) : ''
    throw new ApiError(detail || `请求失败 (${response.status})`, response.status, payload)
  }
  const contentRange = response.headers.get('Content-Range') || ''
  const text = await response.text()
  if (response.status === 416) {
    // Content-Range: bytes */{total}
    const match = contentRange.match(/bytes\s+\*\/(\d+)/)
    const total = match ? Number(match[1]) : offset
    if (total < offset) {
      // file was truncated/rewritten → reset and replay from 0
      return { text, nextOffset: 0 }
    }
    // file simply hasn't grown past offset yet (waiting for LLM) → keep offset, no new data
    return { text: '', nextOffset: offset }
  }
  if (response.status === 206 && contentRange) {
    // Content-Range: bytes {start}-{end}/{total}
    const match = contentRange.match(/bytes\s+(\d+)-(\d+)\/(\d+)/)
    if (match) {
      const end = Number(match[2])
      return { text, nextOffset: end + 1 }
    }
  }
  // 200 fallback (no Range handling): full file, next offset = total length
  const len = Number(response.headers.get('Content-Length')) || text.length
  return { text, nextOffset: len }
}

// ==================== Prediction Dashboard ====================

export interface PredictExperiment {
  trace_id: string
  name: string
  created_at: string
  factor_count: number
  metrics: { IC: number | null; annualized_return: number | null; max_drawdown: number | null }
  has_model: boolean
}

export interface Top20Item { rank: number; instrument: string; score: number }
export interface Top20Result { predict_date: string; top20: Top20Item[] }
export interface PredictRecord {
  date: string
  source_trace_id: string
  top20: Top20Item[]
  created_at: string
}

export const fetchPredictExperiments = (signal?: AbortSignal) =>
  fetch('/predict/experiments', { signal }).then(r => parseResponse<{ experiments: PredictExperiment[] }>(r))

export const runPredict = (traceId: string) =>
  fetch('/predict/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trace_id: traceId }) })
    .then(r => parseResponse<{ task_id: string }>(r))

export const fetchPredictHistory = (traceId?: string, signal?: AbortSignal) =>
  fetch(`/predict/history${traceId ? '?trace_id=' + encodeURIComponent(traceId) : ''}`, { signal })
    .then(r => parseResponse<{ records: PredictRecord[] }>(r))

// ==================== Settings ====================

export type ConfigFieldType = 'string' | 'number' | 'boolean' | 'select' | 'json' | 'password' | 'model_map'

export interface ConfigField {
  key: string
  label: string
  type: ConfigFieldType
  value: unknown
  default?: unknown
  options?: string[]
  sensitive?: boolean
  help?: string
}

export interface ConfigCard { id: string; title: string; fields: ConfigField[] }
export interface ConfigGroup { id: string; label: string; icon: string; cards: ConfigCard[] }
export interface SettingsSchema { groups: ConfigGroup[] }

export const fetchSettingsSchema = (signal?: AbortSignal) =>
  fetch('/settings/schema', { signal }).then(r => parseResponse<SettingsSchema>(r))

export const saveSettings = (fields: Record<string, unknown>) =>
  fetch('/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fields }) })
    .then(r => parseResponse<{ status: string; written: string[]; skipped: string[]; restart_required: boolean }>(r))

export interface TestModelResult { ok: boolean; latency_ms: number; error: string }

export const testModel = (model: string, apiKey?: string, apiBase?: string, mode: 'chat' | 'embedding' = 'chat') =>
  fetch('/settings/test-model', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model, api_key: apiKey || '', api_base: apiBase || '', mode }) })
    .then(r => parseResponse<TestModelResult>(r))
