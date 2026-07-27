<template>
  <div class="settings-page">
    <aside class="settings-nav">
      <div class="nav-header">⚙️ 设置</div>
      <button v-for="group in schema?.groups || []" :key="group.id" class="nav-item" :class="{ active: activeGroup === group.id }" @click="activeGroup = group.id">
        <span class="nav-icon">{{ group.icon }}</span>
        <span class="nav-label">{{ group.label }}</span>
      </button>
    </aside>

    <main class="settings-main">
      <div v-if="loading" class="settings-loading"><el-icon class="is-loading"><Loading /></el-icon><span>加载配置...</span></div>
      <div v-else-if="error" class="settings-error">{{ error }}</div>
      <template v-else-if="currentGroup">
        <h2 class="group-title">{{ currentGroup.label }}</h2>

        <section v-for="card in currentGroup.cards" :key="card.id" class="settings-card">
          <h3 class="card-title">{{ card.title }}</h3>

          <!-- Qlib 日期卡片：每行 start~end 并排 -->
          <div v-if="isDateCard(card)" class="date-rows">
            <div v-for="row in pairDateFields(card.fields)" :key="row[0].key" class="date-row">
              <label>{{ row[0].label.replace('开始', '').replace('结束', '') }}</label>
              <el-input v-model="form[row[0].key]" size="small" :placeholder="String(row[0].default || '')" />
              <span class="date-sep">~</span>
              <el-input v-model="form[row[1].key]" size="small" :placeholder="String(row[1].default || '')" />
            </div>
          </div>

          <!-- 默认字段网格 -->
          <div v-else class="field-grid">
            <template v-for="field in card.fields" :key="field.key">
              <!-- 分步模型路由：可视化表格 -->
              <div v-if="field.type === 'model_map'" class="field-item full">
                <label class="field-label">{{ field.label }}</label>
                <div class="model-map-editor">
                  <div class="map-header">
                    <span class="col-step">步骤</span>
                    <span class="col-model">模型</span>
                    <span class="col-temp">温度</span>
                    <span class="col-action"></span>
                  </div>
                  <div v-for="(row, idx) in modelMapRows" :key="idx" class="map-row">
                    <el-select v-model="row.step" size="small" filterable allow-create default-first-option placeholder="选择或输入步骤" class="col-step">
                      <el-option v-for="s in STEP_PRESETS" :key="s.value" :label="s.label" :value="s.value" />
                    </el-select>
                    <el-input v-model="row.model" size="small" placeholder="openai/gpt-4o" class="col-model" />
                    <el-input-number v-model="row.temperature" size="small" :precision="1" :step="0.1" :min="0" :max="2" controls-position="right" class="col-temp" />
                    <el-button text size="small" class="col-action" @click="modelMapRows.splice(idx, 1)">✕</el-button>
                  </div>
                  <el-button text size="small" class="map-add" @click="modelMapRows.push({ step: '', model: '', temperature: undefined })">+ 添加步骤</el-button>
                </div>
                <small class="field-help">{{ field.help }}</small>
              </div>

              <!-- 普通 password -->
              <div v-else-if="field.type === 'password'" class="field-item">
                <label class="field-label">{{ field.label }}<span v-if="field.sensitive" class="sensitive-tag">🔒 敏感</span></label>
                <div class="password-field">
                  <el-input v-model="form[field.key]" :type="showPassword[field.key] ? 'text' : 'password'" size="small" :placeholder="field.value ? String(field.value) : '输入新值'" @focus="onPasswordFocus(field)" />
                  <el-button text size="small" @click="showPassword[field.key] = !showPassword[field.key]">👁</el-button>
                  <el-button text size="small" @click="form[field.key] = ''" title="清空重输">🔄</el-button>
                </div>
                <small v-if="field.help" class="field-help">{{ field.help }}</small>
              </div>

              <!-- number -->
              <div v-else-if="field.type === 'number'" class="field-item">
                <label class="field-label">{{ field.label }}</label>
                <el-input-number v-model="form[field.key]" size="small" controls-position="right" :placeholder="field.default != null ? String(field.default) : ''" />
                <small v-if="field.help" class="field-help">{{ field.help }}</small>
              </div>

              <!-- boolean -->
              <div v-else-if="field.type === 'boolean'" class="field-item">
                <label class="field-label">{{ field.label }}</label>
                <el-switch v-model="form[field.key]" />
                <small v-if="field.help" class="field-help">{{ field.help }}</small>
              </div>

              <!-- select -->
              <div v-else-if="field.type === 'select'" class="field-item">
                <label class="field-label">{{ field.label }}</label>
                <el-select v-model="form[field.key]" size="small">
                  <el-option v-for="opt in field.options" :key="opt" :label="opt" :value="opt" />
                </el-select>
                <small v-if="field.help" class="field-help">{{ field.help }}</small>
              </div>

              <!-- string（默认） -->
              <div v-else class="field-item">
                <label class="field-label">{{ field.label }}</label>
                <el-input v-model="form[field.key]" size="small" :placeholder="field.default != null ? String(field.default) : ''" />
                <small v-if="field.help" class="field-help">{{ field.help }}</small>
              </div>
            </template>
          </div>
        </section>
      </template>
    </main>

    <footer class="settings-footer">
      <span class="restart-hint">⚠️ 修改后需重启服务生效</span>
      <el-button type="primary" :disabled="changeCount === 0" :loading="saving" @click="onSave">保存<span v-if="changeCount"> ({{ changeCount }} 项改动)</span></el-button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fetchSettingsSchema, saveSettings, type SettingsSchema, type ConfigField } from '../../services/rdagent-api'

