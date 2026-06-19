export interface Provider {
  name: string
  type: string
  base_url: string
  api_key?: string
  model: string
  supports_vision: boolean
  supports_audio: boolean
  supports_video: boolean
  prefetch_media: boolean
  extra_body?: Record<string, any>
  description?: string
  request_timeout?: number
  stream_chunk_timeout?: number
}

export interface MCPServer {
  name: string
  enabled: boolean
  transport: string
  command?: string
  args?: string[]
  url?: string
  headers?: Record<string, string>
  env?: Record<string, string>
  description?: string
}

export interface Skill {
  name: string
  version?: string
  description?: string
  auto_inject?: boolean
}

export interface Persona {
  character: string
  display_name?: string
  setting?: string
  reply_instruction?: string
  image_setting?: string
  max_chat_len?: number
  max_analysis_len?: number
  max_quick_reply?: number
  default_temperature?: number
}

export interface ExpressionConfig {
  format: string
  instruction: string
}

export interface ChannelStatus {
  name: string
  running: boolean
  pid?: number
  started_at?: string
  restart_count?: number
  platform_restricted?: string[]
  platform_blocked?: boolean
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  thought?: string
  timestamp?: number
}

export interface MonitorEntry {
  ts?: string
  type?: string
  character?: string
  provider?: string
  model?: string
  request?: any
  response?: any
  tool_name?: string
  arguments?: any
  result?: any
}
