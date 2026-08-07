<template>
  <div class="report">
    <section>
      <h4>策略对比</h4>
      <el-table :data="strategyRows" size="small">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="report-chart">
              <h5>最新轮收益曲线</h5>
              <iframe
                v-if="row.has_chart"
                class="report-chart-frame"
                :src="chartUrl(row.id)"
                sandbox="allow-scripts"
              />
              <div v-else class="empty-chart">该策略暂无收益曲线</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="策略" min-width="140">
          <template #default="{ row }"><strong>{{ formatName(row.id) }}</strong></template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180"/>
        <el-table-column label="轮次" width="60" prop="total_rounds"/>
        <el-table-column label="IC" width="80">
          <template #default="{ row }"><span>{{ row.latest_metrics?.ic?.toFixed(4) ?? '—' }}</span></template>
        </el-table-column>
        <el-table-column label="ICIR" width="80">
          <template #default="{ row }"><span>{{ row.latest_metrics?.icir?.toFixed(4) ?? '—' }}</span></template>
        </el-table-column>
        <el-table-column label="年化收益" width="100">
          <template #default="{ row }"><span>{{ fmtPct(row.latest_metrics?.annualized_return) }}</span></template>
        </el-table-column>
        <el-table-column label="最大回撤" width="100">
          <template #default="{ row }"><span>{{ fmtPct(row.latest_metrics?.max_drawdown) }}</span></template>
        </el-table-column>
        <el-table-column label="信息比率" width="90">
          <template #default="{ row }"><span>{{ row.latest_metrics?.information_ratio?.toFixed(4) ?? '—' }}</span></template>
        </el-table-column>
      </el-table>
    </section>
    <section class="actions">
      <el-button size="small" @click="downloadCsv">下载 CSV</el-button>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { chartUrl } from './api'

const props = defineProps<{ data: any }>()

const strategyRows = computed(() => props.data?.strategies || [])

function fmtPct(v: number | undefined | null) {
  if (v == null) return '—'
  return `${(Math.abs(v) * 100).toFixed(2)}%`
}
function formatName(s: string) { return (s || '').split('/').pop() || s || '' }

function downloadCsv() {
  const rows = strategyRows.value
  if (!rows.length) return
  const headers = ['策略', '轮次', 'IC', 'ICIR', '年化收益', '最大回撤', '信息比率']
  const csv = [
    headers.join(','),
    ...rows.map((r: any) => [
      formatName(r.id),
      r.total_rounds,
      r.latest_metrics?.ic?.toFixed(4) ?? '',
      r.latest_metrics?.icir?.toFixed(4) ?? '',
      r.latest_metrics?.annualized_return != null ? (r.latest_metrics.annualized_return * 100).toFixed(2) + '%' : '',
      r.latest_metrics?.max_drawdown != null ? (r.latest_metrics.max_drawdown * 100).toFixed(2) + '%' : '',
      r.latest_metrics?.information_ratio?.toFixed(4) ?? '',
    ].join(',')),
  ].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'report.csv'
  link.click(); URL.revokeObjectURL(link.href)
}
</script>
<style scoped>
.report { padding: 8px 0; }
h4 { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
.actions { margin-top: 16px; text-align: right; }
.report-chart { padding: 8px 16px; }
.report-chart h5 { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #606266; }
.report-chart-frame { width: 100%; height: 360px; border: 1px solid #e4e7ed; border-radius: 4px; }
.empty-chart { padding: 24px; text-align: center; color: #909399; font-size: 13px; background: #fafafa; border-radius: 4px; }
</style>