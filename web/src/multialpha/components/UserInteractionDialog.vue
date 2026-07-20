<template>
  <div v-if="visible && !minimized" class="dialog-box">
    <div class="dialog-content user-interaction-dialog" :class="{ 'user-interaction-dialog--wide': isFeatureInteraction }">
      <div class="dialog-header">
        <h1>需要用户交互</h1>
        <button class="dialog-minimize" type="button" @click="minimizeUserInteraction">最小化</button>
      </div>
      <template v-if="waitingHypothesis && !hasEnd">
        <div class="interaction-waiting">
          <span class="interaction-waiting-spinner" aria-hidden="true"></span>
          <span>R&amp;D-Agent 正在生成假设</span>
        </div>
        <div class="interaction-form read-only">
          <div class="interaction-row" v-for="(entry, index) in lastFeedbackEntries" :key="entry.key + '-readonly-' + index">
            <label class="interaction-key">{{ entry.key }}</label>
            <select v-if="entry.key === 'decision'" class="interaction-select" :value="entry.value" disabled>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
            <textarea v-else class="interaction-textarea" :value="entry.value" rows="8" readonly></textarea>
          </div>
        </div>
      </template>
      <template v-else>
        <p v-if="isFeatureInteraction">更新基础特征后提交以继续。</p>
        <p v-else-if="isUserInstructionInteraction">请更新总体指令后提交以继续。</p>
        <p v-else-if="isFeedbackInteraction">您可以编辑系统生成的决策与原因，然后提交以继续。</p>
        <p v-else>您可以编辑系统生成的假设与原因，然后提交以继续。</p>
        <div class="feature-validation-msg" v-if="isFeatureInteraction && (localFeatureError || featureValidationMsg)">
          {{ localFeatureError || featureValidationMsg }}
        </div>
        <div class="interaction-form">
          <div v-if="isFeatureInteraction" class="feature-table">
            <div class="feature-layout">
              <div class="feature-pool-block" v-if="availableFeatureTags.length">
                <div class="feature-pool-title">基础特征 (Alpha158)</div>
                <div class="feature-pool"><div class="feature-pool-tags">
                  <button class="feature-tag" type="button" v-for="tag in availableFeatureTags" :key="tag.name"
                    :title="tag.expression" @click="addFeatureFromPool(tag)">{{ tag.name }}</button>
                </div></div>
              </div>
              <div class="feature-editor">
                <div class="feature-sticky-head">
                  <div class="feature-editor-meta">已配置特征：{{ configuredFeatureCount }}</div>
                  <div class="feature-header"><span>特征名称</span><span>特征表达式</span></div>
                </div>
                <div class="feature-row" v-for="(row, index) in featureRows" :key="`feature-${index}`">
                  <input class="feature-input" type="text" v-model="row.name" placeholder="name" />
                  <input class="feature-input feature-input--math" type="text" v-model="row.expression" placeholder="expression" />
                  <button class="feature-remove" type="button" @click="removeFeatureRow(index)"
                    :disabled="featureRows.length === 1" aria-label="Remove feature">×</button>
                </div>
                <button class="feature-add" type="button" @click="addFeatureRow">+ 添加特征</button>
              </div>
            </div>
          </div>
          <div class="interaction-row" v-for="(entry, index) in entries" :key="entry.key + '-' + index"
            :class="{ 'interaction-row--stack': entry.key === 'user_instruction' }">
            <label class="interaction-key" v-if="entry.key !== 'user_instruction'">{{ entry.key }}</label>
            <div v-else class="interaction-key interaction-key--highlight">您的总体指令</div>
            <select v-if="entry.key === 'decision'" class="interaction-select" v-model="entry.value">
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
            <textarea v-else class="interaction-textarea" v-model="entry.value" rows="8"
              :placeholder="entry.key === 'user_instruction' ? 'Example: 请使用中文表示hypothesis' : ''"></textarea>
          </div>
        </div>
        <div class="dialog-footer">
          <label class="auto-skip-toggle">
            <input type="checkbox" :checked="autoSkip" @change="handleAutoSkipToggle(($event.target as HTMLInputElement).checked)" />
            自动跳过后续交互
          </label>
          <div class="btn-box">
            <button class="btn-skip" @click="submitOriginalUserInteraction" :disabled="submitting">跳过</button>
            <button class="btn-submit" @click="submitUserInteractionForm" :disabled="submitting">提交</button>
          </div>
        </div>
      </template>
    </div>
  </div>
  <div class="dialog-minimized" v-if="visible && minimized" @click="restoreUserInteraction">
    <div class="dialog-minimized-content">
      <span class="dialog-waiting-spinner" aria-hidden="true"></span>
      <span>等待用户交互</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { submitUserInteraction } from '../api'
