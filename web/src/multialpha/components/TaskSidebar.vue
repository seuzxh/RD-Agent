<template>
  <aside class="task-sidebar" :class="{ drawer }">
    <header class="task-sidebar-head">
      <div class="section-kicker">TASKS</div>
      <el-select v-model="scenario" size="small" placeholder="全部场景" clearable>
        <el-option v-for="item in scenarios" :key="item" :label="scenarioLabel(item)" :value="item" />
      </el-select>
      <div class="chip-row">
        <button v-for="item in filters" :key="item.value" class="chip" :class="{ active: status === item.value }" @click="status = item.value">{{ item.label }}</button>
      </div>
    </header>
    <div class="task-list">
      <div v-if="loading" class="empty-small"><span class="mini-loader" />正在加载任务...</div>
      <div v-else-if="error" class="empty-small error-state"><b>任务加载失败</b><span>{{ error }}</span><el-button text size="small" @click="$emit('retry')">重新加载</el-button></div>
      <template v-else>
      <button v-for="task in visibleTasks" :key="task.id" class="task-item" :class="{ active: task.id === activeId }" @click="$emit('select', task.id)">
        <span class="task-name"><i v-if="task.status !== 'idle'" class="status-dot" :class="task.status" />{{ task.name || task.id }}</span>
        <span class="task-meta">{{ scenarioLabel(task.scenario) }} · {{ statusLabel(task.status) }}</span>
      </button>
      <div v-if="!visibleTasks.length" class="empty-small">暂无任务</div>
      <el-button v-if="filteredTasks.length > limit" text class="load-more" @click="limit += 10">加载更多</el-button>
      </template>
    </div>
  </aside>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TraceStatus, TraceTask } from '../types'
const props = withDefaults(defineProps<{ tasks: TraceTask[]; activeId?: string; drawer?: boolean; loading?:boolean; error?:string }>(), { activeId: '', drawer: false, loading:false, error:'' })
defineEmits<{ select: [id: string]; retry:[] }>()
const scenario = ref(''); const status = ref<'all' | TraceStatus>('all'); const limit = ref(10)
const filters = [{ label: '全部', value: 'all' }, { label: '完成', value: 'done' }, { label: '运行中', value: 'running' }] as const
const scenarios = computed(() => [...new Set(props.tasks.map(task => task.scenario))])
const filteredTasks = computed(() => props.tasks.filter(task => (!scenario.value || task.scenario === scenario.value) && (status.value === 'all' || task.status === status.value)))
const visibleTasks = computed(() => filteredTasks.value.slice(0, limit.value))
const labels: Record<string, string> = { 'Finance Data Building': '因子挖掘', 'Finance Data Building (Reports)': '研报因子提取', 'Finance Whole Pipeline': '量化全流程', 'Finance Model Implementation': '模型实现', 'Data Science': '数据科学' }
const scenarioLabel = (value: string) => labels[value] || value
const statusLabel = (value: TraceStatus) => ({ idle: '待查看', running: '运行中', done: '已完成', error: '异常' }[value])
</script>
