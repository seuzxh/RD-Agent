import type { AgentAnalysis, AgentDirection, StockOption } from './types'

const API_BASE = (import.meta.env.VITE_ANA_AGENTS_API_BASE || 'https://appt15.crsec.com.cn:3004').replace(/\/$/, '')

interface AnalysisPayload {
  core_view?: unknown
  direction?: unknown
  key_risk?: unknown
  summary?: unknown
}

interface AnalysisInnerResponse {
  errorMsg?: string
  errorNo?: number | string
  results?: {
    analysisRes?: AnalysisPayload
    createTime?: string
    stockCode?: string
    stockName?: string
  }
}

function getErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback
  const record = payload as Record<string, unknown>
  return String(record.ErrorInfo || record.errorMsg || record.message || fallback)
}

async function requestJson(url: URL, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await fetch(url, { signal })
  const payload = (await response.json()) as unknown
  if (!response.ok) {
    throw new Error(getErrorMessage(payload, `请求失败 (${response.status})`))
  }
  if (!payload || typeof payload !== 'object') {
    throw new Error('接口返回格式异常')
  }
  return payload as Record<string, unknown>
}

function splitField(value: unknown): string[] {
  return typeof value === 'string' && value ? value.split('|') : []
}

export async function searchStocks(keyword: string, signal?: AbortSignal): Promise<StockOption[]> {
  const url = new URL(`https://newapp.crsec.com.cn:3004/reqxml`)
  url.search = new URLSearchParams({
    funcNo: '1500102',
    action: '5811',
    StockCode: keyword.trim(),
    count: '10',
  }).toString()

  const payload = await requestJson(url, signal)
  if (String(payload.ErrorNo ?? '') !== '0') {
    throw new Error(getErrorMessage(payload, '股票搜索失败'))
  }

  const codes = splitField(payload['0'])
  const names = splitField(payload['2'])
  const labels = splitField(payload.StockLabel)
  const prices = splitField(payload['10'])
  const changePercents = splitField(payload['514'])

  return codes.reduce<StockOption[]>((results, code, index) => {
    const name = names[index]?.trim()
    const normalizedCode = code.trim()
    if (!normalizedCode || !name) return results
    results.push({
      id: `${normalizedCode}:${index}`,
      code: normalizedCode,
      name,
      marketLabel: labels[index]?.trim() || '',
      latestPrice: prices[index]?.trim() || '',
      changePercent: changePercents[index]?.trim() || '',
    })
    return results
  }, [])
}

function normalizeDirection(direction: unknown): AgentDirection {
  const normalized = String(direction || '').toUpperCase()
  if (normalized === 'POSITIVE') return 'positive'
  if (normalized === 'NEUTRAL') return 'neutral'
  if (normalized === 'NEGATIVE') return 'negative'
  throw new Error(`无法识别的观点方向：${normalized || '空值'}`)
}

function normalizeTextList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item).trim()).filter(Boolean)
}

export async function analyzeStock(
  agentId: number,
  stockCode: string,
  signal?: AbortSignal,
): Promise<AgentAnalysis> {
  const url = new URL(`${API_BASE}/reqxml`)
  url.search = new URLSearchParams({
    funcNo: '1500105',
    action: '5825',
    paramStr: JSON.stringify({ aiAppId: agentId, stkCode: stockCode }),
  }).toString()

  const payload = await requestJson(url, signal)
  if (String(payload.ErrorNo ?? '') !== '0') {
    throw new Error(getErrorMessage(payload, '智能体分析失败'))
  }

  let inner: AnalysisInnerResponse
  try {
    inner = JSON.parse(String(payload.result || '{}')) as AnalysisInnerResponse
  } catch {
    throw new Error('智能体分析结果解析失败')
  }

  if (String(inner.errorNo ?? '') !== '0') {
    throw new Error(inner.errorMsg || '智能体分析失败')
  }

  const result = inner.results
  const analysis = result?.analysisRes
  if (!result || !analysis) {
    throw new Error('智能体未返回分析内容')
  }

  const coreViews = normalizeTextList(analysis.core_view)
  const risk = String(analysis.key_risk || '').trim()
  const summary = String(analysis.summary || '').trim()
  if (!coreViews.length && !risk && !summary) {
    throw new Error('智能体返回了空分析')
  }

  return {
    coreViews,
    direction: normalizeDirection(analysis.direction),
    risk,
    summary,
    stockCode: String(result.stockCode || stockCode),
    stockName: String(result.stockName || ''),
    createdAt: String(result.createTime || ''),
  }
}