defineEmits<{ home: [] }>()

const STEP_PRESETS = [
  { label: '实验生成 (direct_exp_gen)', value: 'direct_exp_gen' },
  { label: '代码实现 (coding)', value: 'coding' },
  { label: '运行回测 (running)', value: 'running' },
  { label: '反馈评审 (feedback)', value: 'feedback' },
]

interface MapRow { step: string; model: string; temperature?: number }

const schema = ref<SettingsSchema | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const activeGroup = ref('llm')
const form = reactive<Record<string, unknown>>({})
const initialValues = reactive<Record<string, unknown>>({})
const showPassword = reactive<Record<string, boolean>>({})
const modelMapRows = ref<MapRow[]>([])
const initialModelMapJson = ref('')

const currentGroup = computed(() => schema.value?.groups.find(g => g.id === activeGroup.value))

const currentModelMapJson = computed(() => {
  const obj: Record<string, Record<string, string>> = {}
  for (const row of modelMapRows.value) {
    if (!row.step || !row.model) continue
    const cfg: Record<string, string> = { model: row.model }
    if (row.temperature != null) cfg.temperature = String(row.temperature)
    obj[row.step] = cfg
  }
  return JSON.stringify(obj)
})

const changeCount = computed(() => {
  let count = 0
  for (const key in form) {
    if (JSON.stringify(form[key]) !== JSON.stringify(initialValues[key])) count++
  }
  // 分步路由单独计数
  if (currentModelMapJson.value !== initialModelMapJson.value) count++
  return count
})

function isDateCard(card: { fields: ConfigField[] }) {
  return card.fields.length === 6 && card.fields[0].key.includes('_TRAIN_START')
}

function pairDateFields(fields: ConfigField[]): [ConfigField, ConfigField][] {
  const pairs: [ConfigField, ConfigField][] = []
  for (let i = 0; i < fields.length; i += 2) {
    if (fields[i + 1]) pairs.push([fields[i], fields[i + 1]])
  }
  return pairs
}

function onPasswordFocus(field: ConfigField) {
  if (form[field.key] === field.value) form[field.key] = ''
}

function loadModelMap(value: unknown) {
  const obj = (typeof value === 'object' && value !== null ? value : {}) as Record<string, Record<string, string>>
  modelMapRows.value = Object.entries(obj).map(([step, cfg]) => ({
    step,
    model: cfg.model || '',
    temperature: cfg.temperature != null ? Number(cfg.temperature) : undefined,
  }))
  initialModelMapJson.value = JSON.stringify(
    Object.fromEntries(
      modelMapRows.value
        .filter(r => r.step && r.model)
        .map(r => [r.step, { model: r.model, ...(r.temperature != null ? { temperature: String(r.temperature) } : {}) }])
    )
  )
}

async function loadSchema() {
  loading.value = true; error.value = ''
  try {
    schema.value = await fetchSettingsSchema()
    for (const group of schema.value.groups) {
      for (const card of group.cards) {
        for (const field of card.fields) {
          if (field.type === 'model_map') {
            loadModelMap(field.value)
          } else {
            form[field.key] = field.value
            initialValues[field.key] = field.value
          }
        }
      }
    }
  } catch (e) { error.value = e instanceof Error ? e.message : '加载配置失败' }
  finally { loading.value = false }
}

