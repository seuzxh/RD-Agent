<template>
  <div class="model-lab">
    <div class="strategy-tags">
      <el-tag
        v-for="s in strategyNames" :key="s"
        :type="activeStrategy === s ? 'primary' : 'info'"
        size="small"
        style="cursor:pointer"
        @click="toggleStrategy(s)"
      >{{ formatName(s) }}</el-tag>
      <el-tag v-if="activeStrategy" size="small" style="cursor:pointer" @click="activeStrategy=''">清除筛选</el-tag>
    </div>
    <el-table :data="displayModels" size="small" @expand-change="onExpandChange">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="detail">
            <section v-if="row.features?.length"><b>特征因子</b><p>{{ row.features.join(', ') }}</p></section>
            <section v-if="row.hyperparameters && Object.keys(row.hyperparameters).length"><b>超参数</b><pre>{{ JSON.stringify(row.hyperparameters, null, 2) }}</pre></section>
            <section v-if="row.code_path">
              <b>代码</b>
              <pre v-if="rowCode[row._codeKey]">{{ rowCode[row._codeKey] }}</pre>
              <p v-else-if="loadingCode[row._codeKey]">加载中…</p>
              <p v-else class="hint">展开后加载代码</p>
            </section>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="模型名" min-width="120"/>
      <el-table-column prop="model_type" label="类型" width="80"/>
      <el-table-column label="年化收益" width="100">
        <template #default="{ row }"><span>{{ fmtPct(row.annualized_return ?? row.strategy_metrics?.annualized_return) }}</span></template>
      </el-table-column>
      <el-table-column label="最大回撤" width="100">
        <template #default="{ row }"><span>{{ fmtPct(row.max_drawdown ?? row.strategy_metrics?.max_drawdown) }}</span></template>
      </el-table-column>
      <el-table-column label="信息比率" width="90">
        <template #default="{ row }"><span>{{ (row.information_ratio ?? row.strategy_metrics?.information_ratio)?.toFixed(4) ?? '—' }}</span></template>
      </el-table-column>
      <el-table-column label="状态" width="70">
        <template #default="{ row }">
          <el-tag :type="row.status==='sota'?'success':'info'" size="small">{{ row.status==='sota'?'SOTA':'活跃' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="策略" min-width="140">
        <template #default="{ row }"><el-tag size="small">{{ formatName(row.strategy_id || row._strategy_name) }}</el-tag></template>
      </el-table-column>
    </el-table>
    <div v-if="!displayModels.length" class="empty">暂无模型数据</div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { fetchCode } from './api'

const props = defineProps<{ models: any[] }>()
const activeStrategy = ref('')
const rowCode = ref<Record<string, string>>({})
const loadingCode = ref<Record<string, boolean>>({})

const strategyNames = computed(() => {
  const names = new Set(props.models.map((m: any) => m.strategy_id || m._strategy_name))
  return Array.from(names).filter(Boolean)
})

const displayModels = computed(() => {
  let list = [...props.models]
  if (activeStrategy.value) list = list.filter(m => (m.strategy_id || m._strategy_name) === activeStrategy.value)
  return list.map((m: any) => ({
    ...m,
    _codeKey: `${m.strategy_id || m._strategy_name || ''}:${m.name}`,
  }))
})

async function onExpandChange(row: any, expandedRows: any[]) {
  const expanded = (expandedRows || []).some((r: any) => r._codeKey === row._codeKey)
  if (!expanded) return
  if (!row.code_path || rowCode.value[row._codeKey] != null) return
  loadingCode.value[row._codeKey] = true
  try {
    const strategyId = row.strategy_id || row._strategy_name
    const res = await fetchCode(strategyId, row.name, 'model')
    rowCode.value[row._codeKey] = res.code
  } catch {
    rowCode.value[row._codeKey] = ''
  } finally {
    loadingCode.value[row._codeKey] = false
  }
}

function fmtPct(v: number | undefined | null) {
  if (v == null) return '—'
  return `${(Math.abs(v) * 100).toFixed(2)}%`
}
function formatName(s: string) { return (s || '').split('/').pop() || s || '' }
function toggleStrategy(s: string) { activeStrategy.value = activeStrategy.value === s ? '' : s }
</script>
<style scoped>
.model-lab { padding: 8px 0; }
.strategy-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.detail { padding: 12px; }
.detail section { margin-bottom: 12px; }
.detail b { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.detail pre { background: #f5f7fa; padding: 8px; border-radius: 4px; font-size: 12px; max-height: 200px; overflow: auto; }
.detail .hint { color: #909399; font-size: 12px; }
.empty { text-align: center; padding: 40px; color: #909399; }
</style>