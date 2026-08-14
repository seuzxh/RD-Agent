<template>
  <section class="round-agent-flow">
    <h3>{{ title }}</h3>
    <div v-if="!agents.length" class="raf-empty">暂无轮次数据</div>
    <template v-else>
      <div class="raf-row">
        <template v-for="(agent, index) in agents" :key="agent.key">
          <button
            class="raf-agent"
            :class="[statusOf(agent).code, { active: active === agent.key }]"
            :disabled="!canOpen(agent)"
            @click="toggle(agent)"
          >
            <span class="raf-icon">{{ agent.icon }}</span>
            <b>{{ agent.name }}</b>
            <em>{{ agent.role }}</em>
            <small class="raf-status">
              {{ statusOf(agent).label }}
              <i v-if="statusOf(agent).code === 'failed'" class="raf-err" :title="statusOf(agent).error">{{ failedHint }}</i>
            </small>
            <i v-if="statusOf(agent).code === 'completed'" class="raf-open">▣ 点击查看产物</i>
          </button>
          <span v-if="index < agents.length - 1" class="raf-arrow">→</span>
        </template>
      </div>

      <div v-if="activeAgent" class="raf-product">
        <header><b>{{ activeAgent.name }}产物</b><button @click="active = ''">关闭 ×</button></header>
        <div v-if="activeAgent.product === 'hypothesis'" class="raf-body">
          <h4>研究假设</h4>
          <p>{{ experiment?.hypothesis_text || '暂无研究假设' }}</p>
        </div>
        <div v-else-if="activeAgent.product === 'design'" class="raf-body">
          <h4>实验设计</h4>
          <p v-if="experiment?.type">{{ roundKindLabel }} · {{ roundType }}</p>
          <p v-if="experiment?.hypothesis_reason" class="raf-muted">{{ experiment.hypothesis_reason }}</p>
          <p v-if="experiment?.hypothesis_assumption" class="raf-muted">{{ experiment.hypothesis_assumption }}</p>
          <p v-if="!experiment" class="raf-muted">暂无实验设计信息</p>
        </div>
        <div v-else-if="activeAgent.product === 'code'" class="raf-body">
          <template v-if="codes.length">
            <label v-if="codes.length > 1" class="raf-code-sel">选择{{ roundCodeNoun }}<select v-model="selectedCode"><option v-for="c in codes" :key="c.name" :value="c.name">{{ c.name }}</option></select></label>
            <pre class="raf-code-block"><code>{{ selectedCodeContent }}</code></pre>
          </template>
          <p v-else class="raf-muted">暂无{{ roundCodeNoun }}代码</p>
        </div>
        <div v-else-if="activeAgent.product === 'metrics'" class="raf-body raf-metric">
          <article v-for="item in metrics" :key="item.label">
            <small>{{ item.label }}</small>
            <b>{{ formatMetric(item) }}</b>
          </article>
          <p v-if="!metrics.length" class="raf-muted">本轮暂无指标数据</p>
        </div>
        <div v-else-if="activeAgent.product === 'feedback'" class="raf-body">
          <span v-if="experiment?.decision != null" class="raf-chip" :class="experiment.decision ? 'accepted' : 'rejected'">{{ experiment.decision ? '✓ SOTA' : '✕ 拒绝' }}</span>
          <section v-for="item in feedbackItems" :key="item.label">
            <b>{{ item.label }}</b>
            <p>{{ item.value || '—' }}</p>
          </section>
        </div>
        <div v-else class="raf-body raf-muted">本轮流程记录</div>
      </div>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { AGENT_DEFS, type RoundAgentDef, type RoundType } from '../livelab-model'
import type { CodeFile, FactorItem, MetricItem } from '../types'

const props = defineProps<{
  roundType?: RoundType
  nodes: any[]
  experiment: Record<string, any> | null
  codes: CodeFile[]
  metrics: MetricItem[]
  factors?: FactorItem[]
}>()

const active = ref('')
const selectedCode = ref('')

const agents = computed<RoundAgentDef[]>(() => (props.roundType ? AGENT_DEFS[props.roundType] : []))
const isModel = computed(() => props.roundType === 'model')
const title = computed(() => (isModel.value ? '模型轮 Agent 流程' : '因子轮 Agent 流程'))
const roundKindLabel = computed(() => (isModel.value ? '模型轮' : '因子轮'))
const roundCodeNoun = computed(() => (isModel.value ? '模型' : '因子'))

const selectedCodeContent = computed(() =>
  props.codes.find(c => c.name === selectedCode.value)?.content || props.codes[0]?.content || '',
)

