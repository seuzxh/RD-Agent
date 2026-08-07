/**
 * Research API — REST + SSE client for the SQLite-backed ResearchDB layer.
 *
 * Replaces the old rdagent-api.ts polling-based endpoints.
 */

// ── Types ──

export interface StrategyItem {
  id: string
  description: string | null
  scenario: string | null
  source: string | null
  status: string
  created_at: string | null
  updated_at: string | null
  total_experiments: number
  total_factors: number
  total_models: number
}

export interface StrategyDetail extends StrategyItem {
  experiments: ExperimentItem[]
}

export interface ExperimentItem {
  id: number
  strategy_id: string
  loop_id: number
  type: string
  status: string
  hypothesis_text: string | null
  decision: number | null
  ic: number | null
  icir: number | null
  annualized_return: number | null
  max_drawdown: number | null
  information_ratio: number | null
  workspace_path: string | null
  started_at: string | null
  completed_at: string | null
}

export interface FactorItem {
  id: number
  strategy_id: string
  experiment_id: number | null
  name: string
  description: string | null
  formulation: string | null
  variables: string | null
  code_path: string | null
  status: string
  round_number: number | null
  ic: number | null
  icir: number | null
  annualized_return: number | null
  max_drawdown: number | null
  information_ratio: number | null
}

export interface ModelItem {
  id: number
  strategy_id: string
  experiment_id: number | null
  name: string
  model_type: string | null
  architecture: string | null
  hyperparameters: string | null
  code_path: string | null
  status: string
  round_number: number | null
  annualized_return: number | null
  max_drawdown: number | null
  information_ratio: number | null
}

export interface PipelineNode {
  id: number
  strategy_id: string
  experiment_id: number | null
  loop_id: number
  step_name: string
  status: string
  input_summary: string | null
  output_summary: string | null
  artifact_refs: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  error_message: string | null
  prompt_tokens: number
  completion_tokens: number
  call_count: number
}

export interface ReportResponse {
  strategy_id: string
  total_rounds: number
  experiments: ExperimentItem[]
  summary_metrics: Record<string, any>
}

export interface SseEvent {
  type: 'node_update' | 'metric_update' | 'strategy_status'
  data: any
}

// ── API Base ──

const API_BASE = '/api'

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.error || `Request failed: ${response.status}`)
  }
  return response.json()
}

async function del(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, { method: 'DELETE' })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.error || `Delete failed: ${response.status}`)
  }
}

// ── Strategy endpoints ──

export const fetchStrategies = (signal?: AbortSignal) =>
  get<StrategyItem[]>('/strategies', signal)

export const fetchStrategy = (id: string, signal?: AbortSignal) =>
  get<StrategyDetail>(`/strategies/${encodeURIComponent(id)}`, signal)

export const fetchStrategyFactors = (id: string, signal?: AbortSignal) =>
  get<FactorItem[]>(`/strategies/${encodeURIComponent(id)}/factors`, signal)

export const fetchStrategyModels = (id: string, signal?: AbortSignal) =>
  get<ModelItem[]>(`/strategies/${encodeURIComponent(id)}/models`, signal)

export const fetchStrategyPipeline = (id: string, signal?: AbortSignal) =>
  get<PipelineNode[]>(`/strategies/${encodeURIComponent(id)}/pipeline`, signal)

export const fetchStrategyReport = (id: string, signal?: AbortSignal) =>
  get<ReportResponse>(`/strategies/${encodeURIComponent(id)}/report`, signal)

export const fetchStrategyMessages = (id: string, signal?: AbortSignal) =>
  get<{ messages: any[]; total: number }>(`/strategies/${encodeURIComponent(id)}/messages`, signal)

export const deleteStrategy = (id: string) =>
  del(`/strategies/${encodeURIComponent(id)}`)

// ── Cross-strategy endpoints ──

export const fetchAllFactors = (strategyId?: string, signal?: AbortSignal) => {
  const qs = strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}` : ''
  return get<FactorItem[]>(`/factors${qs}`, signal)
}

export const fetchAllModels = (strategyId?: string, signal?: AbortSignal) => {
  const qs = strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}` : ''
  return get<ModelItem[]>(`/models${qs}`, signal)
}

// ── SSE client ──

export function subscribeStrategyEvents(
  strategyId: string,
  onEvent: (event: SseEvent) => void,
  onError?: (error: Event) => void,
): () => void {
  const url = `${API_BASE}/strategies/${encodeURIComponent(strategyId)}/events`
  const eventSource = new EventSource(url)

  eventSource.addEventListener('node_update', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* ignore parse errors */ }
  })
  eventSource.addEventListener('metric_update', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* ignore parse errors */ }
  })
  eventSource.addEventListener('strategy_status', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* ignore parse errors */ }
  })
  eventSource.addEventListener('connected', () => {
    /* connection established — no action needed */
  })

  if (onError) {
    eventSource.onerror = onError
  }

  // Return unsubscribe function
  return () => { eventSource.close() }
}