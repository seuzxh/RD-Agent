<template>
  <div class="artifact-app">
    <header class="artifact-header">
      <h1>量化研究工坊</h1>
    </header>
    <main class="artifact-main" v-loading="loading">
      <div v-if="error" class="error">
        <p>{{ error }}</p>
        <el-button size="small" @click="loadAll">重试</el-button>
      </div>
      <template v-else>
        <el-tabs type="border-card" class="artifact-tabs">
          <el-tab-pane label="📊 策略看板">
            <StrategyDashboard :strategies="strategies" @create="showCreateDialog=true" @select="selectedStrategyId=$event; detailVisible=true" />
          </el-tab-pane>
          <el-tab-pane label="🔬 因子库">
            <AlphaLabPanel :factors="factors" />
          </el-tab-pane>
          <el-tab-pane label="🤖 模型库">
            <ModelLabPanel :models="models" />
          </el-tab-pane>
          <el-tab-pane label="⚡ 运行中">
            <LiveLab :strategies="strategies" />
          </el-tab-pane>
          <el-tab-pane label="📋 报告">
            <ReportPanel :data="reportData" />
          </el-tab-pane>
        </el-tabs>
      </template>
    </main>

    <!-- Create Strategy Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建因子挖掘任务" width="500px">
      <el-form label-position="top">
        <el-form-item label="策略描述">
          <el-input v-model="newDescription" type="textarea" :rows="4" placeholder="用自然语言描述你的策略思路，例如：市场情绪冰点，反转信号..."/>
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
          <el-select v-model="newLoops" style="width:100%">
            <el-option v-for="item in [1,3,5,10]" :key="item" :label="`${item} 轮`" :value="item"/>
          </el-select>
        </el-form-item>
        <el-form-item label="运行模式">
          <el-switch v-model="autoMode" active-text="全自动（每轮无需人工确认）" inactive-text="交互式（每轮可调整假设和反馈）"/>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog=false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createStrategy">启动任务</el-button>
      </template>
    </el-dialog>

    <!-- Strategy Detail Dialog -->
    <el-dialog v-model="detailVisible" title="策略详情" width="80%" top="5vh">
      <div v-if="detailLoading" v-loading="detailLoading" style="height:200px"></div>
      <div v-else-if="detailError" class="error">{{ detailError }}</div>
      <div v-else-if="detailData" class="strategy-detail">
        <section class="detail-metrics">
          <div class="metric-card"><small>总轮次</small><strong>{{ detailData.total_rounds || 0 }}</strong></div>
          <div class="metric-card"><small>因子数</small><strong>{{ detailData.factors?.length || Object.keys(detailData.alpha_pool?.factors || {}).length }}</strong></div>
          <div class="metric-card"><small>模型数</small><strong>{{ detailData.models?.length || Object.keys(detailData.model_registry?.models || {}).length }}</strong></div>
        </section>
        <section v-if="detailData.experiments?.length" class="detail-experiments">
          <h4>实验历史</h4>
          <el-table :data="detailData.experiments" size="small" max-height="300">
            <el-table-column prop="round_number" label="轮次" width="60"/>
            <el-table-column prop="type" label="类型" width="80"/>
            <el-table-column prop="hypothesis_text" label="假设" min-width="200"/>
            <el-table-column prop="decision" label="决策" width="80">
              <template #default="{ row }"><el-tag :type="row.decision?'success':'danger'" size="small">{{ row.decision?'采纳':'拒绝' }}</el-tag></template>
            </el-table-column>
          </el-table>
        </section>
      </div>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { fetchAlphaLab, fetchModelLab, fetchReport, fetchStrategies } from './api'
import StrategyDashboard from './StrategyDashboard.vue'
import AlphaLabPanel from './AlphaLabPanel.vue'
import ModelLabPanel from './ModelLabPanel.vue'
import ReportPanel from './ReportPanel.vue'
import LiveLab from './LiveLab.vue'

const loading = ref(false)
const error = ref('')
const strategies = ref<any[]>([])
const factors = ref<any[]>([])
const models = ref<any[]>([])
const reportData = ref<any>(null)

// Create dialog
const showCreateDialog = ref(false)
const newDescription = ref('')
const modelSelector = ref('lgbm')
const newLoops = ref(3)
const autoMode = ref(true)
const creating = ref(false)

// Detail dialog
const selectedStrategyId = ref('')
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailData = ref<any>(null)

async function loadAll() {
  loading.value = true; error.value = ''
  try {
    const [s, f, m, r] = await Promise.all([
      fetchStrategies(),
      fetchAlphaLab(),
      fetchModelLab(),
      fetchReport(),
    ])
    strategies.value = s
    // research_api /api/factors returns flat array, not {factors: [...]}
    factors.value = Array.isArray(f) ? f : (f as any).factors || []
    models.value = Array.isArray(m) ? m : (m as any).models || []
    reportData.value = r
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function createStrategy() {
  if (!newDescription.value) { ElMessage.warning('请输入策略描述'); return }
  creating.value = true
  try {
    const formData = new FormData()
    formData.append('scenario', 'Finance Data Building')
    formData.append('description', newDescription.value)
    formData.append('loops', String(newLoops.value))
    formData.append('auto_mode', autoMode.value ? '1' : '0')
    formData.append('model_selector', modelSelector.value)
    const resp = await fetch('/upload', { method: 'POST', body: formData })
    const result = await resp.json()
    if (result.id) {
      ElMessage.success(`策略已启动: ${result.id}`)
      showCreateDialog.value = false
      newDescription.value = ''
      setTimeout(loadAll, 2000)
    } else {
      ElMessage.error(result.error || '启动失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

// Watch for detail dialog opening
import { watch } from 'vue'
watch(detailVisible, async (visible) => {
  if (!visible || !selectedStrategyId.value) return
  detailLoading.value = true; detailError.value = ''
  try {
    const resp = await fetch(`/api/strategies/${encodeURIComponent(selectedStrategyId.value)}/detail`)
    if (!resp.ok) throw new Error('Not found')
    detailData.value = await resp.json()
  } catch (e: any) {
    detailError.value = e.message
  } finally {
    detailLoading.value = false
  }
})

onMounted(() => loadAll())
</script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f5f7fa; color: #303133; }
.artifact-app { max-width: 1400px; margin: 0 auto; padding: 16px; }
.artifact-header { margin-bottom: 16px; }
.artifact-header h1 { font-size: 22px; font-weight: 700; color: #1c2b57; }
.artifact-main { min-height: 400px; }
.artifact-tabs { border-radius: 8px; }
.error { text-align: center; padding: 80px 20px; color: #f56c6c; }
.strategy-detail { padding: 8px 0; }
.detail-metrics { display: flex; gap: 16px; margin-bottom: 20px; }
.metric-card { flex: 1; background: #f5f7fa; border-radius: 8px; padding: 16px; text-align: center; }
.metric-card small { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.metric-card strong { font-size: 20px; color: #303133; }
.detail-experiments h4 { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
</style>