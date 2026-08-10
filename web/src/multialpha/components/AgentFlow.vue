<template>
  <section class="agent-flow">
    <h3>多智能体协作流程</h3>
    <div class="agent-flow-row">
      <template v-for="(agent,index) in agents" :key="agent.key">
        <button
          :disabled="!agent.done && !agent.running"
          :class="{active:active===agent.key,done:agent.done,running:agent.running}"
          @click="toggleAgent(agent.key)"
        >
          <span v-if="!agent.running">{{ agent.icon }}</span>
          <span v-else class="step-spinner" />
          <b>{{ agent.name }}</b>
          <em>{{ agent.role }}</em>
          <small>{{ agentFooter(agent) }}</small>
          <i v-if="agent.done">▣ 点击查看产物</i>
          <i v-else-if="agent.running" class="running-hint">运行中…</i>
        </button>
        <span v-if="index<agents.length-1" class="agent-arrow" :class="{active:agent.done}">→</span>
      </template>
    </div>
    <div v-if="active" class="agent-product">
      <header>
        <b>{{ activeAgent?.name }}产物</b>
        <button @click="closeProduct">关闭 ×</button>
      </header>
      <div v-if="active==='hypothesis'" class="agent-product-content">
        <h4>研究假设</h4>
        <p>{{ hypothesisText||'暂无研究假设' }}</p>
        <section v-if="hypothesis?.reason">
          <b>提出理由</b>
          <p>{{ hypothesis.reason }}</p>
        </section>
      </div>
      <div v-else-if="active==='design'" class="agent-product-content factor-product">
        <article v-for="factor in factors" :key="factor.name">
          <b>{{ factor.name }}</b>
          <p>{{ factor.description }}</p>
          <FormulaBlock v-if="factor.formula" :formula="factor.formula"/>
        </article>
      </div>
      <div v-else-if="active==='coding'" class="agent-product-content code-product">
        <div v-for="file in codes" :key="`${file.target}-${file.name}`">
          <b>{{ file.target||file.name }} · {{ file.name }}</b>
          <pre>{{ file.content }}</pre>
        </div>
      </div>
      <div v-else-if="active==='backtest'" class="agent-product-content metric-product">
        <article v-for="(value,key) in metricValues" :key="key">
          <small>{{ key }}</small>
          <b>{{ value }}</b>
        </article>
      </div>
      <div v-else class="agent-product-content">
        <span class="decision-chip" :class="feedback.decision?'accepted':'rejected'">{{ feedback.decision?'✓ 已采纳':'✕ 未采纳' }}</span>
        <section v-for="item in feedbackItems" :key="item.label">
          <b>{{ item.label }}</b>
          <p>{{ item.value }}</p>
        </section>
      </div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed,ref,watch } from 'vue'
import FormulaBlock from './FormulaBlock.vue'
import type { AgentStep, CodeFile, FactorItem, FeedbackSummary, TraceMessage, TraceStatus } from '../types'

const props = defineProps<{
  messages: TraceMessage[]
  factors: FactorItem[]
  codes: CodeFile[]
  metricValues: Record<string, number | string>
  feedback: FeedbackSummary
  hypothesis: Record<string, unknown> | null
  status?: TraceStatus
  currentStep?: AgentStep
}>()

const active = ref('')
let userClosed = false

const agents = computed(() => [
  {
    key: 'hypothesis', name: '假设生成', role: '研究员', icon: '🧠',
    done: !!props.hypothesis, running: props.currentStep === 'hypothesis',
    stat: '',
  },
  {
    key: 'design', name: '实验设计', role: '设计师', icon: '✏️',
    done: !!props.factors.length, running: props.currentStep === 'design',
    stat: props.factors.length ? `${props.factors.length} 因子` : '',
  },
  {
    key: 'coding', name: '代码实现', role: '编码员', icon: '▰',
    done: !!props.codes.length, running: props.currentStep === 'coding',
    stat: props.codes.length ? `${props.codes.length} 文件` : '',
  },
  {
    key: 'backtest', name: '回测执行', role: '执行员', icon: '📊',
    done: props.metricValues.IC != null, running: props.currentStep === 'backtest',
    stat: props.metricValues.IC != null ? `IC=${Number(props.metricValues.IC).toFixed(3)}` : '',
  },
  {
    key: 'feedback', name: '反馈评审', role: '评审员', icon: '🔍',
    done: props.feedback.decision !== null, running: props.currentStep === 'feedback',
    stat: props.feedback.decision === null ? '' : props.feedback.decision ? '已采纳' : '已拒绝',
  },
])

const activeAgent = computed(() => agents.value.find(a => a.key === active.value))
const hypothesisText = computed(() => String(props.hypothesis?.hypothesis || props.hypothesis?.concise_observation || ''))
const feedbackItems = computed(() => [
  { label: '决定理由', value: props.feedback.reason },
  { label: '实验观察', value: props.feedback.observations },
  { label: '假设评估', value: props.feedback.evaluation },
  { label: '下一轮新假设', value: props.feedback.newHypothesis },
  { label: '异常信息', value: props.feedback.exception },
].filter(item => item.value))

function agentFooter(agent: { done: boolean; running: boolean; stat: string }) {
  if (agent.done) return `✓ 完成${agent.stat ? ' · ' + agent.stat : ''}`
  if (agent.running) return '⏳ 正在执行…'
  if (props.status === 'running') return '○ 等待中'
  return '○ 待启动'
}

function toggleAgent(key: string) {
  if (active.value === key) {
    active.value = ''
    userClosed = true
  } else {
    active.value = key
    userClosed = false
  }
}

function closeProduct() {
  active.value = ''
  userClosed = true
}

watch(() => props.currentStep, (step, oldStep) => {
  if (step && step !== oldStep && !userClosed) {
    active.value = step
  }
}, { immediate: true })
</script>
<style scoped>
.step-spinner{
  width:20px;height:20px;
  border:2.5px solid var(--ma-gold-soft);
  border-top-color:var(--ma-gold);
  border-radius:50%;
  animation:step-spin .7s linear infinite;
}
@keyframes step-spin{to{transform:rotate(360deg)}}
.agent-flow-row button.running{
  border-color:var(--ma-gold);
  background:linear-gradient(135deg,var(--ma-gold-soft),#fff);
  box-shadow:0 0 0 2px var(--ma-gold-soft),0 2px 12px rgba(200,163,91,.2);
  animation:step-pulse 2s ease-in-out infinite;
}
@keyframes step-pulse{
  0%,100%{box-shadow:0 0 0 2px var(--ma-gold-soft),0 2px 12px rgba(200,163,91,.2)}
  50%{box-shadow:0 0 0 4px rgba(200,163,91,.15),0 4px 18px rgba(200,163,91,.3)}
}
.agent-flow-row button.running small{color:var(--ma-gold-dark);font-weight:600}
.running-hint{color:var(--ma-gold-dark)!important;font-style:italic;font-size:9px;animation:text-blink 1.4s ease-in-out infinite}
@keyframes text-blink{0%,100%{opacity:1}50%{opacity:.4}}
.agent-arrow.active{color:var(--ma-gold-dark);font-weight:700}
</style>
