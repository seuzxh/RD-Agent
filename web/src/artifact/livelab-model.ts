import type { FactorItem, FeedbackSummary, MetricItem, ModelItem } from './types'

/** Parse a factor's `variables` JSON string into a record. Tolerates null/empty/invalid JSON. */
export function parseVariables(raw: string | null | undefined): Record<string, string> {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const out: Record<string, string> = {}
      for (const [key, value] of Object.entries(parsed)) out[key] = String(value)
      return out
    }
    return {}
  } catch {
    return {}
  }
}

/** Map a raw factor row (research API) to the display FactorItem shape. */
export function buildFactor(factor: Record<string, any>): FactorItem {
  return {
    name: factor.name || '',
    description: factor.description || undefined,
    formula: factor.formulation || undefined,
    variables: parseVariables(factor.variables),
    status: factor.status,
    round_number: factor.round_number,
    ic: factor.ic ?? null,
    icir: factor.icir ?? null,
  }
}

/** Map a raw model row to the display ModelItem shape (identity-ish passthrough). */
export function buildModel(model: Record<string, any>): ModelItem {
  return {
    name: model.name || '',
    model_type: model.model_type || undefined,
    architecture: model.architecture ?? null,
    hyperparameters: model.hyperparameters ?? null,
    code_path: model.code_path || undefined,
    status: model.status,
    round_number: model.round_number,
    annualized_return: model.annualized_return ?? null,
    max_drawdown: model.max_drawdown ?? null,
    information_ratio: model.information_ratio ?? null,
    experiment_id: model.experiment_id ?? null,
  }
}

/**
 * Map a model to the FactorItem shape so the ResultWorkspace tab can render a
 * model round with the same card layout used for factor rounds. The model's
 * architecture becomes the "formula" and its hyperparameters the "variables".
 */
export function buildModelAsFactor(model: ModelItem): FactorItem {
  return {
    name: model.name || '',
    description: model.model_type || undefined,
    formula: model.architecture || undefined,
    variables: parseVariables(model.hyperparameters),
    status: model.status,
    round_number: model.round_number,
  }
}

/** Map a list of raw factor rows, filtered to the given round. */
export function buildFactors(factors: Record<string, any>[] | undefined, round: number): FactorItem[] {
  if (!Array.isArray(factors)) return []
  return factors
    .filter(f => f.round_number === round)
    .map(buildFactor)
}

/** Derive the up/down tone used by the conclusion view for a metric value. */
function toneOf(value: number): 'up' | 'down' {
  return value >= 0 ? 'up' : 'down'
}

/** Build the metrics list from an experiment's metric columns. */
export function buildMetrics(experiment: Record<string, any> | undefined): MetricItem[] {
  if (!experiment) return []
  const out: MetricItem[] = []
  const add = (label: string, value: number | null | undefined, opts: Partial<MetricItem> = {}) => {
    if (value == null) return
    out.push({ label, value, rawValue: value, tone: toneOf(value), ...opts })
  }
  add('IC', experiment.ic)
  add('ICIR', experiment.icir)
  add('年化收益', experiment.annualized_return, { percent: true })
  add('最大回撤', experiment.max_drawdown, { percent: true })
  add('信息比率', experiment.information_ratio)
  return out
}

/** Build the feedback summary from an experiment's decision/reason/observation fields. */
export function buildFeedback(experiment: Record<string, any> | undefined): FeedbackSummary {
  return {
    decision: experiment?.decision == null ? null : !!experiment.decision,
    reason: experiment?.decision_reason || '',
    observations: experiment?.observations || '',
    evaluation: '',
    newHypothesis: '',
    exception: '',
  }
}

/** Build the hypothesis summary object consumed by MetricsPanel. */
export function buildHypothesis(experiment: Record<string, any> | undefined): Record<string, unknown> | null {
  const text = experiment?.hypothesis_text
  if (!text) return null
  return {
    hypothesis: text,
    reason: experiment?.hypothesis_reason || '',
    assumption: experiment?.hypothesis_assumption || '',
  }
}

/** A single agent in a fin_quant round's flow, mapped to a pipeline step. */
export interface RoundAgentDef {
  key: string
  step: string
  name: string
  role: string
  icon: string
  product: 'hypothesis' | 'design' | 'code' | 'metrics' | 'feedback' | 'record'
}

export type RoundType = 'factor' | 'model'

/**
 * Fin_quant per-round agent sets. Each agent's status is driven by the pipeline
 * node matching `step` (not by lagging signals like code/metric availability).
 * `direct_exp_gen` drives both the hypothesis (🧠) and design (✏️) agents.
 */
export const AGENT_DEFS: Record<RoundType, RoundAgentDef[]> = {
  factor: [
    { key: 'hypothesis', step: 'direct_exp_gen', name: '因子假设', role: '研究员', icon: '🧠', product: 'hypothesis' },
    { key: 'design', step: 'direct_exp_gen', name: '因子设计', role: '设计师', icon: '✏️', product: 'design' },
    { key: 'coding', step: 'coding', name: '因子实现', role: '编码员', icon: '▰', product: 'code' },
    { key: 'backtest', step: 'running', name: '因子回测', role: '执行员', icon: '📊', product: 'metrics' },
    { key: 'feedback', step: 'feedback', name: '因子评审', role: '评审员', icon: '🔍', product: 'feedback' },
    { key: 'record', step: 'record', name: '记录', role: '记录员', icon: '📋', product: 'record' },
  ],
  model: [
    { key: 'hypothesis', step: 'direct_exp_gen', name: '模型假设', role: '研究员', icon: '🧠', product: 'hypothesis' },
    { key: 'design', step: 'direct_exp_gen', name: '模型设计', role: '设计师', icon: '✏️', product: 'design' },
    { key: 'coding', step: 'coding', name: '模型实现', role: '编码员', icon: '▰', product: 'code' },
    { key: 'training', step: 'running', name: '模型训练', role: '执行员', icon: '📈', product: 'metrics' },
    { key: 'feedback', step: 'feedback', name: '模型评估', role: '评审员', icon: '📉', product: 'feedback' },
    { key: 'record', step: 'record', name: '记录', role: '记录员', icon: '📋', product: 'record' },
  ],
}