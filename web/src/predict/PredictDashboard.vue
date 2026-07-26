<template>
  <div class="predict-dashboard">
    <header class="predict-header">
      <h2>股池预测看板</h2>
      <el-button text @click="$emit('home')">← 返回主站</el-button>
    </header>

    <div class="predict-body">
      <!-- 左栏:实验列表 -->
      <aside class="predict-sidebar">
        <div class="sidebar-header">可选实验</div>
        <div v-if="status === 'loading-list'" class="loading-hint">加载中...（首次 10-30s）</div>
        <div v-else-if="experiments.length === 0" class="empty-hint">暂无可用的 SOTA 因子实验</div>
        <button
          v-for="exp in experiments"
          :key="exp.trace_id"
          class="exp-item"
          :class="{ active: selectedTraceId === exp.trace_id }"
          @click="selectExperiment(exp)"
        >
          <div class="exp-name">{{ exp.name }}</div>
          <div class="exp-meta">
            因子 {{ exp.factor_count }} · IC {{ exp.metrics.IC ?? '—' }} · 年化 {{ exp.metrics.annualized_return != null ? (exp.metrics.annualized_return * 100).toFixed(2) + '%' : '—' }}
          </div>
        </button>
      </aside>

      <!-- 右栏:实验信息 + 预测 + Top20 -->
      <main class="predict-main">
        <div v-if="!selectedExp" class="empty-main">← 请选择一个实验</div>
        <template v-else>
          <!-- 实验信息卡 -->
          <section class="exp-info">
            <div class="exp-info-head">
              <h3>{{ selectedExp.name }}</h3>
              <span class="exp-date">{{ selectedExp.created_at }}</span>
            </div>
            <div class="metric-grid">
              <div class="metric-item"><small>IC</small><strong>{{ selectedExp.metrics.IC ?? '—' }}</strong></div>
              <div class="metric-item"><small>年化收益</small><strong>{{ selectedExp.metrics.annualized_return != null ? (selectedExp.metrics.annualized_return * 100).toFixed(2) + '%' : '—' }}</strong></div>
              <div class="metric-item"><small>最大回撤</small><strong>{{ selectedExp.metrics.max_drawdown != null ? (selectedExp.metrics.max_drawdown * 100).toFixed(2) + '%' : '—' }}</strong></div>
              <div class="metric-item"><small>因子数</small><strong>{{ selectedExp.factor_count }}</strong></div>
            </div>
          </section>

          <!-- 操作栏 -->
          <section class="action-bar">
            <el-button type="primary" :loading="status === 'predicting'" @click="runPrediction">
              {{ status === 'predicting' ? '预测中...' : '预测 T+1' }}
            </el-button>
            <el-button @click="showHistory">查看历史</el-button>
          </section>

          <!-- 错误提示 -->
          <div v-if="error" class="error-hint">{{ error }}</div>

          <!-- 预测状态 -->
          <div v-if="status === 'predicting'" class="status-hint">
            <el-icon class="is-loading"><Loading /></el-icon>
            正在执行预测 pipeline（约 2-5 分钟）...
          </div>

          <!-- Top20 表格 -->
          <section v-if="top20 && top20.length > 0" class="top20-section">
            <h4>T+1 Top20 股池 <span class="predict-date">（{{ predictDate }}）</span></h4>
            <el-table :data="top20" stripe size="small" border>
              <el-table-column prop="rank" label="排名" width="70" align="center" />
              <el-table-column prop="instrument" label="股票代码" />
              <el-table-column prop="score" label="得分" align="right">
                <template #default="{ row }">{{ row.score.toFixed(6) }}</template>
              </el-table-column>
            </el-table>
          </section>
        </template>
      </main>
    </div>

    <!-- 历史记录弹窗 -->
    <el-dialog v-model="historyVisibleInternal" title="历史预测记录" width="600px">
      <div v-if="history.length === 0" class="empty-hint">暂无历史记录</div>
      <div v-else class="history-list">
        <div v-for="rec in history" :key="rec.date + rec.source_trace_id" class="history-item" @click="showHistoryDetail(rec)">
          <div class="history-date">{{ rec.date }}</div>
          <div class="history-meta">{{ rec.source_trace_id.split('/').pop() }} · Top{{ rec.top20.length }}</div>
        </div>
      </div>
    </el-dialog>

    <!-- 历史详情弹窗 -->
    <el-dialog v-model="historyDetailVisible" :title="`历史预测 ${historyDetailDate}`" width="500px" append-to-body>
      <el-table v-if="historyDetail.length > 0" :data="historyDetail" stripe size="small" border>
        <el-table-column prop="rank" label="排名" width="70" align="center" />
        <el-table-column prop="instrument" label="股票代码" />
        <el-table-column prop="score" label="得分" align="right">
          <template #default="{ row }">{{ row.score.toFixed(6) }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { usePredict } from '../use-predict'
