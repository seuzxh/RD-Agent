<template>
  <div class="live-lab">
    <section class="task-list">
      <h4>运行中的任务</h4>
      <el-table :data="runningTasks" size="small" v-loading="loading" @row-click="selectTask" :row-class-name="'clickable'">
        <el-table-column label="任务 ID" min-width="160">
          <template #default="{ row }"><strong>{{ formatName(row.id) }}</strong></template>
        </el-table-column>
        <el-table-column label="任务类型" width="110">
          <template #default="{ row }">
            <el-tag :type="scenarioType(row)" size="small">{{ scenarioLabel(row) }}</el-tag>
          </template>
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

        <!-- 5-stage collaboration flow -->
        <AgentFlow :experiments="filteredExperiments" :codes="codes" :active-step="activeStep" />

        <div class="detail-layout">
          <div class="detail-main">
            <!-- Result workspace: conclusion / factors / chart / code -->
            <ResultWorkspace
              :factors="factors"
              :codes="codes"
              :chart-url="chartUrl"
              :metrics="metrics"
              :feedback="feedback"
              @download="downloadResult"
            />
          </div>
          <MetricsPanel
            :metrics="metrics"
            :factors="factors"
            :hypothesis="hypothesis"
            :feedback="feedback"
            @download="downloadResult"
          />
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
      </template>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { fetchStrategyDetail, fetchCode, chartUrl as buildChartUrl } from './api'
import AgentFlow from './components/AgentFlow.vue'
import ResultWorkspace from './components/ResultWorkspace.vue'
import MetricsPanel from './components/MetricsPanel.vue'
import { buildFactors, buildMetrics, buildFeedback, buildHypothesis } from './livelab-model'
import type { CodeFile, FactorItem, FeedbackSummary, MetricItem } from './types'
import './livelab-detail.css'

const props = defineProps<{ strategies: any[] }>()
const loading = ref(false)
const selectedId = ref('')
const detailLoading = ref(false)
const detailError = ref('')
const selectedLoop = ref<number | null>(null)
const strategyDetail = ref<any>(null)
const pipelineNodes = ref<any[]>([])
const codes = ref<CodeFile[]>([])

// SSE event source for the selected strategy
let eventSource: EventSource | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null

// Show all strategies (running + completed) so a strategy that just finished
// stays listed with its updated status tag instead of vanishing from the tab.
// Props are refreshed periodically by App.vue, so the status stays current.
const runningTasks = computed(() => props.strategies)

// Pipeline stages from ResearchDB pipeline_nodes
const pipelineStages = computed(() => {
  // Filter to the selected loop so each round shows only its own progression.
  // Before a loop is selected (selectedLoop == null), fall back to all nodes.
  const loop = selectedLoop.value
  const nodes = loop == null
    ? pipelineNodes.value
    : pipelineNodes.value.filter((n: any) => n.loop_id === loop)
  const steps = nodes.map((n: any) => n.step_name)
  const defs = ['direct_exp_gen', 'coding', 'running', 'feedback', 'record']
  let activeFound = false
  return defs.map(name => {
    const done = steps.includes(name)
    const state = done ? 'done' : !activeFound ? (activeFound = true, 'active') : 'idle'
    return { name, state }
  })
})

