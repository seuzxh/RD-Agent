<template>
  <nav v-if="loops.length" class="loop-switcher">
    <span class="loop-label">轮次:</span>
    <button
      v-for="loop in loops"
      :key="loop"
      :class="{active:modelValue===loop,sota:sotaLoop===loop,running:isRunningLoop(loop)}"
      @click="$emit('update:modelValue',loop)"
    >
      {{ loopLabel(loop) }}
      <small v-if="metrics[loop]">{{ metrics[loop] }}</small>
      <span v-if="isRunningLoop(loop)" class="loop-dot" />
      <span v-if="sotaLoop===loop" class="sota-mark" title="SOTA">🏆</span>
    </button>
  </nav>
</template>
<script setup lang="ts">
const props = defineProps<{
  loops: number[]
  modelValue: number | null
  metrics: Record<number, string>
  sotaLoop?: number | null
  latestLoop?: number | null
  status?: string
}>()
defineEmits<{ 'update:modelValue': [value: number] }>()
const numbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const loopLabel = (loop: number) => `第${numbers[loop] || loop + 1}轮`
function isRunningLoop(loop: number) {
  return props.status === 'running' && props.latestLoop != null && loop === props.latestLoop
}
</script>
<style scoped>
.loop-dot{
  display:inline-block;width:6px;height:6px;margin-left:4px;border-radius:50%;
  background:var(--ma-warning);
  animation:loop-dot-pulse 1.2s ease-in-out infinite;
}
@keyframes loop-dot-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.6)}}
.loop-switcher button.running{border-color:var(--ma-gold);background:var(--ma-gold-soft);color:var(--ma-gold-dark)}
</style>