async function onSave() {
  saving.value = true
  try {
    const changed: Record<string, unknown> = {}
    for (const key in form) {
      if (JSON.stringify(form[key]) !== JSON.stringify(initialValues[key])) changed[key] = form[key]
    }
    // 分步路由
    if (currentModelMapJson.value !== initialModelMapJson.value) {
      changed['CHAT_MODEL_MAP'] = JSON.parse(currentModelMapJson.value)
    }
    const result = await saveSettings(changed)
    for (const key in changed) initialValues[key] = form[key] ?? changed[key]
    if ('CHAT_MODEL_MAP' in changed) initialModelMapJson.value = currentModelMapJson.value
    ElMessage.success(`已保存${result.written.length ? `（${result.written.length} 项）` : ''}，重启服务后生效`)
  } catch (e) { ElMessage.error(e instanceof Error ? e.message : '保存失败') }
  finally { saving.value = false }
}

onMounted(loadSchema)
</script>

<style scoped>
.settings-page { display: flex; height: 100%; position: relative; }
.settings-nav { width: 200px; flex: none; border-right: 1px solid var(--ma-line); background: #fff; padding: 8px 0; overflow-y: auto; }
.nav-header { padding: 12px 16px; font-size: 13px; font-weight: 600; color: var(--ma-gold-dark); }
.nav-item { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 16px; border: 0; border-left: 3px solid transparent; background: none; text-align: left; cursor: pointer; font-size: 13px; color: var(--ma-ink); }
.nav-item:hover { background: var(--ma-surface-2); }
.nav-item.active { border-left-color: var(--ma-gold); background: var(--ma-gold-soft); color: var(--ma-gold-dark); font-weight: 500; }
.nav-icon { font-size: 14px; }
.settings-main { flex: 1; overflow-y: auto; padding: 20px; max-width: 820px; }
.settings-loading, .settings-error { display: flex; align-items: center; gap: 8px; justify-content: center; padding: 60px; color: var(--ma-muted); }
.settings-error { color: var(--ma-danger); }
.group-title { margin: 0 0 16px; font-size: 18px; font-weight: 600; }
.settings-card { border: 1px solid var(--ma-line); border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fff; }
.card-title { margin: 0 0 14px; font-size: 13px; font-weight: 600; color: var(--ma-gold-dark); }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 20px; }
.field-item { display: flex; flex-direction: column; gap: 4px; }
.field-item.full { grid-column: 1 / -1; }
.field-label { font-size: 12px; color: var(--ma-muted); display: flex; align-items: center; gap: 6px; }
.sensitive-tag { font-size: 10px; color: var(--ma-warning); }
.field-help { font-size: 11px; color: var(--ma-muted); margin-top: 2px; }
.password-field { display: flex; align-items: center; gap: 4px; }
.password-field .el-input { flex: 1; }
.date-rows { display: flex; flex-direction: column; gap: 10px; }
.date-row { display: flex; align-items: center; gap: 10px; }
.date-row label { width: 60px; font-size: 12px; color: var(--ma-muted); flex: none; }
.date-row .el-input { flex: 1; }
.date-sep { color: var(--ma-muted); flex: none; }

/* 分步模型路由可视化编辑器 */
.model-map-editor { border: 1px solid var(--ma-line); border-radius: 6px; overflow: hidden; }
.map-header { display: flex; gap: 8px; padding: 8px 10px; background: var(--ma-surface-2); font-size: 11px; font-weight: 600; color: var(--ma-muted); }
.map-row { display: flex; gap: 8px; padding: 8px 10px; border-top: 1px solid var(--ma-line); align-items: center; }
.col-step { flex: 0 0 180px; }
.col-model { flex: 1; }
.col-temp { flex: 0 0 100px; }
.col-action { flex: 0 0 28px; text-align: center; }
.map-add { margin-top: 8px; color: var(--ma-gold-dark); }

.settings-footer { position: absolute; bottom: 0; left: 200px; right: 0; height: 48px; border-top: 1px solid var(--ma-line); display: flex; align-items: center; justify-content: space-between; padding: 0 20px; background: #fff; z-index: 10; }
.restart-hint { font-size: 12px; color: var(--ma-warning); }
</style>