import ALPHA158 from '../../constants/qlib'
import type { TraceMessage } from '../types'

interface FeatureRow { name: string; expression: string }
interface Entry { key: string; value: string }
interface FeatureTag { name: string; expression: string }

const props = defineProps<{ messages: TraceMessage[]; traceId: string }>()

// Dialog state
const visible = ref(false)
const submitting = ref(false)
const queue = ref<Record<string, unknown>[]>([])
const entries = ref<Entry[]>([])
const originalPayload = ref<Record<string, unknown>>({})
const autoSkip = ref(false)
const minimized = ref(false)
const waitingHypothesis = ref(false)
const lastFeedbackEntries = ref<Entry[]>([])
let timeoutHandle: ReturnType<typeof setTimeout> | null = null
const initialBaseFactors = ref<Record<string, string> | null>(null)

// Feature table state (form 2)
const featureRows = ref<FeatureRow[]>([])
const featureValidationMsg = ref('')
const localFeatureError = ref('')

// Track the last interaction request we've already opened, to avoid re-opening on every poll
let lastOpenedTimestamp: string | undefined

const hasEnd = computed(() => props.messages.some(message => message.tag === 'END'))

// Form-type detection (order matters, mirrors PlaygroundPage.vue:642-670)
const isUserInstructionInteraction = computed(() => {
  if (waitingHypothesis.value) return false
  return Object.prototype.hasOwnProperty.call(originalPayload.value, 'user_instruction')
})
const isFeatureInteraction = computed(() => {
  if (waitingHypothesis.value) return false
  return Object.prototype.hasOwnProperty.call(originalPayload.value, 'features')
})
const isFeedbackInteraction = computed(() => {
  if (waitingHypothesis.value) return false
  // feedback form = decision+reason (no hypothesis/user_instruction/features)
  const payload = originalPayload.value
  return !Object.prototype.hasOwnProperty.call(payload, 'hypothesis')
    && !Object.prototype.hasOwnProperty.call(payload, 'user_instruction')
    && !Object.prototype.hasOwnProperty.call(payload, 'features')
})

const availableFeatureTags = computed<FeatureTag[]>(() => {
  const used = new Set(featureRows.value.map(row => String(row.name ?? '').trim()).filter(Boolean))
  return Object.keys(ALPHA158).filter(name => !used.has(name)).map(name => ({ name, expression: ALPHA158[name] }))
})
const configuredFeatureCount = computed(() =>
  featureRows.value.filter(row => String(row.name ?? '').trim() && String(row.expression ?? '').trim()).length
)

function normalizeDecision(value: unknown): boolean {
  if (value === true || value === false) return value
  if (value == null) return false
  if (typeof value === 'string') return value.trim().toLowerCase() === 'true'
  return Boolean(value)
}

function isFeedbackPayload(payload: Record<string, unknown> | null | undefined): boolean {
  if (!payload || typeof payload !== 'object') return false
  if (Object.prototype.hasOwnProperty.call(payload, 'user_instruction')) return false
  if (Object.prototype.hasOwnProperty.call(payload, 'features')) return false
  return !Object.prototype.hasOwnProperty.call(payload, 'hypothesis')
}

