<template>
  <section class="log-panel">
    <header class="log-header">
      <span class="log-title">📄 实时日志</span>
      <el-tag v-if="running" type="warning" size="small">● 运行中</el-tag>
      <el-tag v-else-if="failed" type="danger" size="small">✕ 已失败</el-tag>
      <el-tag v-else type="info" size="small">已结束</el-tag>
      <div class="log-actions">
        <el-button text size="small" @click="clearLog">清空</el-button>
        <el-button text size="small" @click="toBottom">底部</el-button>
      </div>
    </header>
    <div ref="logBox" class="log-body" @scroll="onScroll">
      <p v-for="(line, i) in lines" :key="i" class="log-line">{{ line }}</p>
      <div v-if="!lines.length" class="empty-log">暂无日志输出（等待任务写入 stdout …）</div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { fetchStdoutRange } from '../../services/rdagent-api'

const props = defineProps<{ strategyId: string; running?: boolean; failed?: boolean }>()

const lines = ref<string[]>([])
const logBox = ref<HTMLElement | null>(null)
let offset = 0
let buffer = ''
let autoScroll = true
let timer: ReturnType<typeof setInterval> | null = null
let aborter: AbortController | null = null

const MAX_LINES = 500
const POLL_MS = 2000

function scrollToBottom() {
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
}

function onScroll() {
  if (!logBox.value) return
  const el = logBox.value
  autoScroll = el.scrollHeight - el.scrollTop - el.clientHeight < 40
}

function append(text: string) {
  if (!text) return
  buffer += text
  const parts = buffer.split('\n')
  buffer = parts.pop() ?? ''
  // Build a plain array and assign once — per-item push() into a reactive array
  // (and per-line shift()) was O(n²) on large historical logs (e.g. a 1MB
  // running-task stdout), which froze the main thread and blocked page clicks.
  const merged = lines.value.concat(parts)
  if (merged.length > MAX_LINES) merged.splice(0, merged.length - MAX_LINES)
  lines.value = merged
  if (autoScroll) nextTick(scrollToBottom)
}

async function poll() {
  if (!props.strategyId) return
  aborter?.abort()
  aborter = new AbortController()
  try {
    const { text, nextOffset } = await fetchStdoutRange(props.strategyId, offset, aborter.signal)
    offset = nextOffset
    append(text)
  } catch {
    // transient (e.g. file not yet created / 404); retry on next poll
  }
}

function start() {
  stop()
  offset = 0
  lines.value = []
  buffer = ''
  poll()
  timer = setInterval(poll, POLL_MS)
}

function stop() {
  if (timer) { clearInterval(timer); timer = null }
  aborter?.abort(); aborter = null
}

function clearLog() { lines.value = []; buffer = ''; offset = 0 }
function toBottom() { autoScroll = true; scrollToBottom() }

watch(() => props.strategyId, (id) => { if (id) start(); else stop() }, { immediate: true })
onUnmounted(stop)
</script>
<style scoped>
.log-panel { border: 1px solid var(--ma-line, #e4e7ed); border-radius: 6px; overflow: hidden; }
.log-header { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #fafafa; border-bottom: 1px solid var(--ma-line, #e4e7ed); }
.log-title { font-size: 13px; font-weight: 600; color: #303133; }
.log-actions { margin-left: auto; display: flex; gap: 4px; }
.log-body { height: 320px; overflow: auto; padding: 8px 10px; background: #1e1e1e; font-family: 'Consolas', 'Menlo', monospace; font-size: 12px; line-height: 1.5; }
.log-line { margin: 0; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; }
.empty-log { color: #6a737d; padding: 12px 0; text-align: center; }
</style>