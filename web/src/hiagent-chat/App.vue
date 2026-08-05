<template>
  <div class="hiagent-shell">
    <!-- 左侧面板 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2>HiAgent 智能体</h2>
        <el-button type="primary" size="small" @click="showAddDialog = true">
          + 添加
        </el-button>
      </div>

      <!-- 智能体列表 -->
      <div class="agent-list">
        <div
          v-for="agent in agents"
          :key="agent.id"
          class="agent-card"
          :class="{ active: selectedAgentId === agent.id }"
          @click="selectAgent(agent)"
        >
          <div class="agent-info">
            <div class="agent-avatar" :style="{ background: agent.background || '#409eff' }">
              <img v-if="agent.image" :src="agent.image" :alt="agent.name" @error="(e: any) => e.target.style.display = 'none'" />
              <span v-else>{{ (agent.name || '?')[0] }}</span>
            </div>
            <div class="agent-meta">
              <strong>{{ agent.name || '未命名' }}</strong>
              <small>{{ agent.agent_mode || 'Agent' }}</small>
            </div>
          </div>
          <div class="agent-actions" @click.stop>
            <el-dropdown trigger="click" size="small">
              <el-icon><MoreFilled /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="handleRefreshAgent(agent)">刷新元数据</el-dropdown-item>
                  <el-dropdown-item @click="handleDeleteAgent(agent)" divided>
                    <span style="color: #f56c6c">删除</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
        <div v-if="!agents.length && !loadingAgents" class="empty-hint">
          暂无智能体，点击上方"添加"按钮接入
        </div>
      </div>

      <!-- 对话列表 -->
      <div v-if="selectedAgent" class="conversation-section">
        <div class="section-header">
          <span>对话历史</span>
          <el-button size="small" text @click="openCreateConvDialog">+ 新建</el-button>
        </div>
        <div class="conversation-list">
          <div
            v-for="conv in conversations"
            :key="conv.app_conversation_id"
            class="conv-item"
            :class="{ active: selectedConvId === conv.app_conversation_id }"
            @click="selectConversation(conv)"
          >
            <div class="conv-name">{{ conv.conversation_name || '新对话' }}</div>
            <div class="conv-actions" @click.stop>
              <el-dropdown trigger="click" size="small">
                <el-icon><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="openRenameDialog(conv)">重命名</el-dropdown-item>
                    <el-dropdown-item @click="handleDeleteConv(conv)">
                      <span style="color: #f56c6c">删除</span>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
          <div v-if="!conversations.length && !loadingConvs" class="empty-hint">
            暂无对话
          </div>
        </div>
      </div>
    </aside>

    <!-- 右侧聊天区域 -->
    <main class="chat-main">
      <template v-if="selectedAgent && selectedConvId">
        <!-- 聊天头部 -->
        <header class="chat-header">
          <div>
            <strong>{{ currentConvName }}</strong>
            <small>{{ selectedAgent.name }}</small>
          </div>
          <el-button
            v-if="selectedAgent.variable_configs?.length"
            size="small"
            text
            @click="openEditInputsDialog"
          >
            修改参数
          </el-button>
        </header>

        <!-- 消息列表 -->
        <div ref="messageListRef" class="message-list">
          <!-- 开场白 -->
          <div v-if="!messages.length && selectedAgent.open_message" class="message assistant">
            <div class="message-bubble markdown-body" v-html="renderMarkdown(selectedAgent.open_message)"></div>
          </div>

          <div v-for="msg in messages" :key="msg.id" class="message-group">
            <!-- 用户消息 -->
            <div v-if="msg.query" class="message user">
              <div class="message-bubble">{{ msg.query }}</div>
            </div>
            <!-- 智能体回复 -->
            <div v-if="msg.answer" class="message assistant">
              <div class="message-bubble markdown-body" v-html="renderMarkdown(msg.answer)"></div>
            </div>
          </div>

          <!-- 流式消息（正在生成中） -->
          <div v-if="streamingAnswer" class="message assistant">
            <div class="message-bubble markdown-body">
              <div v-if="streamingThink" class="think-block">
                <div class="think-label">思考过程</div>
                <div v-html="renderMarkdown(streamingThink)"></div>
              </div>
              <div v-html="renderMarkdown(streamingAnswer)"></div>
            </div>
          </div>

          <!-- 加载状态 -->
          <div v-if="chatLoading && !streamingAnswer" class="message assistant">
            <div class="message-bubble loading-bubble">
              <span class="dot-typing"></span>
            </div>
          </div>
        </div>

        <!-- 输入区域 -->
        <div class="chat-input">
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="2"
            placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
            resize="none"
            @keydown.enter.exact.prevent="handleSend"
            @keydown.enter.shift.stop
          />
          <div class="input-actions">
            <el-button
              v-if="chatLoading"
              type="danger"
              size="small"
              @click="handleStop"
            >
              停止
            </el-button>
            <el-button
              v-else
              type="primary"
              size="small"
              :disabled="!inputText.trim()"
              @click="handleSend"
            >
              发送
            </el-button>
          </div>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-else class="empty-state">
        <div class="empty-icon">🤖</div>
        <p v-if="!selectedAgent">选择或添加一个智能体开始对话</p>
        <p v-else>选择一个对话，或创建新对话</p>
      </div>
    </main>

    <!-- 添加智能体弹窗 -->
    <el-dialog v-model="showAddDialog" title="添加智能体" width="420px" :close-on-click-modal="false">
      <el-form @submit.prevent="handleAddAgent">
        <el-form-item label="API Key">
          <el-input
            v-model="addForm.apiKey"
            placeholder="输入 HiAgent 智能体的 API Key"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="addLoading"
          :disabled="!addForm.apiKey.trim()"
          @click="handleAddAgent"
        >
          添加
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建对话弹窗 -->
    <el-dialog
      v-model="showCreateConvDialog"
      title="新建对话"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form v-if="selectedAgent?.variable_configs?.length" @submit.prevent="handleCreateConv">
        <el-form-item
          v-for="vc in selectedAgent.variable_configs"
          :key="vc.key"
          :label="vc.show_name || vc.key"
          :required="vc.required"
        >
          <el-select
            v-if="vc.variable_type === 'Enum' && vc.enum_values"
            v-model="inputsForm[vc.key]"
            placeholder="请选择"
          >
            <el-option v-for="val in vc.enum_values" :key="val" :label="val" :value="val" />
          </el-select>
          <el-input
            v-else-if="vc.variable_type === 'Paragraph'"
            v-model="inputsForm[vc.key]"
            type="textarea"
            :rows="3"
            :placeholder="vc.description || ''"
          />
          <el-input
            v-else
            v-model="inputsForm[vc.key]"
            :placeholder="vc.description || ''"
          />
        </el-form-item>
        <p class="input-hint">这些参数在对话过程中可以随时修改</p>
      </el-form>
      <p v-else>该智能体没有需要填写的入参，点击确认直接创建。</p>
      <template #footer>
        <el-button @click="showCreateConvDialog = false">取消</el-button>
        <el-button type="primary" :loading="createConvLoading" @click="handleCreateConv">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 重命名弹窗 -->
    <el-dialog v-model="showRenameDialog" title="重命名对话" width="360px" :close-on-click-modal="false">
      <el-form @submit.prevent="handleRename">
        <el-form-item label="名称">
          <el-input v-model="renameForm.name" placeholder="输入对话名称" clearable />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRenameDialog = false">取消</el-button>
        <el-button type="primary" :loading="renameLoading" @click="handleRename">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑入参弹窗 -->
    <el-dialog
      v-model="showEditInputsDialog"
      title="修改对话参数"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form v-if="selectedAgent?.variable_configs?.length" @submit.prevent="handleEditInputs">
        <el-form-item
          v-for="vc in selectedAgent.variable_configs"
          :key="vc.key"
          :label="vc.show_name || vc.key"
          :required="vc.required"
        >
          <el-select
            v-if="vc.variable_type === 'Enum' && vc.enum_values"
            v-model="editInputsForm[vc.key]"
            placeholder="请选择"
          >
            <el-option v-for="val in vc.enum_values" :key="val" :label="val" :value="val" />
          </el-select>
          <el-input
            v-else-if="vc.variable_type === 'Paragraph'"
            v-model="editInputsForm[vc.key]"
            type="textarea"
            :rows="3"
            :placeholder="vc.description || ''"
          />
          <el-input
            v-else
            v-model="editInputsForm[vc.key]"
            :placeholder="vc.description || ''"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditInputsDialog = false">取消</el-button>
        <el-button type="primary" :loading="editInputsLoading" @click="handleEditInputs">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 入参填写弹窗（首次发送消息前，如果有必填入参未填） -->
    <el-dialog
      v-model="showInputsDialog"
      title="填写对话参数"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form @submit.prevent="handleConfirmInputs">
        <el-form-item
          v-for="vc in pendingRequiredInputs"
          :key="vc.key"
          :label="vc.show_name || vc.key"
          :required="vc.required"
        >
          <el-select
            v-if="vc.variable_type === 'Enum' && vc.enum_values"
            v-model="inputsForm[vc.key]"
            placeholder="请选择"
          >
            <el-option v-for="val in vc.enum_values" :key="val" :label="val" :value="val" />
          </el-select>
          <el-input
            v-else-if="vc.variable_type === 'Paragraph'"
            v-model="inputsForm[vc.key]"
            type="textarea"
            :rows="3"
            :placeholder="vc.description || ''"
          />
          <el-input
            v-else
            v-model="inputsForm[vc.key]"
            :placeholder="vc.description || ''"
          />
        </el-form-item>
        <p class="input-hint">这些参数在对话过程中可以随时修改</p>
      </el-form>
      <template #footer>
        <el-button @click="showInputsDialog = false">取消</el-button>
        <el-button type="primary" @click="handleConfirmInputs">确认并发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MoreFilled } from '@element-plus/icons-vue'