// Trigger: watch messages for new user_interaction.request
watch(() => props.messages, (msgs) => {
  // END tag clears all dialogs
  if (msgs.some(message => message.tag === 'END')) {
    clearAllDialogs()
    return
  }
  // Find the latest user_interaction.request we haven't opened yet
  const requests = msgs.filter(message => message.tag === 'user_interaction.request')
  if (requests.length === 0) return
  const latest = requests[requests.length - 1]
  const latestTs = latest.timestamp
  if (latestTs === lastOpenedTimestamp) return
  lastOpenedTimestamp = latestTs
  const payload = (latest.content && typeof latest.content === 'object' ? latest.content : {}) as Record<string, unknown>
  openUserInteraction(payload)
}, { deep: true })

function openUserInteraction(payload: Record<string, unknown>) {
  const hasUserInstruction = Object.prototype.hasOwnProperty.call(payload, 'user_instruction')
  const hasFeatures = Object.prototype.hasOwnProperty.call(payload, 'features')

  // autoSkip: skip feedback/hypothesis forms (not instruction/features) without UI
  if (autoSkip.value && !hasUserInstruction && !hasFeatures) {
    if (submitting.value) { queue.value.push(payload); return }
    void submitUserInteractionPayload(payload)
    return
  }
  // Queue if a dialog is already open (not in waiting state)
  if (visible.value && !waitingHypothesis.value) {
    queue.value.push(payload)
    return
  }
  if (waitingHypothesis.value) waitingHypothesis.value = false

  originalPayload.value = payload || {}
  const hasHypothesis = Object.prototype.hasOwnProperty.call(payload, 'hypothesis')
  const filteredKeys: string[] = hasFeatures
    ? []
    : hasUserInstruction
      ? ['user_instruction']
      : hasHypothesis
        ? ['hypothesis', 'reason']
        : ['decision', 'reason']

  const newEntries: Entry[] = filteredKeys.map(key => ({
    key,
    value: (payload && Object.prototype.hasOwnProperty.call(payload, key)
      ? key === 'decision'
        ? String(normalizeDecision(payload[key]))
        : payload[key] == null ? '' : String(payload[key])
      : key === 'decision' ? 'false' : ''),
  }))

  if (hasFeatures) {
    const featureDict = (payload && payload.features ? payload.features : {}) as Record<string, unknown>
    featureRows.value = Object.entries(featureDict).map(([name, expression]) => ({
      name: String(name),
      expression: expression == null ? '' : String(expression),
    }))
    if (featureRows.value.length === 0) featureRows.value.push({ name: '', expression: '' })
    localFeatureError.value = ''
    featureValidationMsg.value = payload.feature_validation_msg ? String(payload.feature_validation_msg) : ''
  } else {
    featureRows.value = []
    featureValidationMsg.value = ''
    localFeatureError.value = ''
  }

  entries.value = newEntries
  visible.value = true
  minimized.value = false
  waitingHypothesis.value = false

  if (timeoutHandle) clearTimeout(timeoutHandle)
  // 10-minute timeout: auto-submit original payload to avoid hanging the agent
  timeoutHandle = setTimeout(() => { void submitOriginalUserInteraction() }, 10 * 60 * 1000)
}

function closeUserInteraction() {
  visible.value = false
  minimized.value = false
  waitingHypothesis.value = false
  lastFeedbackEntries.value = []
  entries.value = []
  originalPayload.value = {}
  if (timeoutHandle) { clearTimeout(timeoutHandle); timeoutHandle = null }
  if (queue.value.length > 0) {
    const nextPayload = queue.value.shift() as Record<string, unknown>
    openUserInteraction(nextPayload)
  }
}

function minimizeUserInteraction() { minimized.value = true }
function restoreUserInteraction() { minimized.value = false }

function submitUserInteractionPayload(payload: Record<string, unknown>) {
  if (submitting.value) return
  submitting.value = true
  const feedbackPayload = isFeedbackPayload(payload)
  const data = { id: props.traceId, payload }
  return submitUserInteraction(data)
    .then(() => {
      if (feedbackPayload && visible.value) {
        // Feedback submitted -> enter waiting state (R&D-Agent generating next hypothesis)
        waitingHypothesis.value = true
        lastFeedbackEntries.value = entries.value.map(entry => ({ key: entry.key, value: entry.value }))
        entries.value = []
        originalPayload.value = {}
        if (timeoutHandle) { clearTimeout(timeoutHandle); timeoutHandle = null }
        return
      }
      closeUserInteraction()
    })
    .catch((err: unknown) => {
      ElMessage.error(err instanceof Error ? err.message : '提交用户交互失败')
    })
    .finally(() => {
      submitting.value = false
      if (autoSkip.value && queue.value.length > 0) {
        const nextPayload = queue.value.shift() as Record<string, unknown>
        void submitUserInteractionPayload(nextPayload || {})
      }
    })
}

