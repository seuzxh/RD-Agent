<template>
  <div class="roundtable-shell">
    <header class="topbar">
      <a class="brand" href="./multialpha.html" aria-label="返回 MultiAlpha">
        <span class="brand-logo-frame">
          <img class="brand-logo" src="https://h5.crsec.com.cn/logo.png" alt="国新证券" />
        </span>
        <span class="brand-copy">
          <strong>AI 投研圆桌</strong>
        </span>
      </a>
      <div class="topbar-center">
        <span class="live-dot"></span>
        <span>六维协作诊股系统</span>
      </div>
    </header>

    <main class="workspace">
      <section class="hero">
        <div class="hero-copy">
          <h1>六维视角，<em>共研一只股票。</em></h1>
          <p>汇总基本面、消息、资金、技术、评级与研报六个维度的既有观点。</p>
        </div>

        <div class="search-console" :class="{ 'has-selection': selectedStock }">
          <div class="console-index">01 / 选择研究标的</div>
          <label for="stock-select">搜索股票</label>
          <div class="search-row">
            <el-select
              id="stock-select"
              v-model="selectedStockId"
              class="stock-select"
              filterable
              remote
              clearable
              reserve-keyword
              :remote-method="queueStockSearch"
              :loading="searchLoading"
              :no-data-text="searchError || '未找到匹配标的'"
              placeholder="例如：600988 或 赤峰黄金"
              @change="handleStockChange"
            >
              <el-option
                v-for="stock in stockOptions"
                :key="stock.id"
                :label="`${stock.code}  ${stock.name}`"
                :value="stock.id"
              >
                <div class="stock-option">
                  <span class="stock-option-code">{{ stock.code }}</span>
                  <strong>{{ stock.name }}</strong>
                  <small v-if="stock.marketLabel">{{ stock.marketLabel }}</small>
                </div>
              </el-option>
            </el-select>
            <button
              class="consult-button"
              :disabled="!selectedStock || isAnalyzing"
              @click="startConsultation"
            >
              <span v-if="isAnalyzing" class="button-spinner"></span>
              <span>{{ isAnalyzing ? '读取观点中' : hasStarted ? '刷新分析' : '查看分析' }}</span>
              <b aria-hidden="true">↗</b>
            </button>
          </div>
          <div class="console-foot">
            <span>读取六个维度已生成的分析结果</span>
            <span v-if="selectedStock" class="selected-target">
              已选 · {{ selectedStock.name }} / {{ selectedStock.code }}
            </span>
          </div>
        </div>
      </section>

      <section v-if="selectedStock" class="stock-focus-bar">
        <div class="stock-focus-title">
          <span class="section-number">02</span>
          <div>
            <h2>
              {{ selectedStock.name }}
              <em>{{ selectedStock.code }}<span v-if="selectedStock.marketLabel"> · {{ selectedStock.marketLabel }}</span></em>
            </h2>
          </div>
        </div>
        <div class="opinion-summary">
          <div class="opinion-summary-head">
            <small>六智能体观点汇总</small>
          </div>
          <div v-if="opinionItems.length" class="opinion-summary-copy">
            <template v-for="(item, index) in opinionItems" :key="item.key">
              <strong :class="item.key">{{ item.count }} {{ item.label }}</strong>
              <i v-if="index < opinionItems.length - 1">·</i>
            </template>
          </div>
          <div v-else class="opinion-summary-empty">
            {{ isAnalyzing ? '观点读取中…' : '暂无有效观点' }}
          </div>
          <div class="opinion-ratio-bar" aria-label="六智能体观点比例">
            <span
              v-for="item in opinionDistribution"
              :key="item.key"
              :class="item.key"
              :style="{ width: `${item.percent}%` }"
            ></span>
          </div>
        </div>
        <div class="stock-quote">
          <div>
            <small>最新价</small>
            <strong>{{ formatPrice(selectedStock.latestPrice) }}</strong>
          </div>
          <div>
            <small>涨跌</small>
            <strong :class="changeTone(selectedStock.changePercent)">
              {{ formatChange(selectedStock.changePercent) }}
            </strong>
          </div>
        </div>
      </section>

      <section class="agents-section">
        <div class="section-heading">
          <div class="section-title">
            <span class="section-number">{{ selectedStock ? '03' : '02' }}</span>
            <div>
              <h2>六维智能体观点</h2>
            </div>
          </div>
          <p>独立取数 · 平行判断 · 各自结论</p>
        </div>

        <div class="agent-grid">
          <article
            v-for="(agent, index) in AGENTS"
            :key="agent.id"
            class="agent-card"
            :class="[`state-${agentStates[agent.id].status}`, analysisDirectionClass(agent.id)]"
            :style="{ '--agent-accent': agent.accent, '--reveal-delay': `${index * 65}ms` }"
          >
            <header class="agent-head">
              <div class="agent-portrait">
                <span>{{ agent.monogram }}</span>
                <i></i>
              </div>
              <div class="agent-identity">
                <small>{{ String(agent.id).padStart(2, '0') }} · {{ agent.dimension }}</small>
                <h3>{{ agent.name }}</h3>
              </div>
              <div
                v-if="agentStates[agent.id].analysis"
                class="direction-badge"
                :class="agentStates[agent.id].analysis?.direction"
              >
                {{ directionLabel(agentStates[agent.id].analysis?.direction) }}
              </div>
              <div v-else class="agent-status" :class="agentStates[agent.id].status">
                {{ statusLabel(agentStates[agent.id].status) }}
              </div>
            </header>

            <div v-if="agentStates[agent.id].status === 'loading'" class="agent-loading">
              <div class="thinking-orbit">
                <span></span><span></span><span></span>
              </div>
              <strong>Thinking...</strong>
              <p>正在读取{{ agent.dimension }}分析结果</p>
              <div class="skeleton-line wide"></div>
              <div class="skeleton-line"></div>
              <div class="skeleton-line short"></div>
            </div>

            <div v-else-if="agentStates[agent.id].status === 'error'" class="agent-error">
              <span>!</span>
              <strong>分析结果加载失败</strong>
              <p>{{ agentStates[agent.id].error }}</p>
              <button @click="retryAgent(agent)">重新加载</button>
            </div>

            <div
              v-else-if="agentStates[agent.id].status === 'success' && agentStates[agent.id].analysis"
              class="analysis-content"
            >
              <section class="view-block">
                <div class="block-label">核心观点</div>
                <ol>
                  <li
                    v-for="(view, viewIndex) in agentStates[agent.id].analysis?.coreViews"
                    :key="viewIndex"
                  >
                    <b>{{ String(viewIndex + 1).padStart(2, '0') }}</b>
                    <span>{{ view }}</span>
                  </li>
                </ol>
                <p v-if="!agentStates[agent.id].analysis?.coreViews.length" class="empty-copy">
                  暂无核心观点明细
                </p>
              </section>
              <section class="risk-block">
                <div class="block-label">风险提示</div>
                <p>{{ agentStates[agent.id].analysis?.risk || '本次分析未提供额外风险提示。' }}</p>
              </section>
              <blockquote>
                <span>结论</span>
                {{ agentStates[agent.id].analysis?.summary || '本次分析暂无总结。' }}
              </blockquote>
              <footer v-if="agentStates[agent.id].analysis?.createdAt">
                数据生成于 {{ agentStates[agent.id].analysis?.createdAt }}
              </footer>
            </div>

            <div v-else class="agent-idle">
              <span class="idle-mark">{{ agent.monogram }}</span>
              <strong>暂无分析</strong>
              <p>选择股票后查看{{ agent.dimension }}已有观点。</p>
            </div>
          </article>
        </div>
      </section>

      <footer class="disclaimer">
        <span>AI</span>
        <p>以上内容由人工智能基于公开及授权数据生成，仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。</p>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { AGENTS } from './agents'
