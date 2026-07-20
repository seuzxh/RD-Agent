<template>
  <header class="topbar">
    <button class="brand" title="返回首页" @click="$emit('home')">
      <span class="brand-logo-frame"><img src="https://h5.crsec.com.cn/logo.png" alt="国新证券" class="brand-logo"/></span>
      <span class="brand-text"><small>国新证券</small><strong>MultiAlpha</strong></span>
    </button>
    <div class="topbar-actions">
      <el-button text :loading="healthLoading" @click="checkHealth">🩺 健康检查</el-button>
      <el-button text :loading="loading" @click="$emit('refresh')">刷新任务</el-button>
      <el-button type="primary" @click="$emit('create')">新建任务</el-button>
    </div>
    <el-dialog v-model="healthVisible" title="🩺 环境健康检查" width="560px" destroy-on-close>
      <div v-if="healthError" class="health-error">{{ healthError }}</div>
      <template v-else>
        <div class="health-overall" :class="healthData?.overall">
          <span v-if="healthData?.overall==='pass'">✅ 所有检查项通过</span>
          <span v-else>⚠️ 存在需要注意的配置项</span>
        </div>
        <div class="health-list">
          <div v-for="item in healthData?.checks||[]" :key="item.name" class="health-item" :class="item.status">
            <span class="health-icon">{{ item.icon }}</span>
            <div class="health-info"><strong>{{ item.name }}</strong><small>{{ item.detail }}</small></div>
            <span class="health-status">{{ item.status==='pass'?'✅':item.status==='warn'?'⚠️':'❌' }}</span>
          </div>
        </div>
      </template>
    </el-dialog>
  </header>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { fetchHealth, type HealthCheck } from '../api'
defineProps<{loading:boolean}>();defineEmits<{home:[];refresh:[];create:[]}>()
const healthVisible=ref(false),healthLoading=ref(false),healthData=ref<HealthCheck|null>(null),healthError=ref('')
async function checkHealth(){healthLoading.value=true;healthVisible.value=true;healthError.value='';healthData.value=null;try{healthData.value=await fetchHealth()}catch(err){healthError.value=err instanceof Error?err.message:'健康检查失败'}finally{healthLoading.value=false}}
</script>
<style scoped>
.health-overall{padding:.8em 1em;border-radius:8px;margin-bottom:1em;font-weight:700;font-size:1.05em}
.health-overall.pass{background:rgba(103,194,58,.1);color:#67c23a}
.health-overall.issues{background:rgba(230,162,60,.1);color:#e6a23c}
.health-list{display:flex;flex-direction:column;gap:.6em}
.health-item{display:flex;align-items:flex-start;gap:.6em;padding:.6em .8em;border-radius:8px;border:1px solid #ebeef5}
.health-item.pass{background:rgba(103,194,58,.03)}
.health-item.warn{background:rgba(230,162,60,.05);border-color:rgba(230,162,60,.2)}
.health-item.fail{background:rgba(245,108,108,.05);border-color:rgba(245,108,108,.2)}
.health-icon{font-size:1.3em;line-height:1}
.health-info{flex:1;display:flex;flex-direction:column;gap:.15em}
.health-info strong{font-size:.92em;color:#303133}
.health-info small{font-size:.82em;color:#909399;line-height:1.4}
.health-status{font-size:1.1em}
.health-error{color:#f56c6c;padding:1em;text-align:center}
</style>
