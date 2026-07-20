export interface TraceMessage {
  tag: string
  timestamp?: string
  loop_id?: string | number | null
  content: unknown
}

export interface TraceRequest { id: string; all: boolean; reset: boolean }

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
export const fetchTrace = (data: TraceRequest, signal?: AbortSignal) => fetch('/trace', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal }).then(response => parseResponse<TraceMessage[]>(response))
export const uploadTask = (data: FormData, signal?: AbortSignal) => fetch('/upload', { method: 'POST', body: data, signal }).then(response => parseResponse<{ id?: string; error?: string }>(response))
export const controlTask = (id: string, action: string, signal?: AbortSignal) => fetch('/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, action }), signal }).then(response => parseResponse<unknown>(response))
export const stdoutUrl = (id: string) => `/stdout?${new URLSearchParams({ id }).toString()}`
export const logStreamUrl = (id: string) => `/logs/sse?${new URLSearchParams({ trace: id }).toString()}`