import {
  fetchAgents,
  addAgent,
  deleteAgent,
  refreshAgent,
  fetchConversations,
  createConversation,
  deleteConversation,
  updateConversation,
  fetchConversationInputs,
  fetchMessages,
  chatStream,
  stopMessage,
} from './api'
import type { Agent, ChatMessage, Conversation, VariableConfig } from './types'

// ==================== 状态 ====================

const agents = ref<Agent[]>([])
const loadingAgents = ref(false)
const selectedAgentId = ref('')
const selectedAgent = ref<Agent | null>(null)

const conversations = ref<Conversation[]>([])
const loadingConvs = ref(false)
const selectedConvId = ref('')

const messages = ref<ChatMessage[]>([])
const messageListRef = ref<HTMLElement | null>(null)

const inputText = ref('')
const chatLoading = ref(false)
const streamingAnswer = ref('')
const streamingThink = ref('')
let streamController: AbortController | null = null
const currentMessageId = ref('')

// 添加智能体
const showAddDialog = ref(false)
const addForm = reactive({ apiKey: '' })
const addLoading = ref(false)

// 入参弹窗
const showInputsDialog = ref(false)
const inputsForm = reactive<Record<string, string>>({})
const pendingQuery = ref('') // 暂存用户要发送的消息
const pendingRequiredInputs = ref<VariableConfig[]>([])