// The pipeline step currently in progress (first not-done step), fed to AgentFlow
// so the corresponding agent shows "进行中" instead of "待启动" while it runs.
const activeStep = computed(() => {
  const active = pipelineStages.value.find(s => s.state === 'active')
  return active ? active.name : ''
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

// Selected experiment for the current loop (for metrics/feedback/hypothesis)
const selectedExperiment = computed<Record<string, any> | undefined>(() => {
  const exps = filteredExperiments.value
  if (!exps.length) return undefined
  return exps[exps.length - 1]
})

// Factors read from SQLite, filtered by round_number = selected loop
const factors = computed<FactorItem[]>(() => {
  const raw = strategyDetail.value?.factors || []
  return buildFactors(raw, selectedLoop.value ?? -1)
})

// Metrics from the selected experiment (SQLite)
const metrics = computed<MetricItem[]>(() => buildMetrics(selectedExperiment.value))

// Feedback from SQLite experiment fields (decision / decision_reason / observations)
const feedback = computed<FeedbackSummary>(() => buildFeedback(selectedExperiment.value))

// Hypothesis summary for MetricsPanel
const hypothesis = computed<Record<string, unknown> | null>(() => buildHypothesis(selectedExperiment.value))

// chartUrl for the selected loop's return-curve plotly HTML (ticket 04).
// Empty when the selected loop has no chart yet, so the chart tab shows an
// empty state instead of a broken iframe. The guard checks any experiment in
// the loop (the /chart endpoint serves the first chart-bearing one).
const chartUrl = computed(() => {
  if (!selectedId.value || selectedLoop.value == null) return ''
  const hasChart = filteredExperiments.value.some((e: any) => e.chart_path)
  if (!hasChart) return ''
  return buildChartUrl(selectedId.value, selectedLoop.value)
})

// Token usage from pipeline nodes
const promptTokens = computed(() => pipelineNodes.value.reduce((s: number, n: any) => s + (n.prompt_tokens || 0), 0))
const completionTokens = computed(() => pipelineNodes.value.reduce((s: number, n: any) => s + (n.completion_tokens || 0), 0))
const callCount = computed(() => pipelineNodes.value.reduce((s: number, n: any) => s + (n.call_count || 0), 0))
const totalTokens = computed(() => promptTokens.value + completionTokens.value)

function formatName(s: string) { return (s || '').split('/').pop() || s || '' }

// 任务类型标签：按 scenario 区分 fin_factor / fin_model / fin_quant / fin_factor_report，
// scenario 缺失时回退到 id 前缀（id 形如 "<scenario>/<trace_name>"）。
const SCENARIO_LABELS: Record<string, string> = {
  'Finance Data Building': '因子挖掘',
  'Finance Model Implementation': '模型实现',
  'Finance Whole Pipeline': '量化全过程',
  'Finance Data Building (Reports)': 'PDF因子挖掘',
}
const SCENARIO_TYPES: Record<string, string> = {
  'Finance Data Building': 'primary',
  'Finance Model Implementation': 'success',
  'Finance Whole Pipeline': 'warning',
  'Finance Data Building (Reports)': 'info',
}
function scenarioOf(row: any): string {
  return row.scenario || (String(row.id || '').split('/')[0])
}
function scenarioLabel(row: any): string { return SCENARIO_LABELS[scenarioOf(row)] || '其他' }
function scenarioType(row: any): string { return SCENARIO_TYPES[scenarioOf(row)] || 'info' }
function formatTime(ts: string) { return ts ? ts.slice(0, 19) : '' }
function statusType(s: string) { return s === 'running' ? 'warning' : s === 'completed' ? 'success' : 'info' }
function statusLabel(s: string) { return s === 'running' ? '运行中' : s === 'completed' ? '已完成' : '待处理' }

function downloadResult() {
  // Leave the download handling to the parent in ticket 04; no-op for ticket 03.
}

// Refetch factor code via /code when strategy or loop changes
async function reloadCodes() {
  codes.value = []
  if (!selectedId.value) return
  const names = factors.value.map(f => f.name).filter(Boolean)
  if (!names.length) return
  try {
    const loaded = await Promise.all(
      names.map(async name => {
        try {
          const res = await fetchCode(selectedId.value, name, 'factor')
          return { name: res.name, content: res.code }
        } catch { return null }
      }),
    )
    codes.value = loaded.filter((c): c is CodeFile => !!c && !!c.content)
  } catch { /* keep empty */ }
}

watch([selectedId, selectedLoop], () => reloadCodes())

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
    const [detail, nodes] = await Promise.all([
      fetchStrategyDetail(id),
      fetch(`/api/strategies/${encodeURIComponent(id)}/pipeline`).then(r => r.json()),
    ])
    strategyDetail.value = detail
    pipelineNodes.value = Array.isArray(nodes) ? nodes : []
    await reloadCodes()
  } catch { /* keep existing data */ }
}

async function selectTask(row: any) {
  selectedId.value = row.id
  selectedLoop.value = null
  detailLoading.value = true; detailError.value = ''
  strategyDetail.value = null; pipelineNodes.value = []; codes.value = []
  try {
    await reloadDetail(row.id)
    // Default to the latest round so the per-loop detail view is populated immediately
    const loops = availableLoops.value
    selectedLoop.value = loops.length ? loops[loops.length - 1] : null
    subscribeSse(row.id)
    // Fallback polling for strategies that are not in ResearchDB
    refreshTimer = setInterval(() => reloadDetail(row.id), 10000)
  } catch (e: any) {
    detailError.value = e.message
  } finally {
    detailLoading.value = false
  }
}

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
.detail-layout { display: flex; gap: 16px; align-items: flex-start; }
.detail-main { flex: 1; min-width: 0; }
.token-grid { display: flex; gap: 16px; }
.token-item { text-align: center; padding: 8px 16px; background: #f5f7fa; border-radius: 4px; }
.token-item small { display: block; font-size: 11px; color: #909399; }
.token-item strong { font-size: 14px; }
.error { color: #f56c6c; padding: 20px; }
:deep(.clickable) { cursor: pointer; }
@media (max-width: 900px) {
  .detail-layout { flex-direction: column; }
  .metrics-panel { width: 100%; border-left: 0; border-top: 1px solid var(--ma-line); }
}
</style>