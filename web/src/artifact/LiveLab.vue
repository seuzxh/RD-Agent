<template>
  <div class="live-lab">
    <section class="task-list">
      <h4>运行中的任务</h4>
      <el-table :data="runningTasks" size="small" v-loading="loading" @row-click="selectTask" :row-class-name="'clickable'">
        <el-table-column label="任务 ID" min-width="160">
          <template #default="{ row }"><strong>{{ formatName(row.id) }}</strong></template>
        </el-table-column>
        <el-table-column label="描述" min-width="200">
          <template #default="{ row }"><span class="desc">{{ row.description || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }"><span>{{ formatTime(row.created_at || row.timestamp) }}</span></template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="selectedId" class="task-detail">
      <h4>任务详情: {{ formatName(selectedId) }}</h4>
      <div v-if="taskLoading" v-loading="taskLoading" style="height:100px"></div>
      <div v-else-if="taskError" class="error">{{ taskError }}</div>
      <template v-else>
        <!-- Pipeline Stages -->
        <div class="pipeline">
          <div v-for="(stage, i) in pipelineStages" :key="stage.name" class="pipeline-item" :class="stage.state">
            <span>{{ stage.state==='done'?'✓':i+1 }}</span>{{ stage.name }}<i v-if="i<pipelineStages.length-1">→</i>
          </div>
        </div>
        <!-- Hypothesis -->
        <div v-if="hypothesis" class="detail-section">
          <h5>研究假设</h5>
          <p>{{ hypothesisText }}</p>
          <p v-if="hypothesis.reason" class="reason"><b>理由：</b>{{ hypothesis.reason }}</p>
        </div>
        <!-- Tasks (Factors) -->
        <div v-if="factors.length" class="detail-section">
          <h5>因子任务 ({{ factors.length }})</h5>
          <div v-for="f in factors" :key="f.name" class="factor-item">
            <b>{{ f.name }}</b><p>{{ f.description }}</p>
          </div>
        </div>
        <!-- Metrics -->
        <div v-if="metricKeys.length" class="detail-section">
          <h5>回测指标</h5>
          <div class="metric-grid">
            <div v-for="k in metricKeys" :key="k" class="metric-item">
              <small>{{ k }}</small><strong>{{ metricValues[k] }}</strong>
            </div>
          </div>
        </div>
        <!-- Feedback -->
        <div v-if="feedbackText" class="detail-section">
          <h5>反馈</h5>
          <p>{{ feedbackText }}</p>
        </div>
        <!-- Raw messages -->
        <div class="detail-section">
          <h5>消息日志 ({{ taskMessages.length }})</h5>
          <div class="message-list">
            <div v-for="(msg, i) in taskMessages" :key="i" class="message-item">
              <span class="msg-tag">{{ msg.tag }}</span>
              <span class="msg-time">{{ formatTime(msg.timestamp) }}</span>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{ strategies: any[] }>()
const loading = ref(false)
const tasks = ref<any[]>([])
const selectedId = ref('')
const taskLoading = ref(false)
const taskError = ref('')
const taskMessages = ref<any[]>([])

const runningTasks = computed(() => {
  const running = props.strategies.filter(s => s.status === 'running' || s.status === 'pending')
  return running.length ? running : tasks.value
})

// Parse messages into pipeline stages
const pipelineStages = computed(() => {
  const tags = new Set(taskMessages.value.map((m: any) => m.tag))
  const defs = [
    ['研究', ['research.hypothesis', 'research.tasks']],
    ['编码', ['evolving.codes']],
    ['回测', ['feedback.metric']],
    ['反馈', ['feedback.hypothesis_feedback']],
  ]
  let activeFound = false
  return defs.map(([name, required]) => {
    const done = (required as string[]).some(tag => tags.has(tag))
    const state = done ? 'done' : !activeFound ? (activeFound = true, 'active') : 'idle'
    return { name: name as string, state }
  })
})

const hypothesis = computed(() => {
  const msg = taskMessages.value.find((m: any) => m.tag === 'research.hypothesis')
  return msg?.content || null
})
const hypothesisText = computed(() => {
  if (!hypothesis.value) return ''
  return String(hypothesis.value.hypothesis || hypothesis.value.concise_observation || '')
})
const factors = computed(() => {
  const msg = taskMessages.value.find((m: any) => m.tag === 'research.tasks')
  return msg?.content || []
})
const metricValues = computed(() => {
  const msg = taskMessages.value.find((m: any) => m.tag === 'feedback.metric')
  return (msg?.content?.result || msg?.content?.metrics || msg?.content || {}) as Record<string, any>
})
const metricKeys = computed(() => Object.keys(metricValues.value).slice(0, 8))
const feedbackText = computed(() => {
  const msg = taskMessages.value.find((m: any) => m.tag === 'feedback.hypothesis_feedback')
  return msg?.content?.observations || msg?.content?.reason || ''
})

function formatName(s: string) { return s.split('/').pop() || s }
function formatTime(ts: string) { return ts ? ts.slice(0, 19) : '' }
function statusType(s: string) { return s === 'running' ? 'warning' : s === 'completed' ? 'success' : 'info' }
function statusLabel(s: string) { return s === 'running' ? '运行中' : s === 'completed' ? '已完成' : '待处理' }

async function selectTask(row: any) {
  selectedId.value = row.id
  taskLoading.value = true; taskError.value = ''; taskMessages.value = []
  try {
    const resp = await fetch('/trace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: row.name || row.id, all: true, cursor: 0 }),
    })
    if (!resp.ok) throw new Error('Not found')
    const data = await resp.json()
    taskMessages.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    taskError.value = e.message
  } finally {
    taskLoading.value = false
  }
}

async function loadLive() {
  try {
    const resp = await fetch('/api/live')
    const data = await resp.json()
    tasks.value = data.tasks || []
  } catch { /* ignore */ }
}

onMounted(() => { loadLive(); timer = setInterval(loadLive, 5000) })
onUnmounted(() => clearInterval(timer))
let timer: any = null
</script>
<style scoped>
.live-lab { padding: 8px 0; }
h4 { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
h5 { font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #409eff; }
.task-detail { margin-top: 20px; }
.detail-section { margin-bottom: 16px; padding: 12px; background: #fafafa; border-radius: 6px; }
.desc { font-size: 13px; color: #606266; }
.pipeline { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.pipeline-item { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 4px; font-size: 13px; background: #f0f0f0; color: #999; }
.pipeline-item.done { background: #e6f7e6; color: #28a745; }
.pipeline-item.active { background: #e6f0ff; color: #409eff; }
.pipeline-item i { margin-left: 4px; color: #ccc; }
.reason { font-size: 12px; color: #909399; margin-top: 4px; }
.factor-item { margin-bottom: 8px; }
.factor-item b { font-size: 13px; }
.factor-item p { font-size: 12px; color: #606266; margin: 2px 0 0 8px; }
.metric-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.metric-item { flex: 1; min-width: 80px; text-align: center; padding: 8px; background: #f5f7fa; border-radius: 4px; }
.metric-item small { display: block; font-size: 11px; color: #909399; }
.metric-item strong { font-size: 14px; }
.message-list { max-height: 300px; overflow-y: auto; }
.message-item { padding: 4px 8px; border-bottom: 1px solid #f0f0f0; font-size: 12px; }
.msg-tag { color: #409eff; font-weight: 600; margin-right: 8px; }
.msg-time { color: #999; font-size: 11px; }
.error { color: #f56c6c; padding: 20px; }
:deep(.clickable) { cursor: pointer; }
</style>