import { analyzeStock, searchStocks } from './api'
import type {
  AgentDefinition,
  AgentDirection,
  AgentResultState,
  AgentResultStatus,
  StockOption,
} from './types'

const selectedStockId = ref('')
const selectedStock = ref<StockOption | null>(null)
const stockOptions = ref<StockOption[]>([])
const searchLoading = ref(false)
const searchError = ref('')
const hasStarted = ref(false)

const agentStates = reactive<Record<number, AgentResultState>>(
  Object.fromEntries(
    AGENTS.map((agent) => [
      agent.id,
      { status: 'idle', analysis: null, error: '' } satisfies AgentResultState,
    ]),
  ),
)

let searchTimer: number | undefined
let searchController: AbortController | null = null
let searchGeneration = 0
let consultationGeneration = 0
const agentControllers = new Map<number, AbortController>()

const isAnalyzing = computed(() => AGENTS.some((agent) => agentStates[agent.id].status === 'loading'))
const opinionDistribution = computed(() => {
  const definitions: Array<{ key: AgentDirection; label: string }> = [
    { key: 'positive', label: '积极' },
    { key: 'neutral', label: '中立' },
    { key: 'negative', label: '消极' },
  ]
  const successfulAnalyses = AGENTS
    .map((agent) => agentStates[agent.id].analysis)
    .filter((analysis) => analysis !== null)
  const total = successfulAnalyses.length

  return definitions.map((definition) => {
    const count = successfulAnalyses.filter((analysis) => analysis.direction === definition.key).length
    return {
      ...definition,
      count,
      percent: total ? (count / total) * 100 : 0,
    }
  })
})
const opinionItems = computed(() => opinionDistribution.value.filter((item) => item.count > 0))