function nodeOf(agent: RoundAgentDef): any {
  return props.nodes.find(n => n.step_name === agent.step)
}

function statusOf(agent: RoundAgentDef): { code: 'pending' | 'running' | 'completed' | 'failed'; label: string; error: string } {
  const node = nodeOf(agent)
  if (!node) return { code: 'pending', label: '○ 待启动', error: '' }
  switch (node.status) {
    case 'running': return { code: 'running', label: '● 进行中', error: '' }
    case 'completed': return { code: 'completed', label: '✓ 完成', error: '' }
    case 'failed': return { code: 'failed', label: '✕ 失败', error: node.error_message || '' }
    default: return { code: 'pending', label: '○ 待启动', error: '' }
  }
}

const failedHint = computed(() => '↑ 失败原因')

function canOpen(agent: RoundAgentDef): boolean {
  if (agent.product === 'record') return false
  return statusOf(agent).code === 'completed'
}

function toggle(agent: RoundAgentDef) {
  active.value = active.value === agent.key ? '' : agent.key
}

const activeAgent = computed(() => agents.value.find(a => a.key === active.value))

const feedbackItems = computed(() => [
  { label: '决定理由', value: props.experiment?.decision_reason || '' },
  { label: '实验观察', value: props.experiment?.observations || '' },
].filter(item => item.value))

function formatMetric(item: MetricItem): string {
  if (item.rawValue == null) return String(item.value)
  if (item.percent) return `${(item.rawValue * 100).toFixed(2)}%`
  return item.rawValue.toFixed(4)
}
</script>
<style scoped>
.round-agent-flow { margin-bottom: 16px; }
.round-agent-flow h3 { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #303133; }
.raf-row { display: flex; gap: 6px; flex-wrap: wrap; align-items: stretch; }
.raf-agent { flex: 1 1 120px; min-width: 120px; display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--ma-line, #e4e7ed); background: #fff; text-align: left; cursor: pointer; }
.raf-agent:disabled { cursor: not-allowed; }
.raf-agent .raf-icon { font-size: 16px; }
.raf-agent b { font-size: 13px; }
.raf-agent em { font-size: 11px; color: #909399; font-style: normal; }
.raf-status { font-size: 12px; }
.raf-status i { font-style: normal; }
.raf-agent.pending .raf-status { color: #909399; }
.raf-agent.running { border-color: #409eff; background: #e6f0ff; }
.raf-agent.running .raf-status { color: #409eff; }
.raf-agent.completed { border-color: #67c23a; background: #f0f9eb; }
.raf-agent.completed .raf-status { color: #67c23a; }
.raf-agent.failed { border-color: #f56c6c; background: #fef0f0; }
.raf-agent.failed .raf-status { color: #f56c6c; }
.raf-open { font-size: 11px; color: #b7842a; display: block; }
.raf-err { color: #f56c6c; }
.raf-arrow { align-self: center; color: #c0c4cc; }
.raf-empty { color: #909399; font-size: 12px; padding: 12px; }
.raf-product { margin-top: 10px; padding: 12px; border: 1px solid var(--ma-line, #e4e7ed); border-radius: 6px; background: #fafafa; }
.raf-product header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.raf-product header b { font-size: 13px; }
.raf-product header button { border: none; background: none; color: #909399; cursor: pointer; font-size: 12px; }
.raf-body { font-size: 13px; }
.raf-body h4 { font-size: 12px; color: #909399; margin: 6px 0; }
.raf-body p { margin: 4px 0; }
.raf-muted { color: #909399; }
.raf-chip { display: inline-block; padding: 2px 8px; border-radius: 9px; font-size: 12px; font-weight: 600; margin-bottom: 8px; }
.raf-chip.accepted { background: #f0f9eb; color: #67c23a; }
.raf-chip.rejected { background: #fef0f0; color: #f56c6c; }
.raf-code-sel { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #606266; margin-bottom: 8px; }
.raf-code-sel select { padding: 4px 8px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 13px; }
.raf-code-block { max-height: 320px; overflow: auto; background: #1e1e1e; color: #d4d4d4; border-radius: 6px; padding: 12px; font-size: 12px; line-height: 1.5; white-space: pre; }
.raf-code-block code { font-family: Consolas, 'Courier New', monospace; }
.raf-metric { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
.raf-metric article { background: #fff; border: 1px solid var(--ma-line, #e4e7ed); border-radius: 6px; padding: 8px 10px; }
.raf-metric article small { display: block; font-size: 11px; color: #909399; }
.raf-metric article b { font-size: 14px; }
.raf-body section { margin-top: 8px; }
.raf-body section b { display: block; font-size: 12px; color: #606266; margin-bottom: 2px; }
</style>