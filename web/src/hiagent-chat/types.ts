export interface VariableConfig {
  key: string
  description: string
  show_name: string
  required: boolean
  variable_type: string // Text, Paragraph, Enum
  enum_values: string[] | null
}

export interface Agent {
  id: string
  api_key: string
  name: string
  icon: string
  image: string
  background: string
  open_message: string
  open_query: string[]
  suggest_enabled: boolean
  agent_mode: string
  variable_configs: VariableConfig[]
  created_at: string
  updated_at: string
}

export interface Conversation {
  app_conversation_id: string
  conversation_id?: string
  conversation_name: string
  create_time?: string
  last_chat_time?: string
}

export interface ChatMessage {
  id: string
  conversation_id: string
  query: string
  answer: string
  created_at: number
  task_id?: string
  status?: string
}

export interface StreamEvent {
  event: 'message' | 'message_end' | 'message_failed' | 'think_message'
  data: {
    answer?: string
    id?: string
    error?: string
  }
}
