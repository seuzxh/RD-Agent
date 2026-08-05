<template>
  <div class="strategy-dashboard" v-loading="loading">
    <div v-if="error" class="error-state">
      <p>{{ error }}</p>
      <el-button size="small" @click="$emit('retry')">重试</el-button>
    </div>
    <template v-else-if="data">
      <section class="dashboard-header">
        <div class="stat-cards">
          <div class="stat-card"><small>总轮次</small><strong>{{ data.total_rounds || 0 }}</strong></div>
          <div class="stat-card"><small>因子数</small><strong>{{ factorCount }}</strong></div>
          <div class="stat-card"><small>模型数</small><strong>{{ modelCount }}</strong></div>
        </div>
      </section>
      <section class="dashboard-chart">
        <h4>指标趋势</h4>
        <div ref="chartRef" style="height:300px"></div>
      </section>
      <section class="dashboard-hypotheses">
        <h4>假设历史</h4>
        <el-table :data="hypotheses" size="small" max-height="300">
          <el-table-column prop="round" label="轮次" width="60"/>
          <el-table-column prop="text" label="假设" min-width="200"/>
          <el-table-column prop="decision" label="决策" width="80">
            <template #default="{ row }"><el-tag :type="row.decision?'success':'danger'" size="small">{{ row.decision?'采纳':'拒绝' }}</el-tag></template>
          </el-table-column>
        </el-table>
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { fetchStrategy, fetchStrategyFactors, fetchStrategyModels } from '../../services/research-api'

const props = defineProps<{ strategyId: string }>()
defineEmits<{ retry: [] }>()

const loading = ref(false)
const error = ref('')
const data = ref<Record<string, any> | null>(null)
const factors = ref<any[]>([])
const models = ref<any[]>([])
const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const factorCount = computed(() => factors.value.length)
const modelCount = computed(() => models.value.length)
const hypotheses = computed(() => {
  const exps: any[] = data.value?.experiments || []
  return exps.map((e: any) => ({ round: e.loop_id || e.round_number, text: (e.hypothesis_text || '—').slice(0, 80), decision: e.decision }))
})

async function load() {
  loading.value = true; error.value = ''
  try {
    const [strategy, f, m] = await Promise.all([
      fetchStrategy(props.strategyId),
      fetchStrategyFactors(props.strategyId),
      fetchStrategyModels(props.strategyId),
    ])
    data.value = strategy
    factors.value = f
    models.value = m
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

watch(() => props.strategyId, () => load())
onMounted(() => load())

watch([data, chartRef], () => {
  if (!chartRef.value || !data.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const exps: any[] = data.value.experiments || []
  const rounds = exps.map((e: any) => `#${e.loop_id}`)
  const icData = exps.map((e: any) => e.ic ?? null)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rounds },
    yAxis: { type: 'value' },
    series: [
      { name: 'IC', type: 'line', data: icData, connectNulls: true, smooth: true },
    ],
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
  })
}, { deep: true })

onUnmounted(() => chart?.dispose())
</script>
<style scoped>
.strategy-dashboard { padding: 16px; }
.stat-cards { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { flex: 1; background: #f5f7fa; border-radius: 8px; padding: 16px; text-align: center; }
.stat-card small { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.stat-card strong { font-size: 24px; color: #303133; }
.dashboard-chart, .dashboard-hypotheses { margin-bottom: 20px; }
.dashboard-chart h4, .dashboard-hypotheses h4 { font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #303133; }
.error-state { text-align: center; padding: 40px; color: #909399; }
</style>