// 编辑入参弹窗
const showEditInputsDialog = ref(false)
const editInputsForm = reactive<Record<string, string>>({})
const editInputsLoading = ref(false)

// 重命名弹窗
const showRenameDialog = ref(false)
const renameForm = reactive({ name: '', convId: '' })
const renameLoading = ref(false)

// 当前对话的入参值（可修改）
const convInputs = reactive<Record<string, string>>({})

// ==================== 工具函数 ====================

function renderMarkdown(text: string): string {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

const currentConvName = ref('')

function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

// ==================== 智能体操作 ====================

async function loadAgents() {
  loadingAgents.value = true
  try {
    agents.value = await fetchAgents()
  } catch (e: any) {
    ElMessage.error(e.message || '加载智能体列表失败')
  } finally {
    loadingAgents.value = false
  }
}

async function handleAddAgent() {
  if (!addForm.apiKey.trim()) return
  addLoading.value = true
  try {
    const agent = await addAgent(addForm.apiKey.trim())
    agents.value.push(agent)
    showAddDialog.value = false
    addForm.apiKey = ''
    ElMessage.success(`已添加智能体: ${agent.name}`)
    // 自动选中并创建对话
    selectAgent(agent)
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  } finally {
    addLoading.value = false
  }
}

async function handleDeleteAgent(agent: Agent) {
  try {
    await ElMessageBox.confirm(`确定删除智能体"${agent.name}"？`, '确认')
    await deleteAgent(agent.id)
    agents.value = agents.value.filter((a) => a.id !== agent.id)
    if (selectedAgentId.value === agent.id) {
      selectedAgentId.value = ''
      selectedAgent.value = null
      conversations.value = []
      selectedConvId.value = ''
      messages.value = []
    }
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

async function handleRefreshAgent(agent: Agent) {
  try {
    const updated = await refreshAgent(agent.id)
    const idx = agents.value.findIndex((a) => a.id === agent.id)
    if (idx >= 0) agents.value[idx] = updated
    if (selectedAgentId.value === agent.id) selectedAgent.value = updated
    ElMessage.success('已刷新')
  } catch (e: any) {
    ElMessage.error(e.message || '刷新失败')
  }
}

async function selectAgent(agent: Agent) {
  selectedAgentId.value = agent.id
  selectedAgent.value = agent
  selectedConvId.value = ''
  messages.value = []
  // 清空入参
  Object.keys(convInputs).forEach((k) => delete convInputs[k])
  await loadConversations(agent.id)
}

// ==================== 对话操作 ====================

async function loadConversations(agentId: string) {
  loadingConvs.value = true
  try {
    conversations.value = await fetchConversations(agentId)
  } catch (e: any) {
    ElMessage.error(e.message || '加载对话列表失败')
  } finally {
    loadingConvs.value = false
  }
}

const showCreateConvDialog = ref(false)
const createConvLoading = ref(false)

function openCreateConvDialog() {
  if (!selectedAgent.value) return
  // 预填已有入参值
  if (selectedAgent.value.variable_configs) {
    selectedAgent.value.variable_configs.forEach((vc) => {
      inputsForm[vc.key] = convInputs[vc.key] || ''
    })
  }
  showCreateConvDialog.value = true
}

async function handleCreateConv() {
  if (!selectedAgent.value) return
  // 检查必填项
  const missing = (selectedAgent.value.variable_configs || []).filter(
    (vc) => vc.required && !inputsForm[vc.key]?.trim()
  )
  if (missing.length) {
    ElMessage.warning(`请填写: ${missing.map((v) => v.show_name || v.key).join('、')}`)
    return
  }
  // 保存入参
  Object.entries(inputsForm).forEach(([k, v]) => {
    convInputs[k] = v
  })
  createConvLoading.value = true
  try {
    const conv = await createConversation(selectedAgent.value.id, { ...convInputs })
    conversations.value.unshift(conv)
    showCreateConvDialog.value = false
    selectConversation(conv)
  } catch (e: any) {
    ElMessage.error(e.message || '创建对话失败')
  } finally {
    createConvLoading.value = false
  }
}

async function handleDeleteConv(conv: Conversation) {
  if (!selectedAgent.value) return
  try {
    await ElMessageBox.confirm('确定删除该对话？', '确认')
    await deleteConversation(selectedAgent.value.id, conv.app_conversation_id)
    conversations.value = conversations.value.filter(
      (c) => c.app_conversation_id !== conv.app_conversation_id,
    )
    if (selectedConvId.value === conv.app_conversation_id) {
      selectedConvId.value = ''
      messages.value = []
    }
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

function openRenameDialog(conv: Conversation) {
  renameForm.convId = conv.app_conversation_id
  renameForm.name = conv.conversation_name || ''
  showRenameDialog.value = true
}

async function handleRename() {
  if (!selectedAgent.value || !renameForm.convId) return
  renameLoading.value = true
  try {
    // 先获取当前入参，避免清空
    const currentInputs = await fetchConversationInputs(selectedAgent.value.id, renameForm.convId)
    await updateConversation(selectedAgent.value.id, renameForm.convId, currentInputs, renameForm.name)
    // 更新本地列表
    const conv = conversations.value.find((c) => c.app_conversation_id === renameForm.convId)
    if (conv) conv.conversation_name = renameForm.name
    if (selectedConvId.value === renameForm.convId) {
      currentConvName.value = renameForm.name
    }
    showRenameDialog.value = false
    ElMessage.success('已重命名')
  } catch (e: any) {
    ElMessage.error(e.message || '重命名失败')
  } finally {
    renameLoading.value = false
  }
}

async function selectConversation(conv: Conversation) {
  selectedConvId.value = conv.app_conversation_id
  currentConvName.value = conv.conversation_name || '新对话'
  messages.value = []
  streamingAnswer.value = ''
  streamingThink.value = ''
  chatLoading.value = false
  if (streamController) {
    streamController.abort()
    streamController = null
  }

  if (!selectedAgent.value) return

  // 获取当前对话的入参
  try {
    const inputs = await fetchConversationInputs(selectedAgent.value.id, conv.app_conversation_id)
    Object.keys(convInputs).forEach((k) => delete convInputs[k])
    Object.entries(inputs).forEach(([k, v]) => {
      convInputs[k] = v
    })
  } catch {
    // 入参获取失败不影响对话
  }

  try {
    messages.value = await fetchMessages(selectedAgent.value.id, conv.app_conversation_id)
    scrollToBottom()
  } catch (e: any) {
    ElMessage.error(e.message || '加载消息历史失败')
  }
}

// ==================== 入参检查 ====================

function getRequiredInputs(): VariableConfig[] {
  if (!selectedAgent.value?.variable_configs) return []
  return selectedAgent.value.variable_configs.filter(
    (vc) => vc.required && !convInputs[vc.key]?.trim()
  )
}

function handleConfirmInputs() {
  // 检查所有必填项是否已填
  const missing = pendingRequiredInputs.value.filter((vc) => !inputsForm[vc.key]?.trim())
  if (missing.length) {
    ElMessage.warning(`请填写: ${missing.map((v) => v.show_name || v.key).join('、')}`)
    return
  }
  // 将填入的值保存到 convInputs
  Object.entries(inputsForm).forEach(([k, v]) => {
    convInputs[k] = v
  })
  showInputsDialog.value = false
  // 创建对话并发送暂存的消息
  doCreateAndSend()
}

async function doCreateAndSend() {
  if (!selectedAgent.value) return
  // 如果还没有对话，先创建
  if (!selectedConvId.value) {
    try {
      const conv = await createConversation(selectedAgent.value.id, { ...convInputs })
      conversations.value.unshift(conv)
      selectedConvId.value = conv.app_conversation_id
      currentConvName.value = conv.conversation_name || '新对话'
    } catch (e: any) {
      ElMessage.error(e.message || '创建对话失败')
      return
    }
  }
  // 发送暂存的消息
  if (pendingQuery.value) {
    const q = pendingQuery.value
    pendingQuery.value = ''
    doSend(q)
  }
}

// ==================== 编辑入参 ====================

async function openEditInputsDialog() {
  if (!selectedAgent.value || !selectedConvId.value) return
  // 从 API 获取当前入参值
  try {
    const currentInputs = await fetchConversationInputs(selectedAgent.value.id, selectedConvId.value)
    ;(selectedAgent.value.variable_configs || []).forEach((vc) => {
      editInputsForm[vc.key] = currentInputs[vc.key] ?? convInputs[vc.key] ?? ''
    })
  } catch {
    // 回退到本地缓存
    ;(selectedAgent.value.variable_configs || []).forEach((vc) => {
      editInputsForm[vc.key] = convInputs[vc.key] || ''
    })
  }
  showEditInputsDialog.value = true
}

async function handleEditInputs() {
  if (!selectedAgent.value || !selectedConvId.value) return
  editInputsLoading.value = true
  try {
    await updateConversation(selectedAgent.value.id, selectedConvId.value, { ...editInputsForm })
    // 更新本地入参状态
    Object.entries(editInputsForm).forEach(([k, v]) => {
      convInputs[k] = v
    })
    showEditInputsDialog.value = false
    ElMessage.success('参数已更新')
  } catch (e: any) {
    ElMessage.error(e.message || '更新失败')
  } finally {
    editInputsLoading.value = false
  }
}

// ==================== 聊天操作 ====================

async function handleSend() {
  const query = inputText.value.trim()
  if (!query || !selectedAgent.value || chatLoading.value) return

  // 检查是否有必填入参未填
  const required = getRequiredInputs()
  if (required.length) {
    // 显示入参弹窗
    pendingQuery.value = query
    pendingRequiredInputs.value = required
    // 预填已有值
    required.forEach((vc) => {
      inputsForm[vc.key] = convInputs[vc.key] || ''
    })
    showInputsDialog.value = true
    return
  }

  // 如果还没有对话，先创建
  if (!selectedConvId.value) {
    try {
      const conv = await createConversation(selectedAgent.value.id, { ...convInputs })
      conversations.value.unshift(conv)
      selectedConvId.value = conv.app_conversation_id
      currentConvName.value = conv.conversation_name || '新对话'
    } catch (e: any) {
      ElMessage.error(e.message || '创建对话失败')
      return
    }
  }

  inputText.value = ''
  doSend(query)
}

function doSend(query: string) {
  if (!selectedAgent.value || !selectedConvId.value || chatLoading.value) return

  chatLoading.value = true
  streamingAnswer.value = ''
  streamingThink.value = ''
  currentMessageId.value = ''

  // 先显示用户消息
  const tempId = `temp-${Date.now()}`
  messages.value.push({
    id: tempId,
    conversation_id: selectedConvId.value,
    query,
    answer: '',
    created_at: Date.now(),
    status: 'sending',
  })
  scrollToBottom()

  streamController = chatStream(
    selectedAgent.value.id,
    selectedConvId.value,
    query,
    // onMessage
    (answer) => {
      streamingAnswer.value += answer
      scrollToBottom()
    },
    // onThinkMessage
    (answer) => {
      streamingThink.value += answer
      scrollToBottom()
    },
    // onEnd
    (id) => {
      currentMessageId.value = id
      const idx = messages.value.findIndex((m) => m.id === tempId)
      if (idx >= 0) {
        messages.value[idx].answer = streamingAnswer.value || '*（无回复内容）*'
        messages.value[idx].status = 'done'
      }
      streamingAnswer.value = ''
      streamingThink.value = ''
      chatLoading.value = false
      scrollToBottom()
    },
    // onError
    (error) => {
      const idx = messages.value.findIndex((m) => m.id === tempId)
      if (idx >= 0) {
        messages.value[idx].answer = streamingAnswer.value || ''
        messages.value[idx].status = 'error'
      }
      streamingAnswer.value = ''
      streamingThink.value = ''
      chatLoading.value = false
      ElMessage.error(error)
    },
  )
}

function handleStop() {
  if (streamController) {
    streamController.abort()
    streamController = null
  }
  if (selectedAgent.value && selectedConvId.value && currentMessageId.value) {
    stopMessage(selectedAgent.value.id, selectedConvId.value, currentMessageId.value, '').catch(
      console.warn,
    )
  }
  chatLoading.value = false
  if (streamingAnswer.value) {
    const idx = messages.value.findIndex((m) => m.id.startsWith('temp-') && m.status === 'sending')
    if (idx >= 0) {
      messages.value[idx].answer = streamingAnswer.value + '\n\n*[已停止]*'
      messages.value[idx].status = 'stopped'
    }
  }
  streamingAnswer.value = ''
  streamingThink.value = ''
}

// 初始化
onMounted(() => {
  loadAgents()
})
</script>

<style scoped>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

.hiagent-shell {
  display: flex;
  height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif;
  background: #f5f7fa;
  color: #303133;
}

/* ==================== 左侧面板 ==================== */

.sidebar {
  width: 320px;
  min-width: 320px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.sidebar-header h2 {
  font-size: 16px;
  font-weight: 600;
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.agent-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.agent-card:hover {
  background: #f0f2f5;
}

.agent-card.active {
  background: #ecf5ff;
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 600;
  font-size: 16px;
  flex-shrink: 0;
  overflow: hidden;
}

.agent-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.agent-meta {
  min-width: 0;
}

.agent-meta strong {
  display: block;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-meta small {
  color: #909399;
  font-size: 12px;
}

.agent-actions {
  opacity: 0;
  transition: opacity 0.15s;
}

.agent-card:hover .agent-actions {
  opacity: 1;
}

/* ==================== 对话列表 ==================== */

.conversation-section {
  border-top: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  max-height: 50%;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  font-size: 13px;
  color: #606266;
  font-weight: 500;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 8px;
}

.conv-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}

.conv-item:hover {
  background: #f0f2f5;
}

.conv-item.active {
  background: #ecf5ff;
}

.conv-name {
  flex: 1;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-time {
  font-size: 11px;
  color: #909399;
  margin-left: 8px;
  flex-shrink: 0;
}

.conv-actions {
  opacity: 0;
  margin-left: 4px;
  cursor: pointer;
  color: #909399;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.conv-item:hover .conv-actions {
  opacity: 1;
}

.conv-actions:hover {
  color: #409eff;
}

.empty-hint {
  text-align: center;
  color: #909399;
  font-size: 13px;
  padding: 20px 10px;
}

/* ==================== 聊天区域 ==================== */

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  padding: 12px 20px;
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-header strong {
  font-size: 15px;
}

.chat-header small {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.message {
  display: flex;
  margin-bottom: 16px;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.message.user .message-bubble {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-bubble {
  background: #fff;
  color: #303133;
  border: 1px solid #e4e7ed;
  border-bottom-left-radius: 4px;
}

.think-block {
  background: #f5f5f5;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #909399;
  border-left: 3px solid #c0c4cc;
}

.think-label {
  font-weight: 500;
  margin-bottom: 4px;
  color: #606266;
}

.loading-bubble {
  padding: 14px 20px;
}

.dot-typing {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #909399;
  animation: dotTyping 1.2s infinite;
}

@keyframes dotTyping {
  0%,
  80%,
  100% {
    opacity: 0.3;
  }
  40% {
    opacity: 1;
  }
}

.markdown-body pre {
  background: #f6f8fa;
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 6px 0;
}

.markdown-body code {
  background: #f0f0f0;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 13px;
}

.markdown-body pre code {
  background: none;
  padding: 0;
}

/* ==================== 输入区域 ==================== */

.chat-input {
  padding: 12px 20px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

/* ==================== 空状态 ==================== */

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  font-size: 14px;
}

.input-hint {
  font-size: 12px;
  color: #909399;
  margin-top: -4px;
}
</style>
