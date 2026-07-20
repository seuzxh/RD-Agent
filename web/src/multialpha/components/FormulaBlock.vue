<template><div class="formula-block" :class="{'formula-fallback':failed}"><div v-if="!failed" class="formula-rendered" v-html="rendered"/><code v-else>{{ formula }}</code></div></template>
<script setup lang="ts">
import { computed,ref,watchEffect } from 'vue';import katex from 'katex'
const props=defineProps<{formula:string}>();const failed=ref(false)
function normalizeFormula(value:string){const trimmed=value.trim().replace(/\r?\n/g,' \\\\ ');return /\\\\/.test(trimmed)?`\\begin{aligned}${trimmed}\\end{aligned}`:trimmed}
const rendered=computed(()=>{if(!props.formula.trim())return'';try{const html=katex.renderToString(normalizeFormula(props.formula),{displayMode:true,throwOnError:true,strict:'ignore',trust:false});failed.value=false;return html}catch{failed.value=true;return''}});watchEffect(()=>void rendered.value)
</script>
