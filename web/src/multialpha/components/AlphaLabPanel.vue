<template>
  <div class="alpha-lab" v-loading="loading">
    <div v-if="error" class="error-state">
      <p>{{ error }}</p>
      <el-button size="small" @click="$emit('retry')">重试</el-button>
    </div>
    <template v-else-if="factors.length">
      <div class="alpha-toolbar">
        <el-select v-model="statusFilter" size="small" style="width:120px">
          <el-option label="全部" value=""/>
          <el-option label="SOTA" value="sota"/>
          <el-option label="活跃" value="active"/>
          <el-option label="已淘汰" value="deprecated"/>
        </el-select>
        <el-input v-model="search" size="small" placeholder="搜索因子名..." clearable style="width:200px"/>
        <el-button type="primary" size="small" style="margin-left:auto" @click="emit('createModel', [...factors])">新建模型任务</el-button>
      </div>
      <el-table :data="filteredFactors" size="small">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="factor-detail">
              <section v-if="row.formulation"><b>公式</b><p>{{ row.formulation }}</p></section>
              <section v-if="row.code"><b>代码</b><pre>{{ row.code }}</pre></section>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="因子名" min-width="120"/>
        <el-table-column prop="ic" label="IC" width="80">
          <template #default="{ row }"><span>{{ row.ic?.toFixed(4) ?? '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="icir" label="ICIR" width="80">
          <template #default="{ row }"><span>{{ row.icir?.toFixed(4) ?? '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status==='sota'?'success':row.status==='deprecated'?'danger':'info'" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="round_number" label="轮次" width="60"/>
      </el-table>
    </template>
    <div v-else class="empty-state">暂无因子数据</div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { fetchStrategyFactors, type FactorItem } from '../../services/research-api'

const props = defineProps<{ strategyId: string }>()
const emit = defineEmits<{ retry: []; createModel: [factors: FactorItem[]] }>()

const loading = ref(false)
const error = ref('')
const factors = ref<any[]>([])
const statusFilter = ref('')
const search = ref('')

const filteredFactors = computed(() => {
  let list = [...factors.value]
  if (statusFilter.value) list = list.filter(f => f.status === statusFilter.value)
  if (search.value) list = list.filter(f => (f.name || '').toLowerCase().includes(search.value.toLowerCase()))
  return list
})

function statusLabel(s: string) {
  return { sota: 'SOTA', active: '活跃', deprecated: '已淘汰', pending: '待定' }[s] || s
}

async function load() {
  loading.value = true; error.value = ''
  try { factors.value = await fetchStrategyFactors(props.strategyId) } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

watch(() => props.strategyId, () => load())
onMounted(() => load())
</script>
<style scoped>
.alpha-lab { padding: 16px; }
.alpha-toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
.factor-detail { padding: 12px; }
.factor-detail section { margin-bottom: 12px; }
.factor-detail b { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.factor-detail pre { background: #f5f7fa; padding: 8px; border-radius: 4px; font-size: 12px; max-height: 200px; overflow: auto; }
.error-state, .empty-state { text-align: center; padding: 40px; color: #909399; }
</style>