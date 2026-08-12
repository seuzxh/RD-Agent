<template><nav v-if="loops.length" class="loop-switcher"><span class="loop-label">轮次:</span><button v-for="loop in loops" :key="loop" :class="{active:modelValue===loop}" @click="$emit('update:modelValue',loop)">{{ loopLabel(loop) }}<small v-if="metrics[loop]">{{ metrics[loop] }}</small></button></nav></template>
<script setup lang="ts">
import { computed } from 'vue'
import type { ExperimentItem } from '../../services/research-api'
const props = defineProps<{ experiments: ExperimentItem[]; modelValue: number | null }>()
defineEmits<{'update:modelValue':[value:number]}>()
const numbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const loopLabel = (loop: number) => `第${numbers[loop] || loop + 1}轮`
const loops = computed(() => [...new Set(props.experiments.map(e => e.loop_id))].sort((a, b) => a - b))
const metrics = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {}
  for (const exp of props.experiments) {
    if (exp.ic != null) map[exp.loop_id] = `IC=${Number(exp.ic).toFixed(3)}`
  }
  return map
})
</script>