function formatPrice(value: string): string {
  if (!value.trim()) return '—'
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed.toFixed(2) : '—'
}

function formatChange(value: string): string {
  const parsed = Number.parseFloat(value)
  if (!Number.isFinite(parsed)) return '—'
  if (parsed > 0) return `+${parsed.toFixed(2)}%`
  return `${parsed.toFixed(2)}%`
}

function changeTone(value: string): 'up' | 'down' | 'flat' {
  const parsed = Number.parseFloat(value)
  if (!Number.isFinite(parsed) || parsed === 0) return 'flat'
  return parsed > 0 ? 'up' : 'down'
}

function queueStockSearch(keyword: string): void {
  const generation = ++searchGeneration
  window.clearTimeout(searchTimer)
  searchController?.abort()
  searchController = null
  searchLoading.value = false
  searchError.value = ''
  const normalizedKeyword = keyword.trim()
  if (!normalizedKeyword) {
    stockOptions.value = selectedStock.value ? [selectedStock.value] : []
    searchLoading.value = false
    return
  }

  searchTimer = window.setTimeout(async () => {
    if (generation !== searchGeneration) return
    const controller = new AbortController()
    searchController = controller
    searchLoading.value = true
    try {
      stockOptions.value = await searchStocks(normalizedKeyword, controller.signal)
    } catch (error) {
      if (controller.signal.aborted) return
      stockOptions.value = []
      searchError.value = error instanceof Error ? error.message : '股票搜索失败'
    } finally {
      if (searchController === controller && generation === searchGeneration) {
        searchLoading.value = false
        searchController = null
      }
    }
  }, 500)
}

function resetAgentStates(): void {
  AGENTS.forEach((agent) => {
    agentStates[agent.id] = { status: 'idle', analysis: null, error: '' }
  })
}

function abortAnalysis(): void {
  consultationGeneration += 1
  agentControllers.forEach((controller) => controller.abort())
  agentControllers.clear()
}

function handleStockChange(stockId: string): void {
  abortAnalysis()
  selectedStock.value = stockOptions.value.find((stock) => stock.id === stockId) || null
  hasStarted.value = false
  resetAgentStates()
}

async function runAgent(agent: AgentDefinition, generation: number): Promise<void> {
  if (!selectedStock.value) return
  agentControllers.get(agent.id)?.abort()
  const controller = new AbortController()
  agentControllers.set(agent.id, controller)
  agentStates[agent.id] = { status: 'loading', analysis: null, error: '' }
  try {
    const analysis = await analyzeStock(agent.id, selectedStock.value.code, controller.signal)
    if (generation !== consultationGeneration || controller.signal.aborted) return
    agentStates[agent.id] = { status: 'success', analysis, error: '' }
  } catch (error) {
    if (generation !== consultationGeneration || controller.signal.aborted) return
    agentStates[agent.id] = {
      status: 'error',
      analysis: null,
      error: error instanceof Error ? error.message : '智能体分析失败',
    }
  } finally {
    if (agentControllers.get(agent.id) === controller) {
      agentControllers.delete(agent.id)
    }
  }
}

async function startConsultation(): Promise<void> {
  if (!selectedStock.value) return
  abortAnalysis()
  hasStarted.value = true
  const generation = consultationGeneration
  await Promise.allSettled(AGENTS.map((agent) => runAgent(agent, generation)))
}

function retryAgent(agent: AgentDefinition): void {
  if (!selectedStock.value) return
  void runAgent(agent, consultationGeneration)
}

function directionLabel(direction?: AgentDirection): string {
  return direction === 'positive' ? '↑ 积极' : direction === 'neutral' ? '中立' : direction === 'negative' ? '↓ 消极' : ''
}

function statusLabel(status: AgentResultStatus): string {
  if (status === 'loading') return '分析中'
  if (status === 'error') return '异常'
  return '暂无内容'
}

function analysisDirectionClass(agentId: number): string {
  const direction = agentStates[agentId].analysis?.direction
  return direction ? `vote-${direction}` : ''
}

onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
  searchController?.abort()
  abortAnalysis()
})
</script>