function submitUserInteractionForm() {
  const payload: Record<string, unknown> = { ...(originalPayload.value || {}) }
  if (isFeatureInteraction.value) {
    const features: Record<string, string> = {}
    const seenNames = new Set<string>()
    localFeatureError.value = ''
    for (const row of featureRows.value) {
      const name = String(row.name ?? '').trim()
      const expression = String(row.expression ?? '').trim()
      if (!name || !expression) { localFeatureError.value = 'Feature name and expression cannot be empty.'; break }
      if (seenNames.has(name)) { localFeatureError.value = 'Feature names must be unique.'; break }
      seenNames.add(name)
      features[name] = expression
    }
    if (localFeatureError.value) return
    if (!initialBaseFactors.value) initialBaseFactors.value = { ...features }
    void submitUserInteractionPayload(features as unknown as Record<string, unknown>)
    return
  }
  entries.value.forEach(entry => {
    if (entry.key === 'decision') { payload[entry.key] = normalizeDecision(entry.value); return }
    payload[entry.key] = entry.value == null ? '' : String(entry.value)
  })
  void submitUserInteractionPayload(payload)
}

function addFeatureRow() { featureRows.value.push({ name: '', expression: '' }) }
function addFeatureFromPool(tag: FeatureTag) {
  const emptyRow = featureRows.value.find(row => !row.name || !String(row.name).trim())
  if (emptyRow) { emptyRow.name = tag.name; emptyRow.expression = tag.expression; return }
  featureRows.value.push({ name: tag.name, expression: tag.expression })
}
function removeFeatureRow(index: number) {
  if (featureRows.value.length <= 1) { featureRows.value[0] = { name: '', expression: '' }; return }
  featureRows.value.splice(index, 1)
}

function submitOriginalUserInteraction() {
  if (isFeatureInteraction.value) {
    const original = originalPayload.value || {}
    const features = (original.features || {}) as Record<string, string>
    if (!initialBaseFactors.value) initialBaseFactors.value = { ...features }
    void submitUserInteractionPayload(features as unknown as Record<string, unknown>)
    return
  }
  void submitUserInteractionPayload(originalPayload.value || {})
}

function handleAutoSkipToggle(enabled: boolean) {
  autoSkip.value = enabled
  if (!enabled) return
  if (visible.value) { void submitOriginalUserInteraction(); return }
  if (!submitting.value && queue.value.length > 0) {
    const nextPayload = queue.value.shift() as Record<string, unknown>
    void submitUserInteractionPayload(nextPayload || {})
  }
}

function clearAllDialogs() {
  queue.value = []
  visible.value = false
  minimized.value = false
  waitingHypothesis.value = false
  lastFeedbackEntries.value = []
  entries.value = []
  originalPayload.value = {}
  featureRows.value = []
  featureValidationMsg.value = ''
  localFeatureError.value = ''
  lastOpenedTimestamp = undefined
  if (timeoutHandle) { clearTimeout(timeoutHandle); timeoutHandle = null }
}
</script>

