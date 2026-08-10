<template>
  <section class="result-workspace">
    <nav class="result-tabs">
      <button v-for="item in tabs" :key="item.value" :class="{active:tab===item.value}" :disabled="!item.available && !item.loading" @click="selectTab(item.value)">
        {{ item.label }}
        <span v-if="item.count" class="count-badge">{{ item.count }}</span>
        <span v-if="item.loading" class="tab-dot" />
      </button>
      <el-button text size="small" :loading="sotaLoading" @click="loadSota">🏆 SOTA 产物</el-button>
      <el-button text size="small" @click="$emit('download')">↓ 下载产物</el-button>
    </nav>
    <div class="result-body">
      <div v-if="tab==='factors'" class="factor-grid">
        <article v-for="factor in factors" :key="factor.name" class="factor-card">
          <header><h4>{{ factor.name }}</h4><span>因子</span></header>
          <p v-if="factor.description">{{ factor.description }}</p>
          <FormulaBlock v-if="factor.formula" :formula="factor.formula"/>
          <dl v-if="factor.variables&&Object.keys(factor.variables).length">
            <template v-for="(value,key) in factor.variables" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template>
          </dl>
        </article>
        <div v-if="!factors.length && !loadingStep" class="empty-result">当前轮次暂无因子结果</div>
      </div>
      <div v-else-if="tab==='code'" class="code-wrap">
        <header v-if="codes.length">
          <div><b>{{ currentCode?.name }}</b><span v-if="currentCode?.target"> · {{ currentCode.target }}</span><small> · {{ codeLines }} 行</small></div>
          <div>
            <el-select v-if="codes.length>1" v-model="codeIndex" size="small">
              <el-option v-for="(file,index) in codes" :key="`${file.target}-${file.name}-${index}`" :label="file.target||file.name" :value="index"/>
            </el-select>
            <el-button text size="small" @click="copyCode">复制</el-button>
            <el-button text size="small" @click="downloadCurrent">下载</el-button>
          </div>
        </header>
        <pre v-if="currentCode"><code>{{ currentCode.content }}</code></pre>
        <div v-else-if="loadingStep==='coding'" class="empty-result step-loading">
          <span class="inline-spinner" />
          <p>正在生成因子代码…</p>
        </div>
        <div v-else class="empty-result">当前轮次暂无因子代码</div>
      </div>
      <div v-else-if="tab==='chart'" class="chart-wrap">
        <iframe v-if="chartUrl" class="center-chart-frame" :src="chartUrl" sandbox="allow-scripts"/>
        <div v-else-if="loadingStep==='backtest'" class="empty-result step-loading">
          <span class="inline-spinner" />
          <p>正在执行回测，生成收益曲线…<br><small>回测通常需要 1-3 分钟，请耐心等待</small></p>
        </div>
        <div v-else class="empty-result">当前轮次暂无收益曲线</div>
      </div>
      <div v-else class="conclusion-view">
        <section v-if="hasConclusion" class="conclusion-hero">
          <h4>📊 本轮最终结论</h4>
          <div class="conclusion-metrics"><article v-for="item in coreMetrics" :key="item.label"><small>{{ item.label }}</small><strong :class="item.tone">{{ formatMetric(item) }}</strong></article></div>
          <span v-if="feedback.decision!==null" class="decision-chip" :class="feedback.decision?'accepted':'rejected'">{{ feedback.decision?'✓ 采纳 · 进入下一轮':'✕ 拒绝 · 跳过' }}</span>
          <span v-else-if="loadingStep==='feedback'" class="decision-chip pending"><span class="inline-spinner sm" /> 评审进行中…</span>
          <div class="conclusion-sections"><article v-for="item in feedbackItems" :key="item.label"><small>{{ item.icon }} {{ item.label }}</small><p>{{ item.value }}</p></article></div>
        </section>
        <section v-if="feedback.newHypothesis" class="next-hypothesis"><h4>💡 下一轮新假设</h4><p>{{ feedback.newHypothesis }}</p></section>
        <div v-if="!hasConclusion && loadingStep!=='feedback'" class="empty-result">当前轮次暂无最终结论</div>
      </div>
    </div>
    <el-dialog v-model="sotaVisible" title="🏆 SOTA 产物" width="680px" destroy-on-close>
      <div v-if="sotaError" class="empty-result">{{ sotaError }}</div>
      <template v-else-if="sotaData">
        <div class="sota-section"><h5>📋 最优假设（{{ loopLabel(sotaData.sota_loop_id) }}）</h5><p class="sota-hypothesis">{{ sotaHypothesisText }}</p></div>
        <div class="sota-section"><h5>📊 回测指标</h5><div class="sota-metrics"><span v-for="(value,key) in sotaMetricList" :key="key" class="sota-metric"><small>{{ key }}</small><strong>{{ value }}</strong></span></div></div>
        <div class="sota-section"><h5>✅ 反馈决策</h5><p><el-tag :type="sotaDecision?'success':'danger'" size="small">{{ sotaDecision?'采纳':'拒绝' }}</el-tag> {{ sotaFeedbackReason }}</p></div>
        <div class="sota-section"><h5>🌟 因子代码（{{ sotaFactors.length }} 个）</h5><div v-for="factor in sotaFactors" :key="factor.name" class="sota-factor"><div class="sota-factor-head"><b>{{ factor.name }}</b><el-button text size="small" @click="copySotaCode(factor.code)">复制</el-button></div><p v-if="factor.description" class="sota-factor-desc">{{ factor.description }}</p><pre class="sota-code"><code>{{ factor.code }}</code></pre></div></div>
      </template>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import FormulaBlock from './FormulaBlock.vue'
