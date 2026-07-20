import { controlTask, fetchTrace, fetchTraceIds, stdoutUrl, uploadTask } from '../services/rdagent-api'

export const url = typeof window !== 'undefined' ? `${window.location.origin}/` : '/'
export const uploadFile = (data, config = {}) => uploadTask(data, config.signal)
export const trace = data => fetchTrace(data)
export const getHistoryTraceIds = () => fetchTraceIds()
export const control = data => controlTask(data.id, data.action)

export async function submitUserInteraction(data) {
  const response = await fetch('/user_interaction/submit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
  if (!response.ok) throw new Error(`请求失败 (${response.status})`)
  return response.json()
}

export const getStdoutDownloadUrl = traceId => stdoutUrl(traceId)