<style scoped>
.dialog-box {
  width: 100vw; height: 100vh; position: fixed; left: 0; top: 0;
  background: rgba(255, 255, 255, 0.29); backdrop-filter: blur(4.6px);
  z-index: 999999; display: flex; align-items: center; justify-content: center;
}
.dialog-content.user-interaction-dialog {
  background-color: #fff; border-radius: 18px; padding: 3.5em 4.5em;
  max-width: 72em; width: calc(100% - 4em); font-family: inherit;
}
.dialog-content.user-interaction-dialog.user-interaction-dialog--wide {
  max-width: 88em; padding: 3.75em 5.25em; width: 86vw;
}
.dialog-header { display: flex; align-items: center; justify-content: space-between; gap: 1.5em; }
.dialog-minimize {
  border: none; background: linear-gradient(90deg, #2667ff 0%, #9d41ff 100%);
  color: #fff; font-size: 1em; font-weight: 700; padding: 0.6em 1.2em;
  border-radius: 999px; box-shadow: 0 8px 18px rgba(38, 103, 255, 0.35); cursor: pointer;
}
h1 { color: #1c2b57; text-shadow: 8px 11px 30px #edf0ff; font-size: 1.7em; font-weight: 700; line-height: 200%; }
p { color: #1c2b57; font-size: 1.1em; line-height: 150%; margin: 0.8em 0 1.5em; }
.feature-validation-msg {
  padding: 0.75em 1em; margin: 0 0 1.2em; border-radius: 10px;
  background: rgba(255, 107, 0, 0.08); color: #b94b00; font-weight: 600; line-height: 1.5;
}
.interaction-form { display: flex; flex-direction: column; gap: 0.9em; max-height: none; overflow: visible; }
.feature-table { display: flex; flex-direction: column; gap: 1em; }
.feature-layout { display: grid; grid-template-columns: 1fr 3fr; gap: 1.5em; align-items: start; }
.feature-pool-block { display: flex; flex-direction: column; gap: 0.6em; }
.feature-pool {
  padding: 0.9em 1em; border-radius: 12px; background: rgba(38, 103, 255, 0.06);
  border: 1px solid rgba(38, 103, 255, 0.2); max-height: 56vh; overflow: visible;
}
.feature-pool-title { font-weight: 700; color: #1c2b57; margin-bottom: 0.6em; }
.feature-pool-tags { display: flex; flex-wrap: wrap; gap: 0.6em; max-height: 56vh; overflow: auto; overflow-x: hidden; }
.feature-editor { display: flex; flex-direction: column; gap: 0.9em; max-height: 56vh; overflow: auto; padding-right: 0.4em; }
.feature-sticky-head { position: sticky; top: 0; z-index: 3; background: #fff; padding-bottom: 0.2em; }
.feature-editor-meta { font-weight: 700; color: #1c2b57; font-size: 0.95em; line-height: 1.4; padding: 0.15em 0.2em 0.45em; }
.feature-tag {
  border: 1px solid rgba(38, 103, 255, 0.35); background: #fff; color: #1c2b57;
  font-weight: 600; font-size: 0.9em; padding: 0.35em 0.7em; border-radius: 999px; cursor: pointer; position: relative;
}
.feature-tag:hover { background: rgba(38, 103, 255, 0.12); }
.feature-header, .feature-row { display: grid; grid-template-columns: 1fr 4fr auto; gap: 1.4em; align-items: center; }
.feature-header {
  font-weight: 700; color: #1c2b57; font-size: 0.95em; text-transform: uppercase;
  letter-spacing: 0.04em; background: #fff; padding: 0.45em 0.2em; border-bottom: 1px solid #e0e6f5;
}
.feature-input {
  width: 100%; padding: 0.45em 0.7em; border-radius: 10px; border: 1px solid #c5d2e6;
  font-size: 0.88em; color: #1c2b57; min-width: 0;
}
.feature-input--math { font-family: "STIX Two Math", "Cambria Math", "Times New Roman", serif; }
.feature-add {
  align-self: flex-start; border: none; background: rgba(38, 103, 255, 0.12); color: #1c2b57;
  font-weight: 700; padding: 0.5em 1em; border-radius: 999px; cursor: pointer;
}
.feature-remove {
  border: 1px solid #ee6a58; background: #ee6a58; color: #fff; font-weight: 700;
  width: 1.7em; height: 1.7em; padding: 0; border-radius: 8px; cursor: pointer; white-space: nowrap;
  justify-self: end; font-size: 1em; display: inline-flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 14px rgba(238, 106, 88, 0.3); transition: transform 0.15s ease, background-color 0.15s ease;
}
.feature-remove:hover { background: #e15f4e; transform: translateY(-1px); }
.feature-remove:disabled { cursor: not-allowed; opacity: 0.5; }
.interaction-form.read-only { opacity: 0.7; pointer-events: none; }
.interaction-waiting {
  display: flex; align-items: center; justify-content: center; gap: 0.8em;
  min-height: 12em; font-size: 1.15em; font-weight: 600; color: #1c2b57;
}
.interaction-waiting-spinner {
  width: 1.3em; height: 1.3em; border-radius: 999px; border: 2px solid rgba(38, 103, 255, 0.2);
  border-top-color: #2667ff; animation: dialog-spin 0.9s linear infinite;
}
.interaction-row { display: flex; align-items: flex-start; gap: 1em; }
.interaction-row--stack { flex-direction: column; align-items: stretch; }
.interaction-key--highlight {
  width: 100%; font-size: 1.1em; font-weight: 700; color: #1c2b57;
  margin-bottom: 0.4em; text-shadow: 0 8px 20px rgba(38, 103, 255, 0.18); white-space: nowrap;
}
.interaction-key {
  width: 12%; font-weight: 600; color: #1c2b57; word-break: break-all; font-size: 1em; line-height: 1.2; padding-top: 0.2em;
}
.interaction-textarea {
  flex: 1; min-height: 14em; padding: 1em 1.1em; border-radius: 10px; border: 1px solid #c5d2e6;
  color: #1c2b57; font-size: 1.1em; font-family: inherit; outline: none; resize: vertical; line-height: 1.5;
}
.interaction-textarea::placeholder { font-style: italic; }
.interaction-select {
  flex: 1; min-height: 3.2em; padding: 0.6em 1.1em; border-radius: 10px; border: 1px solid #c5d2e6;
  color: #1c2b57; font-size: 1.05em; font-family: inherit; outline: none; background: #fff;
}
.dialog-footer { display: flex; align-items: center; justify-content: space-between; gap: 1.5em; margin-top: 2.5em; }
.auto-skip-toggle {
  display: flex; align-items: center; gap: 0.5em; font-size: 0.95em; color: #1c2b57; cursor: pointer; user-select: none;
}
.auto-skip-toggle input { cursor: pointer; }
.btn-box { display: flex; gap: 1em; }
.btn-skip, .btn-submit {
  width: 10em; height: 3em; color: #1c2b57; font-size: 1.05em; font-weight: 700;
  line-height: 150%; text-transform: uppercase; border: none; cursor: pointer; border-radius: 37.5px;
}
.btn-submit {
  background: linear-gradient(90deg, #2667ff 0%, #9d41ff 100%);
  box-shadow: 8px 11px 30px 0px rgba(38, 103, 255, 0.25); color: #fff;
}
.btn-skip { background: rgba(38, 103, 255, 0.08); }
.btn-skip:hover { background: rgba(38, 103, 255, 0.15); }
.btn-skip:disabled, .btn-submit:disabled { cursor: not-allowed; opacity: 0.6; }
.dialog-minimized {
  position: fixed; right: 1.8em; bottom: 1.8em; z-index: 1000000;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
}
.dialog-minimized-content {
  display: flex; align-items: center; gap: 0.9em; padding: 1em 1.5em; border-radius: 999px;
  background: linear-gradient(90deg, #2667ff 0%, #9d41ff 100%); box-shadow: 0 16px 40px rgba(38, 103, 255, 0.35);
  color: #fff; font-weight: 700; border: 2px solid rgba(255, 255, 255, 0.65); animation: dialog-pulse 1.6s ease-in-out infinite;
}
.dialog-waiting-spinner {
  width: 1.2em; height: 1.2em; border-radius: 999px; border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: #fff; animation: dialog-spin 0.9s linear infinite;
}
@keyframes dialog-spin { to { transform: rotate(360deg); } }
@keyframes dialog-pulse {
  0%, 100% { transform: translateY(0); box-shadow: 0 16px 40px rgba(38, 103, 255, 0.35); }
  50% { transform: translateY(-3px); box-shadow: 0 22px 48px rgba(38, 103, 255, 0.5); }
}
</style>