import { fetchSota } from '../api'
import type { AgentStep, CodeFile, ChartRef, FactorItem, FeedbackSummary, MetricItem, ResultTab } from '../types'

const props = defineProps<{
  traceId: string
  factors: FactorItem[]
  codes: CodeFile[]
  chartRef: ChartRef | null
  chartHtml: string
  metrics: MetricItem[]
  feedback: FeedbackSummary
  currentStep?: AgentStep
}>()
defineEmits<{ download: [] }>()

const tab = ref<ResultTab>('factors')
const codeIndex = ref(0)
const userPinned = ref(false)

watch(() => props.codes, () => { codeIndex.value = 0 })

const currentCode = computed(() => props.codes[codeIndex.value])
const codeLines = computed(() => currentCode.value?.content.split('\n').length || 0)
const hasConclusion = computed(() => props.metrics.length > 0 || props.feedback.decision !== null || !!props.feedback.reason)

const chartUrl = computed(() => {
  if (props.chartRef) {
    const params = new URLSearchParams({ id: props.chartRef.trace_id })
    if (props.chartRef.loop_id != null) params.set('loop', String(props.chartRef.loop_id))
    return `/api/v2/trace/artifact?${params.toString()}`
  }
  if (props.chartHtml) {
    const blob = new Blob([props.chartHtml], { type: 'text/html' })
    return URL.createObjectURL(blob)
  }
  return ''
})

const stepTabMap: Record<string, ResultTab> = {
  hypothesis: 'factors',
  design: 'factors',
  coding: 'code',
  backtest: 'chart',
  feedback: 'conclusion',
}

const loadingStep = computed(() => props.currentStep)

const tabs = computed(() => [
  { label: '因子结果', value: 'factors' as ResultTab, count: props.factors.length, available: props.factors.length > 0, loading: props.currentStep === 'design' || props.currentStep === 'hypothesis' },
  { label: '因子代码', value: 'code' as ResultTab, count: props.codes.length, available: props.codes.length > 0, loading: props.currentStep === 'coding' },
  { label: '收益曲线', value: 'chart' as ResultTab, count: 0, available: !!chartUrl.value, loading: props.currentStep === 'backtest' },
  { label: '最终结论', value: 'conclusion' as ResultTab, count: 0, available: hasConclusion.value, loading: props.currentStep === 'feedback' },
])

watch(() => props.currentStep, (step, oldStep) => {
  if (step && step !== oldStep && !userPinned.value) {
    const target = stepTabMap[step]
    if (target) tab.value = target
  }
}, { immediate: true })

watch(() => props.feedback.decision, (decision) => {
  if (decision !== null && !userPinned.value) tab.value = 'conclusion'
})

function selectTab(value: ResultTab) {
  tab.value = value
  userPinned.value = true
}

const coreMetrics = computed(() => props.metrics.filter(item => ['IC', '年化收益', '最大回撤', '信息比率'].includes(item.label)).slice(0, 4))
const feedbackItems = computed(() => [
  { icon: '📌', label: '决定理由', value: props.feedback.reason },
  { icon: '🔍', label: '实验观察', value: props.feedback.observations },
  { icon: '📊', label: '假设评估', value: props.feedback.evaluation },
  { icon: '⚠', label: '异常信息', value: props.feedback.exception },
].filter(item => item.value))

function formatMetric(item: MetricItem) {
  if (item.rawValue == null) return item.value
  if (item.percent) return `${(item.rawValue * 100).toFixed(2)}%`
  return item.rawValue.toFixed(4)
}
async function copyCode() {
  if (!currentCode.value) return
  await navigator.clipboard.writeText(currentCode.value.content)
  ElMessage.success('代码已复制')
}
function downloadCurrent() {
  if (!currentCode.value) return
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([currentCode.value.content], { type: 'text/plain' }))
  link.download = currentCode.value.name
  link.click()
  URL.revokeObjectURL(link.href)
}

const numbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const loopLabel = (loop: number | null) => loop == null ? '—' : `第${numbers[loop] || loop + 1}轮`
const sotaVisible = ref(false), sotaLoading = ref(false), sotaData = ref<Record<string, any> | null>(null), sotaError = ref('')
const sotaHypothesisText = computed(() => sotaData.value?.sota_hypothesis?.hypothesis || sotaData.value?.sota_hypothesis?.concise_reason || '—')
const sotaDecision = computed(() => sotaData.value?.sota_feedback?.decision === true)
const sotaFeedbackReason = computed(() => sotaData.value?.sota_feedback?.reason || '')
const sotaMetricList = computed(() => {
  const m = sotaData.value?.sota_metrics || {}
  const labels: Record<string, string> = { IC: 'IC', '1day.excess_return_without_cost.annualized_return': '年化收益', '1day.excess_return_without_cost.max_drawdown': '最大回撤', '1day.excess_return_without_cost.information_ratio': '信息比率', '1day.excess_return_with_cost.annualized_return': '年化收益(扣费)', '1day.excess_return_with_cost.max_drawdown': '最大回撤(扣费)', '1day.excess_return_with_cost.information_ratio': '信息比率(扣费)' }
  const out: Record<string, string> = {}
  for (const [key, label] of Object.entries(labels)) {
    if (m[key] != null) {
      const v = Number(m[key])
      out[label] = label.includes('年化') || label.includes('回撤') ? `${(v * 100).toFixed(2)}%` : v.toFixed(4)
    }
  }
  return out
})
const sotaFactors = computed(() => Array.isArray(sotaData.value?.sota_factors) ? sotaData.value.sota_factors : [])
async function loadSota() {
  if (!props.traceId) return
  sotaLoading.value = true; sotaVisible.value = true; sotaError.value = ''; sotaData.value = null
  try { sotaData.value = await fetchSota(props.traceId) }
  catch (err) { sotaError.value = err instanceof Error ? err.message : '获取 SOTA 失败' }
  finally { sotaLoading.value = false }
}
async function copySotaCode(code: string) {
  if (!code) return
  await navigator.clipboard.writeText(code)
  ElMessage.success('代码已复制')
}
</script>
<style scoped>
.count-badge{display:inline-block;min-width:18px;margin-left:6px;padding:1px 6px;border-radius:9px;background:rgba(38,103,255,.12);color:#2857b2;font-size:11px;font-weight:600;line-height:1.5;text-align:center}
.result-tabs>button.active .count-badge{background:var(--ma-gold-dark,#b7842a);color:#fff}
.result-tabs>button:disabled .count-badge{opacity:.5}
.tab-dot{display:inline-block;width:7px;height:7px;margin-left:6px;border-radius:50%;background:var(--ma-warning);animation:dot-pulse 1.2s ease-in-out infinite}
@keyframes dot-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}
.step-loading{display:flex;flex-direction:column;align-items:center;gap:12px;color:var(--ma-gold-dark);font-size:13px}
.step-loading p{margin:0;text-align:center;line-height:1.7}
.step-loading small{color:var(--ma-muted);font-size:11px}
.inline-spinner{width:28px;height:28px;border:3px solid var(--ma-gold-soft);border-top-color:var(--ma-gold);border-radius:50%;animation:inline-spin .7s linear infinite}
.inline-spinner.sm{width:14px;height:14px;border-width:2px;vertical-align:middle;margin-right:5px}
@keyframes inline-spin{to{transform:rotate(360deg)}}
.decision-chip.pending{display:inline-flex;align-items:center;border-color:var(--ma-gold);background:var(--ma-gold-soft);color:var(--ma-gold-dark)}
.sota-section{margin-bottom:1.2em}
.sota-section h5{font-size:.95em;font-weight:700;color:#1c2b57;margin-bottom:.4em}
.sota-hypothesis{font-size:.92em;line-height:1.5;color:#333;white-space:pre-wrap}
.sota-metrics{display:flex;flex-wrap:wrap;gap:.8em}
.sota-metric{display:flex;flex-direction:column;padding:.5em .8em;border-radius:8px;background:rgba(38,103,255,.06);border:1px solid rgba(38,103,255,.15)}
.sota-metric small{font-size:.75em;color:#888}
.sota-metric strong{font-size:1.1em;color:#1c2b57}
.sota-factor{margin-bottom:.8em;border:1px solid #e0e6f5;border-radius:8px;overflow:hidden}
.sota-factor-head{display:flex;justify-content:space-between;align-items:center;padding:.4em .6em;background:rgba(38,103,255,.04)}
.sota-factor-desc{padding:.3em .6em;font-size:.85em;color:#666;margin:0}
.sota-code{margin:0;padding:.6em;max-height:200px;overflow:auto;font-size:.82em;background:#f5f7fa}
.sota-code code{font-family:'SF Mono','Fira Code',monospace}
</style>
