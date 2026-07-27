<template>
  <div class="predict-shell">
    <!-- 顶栏（复用主页 TopBar 视觉） -->
    <header class="predict-topbar">
      <button class="brand" title="返回主站" @click="goHome">
        <span class="brand-logo-frame"><img src="https://h5.crsec.com.cn/logo.png" alt="国新证券" class="brand-logo"/></span>
        <span class="brand-text"><small>国新证券</small><strong>MultiAlpha</strong></span>
      </button>
      <div class="topbar-context">
        <span class="dot"></span>
        <span>STOCKPOOL PREDICTION · <b>股池预测</b></span>
      </div>
      <div class="topbar-actions">
        <button class="ma-btn" :class="{ loading: status === 'loading-list' }" @click="fetchExperiments">刷新实验</button>
        <button class="ma-btn ma-btn-primary" @click="goHome">← 返回主站</button>
      </div>
    </header>

    <main class="predict-main-area">
      <!-- 左栏:实验列表 -->
      <aside class="predict-sidebar">
        <div class="sidebar-head">
          <div class="sidebar-label">SOTA EXPERIMENTS</div>
          <h3>可选实验</h3>
          <div class="sidebar-sub">仅显示 fin_factor · 有 SOTA · 有模型</div>
        </div>
        <div class="sidebar-list">
          <div v-if="status === 'loading-list'" class="sidebar-empty">加载中...（首次 10-30s）</div>
          <div v-else-if="experiments.length === 0" class="sidebar-empty">暂无可用的 SOTA 因子实验</div>
          <button
            v-for="exp in experiments"
            :key="exp.trace_id"
            class="exp-item"
            :class="{ active: selectedTraceId === exp.trace_id }"
            @click="selectExperiment(exp)"
          >
            <div class="exp-item-head">
              <span class="exp-name">{{ exp.name }}</span>
              <span class="exp-badge" :class="exp.has_model ? 'ready' : 'stale'">{{ exp.has_model ? 'READY' : 'NO MODEL' }}</span>
            </div>
            <div class="exp-meta">
              <span>因子 <b>{{ exp.factor_count }}</b></span>
              <span>IC <b>{{ exp.metrics.IC ?? '—' }}</b></span>
              <span>年化 <b>{{ exp.metrics.annualized_return != null ? (exp.metrics.annualized_return * 100).toFixed(2) + '%' : '—' }}</b></span>
            </div>
          </button>
        </div>
      </aside>

      <!-- 右栏:实验信息 + 预测 + Top20 -->
      <section class="predict-content">
        <!-- 空态 -->
        <div v-if="!selectedExp" class="empty-state">
          <div class="empty-ico">α</div>
          <h3>选择一个实验开始预测</h3>
          <p>从左侧选择一个有 SOTA 因子和已训练模型的实验，预测 T+1 Top20 股池。</p>
        </div>

        <template v-else>
          <!-- 实验信息 Hero（终端风格） -->
          <div class="exp-hero">
            <div class="exp-hero-head">
              <div>
                <div class="exp-hero-eyebrow">SELECTED · FACTOR EXPERIMENT</div>
                <h2>{{ selectedExp.name }}</h2>
              </div>
              <div class="exp-hero-date">创建于 {{ selectedExp.created_at }}</div>
            </div>
            <div class="metric-grid">
              <div class="metric-cell">
                <small>IC</small>
                <strong :class="metricClass(selectedExp.metrics.IC)">{{ formatNum(selectedExp.metrics.IC) }}</strong>
                <p>信息系数</p>
              </div>
              <div class="metric-cell">
                <small>ANNUALIZED</small>
                <strong :class="metricClass(selectedExp.metrics.annualized_return)">{{ formatPercent(selectedExp.metrics.annualized_return) }}</strong>
                <p>年化收益</p>
              </div>
              <div class="metric-cell">
                <small>MAX DRAWDOWN</small>
                <strong class="neg">{{ formatPercent(selectedExp.metrics.max_drawdown) }}</strong>
                <p>最大回撤</p>
              </div>
              <div class="metric-cell">
                <small>FACTORS</small>
                <strong>{{ selectedExp.factor_count }}</strong>
                <p>SOTA 因子数</p>
              </div>
            </div>
          </div>

          <!-- 操作栏 -->
          <div class="action-bar">
            <button class="ma-btn ma-btn-primary" :disabled="status === 'predicting'" @click="runPrediction">
              <span v-if="status === 'predicting'" class="spinner-light"></span>
              {{ status === 'predicting' ? '预测中...' : '预测 T+1' }}
            </button>
            <button class="ma-btn" @click="showHistory">查看历史</button>
          </div>

          <!-- 错误提示 -->
          <div v-if="error" class="status-row error">
            <div class="status-txt"><b>预测失败</b><small>{{ error }}</small></div>
          </div>

          <!-- 预测状态 -->
          <div v-if="status === 'predicting'" class="status-row running">
            <span class="spinner"></span>
            <div class="status-txt">
              <b>正在执行预测 pipeline（约 2-5 分钟）</b>
              <small>补齐因子值 → 简化 inference → 取 T 日 Top20</small>
            </div>
          </div>

          <!-- Top20 表格 -->
          <div v-if="top20 && top20.length > 0" class="top20-card">
            <div class="top20-head">
              <div class="top20-title">
                <h3>T+1 Top20 股池</h3>
                <span class="top20-date">预测日 {{ predictDate }}</span>
              </div>
            </div>
            <table class="top20-table">
              <thead>
                <tr>
                  <th class="center">RANK</th>
                  <th>股票代码</th>
                  <th class="right">SCORE</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in top20" :key="item.rank">
                  <td class="rank"><span class="rank-badge" :class="{ top3: item.rank <= 3 }">{{ item.rank }}</span></td>
                  <td class="code">{{ item.instrument }}</td>
                  <td class="score">{{ item.score.toFixed(6) }}<span class="score-bar" :style="{ width: scoreWidth(item.score) }"></span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>
    </main>

    <!-- 历史记录弹窗 -->
    <el-dialog v-model="historyVisibleInternal" title="历史预测记录" width="600px">
      <div v-if="history.length === 0" class="dialog-empty">暂无历史记录</div>
      <div v-else class="history-list">
        <div v-for="rec in history" :key="rec.date + rec.source_trace_id" class="history-item" @click="showHistoryDetail(rec)">
          <div class="history-date">{{ rec.date }}</div>
          <div class="history-meta">{{ rec.source_trace_id.split('/').pop() }} · Top{{ rec.top20.length }}</div>
        </div>
      </div>
    </el-dialog>

    <!-- 历史详情弹窗 -->
    <el-dialog v-model="historyDetailVisible" :title="`历史预测 ${historyDetailDate}`" width="500px" append-to-body>
      <table v-if="historyDetail.length > 0" class="top20-table">
        <thead>
          <tr>
            <th class="center">RANK</th>
            <th>股票代码</th>
            <th class="right">SCORE</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in historyDetail" :key="item.rank">
            <td class="rank"><span class="rank-badge" :class="{ top3: item.rank <= 3 }">{{ item.rank }}</span></td>
            <td class="code">{{ item.instrument }}</td>
            <td class="score">{{ item.score.toFixed(6) }}</td>
          </tr>
        </tbody>
      </table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { usePredict } from './use-predict'
