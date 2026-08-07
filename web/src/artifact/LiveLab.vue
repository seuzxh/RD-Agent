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
      <div v-if="detailLoading" v-loading="detailLoading" style="height:100px"></div>
      <div v-else-if="detailError" class="error">{{ detailError }}</div>
      <template v-else>
        <!-- Loop Switcher -->
        <div class="loop-switcher">
          <el-tag
            v-for="l in availableLoops"
            :key="l"
            :type="selectedLoop === l ? 'primary' : 'info'"
            size="small"
            style="cursor:pointer"
            @click="selectedLoop = l"
          >第 {{ l+1 }} 轮</el-tag>
        </div>

        <!-- Pipeline Stages from ResearchDB -->
        <div class="pipeline">
          <div v-for="(stage, i) in pipelineStages" :key="stage.name" class="pipeline-item" :class="stage.state">
            <span>{{ stage.state==='done'?'✓':i+1 }}</span>{{ stage.name }}<i v-if="i<pipelineStages.length-1">→</i>
          </div>
        </div>

        <!-- Experiments from ResearchDB -->
        <div v-if="experiments.length" class="detail-section">
          <h5>实验历史</h5>
          <el-table :data="filteredExperiments" size="small" max-height="200">
            <el-table-column prop="loop_id" label="轮次" width="60"/>
            <el-table-column prop="type" label="类型" width="80"/>
            <el-table-column prop="hypothesis_text" label="假设" min-width="200" show-overflow-tooltip/>
            <el-table-column label="IC" width="80">
              <template #default="{ row }">{{ row.ic?.toFixed(4) ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="决策" width="70">
              <template #default="{ row }"><el-tag :type="row.decision?'success':'danger'" size="small">{{ row.decision?'采纳':'拒绝' }}</el-tag></template>
            </el-table-column>
          </el-table>
        </div>

        <!-- Factors from ResearchDB -->
        <div v-if="filteredFactors.length" class="detail-section">
          <h5>因子 ({{ filteredFactors.length }})</h5>
          <el-table :data="filteredFactors" size="small">
            <el-table-column prop="name" label="因子名" min-width="140"/>
            <el-table-column label="IC" width="80">
              <template #default="{ row }">{{ row.ic?.toFixed(4) ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="ICIR" width="80">
              <template #default="{ row }">{{ row.icir?.toFixed(4) ?? '—' }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="70"/>
          </el-table>
        </div>

        <!-- Metrics from ResearchDB -->
        <div v-if="metricKeys.length" class="detail-section">
          <h5>回测指标</h5>
          <div class="metric-grid">
            <div v-for="k in metricKeys" :key="k" class="metric-item">
              <small>{{ k }}</small><strong>{{ metricValues[k] }}</strong>
            </div>
          </div>
        </div>

        <!-- Token Dashboard from pipeline nodes -->
        <div v-if="totalTokens > 0" class="detail-section">
          <h5>Token 用量</h5>
          <div class="token-grid">
            <div class="token-item"><small>Prompt</small><strong>{{ promptTokens }}</strong></div>
            <div class="token-item"><small>Completion</small><strong>{{ completionTokens }}</strong></div>
            <div class="token-item"><small>总调用</small><strong>{{ callCount }}</strong></div>
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
import { fetchLive, fetchStrategyMessages, fetchStrategyDetail } from './api'

const props = defineProps<{ strategies: any[] }>()
const loading = ref(false)
const tasks = ref<any[]>([])
const selectedId = ref('')
const detailLoading = ref(false)
const detailError = ref('')
const selectedLoop = ref<number | null>(null)
const taskMessages = ref<any[]>([])
const strategyDetail = ref<any>(null)
const pipelineNodes = ref<any[]>([])

// SSE event source for the selected strategy
let eventSource: EventSource | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null

const runningTasks = computed(() => {
  const running = props.strategies.filter(s => s.status === 'running' || s.status === 'pending')
  return running.length ? running : tasks.value
})

// Pipeline stages from ResearchDB pipeline_nodes
const pipelineStages = computed(() => {
  const steps = pipelineNodes.value.map((n: any) => n.step_name)
  const defs = ['direct_exp_gen', 'coding', 'running', 'feedback', 'record']
  let activeFound = false
  return defs.map(name => {
    const done = steps.includes(name)
    const state = done ? 'done' : !activeFound ? (activeFound = true, 'active') : 'idle'
    return { name, state }
  })
})

// Available loops from experiments
const availableLoops = computed<number[]>(() => {
  const exps: any[] = strategyDetail.value?.experiments || []
  return [...new Set<number>(exps.map((e: any) => e.loop_id as number))].sort((a, b) => a - b)
})

// Experiments from ResearchDB
const experiments = computed(() => strategyDetail.value?.experiments || [])

// Filter experiments by selected loop
const filteredExperiments = computed(() => {
  if (selectedLoop.value == null) return experiments.value
  return experiments.value.filter((e: any) => e.loop_id === selectedLoop.value)
})

// Factors from ResearchDB
const factors = computed(() => strategyDetail.value?.factors || [])

// Filter factors by selected loop (factors carry round_number = loop_id)
const filteredFactors = computed(() => {
  if (selectedLoop.value == null) return factors.value
  return factors.value.filter((f: any) => f.round_number === selectedLoop.value)
})