import type { PredictRecord, Top20Item } from '../api'

defineEmits<{ home: [] }>()

const {
  experiments, selectedExp, selectedTraceId, status, top20, predictDate,
  error, history, historyVisible,
  fetchExperiments, selectExperiment, runPrediction, fetchHistory,
} = usePredict()

const historyVisibleInternal = computed({
  get: () => historyVisible.value,
  set: (v) => { historyVisible.value = v },
})

const historyDetailVisible = ref(false)
const historyDetail = ref<Top20Item[]>([])
const historyDetailDate = ref('')

function showHistory() {
  fetchHistory()
  historyVisible.value = true
}

function showHistoryDetail(rec: PredictRecord) {
  historyDetail.value = rec.top20
  historyDetailDate.value = rec.date
  historyDetailVisible.value = true
}

onMounted(() => {
  fetchExperiments()
})
</script>

<style scoped>
.predict-dashboard { display: flex; flex-direction: column; height: 100%; }
.predict-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid var(--el-border-color-lighter); }
.predict-header h2 { margin: 0; font-size: 18px; }
.predict-body { display: flex; flex: 1; overflow: hidden; }
.predict-sidebar { width: 280px; border-right: 1px solid var(--el-border-color-lighter); overflow-y: auto; padding: 8px; }
.sidebar-header { font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 8px; padding: 4px 8px; }
.exp-item { display: block; width: 100%; text-align: left; padding: 10px 12px; margin-bottom: 6px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; cursor: pointer; background: var(--el-bg-color); transition: all 0.2s; }
.exp-item:hover { border-color: var(--el-color-primary-light-5); }
.exp-item.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.exp-name { font-size: 14px; font-weight: 500; margin-bottom: 4px; }
.exp-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.predict-main { flex: 1; overflow-y: auto; padding: 20px; }
.empty-main, .empty-hint, .loading-hint { color: var(--el-text-color-secondary); font-size: 14px; padding: 20px; text-align: center; }
.exp-info { margin-bottom: 16px; }
.exp-info-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.exp-info-head h3 { margin: 0; font-size: 16px; }
.exp-date { font-size: 12px; color: var(--el-text-color-secondary); }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.metric-item { text-align: center; padding: 8px; background: var(--el-fill-color-light); border-radius: 6px; }
.metric-item small { display: block; font-size: 11px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.metric-item strong { font-size: 16px; }
.action-bar { display: flex; gap: 12px; margin-bottom: 16px; }
.error-hint { color: var(--el-color-danger); font-size: 13px; padding: 8px 12px; background: var(--el-color-danger-light-9); border-radius: 4px; margin-bottom: 16px; }
.status-hint { display: flex; align-items: center; gap: 8px; color: var(--el-color-primary); font-size: 14px; padding: 16px; }
.top20-section h4 { margin: 0 0 12px; font-size: 15px; }
.predict-date { font-size: 13px; color: var(--el-text-color-secondary); font-weight: normal; }
.history-list { max-height: 400px; overflow-y: auto; }
.history-item { display: flex; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid var(--el-border-color-lighter); cursor: pointer; }
.history-item:hover { background: var(--el-fill-color-light); }
.history-date { font-weight: 500; }
.history-meta { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
