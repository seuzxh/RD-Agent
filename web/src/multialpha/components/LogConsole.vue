<template>
  <section v-if="traceId" class="log-console" :class="{ expanded }">
    <button class="log-head" @click="toggle">
      <span><i :class="state" />运行日志 · {{ logSummary }}</span>
      <span>{{ expanded ? '收起 ↓' : '展开 ↑' }}</span>
    </button>

    <div v-if="expanded" class="log-body">
      <header>
        <el-input v-model="keyword" size="small" clearable placeholder="搜索日志…" />
        <el-checkbox v-model="hideInfo">隐藏 INFO</el-checkbox>
        <a :href="stdoutUrl(traceId)" target="_blank">下载 stdout</a>
      </header>

      <div ref="viewport" class="log-lines" @scroll="handleScroll">
        <div v-if="state === 'idle' && !lines.length" class="log-note">点击后正在加载运行日志…</div>
        <div v-else-if="state === 'error' && !lines.length" class="log-note">实时日志连接不可用，可下载 stdout 查看完整日志。</div>
        <div v-else-if="lines.length && !filtered.length" class="log-note">没有匹配的日志</div>

        <div v-if="filtered.length" class="virtual-log-space" :style="{ height: `${totalHeight}px` }">
          <div class="virtual-log-window" :style="{ transform: `translateY(${offsetY}px)` }">
            <pre v-for="row in visibleRows" :key="row.index" :class="classify(row.line)" :title="row.line">{{ row.line }}</pre>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { fetchStdoutRange, stdoutUrl } from '../api'
import type { TraceStatus } from '../types'

const MAX_LINES = 5000
const LINE_HEIGHT = 20
const BUFFER_ROWS = 15
const FLUSH_INTERVAL = 100
const SEARCH_DELAY = 250
const POLL_INTERVAL = 2000

const props = defineProps<{ traceId: string; status: TraceStatus }>()
const expanded = ref(false)
const keyword = ref('')
const debouncedKeyword = ref('')
const hideInfo = ref(false)
const lines = shallowRef<string[]>([])
const state = ref<'idle' | 'live' | 'error'>('idle')
const viewport = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const viewportHeight = ref(248)

let pollTimer: ReturnType<typeof setTimeout> | undefined
let pollAbort: AbortController | null = null
let offset = 0
let pendingLines: string[] = []
let flushTimer: ReturnType<typeof setTimeout> | undefined
let searchTimer: ReturnType<typeof setTimeout> | undefined
let stickToBottom = true

function close() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = undefined }
  if (pollAbort) { pollAbort.abort(); pollAbort = null }
}

function clearTimers() {
  if (flushTimer) clearTimeout(flushTimer)
  if (searchTimer) clearTimeout(searchTimer)
  flushTimer = undefined
  searchTimer = undefined
}

function reset() {
  close()
  clearTimers()
  pendingLines = []
  offset = 0
  expanded.value = false
  lines.value = []
  keyword.value = ''
  debouncedKeyword.value = ''
  hideInfo.value = false
  state.value = 'idle'
  scrollTop.value = 0
  stickToBottom = true
}

function scrollToBottom() {
  const element = viewport.value
  if (!element) return
  element.scrollTop = element.scrollHeight
  scrollTop.value = element.scrollTop
}

function flushPending() {
  flushTimer = undefined
  if (!pendingLines.length) return

  const nextLines = lines.value.concat(pendingLines)
  pendingLines = []
  lines.value = nextLines.length > MAX_LINES ? nextLines.slice(-MAX_LINES) : nextLines

  if (expanded.value && stickToBottom) void nextTick(scrollToBottom)
}

function scheduleFlush() {
  if (!flushTimer) flushTimer = setTimeout(flushPending, FLUSH_INTERVAL)
}

function connect() {
  if (!props.traceId || pollTimer) return
  state.value = 'idle'

  const poll = async () => {
    pollAbort = new AbortController()
    try {
      const result = await fetchStdoutRange(props.traceId, offset, pollAbort.signal)
      pollAbort = null
      offset = result.nextOffset
      if (result.text) {
        // Drop the trailing partial line if the slice doesn't end with \n (it'll come on the next poll)
        const fetched = result.text
        const lastNewline = fetched.lastIndexOf('\n')
        const complete = lastNewline === -1 ? '' : fetched.slice(0, lastNewline)
        if (complete) {
          pendingLines.push(...complete.split(/\r?\n/).filter((line) => line.length > 0))
          scheduleFlush()
        }
        if (state.value === 'idle') state.value = 'live'
      }
    } catch (err) {
      pollAbort = null
      if (err instanceof Error && err.name === 'AbortError') return // closed by close()
      flushPending()
      state.value = 'error'
      close()
      return
    }
    pollTimer = setTimeout(poll, POLL_INTERVAL)
  }

  void poll()
}

function toggle() {
  expanded.value = !expanded.value
  if (!expanded.value) return

  if (!pollTimer && props.status !== 'running' && !lines.value.length) connect()
  void nextTick(() => {
    if (!viewport.value) return
    viewportHeight.value = viewport.value.clientHeight
    if (stickToBottom) scrollToBottom()
  })
}

function handleScroll() {
  const element = viewport.value
  if (!element) return
  scrollTop.value = element.scrollTop
  viewportHeight.value = element.clientHeight
  stickToBottom = element.scrollHeight - element.scrollTop - element.clientHeight < LINE_HEIGHT * 3
}

watch(keyword, (value) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { debouncedKeyword.value = value.trim().toLowerCase() }, SEARCH_DELAY)
})

watch(
  () => [props.traceId, props.status] as const,
  ([id, status], previous) => {
    const oldId = previous?.[0] || ''
    if (id !== oldId) reset()
    if (!id) return
    if (status === 'running') connect()
    else if (oldId === id) {
      flushPending()
      close()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  close()
  clearTimers()
})

const logSummary = computed(() => lines.value.length
  ? `${lines.value.length} 行`
  : props.status === 'running' ? '实时加载中' : '点击加载')

const filtered = computed(() => {
  if (!expanded.value) return []
  const query = debouncedKeyword.value
  return lines.value.filter((line) =>
    (!hideInfo.value || !line.includes('INFO')) &&
    (!query || line.toLowerCase().includes(query)),
  )
})

const startIndex = computed(() => Math.max(0, Math.floor(scrollTop.value / LINE_HEIGHT) - BUFFER_ROWS))
const visibleCount = computed(() => Math.ceil(viewportHeight.value / LINE_HEIGHT) + BUFFER_ROWS * 2)
const visibleRows = computed(() => filtered.value
  .slice(startIndex.value, startIndex.value + visibleCount.value)
  .map((line, offset) => ({ line, index: startIndex.value + offset })))
const totalHeight = computed(() => filtered.value.length * LINE_HEIGHT)
const offsetY = computed(() => startIndex.value * LINE_HEIGHT)

const classify = (line: string) => /error|exception|traceback/i.test(line)
  ? 'error'
  : /warn/i.test(line)
    ? 'warn'
    : /success|done/i.test(line) ? 'success' : ''
</script>
