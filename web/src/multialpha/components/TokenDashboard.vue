<template>
  <section v-if="total||calls" class="token-dashboard">
    <div class="token-summary">
      <div><small>总 TOKEN</small><strong>{{ format(total) }}</strong></div>
      <div><small>输入</small><strong>{{ format(prompt) }}</strong></div>
      <div><small>输出</small><strong>{{ format(completion) }}</strong></div>
      <div><small>调用次数</small><strong>{{ calls }}</strong></div>
    </div>
    <div v-if="byModel && byModel.length > 1" class="token-by-model">
      <div v-for="m in byModel" :key="m.model" class="model-row" :title="m.model">
        <span class="model-name">{{ shortModel(m.model) }}</span>
        <span class="model-stat">入 {{ format(m.prompt) }}</span>
        <span class="model-stat">出 {{ format(m.completion) }}</span>
        <span class="model-calls">{{ m.calls }}次</span>
      </div>
    </div>
  </section>
</template>
<script setup lang="ts">
import type { TokenByModel } from '../types'
defineProps<{ total: number; prompt: number; completion: number; calls: number; byModel: TokenByModel[] }>()
const format = (value: number) => value > 999 ? `${(value / 1000).toFixed(1)}K` : String(value)
const shortModel = (model: string) => {
  // openai/minimax-m3 → minimax-m3；openai/glm-5.2 → glm-5.2
  const parts = model.split('/')
  return parts.length > 1 ? parts.slice(1).join('/') : model
}
</script>
<style scoped>
.token-dashboard { margin: 12px 20px; border: 1px solid var(--ma-line); border-radius: 8px; background: #fff; overflow: hidden; }
.token-summary { display: grid; grid-template-columns: repeat(4, 1fr); }
.token-summary > div { padding: 12px; border-right: 1px solid var(--ma-line); }
.token-summary > div:last-child { border-right: 0; }
.token-summary small { display: block; font-size: 9px; color: var(--ma-muted); margin-bottom: 4px; letter-spacing: 1px; }
.token-summary strong { font: 600 16px var(--ma-font-mono); }
.token-by-model { border-top: 1px solid var(--ma-line); padding: 8px 12px; }
.model-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; font-size: 11px; }
.model-name { font-weight: 600; color: var(--ma-gold-dark); min-width: 120px; }
.model-stat { color: var(--ma-muted); }
.model-calls { color: var(--ma-muted); margin-left: auto; }
</style>
