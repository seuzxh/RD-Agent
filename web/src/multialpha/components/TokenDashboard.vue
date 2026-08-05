<template><section v-if="total||calls" class="token-dashboard"><div><small>总 TOKEN</small><strong>{{ format(total) }}</strong></div><div><small>输入</small><strong>{{ format(prompt) }}</strong></div><div><small>输出</small><strong>{{ format(completion) }}</strong></div><div><small>调用次数</small><strong>{{ calls }}</strong></div></section></template>
<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineNode } from '../../services/research-api'
const props = defineProps<{ nodes: PipelineNode[] }>()
const prompt = computed(() => props.nodes.reduce((s, n) => s + Number(n.prompt_tokens || 0), 0))
const completion = computed(() => props.nodes.reduce((s, n) => s + Number(n.completion_tokens || 0), 0))
const total = computed(() => prompt.value + completion.value)
const calls = computed(() => props.nodes.reduce((s, n) => s + Number(n.call_count || 0), 0))
const format = (value: number) => value > 999 ? `${(value / 1000).toFixed(1)}K` : String(value)
</script>