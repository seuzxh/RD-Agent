<template>
  <div class="dashboard">
    <div class="header-row">
      <div class="stat-cards">
        <div class="stat-card"><small>策略总数</small><strong>{{ strategies.length }}</strong></div>
        <div class="stat-card"><small>总因子数</small><strong>{{ totalFactors }}</strong></div>
        <div class="stat-card"><small>总模型数</small><strong>{{ totalModels }}</strong></div>
        <div class="stat-card"><small>总轮次</small><strong>{{ totalRounds }}</strong></div>
      </div>
      <el-button type="primary" @click="emit('create')">+ 新建策略</el-button>
    </div>
    <section>
      <el-table :data="strategies" size="small" @row-click="onRowClick" :row-class-name="rowClass">
        <el-table-column label="策略名" min-width="140">
          <template #default="{ row }"><strong>{{ formatName(row.id || row.name) }}</strong></template>
        </el-table-column>
        <el-table-column label="描述" min-width="220">
          <template #default="{ row }">
            <span class="desc">{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }"><span>{{ formatTime(row.created_at || row.timestamp) }}</span></template>
        </el-table-column>
        <el-table-column :label="'轮次'" width="60">
          <template #default="{ row }">{{ row.total_experiments ?? row.total_rounds ?? 0 }}</template>
        </el-table-column>
        <el-table-column :label="'因子'" width="60">
          <template #default="{ row }">{{ row.total_factors ?? row.factor_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column :label="'模型'" width="60">
          <template #default="{ row }">{{ row.total_models ?? row.model_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ strategies: any[] }>()
const emit = defineEmits<{ create: []; select: [id: string] }>()

const totalFactors = computed(() => props.strategies.reduce((s: number, st: any) => s + (st.total_factors ?? st.factor_count ?? 0), 0))
const totalModels = computed(() => props.strategies.reduce((s: number, st: any) => s + (st.total_models ?? st.model_count ?? 0), 0))
const totalRounds = computed(() => props.strategies.reduce((s: number, st: any) => s + (st.total_experiments ?? st.total_rounds ?? 0), 0))

function formatName(s: string) { return (s || '').split('/').pop() || s || '' }
function formatTime(t: string) {
  if (!t) return '—'
  return t.slice(0, 19).replace('T', ' ')
}
function statusType(s: string) { return s === 'running' ? 'warning' : s === 'completed' ? 'success' : 'info' }
function statusLabel(s: string) { return s === 'running' ? '运行中' : s === 'completed' ? '已完成' : '待处理' }
function rowClass() { return 'clickable' }
function onRowClick(row: any) { emit('select', row.id) }
</script>
<style scoped>
.dashboard { padding: 8px 0; }
.header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.stat-cards { display: flex; flex: 1; gap: 16px; }
.stat-card { flex: 1; background: #f5f7fa; border-radius: 8px; padding: 16px; text-align: center; }
.stat-card small { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.stat-card strong { font-size: 24px; color: #303133; }
.desc { font-size: 13px; color: #606266; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px; display: block; }
:deep(.clickable) { cursor: pointer; }
:deep(.clickable:hover) { background: #f5f7fa; }
</style>