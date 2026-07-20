<template><transition name="fade"><div v-if="visible" class="trace-loading"><div><span class="loading-spinner"/><section><strong>正在加载任务详情</strong><p>正在获取 {{ name }} 的 Trace 数据，请稍候…</p></section></div></div></transition></template>
<script setup lang="ts">defineProps<{visible:boolean;name:string}>()</script>
