<template><section class="pipeline"><div v-for="(stage,index) in stages" :key="stage.name" class="pipeline-item" :class="stage.state"><span>{{ stage.state==='done'?'✓':index+1 }}</span>{{ stage.name }}<i v-if="index<stages.length-1">→</i></div></section></template>
<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineNode } from '../../services/research-api'
const props = defineProps<{ pipelineNodes: PipelineNode[] }>()
// step_name 对应 RDLoop 主循环步骤：direct_exp_gen / coding / running / feedback / record
const defs: Array<[string, string[]]> = [
  ['研究', ['direct_exp_gen']],
  ['编码', ['coding']],
  ['回测', ['running']],
  ['反馈', ['feedback', 'record']],
]
const stages = computed(() => {
  const byStep = new Map<string, PipelineNode[]>()
  for (const node of props.pipelineNodes) {
    const arr = byStep.get(node.step_name) || []
    arr.push(node)
    byStep.set(node.step_name, arr)
  }
  let activeFound = false
  return defs.map(([name, steps]) => {
    const nodes = steps.flatMap(step => byStep.get(step) || [])
    const done = nodes.some(node => node.status === 'done')
    const state = done ? 'done' : !activeFound ? (activeFound = true, 'active') : 'idle'
    return { name, state }
  })
})
</script>