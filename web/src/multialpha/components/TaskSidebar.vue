<template>
  <aside class="task-sidebar" :class="{ drawer }">
    <header class="task-sidebar-head">
      <div class="task-sidebar-title">
        <div class="section-kicker">TASKS</div>
      </div>
      <div class="filter-label">任务场景</div>
      <nav class="scenario-tabs" aria-label="任务场景" role="tablist" aria-orientation="vertical">
        <button
          v-for="item in scenarioTabs"
          :key="item.value || 'all'"
          type="button"
          role="tab"
          :aria-selected="scenario === item.value"
          :class="{ active: scenario === item.value }"
          @click="scenario = item.value"
        >
          <span>{{ item.label }}</span><small>{{ item.count }}</small>
        </button>
      </nav>
      <div class="filter-label status-filter-label">任务状态</div>
      <div class="chip-row">
        <button v-for="item in filters" :key="item.value" type="button" class="chip" :class="{ active: status === item.value }" @click="status = item.value">{{ item.label }}</button>
      </div>
      <div class="task-list-summary"><span>任务列表</span><small>{{ filteredTasks.length }}</small></div>
    </header>
    <div class="task-list">
      <div v-if="loading" class="empty-small"><span class="mini-loader" />正在加载任务...</div>
      <div v-else-if="error" class="empty-small error-state"><b>任务加载失败</b><span>{{ error }}</span><el-button text size="small" @click="$emit('retry')">重新加载</el-button></div>
      <template v-else>
      <button v-for="task in filteredTasks" :key="task.id" type="button" class="task-item" :class="{ active: task.id === activeId }" @click="$emit('select', task.id)">
        <span class="task-name"><i v-if="task.status !== 'idle'" class="status-dot" :class="task.status" />{{ task.name || task.id }}</span>
        <span class="task-meta">{{ scenarioLabel(task.scenario) }} · {{ statusLabel(task.status) }}</span>
      </button>
      <div v-if="!filteredTasks.length" class="empty-small">暂无任务</div>
      </template>
    </div>
  </aside>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TraceStatus, TraceTask } from '../types'
const props = withDefaults(defineProps<{ tasks: TraceTask[]; activeId?: string; drawer?: boolean; loading?:boolean; error?:string }>(), { activeId: '', drawer: false, loading:false, error:'' })
defineEmits<{ select: [id: string]; retry:[] }>()
const scenario = ref(''); const status = ref<'all' | TraceStatus>('all')
const filters = [{ label: '全部', value: 'all' }, { label: '运行中', value: 'running' }, { label: '已完成', value: 'done' }, { label: '异常', value: 'error' }] as const
const scenarios = computed(() => [...new Set(props.tasks.map(task => task.scenario).filter(Boolean))])
const scenarioTabs = computed(() => [
  { value: '', label: '全部类型', count: props.tasks.length },
  ...scenarios.value.map(value => ({ value, label: scenarioLabel(value), count: props.tasks.filter(task => task.scenario === value).length })),
])
const filteredTasks = computed(() => props.tasks.filter(task => (!scenario.value || task.scenario === scenario.value) && (status.value === 'all' || task.status === status.value)))
const labels: Record<string, string> = { 'Finance Data Building': '因子挖掘', 'Finance Data Building (Reports)': '研报因子提取', 'Finance Whole Pipeline': '量化全流程', 'Finance Model Implementation': '模型实现' }
const scenarioLabel = (value: string) => labels[value] || value
const statusLabel = (value: TraceStatus) => ({ idle: '待查看', running: '运行中', done: '已完成', error: '异常' }[value])
</script>