import type { PredictRecord, Top20Item } from './api'

const {
  experiments, selectedExp, selectedTraceId, status, top20, predictDate,
  error, history, historyVisible,
  fetchExperiments, selectExperiment, runPrediction, fetchHistory,
} = usePredict()

// 跨页返回主站
function goHome() {
  window.location.href = './multialpha.html'
}

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

// 数值格式化（金色品牌下的正负色）
function metricClass(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return ''
  return v >= 0 ? 'pos' : 'neg'
}
function formatNum(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? '—' : v.toFixed(4)
}
function formatPercent(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? '—' : (v * 100).toFixed(2) + '%'
}
// Top20 score 条形宽度（相对最大值）
const maxScore = computed(() => {
  if (!top20.value || top20.value.length === 0) return 1
  return Math.max(...top20.value.map(i => Math.abs(i.score)), 0.0001)
})
function scoreWidth(score: number): string {
  return Math.max(10, Math.round((Math.abs(score) / maxScore.value) * 100)) + '%'
}

// 静默引用 Loading 图标（保留 import 以备后续状态条使用，避免 noUnusedLocals 报错）
void Loading

onMounted(() => {
  fetchExperiments()
})
</script>

<style scoped>
/* ============ 应用骨架 ============ */
.predict-shell { height: 100vh; display: flex; flex-direction: column; overflow: hidden; background: var(--ma-bg); }

