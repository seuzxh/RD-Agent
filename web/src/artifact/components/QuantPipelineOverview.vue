<template>
  <section class="quant-pipeline">
    <header class="pipeline-header">
      <span class="pipeline-title">🧭 量化全流程概览</span>
      <span class="pipeline-summary">{{ summary }}</span>
      <label class="auto-follow" :class="{ on: autoFollow }">
        <span>跟随最新轮</span>
        <input type="checkbox" :checked="autoFollow" @change="emit('update:autoFollow', ($event.target as HTMLInputElement).checked)" />
      </label>
    </header>
    <div class="pipeline-flow">
      <template v-for="(r, i) in rounds" :key="r.loopId">
        <article
          class="round-card"
          :class="[r.kind, r.decisionTone, { selected: r.loopId === selectedLoop }]"
          @click="emit('select', r.loopId)"
        >
          <div class="round-head">
            <b class="round-num">R{{ r.num }}</b>
            <span class="round-kind">{{ r.kindLabel }}</span>
          </div>
          <div v-if="r.status === 'running'" class="round-state running">● 进行中</div>
          <div v-else class="round-decision" :class="r.decisionTone">{{ r.decisionLabel }}</div>
          <div v-if="r.consumedFactors !== null" class="round-consuming" :class="r.consumedFactors ? 'yes' : 'no'">
            {{ r.consumedFactors ? '✓ 消费本会话因子' : 'ALPHA20' }}
          </div>
          <div class="round-metrics">{{ r.metricsLabel }}</div>
        </article>
        <span v-if="i < rounds.length - 1" class="round-arrow">→</span>
      </template>
      <div v-if="!rounds.length" class="empty-round">暂无轮次数据</div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ experiments: any[]; factors: any[]; selectedLoop: number | null; autoFollow: boolean }>()
const emit = defineEmits<{ select: [loopId: number]; 'update:autoFollow': [value: boolean] }>()

// Effective factor rounds = rounds that produced a still-valid factor
// (status 'sota' or 'active', i.e. not deprecated). A model round consumed the
// session's factors iff a prior round produced an effective factor.
const rounds = computed(() => {
  const exps = [...(props.experiments || [])].sort((a, b) => (a.loop_id ?? 0) - (b.loop_id ?? 0))
  const effRound = new Set<number>()
  for (const f of props.factors || []) {
    if (f.status !== 'deprecated' && f.round_number != null) effRound.add(f.round_number)
  }
  const anyEffectiveBefore = (L: number) => { for (const r of effRound) if (r < L) return true; return false }

  return exps.map((e, i) => {
    const isModel = e.type === 'model'
    // decision is stored as INTEGER 0/1 in SQLite, so coerce to boolean/null before
    // comparing — strict === against `true`/`false` would never match and every round
    // would fall through to the default "待定" label.
    const decision = e.decision == null ? null : !!e.decision
    let decisionTone = 'pending'
    let decisionLabel = '待定'
    if (e.status === 'running') { decisionLabel = '进行中' }
    else if (decision === true) { decisionLabel = '✓ SOTA'; decisionTone = 'accepted' }
    else if (decision === false) { decisionLabel = '✕ 拒绝'; decisionTone = 'rejected' }

    let metricsLabel = '—'
    if (isModel) {
      const parts: string[] = []
      if (e.annualized_return != null) parts.push(`年化 ${(e.annualized_return * 100).toFixed(1)}%`)
      if (e.max_drawdown != null) parts.push(`回撤 ${(e.max_drawdown * 100).toFixed(1)}%`)
      metricsLabel = parts.length ? parts.join(' · ') : '—'
    } else {
      const parts: string[] = []
      if (e.ic != null) parts.push(`IC ${e.ic.toFixed(3)}`)
      if (e.icir != null) parts.push(`ICIR ${e.icir.toFixed(3)}`)
      metricsLabel = parts.length ? parts.join(' · ') : '—'
    }

    return {
      loopId: e.loop_id,
      num: i + 1,
      kind: isModel ? 'model' : 'factor',
      kindLabel: isModel ? '模型轮' : '因子轮',
      status: e.status,
      decisionTone,
      decisionLabel,
      metricsLabel,
      consumedFactors: isModel ? anyEffectiveBefore(e.loop_id) : null,
    }
  })
})

const factorCount = computed(() => rounds.value.filter(r => r.kind === 'factor').length)
const modelCount = computed(() => rounds.value.filter(r => r.kind === 'model').length)
const summary = computed(() => `共 ${rounds.value.length} 轮 · ${factorCount.value} 因子轮 · ${modelCount.value} 模型轮`)
</script>
<style scoped>
.quant-pipeline { margin-bottom: 16px; padding: 12px; background: #fafafa; border: 1px solid var(--ma-line, #e4e7ed); border-radius: 6px; }
.pipeline-header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.pipeline-title { font-size: 13px; font-weight: 600; color: #303133; }
.pipeline-summary { font-size: 12px; color: #909399; }
.auto-follow { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #909399; cursor: pointer; user-select: none; }
.auto-follow.on { color: #409eff; font-weight: 600; }
.auto-follow input { accent-color: #409eff; }
.pipeline-flow { display: flex; align-items: stretch; gap: 6px; flex-wrap: wrap; }
.round-card { flex: 1 1 150px; min-width: 150px; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--ma-line, #e4e7ed); background: #fff; display: flex; flex-direction: column; gap: 4px; cursor: pointer; transition: box-shadow .15s ease, border-color .15s ease; }
.round-card:hover { border-color: #a0cfff; }
.round-card.selected { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64, 158, 255, .25); }
.round-card.factor { border-top: 3px solid #409eff; }
.round-card.model { border-top: 3px solid #67c23a; }
.round-head { display: flex; align-items: center; gap: 6px; }
.round-num { font-size: 12px; color: #909399; }
.round-kind { font-size: 13px; font-weight: 600; }
.round-state.running { font-size: 12px; color: #e6a23c; }
.round-decision { font-size: 12px; font-weight: 600; }
.round-decision.accepted { color: #67c23a; }
.round-decision.rejected { color: #f56c6c; }
.round-decision.pending { color: #909399; }
.round-consuming { font-size: 11px; padding: 1px 6px; border-radius: 9px; align-self: flex-start; }
.round-consuming.yes { background: #f0f9eb; color: #67c23a; }
.round-consuming.no { background: #f4f4f5; color: #909399; }
.round-metrics { font-size: 11px; color: #606266; }
.round-arrow { align-self: center; color: #c0c4cc; }
.empty-round { color: #909399; font-size: 12px; padding: 12px; }
</style>