<template>
  <section class="agent-flow">
    <h3>多智能体协作流程</h3>
    <div class="agent-flow-row">
      <template v-for="(agent,index) in agents" :key="agent.key"><button :disabled="!agent.done" :class="{active:active===agent.key,done:agent.done}" @click="active=active===agent.key?'':agent.key"><span>{{ agent.icon }}</span><b>{{ agent.name }}</b><em>{{ agent.role }}</em><small>{{ agent.done?`✓ 完成${agent.stat?' · '+agent.stat:''}`:'○ 待启动' }}</small><i v-if="agent.done">▣ 点击查看产物</i></button><span v-if="index<agents.length-1" class="agent-arrow">→</span></template>
    </div>
    <div v-if="active" class="agent-product">
      <header><b>{{ activeAgent?.name }}产物</b><button @click="active=''">关闭 ×</button></header>
      <div v-if="active==='hypothesis'" class="agent-product-content"><h4>研究假设</h4><p>{{ hypothesisText||'暂无研究假设' }}</p></div>
      <div v-else-if="active==='design'" class="agent-product-content"><h4>实验设计</h4><p v-if="designText">{{ designText }}</p><p v-else>暂无实验设计信息</p></div>
      <div v-else-if="active==='coding'" class="agent-product-content code-product"><article v-if="codingPath"><b>代码工作区</b><code>{{ codingPath }}</code></article><p v-else>暂无代码实现信息</p></div>
      <div v-else-if="active==='backtest'" class="agent-product-content metric-product"><article v-for="(value,key) in metricValues" :key="key"><small>{{ key }}</small><b>{{ value }}</b></article></div>
      <div v-else class="agent-product-content"><span class="decision-chip" :class="decision?'accepted':'rejected'">{{ decision?'✓ 已采纳':'✕ 未采纳' }}</span><section v-for="item in feedbackItems" :key="item.label"><b>{{ item.label }}</b><p>{{ item.value || '—' }}</p></section></div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ExperimentItem } from '../types'
const props = defineProps<{ experiments: ExperimentItem[] }>()
const active = ref('')
const hypothesisText = computed(() => props.experiments[0]?.hypothesis_text || '')
const latestWithIc = computed(() => props.experiments.find(e => e.ic != null) || null)
const latestDecision = computed(() => props.experiments.find(e => e.decision != null) || null)
const metricValues = computed<Record<string, number>>(() => {
  const e = latestWithIc.value
  if (!e) return {}
  const out: Record<string, number> = {}
  if (e.ic != null) out.IC = e.ic
  if (e.icir != null) out.ICIR = e.icir
  if (e.annualized_return != null) out['年化收益'] = e.annualized_return
  if (e.max_drawdown != null) out['最大回撤'] = e.max_drawdown
  if (e.information_ratio != null) out['信息比率'] = e.information_ratio
  return out
})
const decision = computed<boolean | null>(() => {
  const e = latestDecision.value
  if (!e) return null
  return !!e.decision
})
const agents = computed(() => [
  { key: 'hypothesis', name: '假设生成', role: '研究员', icon: '🧠', done: props.experiments.length > 0, stat: '' },
  { key: 'design', name: '实验设计', role: '设计师', icon: '✏️', done: props.experiments.length > 0, stat: props.experiments.length ? `${props.experiments.length} 实验` : '' },
  { key: 'coding', name: '代码实现', role: '编码员', icon: '▰', done: props.experiments.some(e => e.workspace_path), stat: '' },
  { key: 'backtest', name: '回测执行', role: '执行员', icon: '📊', done: !!latestWithIc.value, stat: latestWithIc.value ? `IC=${Number(latestWithIc.value.ic).toFixed(3)}` : '' },
  { key: 'feedback', name: '反馈评审', role: '评审员', icon: '🔍', done: !!latestDecision.value, stat: latestDecision.value ? (latestDecision.value.decision ? '已采纳' : '已拒绝') : '' },
])
const activeAgent = computed(() => agents.value.find(agent => agent.key === active.value))
const designText = computed(() => {
  const types = [...new Set(props.experiments.map(e => e.type).filter(Boolean))]
  return types.length ? `本轮共 ${props.experiments.length} 个实验：${types.join('、')}` : ''
})
const codingPath = computed(() => props.experiments.find(e => e.workspace_path)?.workspace_path || '')
const feedbackItems = computed(() => [
  { label: '决定理由', value: feedbackReason.value },
  { label: '实验观察', value: feedbackObservations.value },
].filter(item => item.value))
const feedbackReason = computed(() => latestDecision.value?.decision_reason || '')
const feedbackObservations = computed(() => latestDecision.value?.observations || '')
</script>