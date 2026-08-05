/** API layer for the artifact view. */

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
  total_rounds: number
  factor_count: number
  model_count: number
  last_round: number
  last_decision: boolean
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

export async function fetchStrategies(): Promise<StrategySummary[]> {
  return fetchJson<StrategySummary[]>('/api/strategies')
}

export async function fetchAlphaLab(): Promise<AggregatedFactors> {
  return fetchJson<AggregatedFactors>('/api/alpha-lab')
}

export async function fetchModelLab(): Promise<AggregatedModels> {
  return fetchJson<AggregatedModels>('/api/model-lab')
}

export async function fetchReport(): Promise<ReportData> {
  return fetchJson<ReportData>('/api/report')
}

export interface LiveData {
  tasks: any[]
  total: number
}

export async function fetchLive(): Promise<LiveData> {
  return fetchJson<LiveData>('/api/live')
}