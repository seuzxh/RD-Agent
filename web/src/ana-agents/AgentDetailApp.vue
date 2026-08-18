<template>
  <div class="roundtable-shell detail-page">
    <header class="topbar">
      <a class="brand" href="./ana-agents.html" aria-label="返回 AI 投研圆桌">
        <span class="brand-logo-frame">
          <img class="brand-logo" src="https://h5.crsec.com.cn/logo.png" alt="国新证券" />
        </span>
        <span class="brand-copy"><strong>AI 投研圆桌</strong></span>
      </a>
      <div class="topbar-center">
        <span class="live-dot"></span>
        <span>六维协作诊股系统</span>
      </div>
      <div class="detail-topbar-mark">智能体观点详情</div>
    </header>

    <main class="detail-workspace">
      <nav class="detail-breadcrumb" aria-label="页面导航">
        <button type="button" @click="goBack">← 返回观点总览</button>
        <span>/</span>
        <strong>{{ currentAgent?.dimension || '智能体' }}分析</strong>
      </nav>

      <section v-if="currentAgent && stockCode" class="detail-subject" :style="agentAccentStyle">
        <div class="detail-agent">
          <span class="detail-agent-mark">{{ currentAgent.monogram }}</span>
          <div>
            <small>{{ String(currentAgent.id).padStart(2, '0') }} · {{ currentAgent.dimension }}</small>
            <h1>{{ currentAgent.name }}</h1>
          </div>
        </div>
        <div class="detail-stock">
          <small>当前研究标的</small>
          <h2>{{ displayStockName }} <em>{{ stockCode }}<span v-if="quote?.marketLabel"> · {{ quote.marketLabel }}</span></em></h2>
        </div>
        <div class="detail-quote">
          <div>
            <small>最新价</small>
            <strong>{{ formatPrice(quote?.latestPrice || '') }}</strong>
          </div>
          <div>
            <small>涨跌</small>
            <strong :class="changeTone(quote?.changePercent || '')">
              {{ formatChange(quote?.changePercent || '') }}
            </strong>
          </div>
        </div>
        <span v-if="analysis" class="detail-direction" :class="analysis.direction">
          {{ directionLabel(analysis.direction) }}
        </span>
      </section>

      <section v-if="status === 'loading'" class="detail-loading" :style="agentAccentStyle">
        <div class="thinking-orbit"><span></span><span></span><span></span></div>
        <strong>Thinking...</strong>
        <p>正在读取{{ currentAgent?.dimension || '' }}分析结果</p>
        <div class="detail-loading-lines">
          <i></i><i></i><i></i><i></i>
        </div>
      </section>

      <section v-else-if="status === 'error'" class="detail-error">
        <span>!</span>
        <h2>观点详情加载失败</h2>
        <p>{{ errorMessage }}</p>
        <div>
          <button v-if="canRetry" type="button" @click="loadDetail(true)">重新加载</button>
          <button type="button" class="secondary" @click="goBack">返回总览</button>
        </div>
      </section>

      <template v-else-if="status === 'success' && analysis && currentAgent">
        <div class="detail-content" :style="agentAccentStyle">
          <article class="detail-core-views">
            <header>
              <span>核心观点</span>
              <small>共 {{ analysis.coreViews.length }} 条</small>
            </header>
            <ol v-if="analysis.coreViews.length">
              <li v-for="(view, index) in analysis.coreViews" :key="index">
                <b>{{ String(index + 1).padStart(2, '0') }}</b>
                <p>{{ view }}</p>
              </li>
            </ol>
            <p v-else class="detail-empty-copy">暂无核心观点明细</p>
          </article>

          <aside class="detail-aside">
            <section class="detail-summary-card">
              <small>结论</small>
              <p>{{ analysis.summary || '本次分析暂无总结。' }}</p>
            </section>
            <section class="detail-risk-card">
              <small>风险提示</small>
              <p>{{ analysis.risk || '本次分析未提供额外风险提示。' }}</p>
            </section>
            <section class="detail-meta-card">
              <dl>
                <div><dt>分析维度</dt><dd>{{ currentAgent.dimension }}</dd></div>
                <div><dt>观点方向</dt><dd :class="analysis.direction">{{ directionLabel(analysis.direction) }}</dd></div>
                <div><dt>数据生成时间</dt><dd>{{ analysis.createdAt || '—' }}</dd></div>
              </dl>
            </section>
          </aside>
        </div>

      </template>

      <template v-if="currentAgent && stockCode">
        <nav class="agent-navigator" aria-label="切换智能体">
          <button
            v-for="agent in AGENTS"
            :key="agent.id"
            type="button"
            :class="{ active: agent.id === currentAgent.id }"
            :style="{ '--nav-accent': agent.accent }"
            :aria-current="agent.id === currentAgent.id ? 'page' : undefined"
            @click="navigateToAgent(agent.id)"
          >
            <span>{{ agent.monogram }}</span>
            <div><small>{{ agent.dimension }}</small><strong>{{ agent.name }}</strong></div>
          </button>
        </nav>

        <div class="detail-pager">
          <button type="button" @click="navigateToAgent(previousAgent.id)">
            ← {{ previousAgent.name }} · {{ previousAgent.dimension }}
          </button>
          <button type="button" @click="navigateToAgent(nextAgent.id)">
            {{ nextAgent.name }} · {{ nextAgent.dimension }} →
          </button>
        </div>
      </template>

      <footer class="disclaimer detail-disclaimer">
        <span>AI</span>
        <p>以上内容由人工智能基于公开及授权数据生成，仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。</p>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AGENTS } from './agents'