/* ============ 顶栏 ============ */
.predict-topbar {
  height: var(--ma-header-height);
  padding: 0 24px 0 20px;
  flex: none;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  background: rgb(255 255 255 / 96%);
  border-bottom: 1px solid var(--ma-line);
  box-shadow: 0 1px 12px rgb(25 27 33 / 4%);
}
.brand { display: flex; align-items: center; gap: 12px; background: none; border: 0; cursor: pointer; padding: 0; }
.brand-logo-frame {
  width: 46px; height: 46px; flex: none;
  display: grid; place-items: center; overflow: hidden; border-radius: 10px;
  background: #fff; box-shadow: 0 5px 16px rgb(132 60 30 / 16%);
}
.brand-logo { width: 100%; height: 100%; object-fit: contain; }
.brand-text { display: flex; flex-direction: column; gap: 1px; line-height: 1; }
.brand-text small { color: #858994; font: 400 12px/1.15 'Noto Sans SC',sans-serif; letter-spacing: 2.5px; }
.brand-text strong { color: #17191e; font: 700 22px/1.1 'Noto Serif SC',serif; letter-spacing: .2px; }
.topbar-context {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 14px; background: var(--ma-gold-soft);
  border: 1px solid var(--ma-gold); border-radius: 999px; color: var(--ma-gold-dark);
}
.topbar-context .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ma-gold); }
.topbar-context span { font-size: 12px; letter-spacing: 1px; }
.topbar-context b { font-weight: 700; }
.topbar-actions { display: flex; align-items: center; gap: 10px; }

