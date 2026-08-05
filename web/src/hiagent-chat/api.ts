import type { Agent, ChatMessage, Conversation } from './types'

const API_BASE = '/api/hiagent'

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.error || `请求失败 (${response.status})`)
  }
  return payload as T
}

// ==================== 智能体管理 ====================

export async function fetchAgents(): Promise<Agent[]> {
  const data = await requestJson<{ agents: Agent[] }>(`${API_BASE}/agents`)
  return data.agents
}

export async function addAgent(apiKey: string): Promise<Agent> {
  const data = await requestJson<{ agent: Agent }>(`${API_BASE}/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
  return data.agent
}

export async function deleteAgent(agentId: string): Promise<void> {
  await requestJson(`${API_BASE}/agents/${agentId}`, { method: 'DELETE' })
}

export async function refreshAgent(agentId: string): Promise<Agent> {
  const data = await requestJson<{ agent: Agent }>(`${API_BASE}/agents/${agentId}/refresh`, {
    method: 'POST',
  })
  return data.agent
}

// ==================== 对话管理 ====================

export async function fetchConversations(agentId: string): Promise<Conversation[]> {
  const data = await requestJson<{ conversations: Conversation[] }>(
    `${API_BASE}/agents/${agentId}/conversations`,
  )
  return data.conversations
}

export async function createConversation(
  agentId: string,
  inputs: Record<string, string>,
): Promise<Conversation> {
  const data = await requestJson<{ conversation: Conversation }>(
    `${API_BASE}/agents/${agentId}/conversations`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inputs }),
    },
  )
  return data.conversation
}

export async function deleteConversation(agentId: string, convId: string): Promise<void> {
  await requestJson(`${API_BASE}/agents/${agentId}/conversations/${convId}`, {
    method: 'DELETE',
  })
}

export async function updateConversation(
  agentId: string,
  convId: string,
  inputs: Record<string, string>,
  conversationName?: string,
): Promise<void> {
  await requestJson(`${API_BASE}/agents/${agentId}/conversations/${convId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ inputs, conversation_name: conversationName }),
  })
}

export async function fetchConversationInputs(
  agentId: string,
  convId: string,
): Promise<Record<string, string>> {
  const data = await requestJson<{ inputs: Record<string, string> }>(
    `${API_BASE}/agents/${agentId}/conversations/${convId}/inputs`,
  )
  return data.inputs
}

export async function fetchMessages(agentId: string, convId: string): Promise<ChatMessage[]> {
  const data = await requestJson<{ messages: ChatMessage[] }>(
    `${API_BASE}/agents/${agentId}/conversations/${convId}/messages`,
  )
  return data.messages
}

// ==================== 流式对话 ====================

export function chatStream(
  agentId: string,
  convId: string,
  query: string,
  onMessage: (answer: string) => void,
  onThinkMessage: (answer: string) => void,
  onEnd: (id: string) => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController()

  fetch(`${API_BASE}/agents/${agentId}/conversations/${convId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ error: `HTTP ${response.status}` }))
        onError(err.error || `请求失败 (${response.status})`)
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('无法读取响应流')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const raw = line.slice(6).trim()
            if (!raw) continue
            try {
              const data = JSON.parse(raw)
              if (currentEvent === 'message') {
                onMessage(data.answer || '')
              } else if (currentEvent === 'think_message') {
                onThinkMessage(data.answer || '')
              } else if (currentEvent === 'message_end') {
                onEnd(data.id || '')
              } else if (currentEvent === 'message_failed') {
                onError(data.error || '消息生成失败')
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message || '网络错误')
      }
    })

  return controller
}

export async function stopMessage(
  agentId: string,
  convId: string,
  messageId: string,
  taskId: string,
): Promise<void> {
  await requestJson(`${API_BASE}/agents/${agentId}/conversations/${convId}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message_id: messageId, task_id: taskId }),
  })
}