import { analyzeStock, searchStocks } from './api'
import type { AgentAnalysis, AgentDirection, StockOption } from './types'

type DetailStatus = 'loading' | 'success' | 'error'

const agentId = ref(0)
const stockCode = ref('')
const requestedStockName = ref('')
const requestedMarketLabel = ref('')
const analysis = ref<AgentAnalysis | null>(null)
const quote = ref<StockOption | null>(null)
const status = ref<DetailStatus>('loading')
const errorMessage = ref('')
const canRetry = ref(true)
let loadGeneration = 0
let requestController: AbortController | null = null

const currentAgent = computed(() => AGENTS.find((agent) => agent.id === agentId.value) || null)
const currentAgentIndex = computed(() => Math.max(0, AGENTS.findIndex((agent) => agent.id === agentId.value)))
const previousAgent = computed(() => AGENTS[(currentAgentIndex.value - 1 + AGENTS.length) % AGENTS.length])
const nextAgent = computed(() => AGENTS[(currentAgentIndex.value + 1) % AGENTS.length])
const displayStockName = computed(() => quote.value?.name || analysis.value?.stockName || requestedStockName.value || '股票')
const agentAccentStyle = computed(() => ({ '--agent-accent': currentAgent.value?.accent || '#8d7650' }))

function readLocation(): boolean {
  const params = new URLSearchParams(window.location.search)
  const nextAgentId = Number(params.get('agentId'))
  const nextStockCode = (params.get('stockCode') || '').trim()
  agentId.value = nextAgentId
  stockCode.value = nextStockCode
  requestedStockName.value = (params.get('stockName') || '').trim()
  requestedMarketLabel.value = (params.get('marketLabel') || '').trim()
  return Boolean(AGENTS.some((agent) => agent.id === nextAgentId) && nextStockCode)
}

function findQuote(options: StockOption[]): StockOption | null {
  const exactCode = options.filter((item) => item.code === stockCode.value)
  return exactCode.find((item) =>
    item.name === requestedStockName.value &&
    (!requestedMarketLabel.value || item.marketLabel === requestedMarketLabel.value)
  ) || exactCode.find((item) => item.name === requestedStockName.value) || exactCode[0] || null
}

async function loadQuote(generation: number, signal: AbortSignal): Promise<void> {
  try {
    const options = await searchStocks(stockCode.value, signal)
    if (generation === loadGeneration && !signal.aborted) quote.value = findQuote(options)
  } catch {
    if (generation === loadGeneration && !signal.aborted) quote.value = null
  }
}

async function loadDetail(forceRefresh = false): Promise<void> {
  requestController?.abort()
  const generation = ++loadGeneration
  const controller = new AbortController()
  requestController = controller
  analysis.value = null
  errorMessage.value = ''
  canRetry.value = true
  if (!readLocation()) {
    status.value = 'error'
    canRetry.value = false
    errorMessage.value = '详情参数不完整，请返回观点总览重新选择。'
    return
  }
  status.value = 'loading'
  if (!quote.value || quote.value.code !== stockCode.value) {
    quote.value = null
    void loadQuote(generation, controller.signal)
  }
  try {
    const result = await analyzeStock(agentId.value, stockCode.value, controller.signal, forceRefresh)
    if (generation !== loadGeneration || controller.signal.aborted) return
    analysis.value = result
    status.value = 'success'
    document.title = `${result.stockName || requestedStockName.value || stockCode.value} · ${currentAgent.value?.name || ''} | AI 投研圆桌`
  } catch (error) {
    if (generation !== loadGeneration || controller.signal.aborted) return
    status.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '智能体分析加载失败'
  } finally {
    if (requestController === controller) requestController = null
  }
}

function navigateToAgent(nextAgentId: number): void {
  if (nextAgentId === agentId.value) return
  const params = new URLSearchParams(window.location.search)
  params.set('agentId', String(nextAgentId))
  window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`)
  void loadDetail()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function goBack(): void {
  const referrer = document.referrer ? new URL(document.referrer) : null
  if (referrer?.origin === window.location.origin && referrer.pathname.endsWith('/ana-agents.html')) {
    window.history.back()
  } else {
    window.location.href = './ana-agents.html'
  }
}

function directionLabel(direction: AgentDirection): string {
  return direction === 'positive' ? '↑ 积极' : direction === 'neutral' ? '中立' : '↓ 消极'
}

function formatPrice(value: string): string {
  const parsed = Number(value)
  return value.trim() && Number.isFinite(parsed) ? parsed.toFixed(2) : '—'
}

function formatChange(value: string): string {
  const parsed = Number.parseFloat(value)
  if (!Number.isFinite(parsed)) return '—'
  return `${parsed > 0 ? '+' : ''}${parsed.toFixed(2)}%`
}

function changeTone(value: string): 'up' | 'down' | 'flat' {
  const parsed = Number.parseFloat(value)
  if (!Number.isFinite(parsed) || parsed === 0) return 'flat'
  return parsed > 0 ? 'up' : 'down'
}

function handlePopState(): void {
  void loadDetail()
}

onMounted(() => {
  window.addEventListener('popstate', handlePopState)
  void loadDetail()
})

onBeforeUnmount(() => {
  requestController?.abort()
  window.removeEventListener('popstate', handlePopState)
})
</script>
