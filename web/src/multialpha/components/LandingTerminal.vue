<template>
  <section class="landing">
    <div class="terminal-frame">
      <header class="terminal-head"><span class="terminal-dots">● ● ●</span><span>MULTIALPHA · QUANT TERMINAL</span><span class="live"><i /> LIVE · {{ clock }}</span></header>
      <div class="hero-grid">
        <div class="hero-copy-block">
          <p class="eyebrow">FACTOR MINING · ◯V · GUOXIN SECURITIES</p>
          <h1>Multi<span>α</span>1pha</h1>
          <h2>量化因子挖掘终端 · V.4</h2>
          <p class="hero-copy">5 个智能体协作，10 轮自动迭代，把一句策略构想转化为可执行、可回测的 α 因子。</p>
          <div class="hero-actions"><el-button type="primary" size="large" @click="$emit('create','text')"><kbd>N</kbd> 新建任务</el-button><el-button size="large" text @click="$emit('history')">查看历史任务 →</el-button></div>
        </div>
        <div class="terminal-stats">
          <div class="ticker"><span class="ticker-label">LIVE · ALL TASKS</span><div class="ticker-track"><span v-for="task in tickerTasks" :key="task.id">{{ task.name }} <b>{{ task.status==='done'?'✓':task.status==='running'?'▶':'○' }}</b></span><span v-if="!tickerTasks.length">等待任务接入 <b>○</b></span></div></div>
          <div class="stat-grid"><div><small>AGENTS</small><strong>05</strong><p>假设 → 评审</p></div><div><small>TASKS</small><strong>{{ String(tasks.length).padStart(2,'0') }}</strong><p>{{ doneCount }} 已完成 · {{ runningCount }} 运行中</p></div><div><small>LOOPS / RUN</small><strong>10</strong><p>单次最大循环数</p></div><div><small>UPTIME</small><strong>--</strong><p>本任务最长 · 暂无数据</p></div></div>
        </div>
      </div>
    </div>

    <div class="landing-content">
      <section class="content-section"><header class="section-heading"><span>I</span><div><p>ARCHITECTURE</p><h3>多智能体协作架构</h3><small>五个专业智能体各司其职，模拟真实量化投研团队的 R&amp;D 协作流程</small></div></header><div class="agent-showcase"><article v-for="(agent,index) in agents" :key="agent.name"><span>{{ agent.icon }}</span><em>0{{ index+1 }}</em><h4>{{ agent.name }}<small>{{ agent.role }}</small></h4><p>{{ agent.desc }}</p><i v-if="index<agents.length-1">→</i></article></div></section>

      <section class="content-section"><header class="section-heading"><span>II</span><div><p>ITERATION</p><h3>多轮自动迭代</h3><small>每一轮反馈自动驱动下一轮优化，因子表现持续提升</small></div></header><div class="iteration-flow"><article v-for="(item,index) in iterations" :key="item"><b>R{{ index+1 }}</b><span>{{ item }}</span><i v-if="index<iterations.length-1" /></article></div><div class="iteration-note"><span>IC</span><div><b>指标逐轮提升</b><small>反馈评审 → 自动优化 → 回测验证 → 逐步收敛</small></div></div></section>

      <section class="content-section"><header class="section-heading"><span>III</span><div><p>ENTRY POINTS</p><h3>任务入口</h3><small>选择输入方式，启动因子挖掘任务</small></div></header><div class="entry-grid"><button v-for="entry in entries" :key="entry.title" :disabled="entry.disabled" @click="handleEntry(entry)"><span class="entry-state" :class="{soon:entry.disabled}">{{ entry.disabled?'即将上线':'可用' }}</span><b>{{ entry.icon }}</b><h4>{{ entry.title }}</h4><p>{{ entry.desc }}</p><i>{{ entry.disabled?'SOON':'ENTER →' }}</i></button></div></section>

      <footer class="capability-strip"><span v-for="item in capabilities" :key="item"><i>◆</i>{{ item }}</span></footer>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed,onBeforeUnmount,ref } from 'vue';import type { TaskMethod,TraceTask } from '../types'
const props=defineProps<{tasks:TraceTask[]}>();const emit=defineEmits<{create:[method:TaskMethod];history:[]}>()
const clock=ref('');const updateClock=()=>clock.value=new Date().toLocaleTimeString('zh-CN',{hour12:false});updateClock();const timer=setInterval(updateClock,1000);onBeforeUnmount(()=>clearInterval(timer))
const doneCount=computed(()=>props.tasks.filter(task=>task.status==='done').length);const runningCount=computed(()=>props.tasks.filter(task=>task.status==='running').length);const tickerTasks=computed(()=>props.tasks.slice(0,8))
const agents=[{icon:'◇',name:'假设生成',role:'研究员',desc:'基于市场观察与历史反馈，提出因子假设与创新思路'},{icon:'⌁',name:'实验设计',role:'设计师',desc:'将抽象假设转化为具体任务，定义公式、变量与去重规则'},{icon:'</>',name:'代码实现',role:'编码员',desc:'CoSTEER 多轮演化生成 factor.py，自动调试并修复错误'},{icon:'↗',name:'回测执行',role:'执行员',desc:'在隔离环境运行 Qlib 回测，完成 IC 去重并产出指标'},{icon:'◎',name:'反馈评审',role:'评审员',desc:'对比 SOTA 结果，评估有效性并指导下一轮迭代'}]
const iterations=['初始假设','代码优化','因子改进','效果提升','收敛稳定']
const entries=[{icon:'Aa',title:'策略文字描述',desc:'通过自然语言描述策略思路，自动生成量化因子并回测验证',method:'text' as TaskMethod},{icon:'PDF',title:'研报因子提取',desc:'上传金工研报，提取因子公式、变量定义并生成代码',method:'pdf' as TaskMethod},{icon:'α+',title:'因子迭代优化',desc:'基于回测反馈持续优化已有因子，提升 IC、ICIR 指标',method:'optimize' as TaskMethod},{icon:'K',title:'K线图形分析',desc:'识别图形形态并生成对应量化因子',method:'image' as TaskMethod,disabled:true},{icon:'CSV',title:'交割单分析',desc:'分析交易风格与弱点，生成针对性优化因子',method:'trade' as TaskMethod,disabled:true},{icon:'↺',title:'历史任务',desc:'查看进行中和已完成任务，对比迭代结果',history:true}]
const capabilities=['数据安全隔离','容器化执行','全流程自动化','多智能体协作']
function handleEntry(entry:typeof entries[number]){if(entry.disabled)return;if(entry.history)emit('history');else if(entry.method)emit('create',entry.method)}
</script>
