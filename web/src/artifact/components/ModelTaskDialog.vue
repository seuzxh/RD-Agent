<template>
  <el-dialog v-model="visible" width="640px" title="新建模型实现任务" destroy-on-close>
    <el-alert v-if="noSota" type="info" :closable="false" show-icon
      title="该策略暂无 SOTA 因子，可手动勾选因子；若未勾选任何因子，模型将回退到 ALPHA20 baseline。" />
    <el-form label-position="top">
      <el-form-item label="父策略（因子池来源）">
        <el-select v-model="selectedStrategyId" style="width:100%">
          <el-option v-for="s in strategies" :key="s.id" :label="s.name" :value="s.id"/>
        </el-select>
      </el-form-item>
      <el-form-item label="模型指令 (A')" required>
        <el-input v-model="directive" type="textarea" :rows="4"
          placeholder="用自然语言描述模型优化方向，如：用 LSTM 处理时序、约束模型规模、压低回撤…"/>
      </el-form-item>
      <el-form-item label="因子池（来自本策略）">
        <div v-if="factors.length" class="factor-pool">
          <el-checkbox-group v-model="selectedNames" class="factor-list">
            <el-checkbox v-for="f in factors" :key="f.name" :value="f.name" class="factor-item">
              <span class="factor-name">{{ f.name }}</span>
              <el-tag v-if="f.status === 'sota'" type="success" size="small">SOTA</el-tag>
              <span class="factor-meta">轮次 {{ f.round_number ?? '—' }} · IC {{ fmt(f.ic) }} · ICIR {{ fmt(f.icir) }}</span>
            </el-checkbox>
          </el-checkbox-group>
        </div>
        <div v-else class="factor-empty">该策略暂无因子，模型将使用 ALPHA20 baseline。</div>
      </el-form-item>
      <el-form-item label="验证模型">
        <el-select v-model="modelSelector" style="width:100%">
          <el-option label="LightGBM（默认）" value="lgbm"/>
          <el-option label="Linear（闭式 OLS，最快）" value="linear"/>
          <el-option label="XGBoost" value="xgboost"/>
          <el-option label="CatBoost" value="catboost"/>
        </el-select>
      </el-form-item>
      <el-form-item label="循环次数">
        <el-select v-model="loops">
          <el-option v-for="item in [1,3,5]" :key="item" :label="`${item} 轮`" :value="item"/>
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible=false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">启动模型任务</el-button>
    </template>
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

export interface ModelParentCandidate {
  id: string          // 完整策略路径 == factor_pool_source 值
  name: string        // 短显示名
  factors: any[]      // 该策略的因子
}

const props = defineProps<{ modelValue: boolean; strategies: ModelParentCandidate[]; defaultStrategyId: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [value: { description: string; strategyId: string; loops: number; modelSelector: string; factorNames: string[] }]
}>()

const visible = ref(props.modelValue)
const submitting = ref(false)
const directive = ref('')
const selectedNames = ref<string[]>([])
const modelSelector = ref('lgbm')
const loops = ref(1)
const selectedStrategyId = ref(props.defaultStrategyId)

const currentStrategy = computed(() => props.strategies.find(s => s.id === selectedStrategyId.value))
const factors = computed(() => currentStrategy.value?.factors || [])

function preselectSota() {
  selectedNames.value = factors.value.filter(f => f.status === 'sota').map(f => f.name)
}

watch(() => props.modelValue, (value) => {
  visible.value = value
  if (value) {
    // 每次打开按默认策略重置：默认勾选该策略的 SOTA 因子，无 SOTA 时允许手动勾选
    selectedStrategyId.value = props.defaultStrategyId || props.strategies[0]?.id || ''
    directive.value = ''
    preselectSota()
  }
})
watch(visible, (value) => emit('update:modelValue', value))
// 切换父策略时实时重算 SOTA 预选
watch(selectedStrategyId, preselectSota)

const noSota = computed(() => factors.value.length > 0 && !factors.value.some(f => f.status === 'sota'))
function fmt(value: number | null | undefined): string {
  return value == null ? '—' : Number(value).toFixed(4)
}

async function submit() {
  if (!directive.value.trim()) {
    ElMessage.warning('请填写模型指令（A′），模型任务必须有明确的优化方向')
    return
  }
  submitting.value = true
  try {
    emit('submit', {
      description: directive.value.trim(),
      strategyId: selectedStrategyId.value,
      loops: loops.value,
      modelSelector: modelSelector.value,
      factorNames: selectedNames.value,
    })
  } finally {
    setTimeout(() => (submitting.value = false), 500)
  }
}
defineExpose({ open: () => { visible.value = true }, close: () => { visible.value = false } })
</script>
<style scoped>
.factor-pool { width: 100%; max-height: 220px; overflow: auto; border: 1px solid var(--el-border-color); border-radius: 4px; padding: 8px; }
.factor-list { display: flex; flex-direction: column; gap: 6px; }
.factor-item { display: flex; align-items: center; gap: 4px; margin-right: 0; height: auto; white-space: normal; }
.factor-item :deep(.el-checkbox__label) { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.factor-name { font-weight: 500; }
.factor-meta { color: var(--el-text-color-secondary); font-size: 12px; }
.factor-empty { color: var(--el-text-color-secondary); font-size: 13px; }
</style>