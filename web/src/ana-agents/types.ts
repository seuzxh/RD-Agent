export type AgentDirection = 'positive' | 'neutral' | 'negative'
export type AgentResultStatus = 'idle' | 'loading' | 'success' | 'error'

export interface StockOption {
  id: string
  code: string
  name: string
  marketLabel: string
  latestPrice: string
  changePercent: string
}

export interface AgentDefinition {
  id: number
  name: string
  dimension: string
  monogram: string
  accent: string
}

export interface AgentAnalysis {
  coreViews: string[]
  direction: AgentDirection
  risk: string
  summary: string
  stockCode: string
  stockName: string
  createdAt: string
}

export interface AgentResultState {
  status: AgentResultStatus
  analysis: AgentAnalysis | null
  error: string
}
