<template>
  <section class="agent-flow">
    <h3>多智能体协作流程</h3>
    <div class="agent-flow-row">
      <template v-for="(agent,index) in agents" :key="agent.key"><button :disabled="!agent.done" :class="{active:active===agent.key,done:agent.done}" @click="active=active===agent.key?'':agent.key"><span>{{ agent.icon }}</span><b>{{ agent.name }}</b><em>{{ agent.role }}</em><small>{{ agent.done?`✓ 完成${agent.stat?' · '+agent.stat:''}`:'○ 待启动' }}</small><i v-if="agent.done">▣ 点击查看产物</i></button><span v-if="index<agents.length-1" class="agent-arrow">→</span></template>
    </div>
    <div v-if="active" class="agent-product">
      <header><b>{{ activeAgent?.name }}产物</b><button @click="active=''">关闭 ×</button></header>
      <div v-if="active==='hypothesis'" class="agent-product-content"><h4>研究假设</h4><p>{{ hypothesisText||'暂无研究假设' }}</p><section v-if="hypothesis?.reason"><b>提出理由</b><p>{{ hypothesis.reason }}</p></section></div>
      <div v-else-if="active==='design'" class="agent-product-content factor-product"><article v-for="factor in factors" :key="factor.name"><b>{{ factor.name }}</b><p>{{ factor.description }}</p><FormulaBlock v-if="factor.formula" :formula="factor.formula"/></article></div>
      <div v-else-if="active==='coding'" class="agent-product-content code-product"><div v-for="file in codes" :key="`${file.target}-${file.name}`"><b>{{ file.target||file.name }} · {{ file.name }}</b><pre>{{ file.content }}</pre></div></div>
      <div v-else-if="active==='backtest'" class="agent-product-content metric-product"><article v-for="(value,key) in metricValues" :key="key"><small>{{ key }}</small><b>{{ value }}</b></article></div>
      <div v-else class="agent-product-content"><span class="decision-chip" :class="feedback.decision?'accepted':'rejected'">{{ feedback.decision?'✓ 已采纳':'✕ 未采纳' }}</span><section v-for="item in feedbackItems" :key="item.label"><b>{{ item.label }}</b><p>{{ item.value }}</p></section></div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed,ref } from 'vue';import FormulaBlock from './FormulaBlock.vue';import type { CodeFile,FactorItem,FeedbackSummary,TraceMessage } from '../types'
const props=defineProps<{messages:TraceMessage[];factors:FactorItem[];codes:CodeFile[];metricValues:Record<string,number|string>;feedback:FeedbackSummary;hypothesis:Record<string,unknown>|null}>();const active=ref('')
const latest=(tag:string)=>[...props.messages].reverse().find(message=>message.tag===tag);const agents=computed(()=>[{key:'hypothesis',name:'假设生成',role:'研究员',icon:'🧠',done:!!latest('research.hypothesis'),stat:''},{key:'design',name:'实验设计',role:'设计师',icon:'✏️',done:!!latest('research.tasks'),stat:props.factors.length?`${props.factors.length} 因子`:''},{key:'coding',name:'代码实现',role:'编码员',icon:'▰',done:!!props.codes.length,stat:props.codes.length?`${props.codes.length} 文件`:''},{key:'backtest',name:'回测执行',role:'执行员',icon:'📊',done:!!latest('feedback.metric'),stat:props.metricValues.IC!=null?`IC=${Number(props.metricValues.IC).toFixed(3)}`:''},{key:'feedback',name:'反馈评审',role:'评审员',icon:'🔍',done:!!latest('feedback.hypothesis_feedback'),stat:props.feedback.decision===null?'':props.feedback.decision?'已采纳':'已拒绝'}]);const activeAgent=computed(()=>agents.value.find(agent=>agent.key===active.value));const hypothesisText=computed(()=>String(props.hypothesis?.hypothesis||props.hypothesis?.concise_observation||''));const feedbackItems=computed(()=>[{label:'决定理由',value:props.feedback.reason},{label:'实验观察',value:props.feedback.observations},{label:'假设评估',value:props.feedback.evaluation},{label:'下一轮新假设',value:props.feedback.newHypothesis},{label:'异常信息',value:props.feedback.exception}].filter(item=>item.value))
</script>
