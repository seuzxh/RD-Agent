import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { controlTask, fetchTrace, fetchTraceIds, fetchTraceStatuses, pollUploadReady, uploadTask } from './api'
import { buildTraceView, deriveTraceStatus } from './trace-model'
import type { TaskMethod, TraceMessage, TraceStatus, TraceTask } from './types'

const CACHE_LIMIT = 5

export function useMultiAlpha() {
  const traceIds = ref<string[]>([])
  const currentTraceId = ref('')
  const messages = shallowRef<TraceMessage[]>([])
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
  const uploading = ref(false)
  const uploadName = ref('')

  const tasks = computed<TraceTask[]>(() => traceIds.value.map(id => {
    const [scenario, ...name] = id.split('/')
    return { id, scenario, name: name.join('/'), status: statuses.value[id] || 'idle' }
  }))
  const view = computed(() => buildTraceView(messages.value, selectedLoop.value))

  function remember(id: string, value: TraceMessage[]) {
    cache.delete(id); cache.set(id, value)
    while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string)
  }

  let listGeneration = 0

  async function loadTraceIds() {
    listLoading.value = true; listError.value = ''
    const generation = ++listGeneration
    try {
      traceIds.value = await fetchTraceIds()
      if (generation !== listGeneration) return  // 被新一轮刷新取代
      // Use cached statuses immediately so the list renders without blocking.
      for (const id of traceIds.value) {
        const cached = cache.get(id)
        if (cached) statuses.value[id] = deriveTraceStatus(cached)
      }
      // C2: 批量获取所有 trace 状态（单次请求，替代 N+1 全量拉取）
      loadStatusesBatch(generation)
    }
    catch (error) { listError.value = error instanceof Error ? error.message : '任务列表加载失败'; ElMessage.error(listError.value) }
    finally { listLoading.value = false }
  }

  async function loadStatusesBatch(generation: number) {
    try {
      const items = await fetchTraceStatuses()
      if (generation !== listGeneration) return  // 旧请求过期，丢弃
      for (const item of items) {
        statuses.value[item.id] = item.status
      }
      // /traces/status 已按 created_at DESC, id ASC 排序——据此重排 traceIds
      const order = new Map(items.map((it, i) => [it.id, i]))
      traceIds.value = [...traceIds.value].sort((a, b) => {
        const ia = order.get(a), ib = order.get(b)
        if (ia !== undefined && ib !== undefined) return ia - ib
        if (ia !== undefined) return -1
        if (ib !== undefined) return 1
        return 0
      })
    } catch {
      // /traces/status 不可用：状态保持默认（idle），不影响列表展示
    }
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
        messages.value = [...messages.value, ...updates]
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

  async function createTask(payload: { method: TaskMethod; description: string; scenario: string; loops: number; modelSelector?: string; autoMode?: boolean; files: File[] }) {
    const data = new FormData()
    const scenario = payload.method === 'pdf' ? 'Finance Data Building (Reports)' : payload.method === 'optimize' ? 'Finance Data Building' : payload.scenario
    data.append('scenario', scenario); data.append('loops', String(payload.loops))
    if (payload.description) data.append('description', payload.description)
    if (payload.modelSelector && payload.modelSelector !== 'lgbm') data.append('model_selector', payload.modelSelector)
    data.append('auto_mode', String(payload.autoMode ?? true))
    payload.files.forEach(file => data.append('files', file))
    const result = await uploadTask(data)
    if (!result.id) throw new Error(result.error || '任务启动失败')
    cache.delete(result.id)
    return result.id
  }

  async function waitForTaskReady(id: string): Promise<void> {
    for (let i = 0; i < 30; i++) {
      try {
        const { ready } = await pollUploadReady(id)
        if (ready) return
      } catch { /* 网络错误，继续重试 */ }
      await new Promise(resolve => setTimeout(resolve, 3000))
    }
    throw new Error('任务初始化超时，请检查日志')
  }

  async function stopCurrentTask() {
    if (!currentTraceId.value) return
    await controlTask(currentTraceId.value, 'stop')
    statuses.value[currentTraceId.value] = 'done'; stopPolling(); ElMessage.success('任务已停止')
  }

  onBeforeUnmount(() => { ++selection; activeController?.abort(); stopPolling() })
  return { traceIds, tasks, currentTraceId, messages, loading, loadingName, listLoading, listError, selectedLoop, statuses, view, loadTraceIds, selectTrace, goHome, createTask, stopCurrentTask, uploading, uploadName, waitForTaskReady }
}
