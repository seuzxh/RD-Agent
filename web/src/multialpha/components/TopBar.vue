<template>
  <header class="topbar">
    <button class="brand" title="返回首页" @click="$emit('home')">
      <span class="brand-logo-frame"><img src="https://h5.crsec.com.cn/logo.png" alt="国新证券" class="brand-logo"/></span>
      <span class="brand-text"><small>国新证券</small><strong>MultiAlpha</strong></span>
    </button>
    <div class="topbar-actions">
      <el-button text :loading="loading" @click="$emit('refresh')">刷新任务</el-button>
      <el-button type="primary" @click="$emit('create')">新建任务</el-button>
    </div>
  </header>
</template>
<script setup lang="ts">defineProps<{loading:boolean}>();defineEmits<{home:[];refresh:[];create:[]}>()</script>
