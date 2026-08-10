<template>
  <section class="pipeline">
    <div v-for="(stage,index) in stages" :key="stage.name" class="pipeline-item" :class="stage.state">
      <span v-if="stage.state==='done'">✓</span>
      <span v-else-if="stage.state==='active'" class="pipeline-spinner" />
      <span v-else>{{ index+1 }}</span>
      {{ stage.name }}
      <i v-if="index<stages.length-1">→</i>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { TraceMessage } from '../types'

const props = defineProps<{ messages: TraceMessage[] }>()

const defs: [string, string[]][] = [
  ['假设生成', ['research.hypothesis']],
  ['实验设计', ['research.tasks']],
  ['因子代码', ['evolving.codes']],
  ['收益曲线', ['feedback.metric', 'feedback.return_chart']],
  ['反馈评审', ['evolving.feedbacks', 'feedback.hypothesis_feedback']],
]

const stages = computed(() => {
  const tags = new Set(props.messages.map(item => item.tag))
  let activeFound = false
  return defs.map(([name, required]) => {
    const done = required.some(tag => tags.has(tag))
    const state = done ? 'done' : !activeFound ? (activeFound = true, 'active') : 'idle'
    return { name, state }
  })
})
</script>
<style scoped>
.pipeline-spinner{
  width:14px;height:14px;
  border:2px solid var(--ma-gold-soft);
  border-top-color:var(--ma-gold);
  border-radius:50%;
  animation:pipe-spin .7s linear infinite;
  display:inline-block;
}
@keyframes pipe-spin{to{transform:rotate(360deg)}}
.pipeline-item.active{animation:pipe-pulse 2s ease-in-out infinite}
@keyframes pipe-pulse{
  0%,100%{box-shadow:0 0 0 0 rgba(200,163,91,.3)}
  50%{box-shadow:0 0 0 4px rgba(200,163,91,0)}
}
</style>