/* ============ 通用按钮（金色品牌） ============ */
.ma-btn {
  display: inline-flex; align-items: center; gap: 6px;
  height: 36px; padding: 0 16px;
  border-radius: 4px; border: 1px solid var(--ma-line);
  background: #fff; color: var(--ma-ink);
  font: 500 13px 'Noto Sans SC',sans-serif; cursor: pointer; transition: .2s;
}
.ma-btn:hover { border-color: var(--ma-gold); color: var(--ma-gold-dark); }
.ma-btn:disabled { opacity: .6; cursor: not-allowed; }
.ma-btn-primary { background: var(--ma-gold); border-color: var(--ma-gold); color: #fff; }
.ma-btn-primary:hover { background: var(--ma-gold-dark); border-color: var(--ma-gold-dark); color: #fff; }
.ma-btn.loading { pointer-events: none; opacity: .7; }

/* ============ 主体 ============ */
.predict-main-area { flex: 1; min-height: 0; display: flex; overflow: hidden; }

/* ============ 左栏 ============ */
.predict-sidebar {
  width: var(--ma-sidebar-width); flex: none;
  display: flex; flex-direction: column;
  background: var(--ma-surface); border-right: 1px solid var(--ma-line);
}
.sidebar-head { padding: 16px 18px 12px; border-bottom: 1px solid var(--ma-line); }
.sidebar-label { color: var(--ma-gold-dark); font: 600 10px/1 'JetBrains Mono',monospace; letter-spacing: 2px; margin-bottom: 6px; }
.sidebar-head h3 { font: 600 15px/1.3 'Noto Sans SC',sans-serif; margin: 0; }
.sidebar-sub { color: var(--ma-muted); font-size: 12px; margin-top: 4px; }
.sidebar-list { flex: 1; overflow-y: auto; padding: 8px; }
.sidebar-empty { color: var(--ma-muted); font-size: 13px; padding: 24px 12px; text-align: center; }
.exp-item {
  display: block; width: 100%; text-align: left;
  padding: 12px 14px; margin-bottom: 8px;
  border: 1px solid var(--ma-line); border-radius: 6px;
  background: var(--ma-surface); cursor: pointer; transition: all .2s;
  font-family: inherit;
}
.exp-item:hover { border-color: var(--ma-gold); transform: translateX(2px); }
.exp-item.active {
  border-color: var(--ma-gold);
  background: linear-gradient(135deg, var(--ma-gold-soft) 0%, #fff 100%);
  box-shadow: inset 3px 0 0 var(--ma-gold);
}
.exp-item-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 6px; }
.exp-name { font-size: 14px; font-weight: 600; color: var(--ma-ink); }
.exp-badge { flex: none; padding: 2px 6px; border-radius: 3px; font: 600 9px/1.4 'JetBrains Mono',monospace; letter-spacing: .5px; }
.exp-badge.ready { background: #e3f3ec; color: var(--ma-success); }
.exp-badge.stale { background: #fbeee0; color: var(--ma-warning); }
.exp-meta { font: 400 11px/1.5 'JetBrains Mono',monospace; color: var(--ma-muted); display: flex; gap: 10px; flex-wrap: wrap; }
.exp-meta b { color: var(--ma-ink); font-weight: 600; }

/* ============ 右栏 ============ */
.predict-content { flex: 1; overflow-y: auto; }
.predict-content-inner { max-width: 1100px; margin: 0 auto; padding: 28px 32px 60px; }

/* 空态 */
.empty-state { display: grid; place-content: center; justify-items: center; height: 100%; min-height: 400px; text-align: center; padding: 40px; }
.empty-ico { width: 72px; height: 72px; display: grid; place-items: center; border-radius: 50%; background: var(--ma-gold-soft); color: var(--ma-gold-dark); font: 600 32px 'Noto Serif SC',serif; margin-bottom: 18px; }
.empty-state h3 { font: 600 18px 'Noto Serif SC',serif; margin: 0 0 8px; }
.empty-state p { color: var(--ma-muted); font-size: 13px; max-width: 340px; margin: 0; }

/* Hero（终端风格） */
.exp-hero {
  position: relative; margin: 28px 32px 20px; padding: 24px 28px;
  background: var(--ma-terminal);
  background-image: linear-gradient(#ffffff0b 1px, transparent 1px), linear-gradient(90deg, #ffffff0b 1px, transparent 1px);
  background-size: 32px 32px;
  border-radius: 8px; color: #f5f0e6; overflow: hidden;
}
.exp-hero::after { content: ''; position: absolute; right: -40px; top: -40px; width: 220px; height: 220px; border-radius: 50%; background: radial-gradient(circle, #cdae5e20, transparent 68%); pointer-events: none; }
.exp-hero-head { display: flex; justify-content: space-between; align-items: flex-start; position: relative; z-index: 1; margin-bottom: 18px; }
.exp-hero-eyebrow { color: #c5a55a; font: 600 10px/1 'JetBrains Mono',monospace; letter-spacing: 2px; margin-bottom: 8px; }
.exp-hero h2 { font: 600 24px/1.2 'Noto Serif SC',serif; color: #fff; margin: 0; }
.exp-hero-date { color: #f5f0e680; font: 400 12px 'JetBrains Mono',monospace; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: #ffffff14; border-radius: 6px; overflow: hidden; position: relative; z-index: 1; }
.metric-cell { background: #11151d; padding: 14px 16px; }
.metric-cell small { display: block; color: #f5f0e661; font: 500 10px/1 'JetBrains Mono',monospace; letter-spacing: 1.5px; margin-bottom: 8px; }
.metric-cell strong { font: 600 22px/1 'JetBrains Mono',monospace; color: #fff; letter-spacing: -.5px; display: block; }
.metric-cell strong.pos { color: #4ade80; }
.metric-cell strong.neg { color: #f87171; }
.metric-cell p { margin: 6px 0 0; font-size: 11px; color: #f5f0e680; }

/* 操作栏 */
.action-bar { display: flex; align-items: center; gap: 12px; padding: 0 32px 8px; margin-bottom: 0; }
.action-bar .ma-btn-primary { height: 40px; padding: 0 22px; font-weight: 600; }

/* 状态条 */
.status-row { display: flex; align-items: center; gap: 14px; padding: 16px 18px; margin: 16px 32px; border-radius: 8px; }
.status-row.running { background: var(--ma-gold-soft); border: 1px solid var(--ma-gold); }
.status-row.error { background: #fdeeef; border: 1px solid var(--ma-danger); }
.status-txt { flex: 1; }
.status-txt b { display: block; font-size: 14px; color: var(--ma-gold-dark); margin-bottom: 2px; }
.status-txt small { color: var(--ma-muted); font-size: 12px; word-break: break-all; }
.status-row.error .status-txt b { color: var(--ma-danger); }
.spinner { width: 18px; height: 18px; flex: none; border: 2px solid #ffffff59; border-top-color: var(--ma-gold); border-radius: 50%; animation: ma-spin .8s linear infinite; }
.spinner-light { width: 14px; height: 14px; border: 2px solid #ffffff59; border-top-color: #fff; border-radius: 50%; animation: ma-spin .8s linear infinite; display: inline-block; }
@keyframes ma-spin { to { transform: rotate(360deg); } }

/* Top20 结果卡 */
.top20-card { margin: 0 32px; background: var(--ma-surface); border: 1px solid var(--ma-line); border-radius: 8px; overflow: hidden; box-shadow: 0 2px 12px rgb(18 21 27 / 4%); }
.top20-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--ma-line); background: var(--ma-surface-2); }
.top20-title { display: flex; align-items: baseline; gap: 10px; }
.top20-head h3 { font: 600 16px 'Noto Sans SC',sans-serif; margin: 0; }
.top20-date { font: 500 12px 'JetBrains Mono',monospace; color: var(--ma-gold-dark); background: var(--ma-gold-soft); padding: 3px 8px; border-radius: 4px; }
.top20-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.top20-table th { text-align: left; padding: 10px 20px; background: var(--ma-surface-2); color: var(--ma-muted); font: 600 11px 'JetBrains Mono',monospace; letter-spacing: 1px; border-bottom: 1px solid var(--ma-line); }
.top20-table th.center { text-align: center; }
.top20-table th.right { text-align: right; }
.top20-table td { padding: 11px 20px; border-bottom: 1px solid var(--ma-line); }
.top20-table tr:last-child td { border-bottom: 0; }
.top20-table tr:hover td { background: var(--ma-gold-soft); }
.rank { text-align: center; }
.rank-badge { display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; background: var(--ma-surface-2); color: var(--ma-muted); font: 700 13px 'JetBrains Mono',monospace; }
.rank-badge.top3 { background: var(--ma-gold); color: #fff; }
.code { font: 500 14px 'JetBrains Mono',monospace; color: var(--ma-ink); }
.score { text-align: right; font: 600 14px 'JetBrains Mono',monospace; color: var(--ma-ink); font-variant-numeric: tabular-nums; position: relative; }
.score-bar { display: block; height: 3px; margin-top: 4px; background: var(--ma-gold); border-radius: 2px; }

/* 弹窗 */
.dialog-empty { color: var(--ma-muted); font-size: 13px; padding: 24px; text-align: center; }
.history-list { max-height: 400px; overflow-y: auto; }
.history-item { display: flex; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid var(--ma-line); cursor: pointer; }
.history-item:hover { background: var(--ma-gold-soft); }
.history-date { font-weight: 500; }
.history-meta { font: 400 12px 'JetBrains Mono',monospace; color: var(--ma-muted); }
</style>
