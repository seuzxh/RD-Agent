<template>
  <div class="model-lab" v-loading="loading">
    <div v-if="error" class="error-state">
      <p>{{ error }}</p>
      <el-button size="small" @click="$emit('retry')">重试</el-button>
    </div>
    <template v-else-if="models.length">
      <el-table :data="models" size="small" @expand-change="onExpand">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="model-detail">
              <section v-if="row.features?.length"><b>特征因子</b><p>{{ row.features.join(', ') }}</p></section>
              <section v-if="row.hyperparameters && Object.keys(row.hyperparameters).length"><b>超参数</b><pre>{{ JSON.stringify(row.hyperparameters, null, 2) }}</pre></section>
              <section v-if="row.code"><b>代码</b><pre>{{ row.code }}</pre></section>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="模型名" min-width="120"/>
        <el-table-column prop="model_type" label="类型" width="80"/>
        <el-table-column prop="strategy_metrics.annualized_return" label="年化收益" width="100">
          <template #default="{ row }"><span>{{ formatPct(row.strategy_metrics?.annualized_return) }}</span></template>
        </el-table-column>
        <el-table-column prop="strategy_metrics.max_drawdown" label="最大回撤" width="100">
          <template #default="{ row }"><span>{{ formatPct(row.strategy_metrics?.max_drawdown) }}</span></template>
        </el-table-column>
        <el-table-column prop="strategy_metrics.information_ratio" label="信息比率" width="90">
          <template #default="{ row }"><span>{{ row.strategy_metrics?.information_ratio?.toFixed(4) ?? '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status==='sota'?'success':'info'" size="small">{{ row.status==='sota'?'SOTA':'活跃' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="round_number" label="轮次" width="60"/>
      </el-table>
    </template>
    <div v-else class="empty-state">暂无模型数据</div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { fetchModelLab } from '../api'

const props = defineProps<{ traceId: string }>()
defineEmits<{ retry: [] }>()

const loading = ref(false)
const error = ref('')
const rawData = ref<Record<string, any> | null>(null)

const models = computed(() => {
  const reg = rawData.value || {}
  const modelMap: Record<string, any> = reg.models || {}
  return Object.values(modelMap) as any[]
})

function formatPct(v: number | undefined | null) {
  if (v == null) return '—'
  return `${(Math.abs(v) * 100).toFixed(2)}%`
}

async function load() {
  loading.value = true; error.value = ''
  try { rawData.value = await fetchModelLab(props.traceId) } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

function onExpand(row: any, expanded: boolean[]) {}

watch(() => props.traceId, () => load())
onMounted(() => load())
</script>
<style scoped>
.model-lab { padding: 16px; }
.model-detail { padding: 12px; }
.model-detail section { margin-bottom: 12px; }
.model-detail b { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.model-detail pre { background: #f5f7fa; padding: 8px; border-radius: 4px; font-size: 12px; max-height: 200px; overflow: auto; }
.error-state, .empty-state { text-align: center; padding: 40px; color: #909399; }
</style>