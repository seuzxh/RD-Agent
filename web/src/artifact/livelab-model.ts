import type { FactorItem, FeedbackSummary, MetricItem } from './types'

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