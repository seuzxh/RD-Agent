import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { controlTask, fetchTrace, fetchTraceIds, uploadTask } from './api'
import { buildTraceView, deriveTraceStatus } from './trace-model'
import type { TaskMethod, TraceMessage, TraceStatus, TraceTask } from './types'

const CACHE_LIMIT = 5

export function useMultiAlpha() {
  const traceIds = ref<string[]>([])
  const currentTraceId = ref('')
  const messages = ref<TraceMessage[]>([])
  const loading = ref(false)
  const listLoading = ref(false)
  const listError = ref('')
  const loadingName = ref('')
  const selectedLoop = ref<number | null>(null)
  const statuses = ref<Record<string, TraceStatus>>({})
  const cache = new Map<string, TraceMessage[]>()
  const requests = new Map<string, Promise<TraceMessage[]>>()
  let activeController: AbortController | null = null
  let activeRequestId = ''
  let pollController: AbortController | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let pollBusy = false
  let selection = 0

  const tasks = computed<TraceTask[]>(() => traceIds.value.map(id => {
    const [scenario, ...name] = id.split('/')
    return { id, scenario, name: name.join('/'), status: statuses.value[id] || 'idle' }
  }))
  const view = computed(() => buildTraceView(messages.value, selectedLoop.value))

  function remember(id: string, value: TraceMessage[]) {
    cache.delete(id); cache.set(id, value)
    while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string)
  }

  async function loadTraceIds() {
    listLoading.value = true; listError.value = ''
    try { traceIds.value = await fetchTraceIds() }
    catch (error) { listError.value = error instanceof Error ? error.message : '任务列表加载失败'; ElMessage.error(listError.value) }
    finally { listLoading.value = false }
  }

  function stopPolling() {
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = null
    pollController?.abort()
    pollController = null
  }

  async function poll(id: string) {
    if (pollBusy || currentTraceId.value !== id) return
    pollBusy = true
    pollController = new AbortController()
    try {
      const updates = await fetchTrace({ id, all: false, reset: false, cursor: messages.value.length }, pollController.signal)
      if (currentTraceId.value !== id) return
      if (updates.length) {
        messages.value.push(...updates)
        if (selectedLoop.value == null) {
          const loops = messages.value.map(message => Number(message.loop_id)).filter(Number.isFinite)
          if (loops.length) selectedLoop.value = Math.max(...loops)
        }
        remember(id, messages.value)
        const status = deriveTraceStatus(messages.value)
        statuses.value[id] = status
        if (status === 'done') return
      }
    } catch { /* Keep the current rendered data and retry. */ }
    finally { pollBusy = false; pollController = null }
    if (currentTraceId.value === id) pollTimer = setTimeout(() => void poll(id), 5000)
  }

  async function requestInitial(id: string) {
    if (cache.has(id)) {
      const cached = cache.get(id) as TraceMessage[]
      remember(id, cached)
      return cached
    }
    if (requests.has(id)) return requests.get(id) as Promise<TraceMessage[]>
    if (activeController && activeRequestId !== id) activeController.abort()
    activeController = new AbortController()
    activeRequestId = id
    const controller = activeController
    const request = fetchTrace({ id, all: true, reset: true }, controller.signal)
    requests.set(id, request)
    try { const result = await request; remember(id, result); return result }
    finally { requests.delete(id); if (activeController === controller) { activeController = null; activeRequestId = '' } }
  }

  async function selectTrace(id: string) {
    const generation = ++selection
    stopPolling()
    if (activeController && activeRequestId !== id) activeController.abort()
    currentTraceId.value = id
    selectedLoop.value = null
    loading.value = true
    loadingName.value = id.split('/').slice(1).join('/') || id
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    try {
      const result = await requestInitial(id)
      if (generation !== selection) return
      messages.value = result
      const loops = [...new Set(result.map(message => Number(message.loop_id)).filter(Number.isFinite))].sort((a, b) => a - b)
      selectedLoop.value = loops.length ? loops[loops.length - 1] : null
      statuses.value[id] = deriveTraceStatus(result)
      if (statuses.value[id] !== 'done') void poll(id)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      ElMessage.error(error instanceof Error ? error.message : '任务详情加载失败')
    } finally {
      if (generation === selection) loading.value = false
    }
  }

  function goHome() {
    ++selection; activeController?.abort(); activeController = null; activeRequestId = ''; stopPolling()
    currentTraceId.value = ''; messages.value = []; selectedLoop.value = null; loading.value = false
  }

  async function createTask(payload: { method: TaskMethod; description: string; scenario: string; loops: number; modelSelector?: string; files: File[] }) {
    const data = new FormData()
    const scenario = payload.method === 'pdf' ? 'Finance Data Building (Reports)' : payload.method === 'optimize' ? 'Finance Data Building' : payload.scenario
    data.append('scenario', scenario); data.append('loops', String(payload.loops))
    if (payload.description) data.append('description', payload.description)
    if (payload.modelSelector && payload.modelSelector !== 'lgbm') data.append('model_selector', payload.modelSelector)
    payload.files.forEach(file => data.append('files', file))
    const result = await uploadTask(data)
    if (!result.id) throw new Error(result.error || '任务启动失败')
    cache.delete(result.id); await loadTraceIds(); await selectTrace(result.id)
    return result.id
  }

  async function stopCurrentTask() {
    if (!currentTraceId.value) return
    await controlTask(currentTraceId.value, 'stop')
    statuses.value[currentTraceId.value] = 'done'; stopPolling(); ElMessage.success('任务已停止')
  }

  onBeforeUnmount(() => { ++selection; activeController?.abort(); stopPolling() })
  return { traceIds, tasks, currentTraceId, messages, loading, loadingName, listLoading, listError, selectedLoop, statuses, view, loadTraceIds, selectTrace, goHome, createTask, stopCurrentTask }
}
