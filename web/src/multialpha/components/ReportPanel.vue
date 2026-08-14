<template>
  <div class="report-panel" v-loading="loading">
    <div v-if="error" class="error-state">
      <p>{{ error }}</p>
      <el-button size="small" @click="$emit('retry')">重试</el-button>
    </div>
    <template v-else-if="data">
      <section class="report-metrics">
        <div v-for="item in summaryMetrics" :key="item.label" class="metric-card">
          <small>{{ item.label }}</small>
          <strong>{{ item.value }}</strong>
        </div>
      </section>
      <section class="report-chart">
        <h4>指标趋势</h4>
        <div ref="trendChartRef" style="height:300px"></div>
      </section>
      <section class="report-actions">
        <el-button size="small" @click="downloadCsv">下载 CSV</el-button>
      </section>
    </template>
    <div v-else-if="!loading" class="empty-state">暂无报告数据</div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { fetchStrategyReport } from '../../services/research-api'

const props = defineProps<{ strategyId: string }>()
defineEmits<{ retry: [] }>()

const loading = ref(false)
const error = ref('')
const data = ref<Record<string, any> | null>(null)
const trendChartRef = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null

const summaryMetrics = computed(() => {
  const exps: any[] = data.value?.experiments || []
  const latest = exps[exps.length - 1] || {}
  return [
    { label: 'IC', value: latest.ic?.toFixed(4) ?? '—' },
    { label: 'ICIR', value: latest.icir?.toFixed(4) ?? '—' },
    { label: '年化收益', value: latest.annualized_return != null ? `${(latest.annualized_return * 100).toFixed(2)}%` : '—' },
    { label: '最大回撤', value: latest.max_drawdown != null ? `${(latest.max_drawdown * 100).toFixed(2)}%` : '—' },
    { label: '信息比率', value: latest.information_ratio?.toFixed(4) ?? '—' },
  ]
})

async function load() {
  loading.value = true; error.value = ''
  try { data.value = await fetchStrategyReport(props.strategyId) } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

function downloadCsv() {
  const exps: any[] = data.value?.experiments || []
  if (!exps.length) return
  const keys = ['loop_id', 'type', 'ic', 'icir', 'annualized_return', 'max_drawdown', 'information_ratio', 'decision']
  const csv = [keys.join(','), ...exps.map(r => keys.map(k => r[k] ?? '').join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'report.csv'
  link.click(); URL.revokeObjectURL(link.href)
}

watch(() => props.strategyId, () => load())
onMounted(() => load())

watch([data, trendChartRef], () => {
  if (!trendChartRef.value || !data.value) return
  if (!trendChart) trendChart = echarts.init(trendChartRef.value)
  const exps: any[] = data.value.experiments || []
  const rounds = exps.map((r: any) => `#${r.loop_id}`)
  const icData = exps.map((r: any) => r.ic ?? null)
  const icirData = exps.map((r: any) => r.icir ?? null)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['IC', 'ICIR'], bottom: 0 },
    xAxis: { type: 'category', data: rounds },
    yAxis: { type: 'value' },
    series: [
      { name: 'IC', type: 'line', data: icData, connectNulls: true, smooth: true },
      { name: 'ICIR', type: 'line', data: icirData, connectNulls: true, smooth: true },
    ],
    grid: { left: 40, right: 20, top: 20, bottom: 40 },
  })
}, { deep: true })

onUnmounted(() => trendChart?.dispose())
</script>
<style scoped>
.report-panel { padding: 16px; }
.report-metrics { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.metric-card { flex: 1; min-width: 120px; background: #f5f7fa; border-radius: 8px; padding: 16px; text-align: center; }
.metric-card small { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.metric-card strong { font-size: 20px; color: #303133; }
.report-chart { margin-bottom: 20px; }
.report-chart h4 { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
.report-actions { text-align: right; }
.error-state, .empty-state { text-align: center; padding: 40px; color: #909399; }
</style>