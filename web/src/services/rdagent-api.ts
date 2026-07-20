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
export const submitUserInteraction = (data: { id: string; payload: unknown }, signal?: AbortSignal) => fetch('/user_interaction/submit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal }).then(response => parseResponse<unknown>(response))
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
