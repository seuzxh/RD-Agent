<template><section class="task-brief"><button class="brief-head" @click="expanded=!expanded"><span>📌 任务起点</span><span>{{ expanded?'收起 ▴':'展开 ▾' }}</span></button><div v-if="expanded" class="brief-body"><div v-if="strategy"><small>智能体假设</small><p class="strategy">{{ strategy }}</p></div><div v-if="config.length"><small>任务配置</small><div class="config-chips"><span v-for="item in config" :key="item.key"><b>{{ item.key }}</b>{{ item.value }}</span></div></div></div></section></template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ExperimentItem } from '../../services/research-api'
const props = defineProps<{ experiments: ExperimentItem[] }>()
const expanded = ref(false)
const strategy = computed(() => props.experiments[0]?.hypothesis_text || '')
const roundCount = computed(() => new Set(props.experiments.map(e => e.loop_id)).size)
const config = computed(() => [
  { key: '总轮次', value: String(roundCount.value) },
  { key: '实验数', value: String(props.experiments.length) },
])
</script>
<style scoped>.agent-tag{opacity:.85;font-style:italic}</style>