// Metrics from experiments
const metricValues = computed(() => {
  const exps = experiments.value
  if (!exps.length) return {}
  // Latest experiment by selected loop or overall
  const target = selectedLoop.value != null
    ? exps.find((e: any) => e.loop_id === selectedLoop.value)
    : exps[exps.length - 1]
  if (!target) return {}
  const m: Record<string, any> = {}
  if (target.ic != null) m['IC'] = target.ic.toFixed(4)
  if (target.icir != null) m['ICIR'] = target.icir.toFixed(4)
  if (target.annualized_return != null) m['年化收益'] = `${(Math.abs(target.annualized_return) * 100).toFixed(2)}%`
  if (target.max_drawdown != null) m['最大回撤'] = `${(Math.abs(target.max_drawdown) * 100).toFixed(2)}%`
  if (target.information_ratio != null) m['信息比率'] = target.information_ratio.toFixed(4)
  return m
})
const metricKeys = computed(() => Object.keys(metricValues.value))

// Token usage from pipeline nodes
const promptTokens = computed(() => pipelineNodes.value.reduce((s: number, n: any) => s + (n.prompt_tokens || 0), 0))
const completionTokens = computed(() => pipelineNodes.value.reduce((s: number, n: any) => s + (n.completion_tokens || 0), 0))
const callCount = computed(() => pipelineNodes.value.reduce((s: number, n: any) => s + (n.call_count || 0), 0))
const totalTokens = computed(() => promptTokens.value + completionTokens.value)

// Feedback from messages
const feedbackText = computed(() => {
  const msg = taskMessages.value.find((m: any) => m.tag === 'feedback.hypothesis_feedback')
  return msg?.content?.observations || msg?.content?.reason || ''
})

function formatName(s: string) { return (s || '').split('/').pop() || s || '' }
function formatTime(ts: string) { return ts ? ts.slice(0, 19) : '' }
function statusType(s: string) { return s === 'running' ? 'warning' : s === 'completed' ? 'success' : 'info' }
function statusLabel(s: string) { return s === 'running' ? '运行中' : s === 'completed' ? '已完成' : '待处理' }

function subscribeSse(strategyId: string) {
  unsubscribeSse()
  eventSource = new EventSource(`/api/strategies/${encodeURIComponent(strategyId)}/events`)
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'node_update' || data.type === 'metric_update' || data.type === 'strategy_status') {
        reloadDetail(strategyId)
      }
    } catch { /* ignore parse errors */ }
  }
  eventSource.onerror = () => {
    setTimeout(() => subscribeSse(strategyId), 3000)
  }
}

function unsubscribeSse() {
  if (eventSource) { eventSource.close(); eventSource = null }
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}

async function reloadDetail(id: string) {
  try {
    const [detail, msgs, nodes] = await Promise.all([
      fetchStrategyDetail(id),
      fetchStrategyMessages(id),
      fetch(`/api/strategies/${encodeURIComponent(id)}/pipeline`).then(r => r.json()),
    ])
    strategyDetail.value = detail
    taskMessages.value = msgs.messages || []
    pipelineNodes.value = Array.isArray(nodes) ? nodes : []
  } catch { /* keep existing data */ }
}

async function selectTask(row: any) {
  selectedId.value = row.id
  selectedLoop.value = null
  detailLoading.value = true; detailError.value = ''
  strategyDetail.value = null; taskMessages.value = []; pipelineNodes.value = []
  try {
    await reloadDetail(row.id)
    subscribeSse(row.id)
    // Fallback polling for strategies that are not in ResearchDB
    refreshTimer = setInterval(() => reloadDetail(row.id), 10000)
  } catch (e: any) {
    detailError.value = e.message
  } finally {
    detailLoading.value = false
  }
}

async function loadLive() {
  try {
    const data = await fetchLive()
    tasks.value = data.tasks || []
  } catch { /* ignore */ }
}

onMounted(() => { loadLive() })
onUnmounted(() => { unsubscribeSse() })
</script>
<style scoped>
.live-lab { padding: 8px 0; }
h4 { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
h5 { font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #409eff; }
.task-detail { margin-top: 20px; }
.detail-section { margin-bottom: 16px; padding: 12px; background: #fafafa; border-radius: 6px; }
.desc { font-size: 13px; color: #606266; }
.pipeline { display: flex; gap: 4px; margin-bottom: 12px; flex-wrap: wrap; }
.pipeline-item { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 4px; font-size: 13px; background: #f0f0f0; color: #999; }
.pipeline-item.done { background: #e6f7e6; color: #28a745; }
.pipeline-item.active { background: #e6f0ff; color: #409eff; }
.pipeline-item i { margin-left: 4px; color: #ccc; }
.loop-switcher { display: flex; gap: 6px; margin-bottom: 12px; }
.reason { font-size: 12px; color: #909399; margin-top: 4px; }
.metric-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.metric-item { flex: 1; min-width: 80px; text-align: center; padding: 8px; background: #f5f7fa; border-radius: 4px; }
.metric-item small { display: block; font-size: 11px; color: #909399; }
.metric-item strong { font-size: 14px; }
.token-grid { display: flex; gap: 16px; }
.token-item { text-align: center; padding: 8px 16px; background: #f5f7fa; border-radius: 4px; }
.token-item small { display: block; font-size: 11px; color: #909399; }
.token-item strong { font-size: 14px; }
.message-list { max-height: 300px; overflow-y: auto; }
.message-item { padding: 4px 8px; border-bottom: 1px solid #f0f0f0; font-size: 12px; }
.msg-tag { color: #409eff; font-weight: 600; margin-right: 8px; }
.msg-time { color: #999; font-size: 11px; }
.error { color: #f56c6c; padding: 20px; }
:deep(.clickable) { cursor: pointer; }
</style>