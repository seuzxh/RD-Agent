<template>
  <section v-if="total || calls" class="token-dashboard">
    <div class="token-summary">
      <div><small>总 TOKEN</small><strong>{{ format(total) }}</strong></div>
      <div><small>输入</small><strong>{{ format(prompt) }}</strong></div>
      <div><small>输出</small><strong>{{ format(completion) }}</strong></div>
      <div><small>调用次数</small><strong>{{ calls }}</strong></div>
    </div>
    <div v-if="byAgent && byAgent.length" class="token-by-agent">
      <table class="agent-table">
        <thead>
          <tr>
            <th class="col-agent">智能体 / 步骤</th>
            <th class="col-stat">输入</th>
            <th class="col-stat">输出</th>
            <th class="col-stat">总计</th>
            <th class="col-calls">调用</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in byAgent" :key="a.agent">
            <td class="col-agent"><span class="agent-name">{{ a.agent }}</span></td>
            <td class="col-stat">{{ format(a.prompt) }}</td>
            <td class="col-stat">{{ format(a.completion) }}</td>
            <td class="col-stat"><strong>{{ format(a.prompt + a.completion) }}</strong></td>
            <td class="col-calls">{{ a.calls }} 次</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
<script setup lang="ts">
import type { TokenByAgent } from '../types'
defineProps<{ total: number; prompt: number; completion: number; calls: number; byAgent: TokenByAgent[] }>()
const format = (value: number) => value > 999 ? `${(value / 1000).toFixed(1)}K` : String(value)
</script>
<style scoped>
.token-dashboard { margin: 12px 20px; border: 1px solid var(--ma-line); border-radius: 8px; background: #fff; overflow: hidden; display: flex; }
.token-summary { display: grid; grid-template-columns: repeat(4, minmax(72px, 1fr)); flex: none; border-right: 1px solid var(--ma-line); }
.token-summary > div { padding: 12px 14px; border-right: 1px solid var(--ma-line); }
.token-summary > div:last-child { border-right: 0; }
.token-summary small { display: block; font-size: 9px; color: var(--ma-muted); margin-bottom: 4px; letter-spacing: 1px; }
.token-summary strong { font: 600 16px var(--ma-font-mono); }
.token-by-agent { flex: 1; overflow-x: auto; padding: 8px 14px; }
.agent-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.agent-table th,
.agent-table td { padding: 6px 10px; text-align: right; white-space: nowrap; }
.agent-table th:first-child,
.agent-table td:first-child { text-align: left; }
.agent-table th { font-size: 10px; color: var(--ma-muted); font-weight: 500; letter-spacing: .5px; }
.agent-table td { color: var(--ma-ink); }
.agent-table td strong { color: var(--ma-gold-dark); font-weight: 600; }
.agent-name { color: var(--ma-gold-dark); font-weight: 600; }
.col-agent { width: 100%; }
.col-stat { width: 64px; }
.col-calls { width: 56px; }
</style>
