/** API layer for the artifact view — backed by research_api (SQLite). */

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`请求失败 (${response.status})`)
  return response.json()
}

export interface StrategySummary {
  id: string
  name: string
  description: string
  timestamp: string
  created_at: string
  total_rounds: number
  factor_count: number
  model_count: number
  last_round: number
  last_decision: boolean
  status: string
}

export interface AggregatedFactors {
  factors: any[]
  total: number
}

export interface AggregatedModels {
  models: any[]
  total: number
}

export interface ReportData {
  strategies: any[]
  total_strategies: number
}

export interface LiveData {
  tasks: any[]
  total: number
}

export interface StrategyDetail {
  id: string
  description: string
  scenario: string
  status: string
  created_at: string
  experiments: any[]
  factors: any[]
  models: any[]
  [key: string]: any
}

export interface MessagesResponse {
  messages: any[]
  total: number
  trace_dir: string
}

/** List all strategies (from ResearchDB SQLite) */
export async function fetchStrategies(): Promise<StrategySummary[]> {
  return fetchJson<StrategySummary[]>('/api/strategies')
}

/** Aggregated factors across all strategies */
export async function fetchAlphaLab(): Promise<AggregatedFactors> {
  return fetchJson<AggregatedFactors>('/api/factors?strategy_id=')
}

/** Aggregated models across all strategies */
export async function fetchModelLab(): Promise<AggregatedModels> {
  return fetchJson<AggregatedModels>('/api/models?strategy_id=')
}

/** Cross-strategy report */
export async function fetchReport(): Promise<ReportData> {
  return fetchJson<ReportData>('/api/reports')
}

/** Running tasks list */
export async function fetchLive(): Promise<LiveData> {
  return fetchJson<LiveData>('/api/live')
}

/** Strategy detail with experiments, factors, models */
export async function fetchStrategyDetail(id: string): Promise<StrategyDetail> {
  return fetchJson<StrategyDetail>(`/api/strategies/${encodeURIComponent(id)}/detail`)
}

/** Strategy trace messages */
export async function fetchStrategyMessages(id: string): Promise<MessagesResponse> {
  return fetchJson<MessagesResponse>(`/api/strategies/${encodeURIComponent(id)}/messages`)
}