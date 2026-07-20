<template><nav v-if="loops.length" class="loop-switcher"><span class="loop-label">轮次:</span><button v-for="loop in loops" :key="loop" :class="{active:modelValue===loop}" @click="$emit('update:modelValue',loop)">{{ loopLabel(loop) }}<small v-if="metrics[loop]">{{ metrics[loop] }}</small></button></nav></template>
<script setup lang="ts">
defineProps<{loops:number[];modelValue:number|null;metrics:Record<number,string>}>();defineEmits<{'update:modelValue':[value:number]}>()
const numbers=['一','二','三','四','五','六','七','八','九','十'];const loopLabel=(loop:number)=>`第${numbers[loop]||loop+1}轮`
</script>
