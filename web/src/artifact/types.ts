export type ResultTab = 'conclusion' | 'factors' | 'chart' | 'code'

export interface CodeFile {
  name: string
  content: string
  target?: string
  evoId?: string | number
}

export interface MetricItem {
  label: string
  value: string | number
  rawValue?: number
  tone?: 'up' | 'down' | 'neutral'
  percent?: boolean
}

export interface FactorItem {
  name: string
  description?: string
  formula?: string
  variables?: Record<string, string>
  status?: string
  round_number?: number
  ic?: number | null
  icir?: number | null
}

/** Model row as returned by the SQLite-backed research API (models table). */
export interface ModelItem {
  name: string
  model_type?: string
  architecture?: string | null
  hyperparameters?: string | null
  code_path?: string
  status?: string
  round_number?: number
  annualized_return?: number | null
  max_drawdown?: number | null
  information_ratio?: number | null
  experiment_id?: number | null
}

export interface FeedbackSummary {
  decision: boolean | null
  reason: string
  observations: string
  evaluation: string
  newHypothesis: string
  exception: string
}

/** Experiment row as returned by the SQLite-backed research API. */
export interface ExperimentItem {
  id: number
  strategy_id: string
  loop_id: number
  type: string
  status: string
  hypothesis_text: string | null
  hypothesis_reason: string | null
  hypothesis_assumption: string | null
  decision: number | null
  decision_reason: string | null
  observations: string | null
  ic: number | null
  icir: number | null
  annualized_return: number | null
  max_drawdown: number | null
  information_ratio: number | null
  workspace_path: string | null
  chart_path: string | null
  started_at: string | null
  completed_at: string | null
}