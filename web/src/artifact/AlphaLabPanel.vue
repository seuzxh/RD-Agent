<template>
  <div class="alpha-lab">
    <div class="toolbar">
      <el-select v-model="statusFilter" size="small" style="width:120px" placeholder="状态" clearable>
        <el-option label="SOTA" value="sota"/>
        <el-option label="活跃" value="active"/>
        <el-option label="已淘汰" value="deprecated"/>
      </el-select>
      <el-input v-model="search" size="small" placeholder="搜索因子名..." clearable style="width:200px"/>
    </div>
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
    <el-table :data="displayFactors" size="small">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="detail">
            <section v-if="row.formulation"><b>公式</b><p>{{ row.formulation }}</p></section>
            <section v-if="row.code"><b>代码</b><pre>{{ row.code }}</pre></section>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="因子名" min-width="120"/>
      <el-table-column label="IC" width="80">
        <template #default="{ row }"><span>{{ (row.ic ?? row.factor_metrics?.ic)?.toFixed(4) ?? '—' }}</span></template>
      </el-table-column>
      <el-table-column label="ICIR" width="80">
        <template #default="{ row }"><span>{{ (row.icir ?? row.factor_metrics?.icir)?.toFixed(4) ?? '—' }}</span></template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status==='sota'?'success':row.status==='deprecated'?'danger':'info'" size="small">{{ labelMap[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="策略" min-width="140">
        <template #default="{ row }"><el-tag size="small">{{ formatName(row.strategy_id || row._strategy_name) }}</el-tag></template>
      </el-table-column>
    </el-table>
    <div v-if="!displayFactors.length" class="empty">暂无因子数据</div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ factors: any[] }>()
const statusFilter = ref('')
const search = ref('')
const activeStrategy = ref('')
const labelMap: Record<string, string> = { sota: 'SOTA', active: '活跃', deprecated: '已淘汰', pending: '待定' }

const strategyNames = computed(() => {
  const names = new Set(props.factors.map((f: any) => f.strategy_id || f._strategy_name))
  return Array.from(names).filter(Boolean)
})

const flatFactors = computed(() => props.factors.map((f: any) => ({
  ...f,
  ic: f.ic ?? f.factor_metrics?.ic,
  icir: f.icir ?? f.factor_metrics?.icir,
  formulation: f.formulation || f.factor_formulation,
})))

const displayFactors = computed(() => {
  let list = [...flatFactors.value]
  if (statusFilter.value) list = list.filter(f => f.status === statusFilter.value)
  if (search.value) list = list.filter(f => (f.name || '').toLowerCase().includes(search.value.toLowerCase()))
  if (activeStrategy.value) list = list.filter(f => (f.strategy_id || f._strategy_name) === activeStrategy.value)
  return list
})

function formatName(s: string) { return (s || '').split('/').pop() || s || '' }
function toggleStrategy(s: string) { activeStrategy.value = activeStrategy.value === s ? '' : s }
</script>
<style scoped>
.alpha-lab { padding: 8px 0; }
.toolbar { display: flex; gap: 12px; margin-bottom: 8px; }
.strategy-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.detail { padding: 12px; }
.detail section { margin-bottom: 12px; }
.detail b { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.detail pre { background: #f5f7fa; padding: 8px; border-radius: 4px; font-size: 12px; max-height: 200px; overflow: auto; }
.empty { text-align: center; padding: 40px; color: #909399; }
</style>