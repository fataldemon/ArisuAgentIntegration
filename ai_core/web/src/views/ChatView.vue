<template>
  <div class="chat-view">
    <div class="session-sidebar">
      <div class="sidebar-header">
        <n-button type="primary" size="small" block @click="createSession">{{ $t('chat.newSession') }}</n-button>
      </div>
      <div class="session-list">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          :class="['session-item', { active: s.session_id === sessionId }]"
          @click="switchSession(s.session_id)"
        >
          <div class="session-preview">{{ s.preview || $t('chat.emptySession') }}</div>
          <div class="session-meta">
            <span class="session-time">{{ formatSessionTime(s.updated) }}</span>
            <n-button text size="tiny" type="error" @click.stop="deleteSession(s.session_id)">✕</n-button>
          </div>
        </div>
        <div v-if="!sessions.length" class="session-empty">{{ $t('chat.noSessions') }}</div>
      </div>
    </div>

    <div class="chat-area">
      <div class="messages-container" ref="messagesRef">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          :class="['message-row', msg.role]"
        >
          <img v-if="msg.role === 'assistant'" :src="getEmotionAvatar(parseEmotions(msg.content))" class="avatar" />
          <div v-if="msg.role === 'user' || msg.role === 'assistant'" class="message-bubble-wrap">
            <div :class="['message-bubble', msg.role]">
              <template v-if="msg.role === 'assistant'">
                <div v-if="msg.thought" class="thinking-section">
                  <n-collapse :default-expanded-names="[]">
                    <n-collapse-item :title="$t('chat.thinking')" name="thinking">
                      <div class="thinking-content">{{ msg.thought }}</div>
                    </n-collapse-item>
                  </n-collapse>
                </div>
                <template v-for="(part, pidx) in parseAssistantContent(msg.content)" :key="pidx">
                  <span v-if="part.type === 'text'">{{ part.value }}</span>
                  <span v-else-if="part.type === 'action'" class="action-text">{{ part.value }}</span>
                </template>
                <div v-if="parseEmotions(msg.content).length" class="emotion-tags">
                  <n-tag
                    v-for="(emo, eidx) in parseEmotions(msg.content)"
                    :key="eidx"
                    size="small"
                    type="info"
                    class="emotion-tag"
                  >
                    {{ emo }}
                  </n-tag>
                </div>
              </template>
              <template v-else>
                {{ msg.content }}
              </template>
            </div>
            <div class="message-time">{{ formatTime(msg.timestamp) }}</div>
          </div>
          <img v-if="msg.role === 'user'" :src="userAvatar" class="avatar" />
          <div v-if="msg.role === 'tool_call' || msg.role === 'tool_result'" class="tool-msg-row">
            <n-collapse :default-expanded-names="msg.role === 'tool_result' ? [] : ['tool']">
              <n-collapse-item name="tool">
                <template #header>
                  <span class="tool-msg-header">
                    <span v-if="msg.role === 'tool_call'" class="tool-icon">&#x1F527;</span>
                    <span v-else class="tool-icon">{{ msg.content.startsWith('Error') ? '&#x274C;' : '&#x2705;' }}</span>
                    <strong>{{ msg.toolName }}</strong>
                    <span v-if="msg.role === 'tool_call'" class="tool-running">running...</span>
                  </span>
                </template>
                <pre class="tool-msg-body" v-if="msg.role === 'tool_result'">{{ msg.content }}</pre>
              </n-collapse-item>
            </n-collapse>
          </div>
        </div>

        <div v-if="isStreaming && streamingSessionId === sessionId" class="message-row assistant">
          <img :src="getEmotionAvatar(parseEmotions(streamingContent))" class="avatar" />
          <div class="message-bubble-wrap">
            <div class="message-bubble assistant">
              <div v-if="streamingThought" class="thinking-section">
                <n-collapse :default-expanded-names="[]">
                  <n-collapse-item :title="$t('chat.thinking')" name="thinking">
                    <div class="thinking-content">{{ streamingThought }}</div>
                  </n-collapse-item>
                </n-collapse>
              </div>
              <template v-if="streamingContent">
                <template v-for="(part, pidx) in parseAssistantContent(streamingContent)" :key="pidx">
                  <span v-if="part.type === 'text'">{{ part.value }}</span>
                  <span v-else-if="part.type === 'action'" class="action-text">{{ part.value }}</span>
                </template>
                <div v-if="parseEmotions(streamingContent).length" class="emotion-tags">
                  <n-tag
                    v-for="(emo, eidx) in parseEmotions(streamingContent)"
                    :key="eidx"
                    size="small"
                    type="info"
                    class="emotion-tag"
                  >
                    {{ emo }}
                  </n-tag>
                </div>
              </template>
              <n-spin :size="16" class="typing-spin" />
            </div>
          </div>
        </div>
      </div>

      <div class="input-area">
        <n-input
          v-model:value="inputText"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          :placeholder="$t('chat.typeMessage')"
          @keydown="handleKeydown"
          class="chat-input"
        />
        <n-button
          type="primary"
          :disabled="!inputText.trim()"
          @click="sendMessage"
          class="send-btn"
        >
          {{ $t('chat.send') }}
        </n-button>
        <n-button
          v-if="isStreaming && streamingSessionId === sessionId"
          type="error"
          @click="abortStream"
          class="stop-btn"
        >
          {{ $t('chat.stopGenerating') }}
        </n-button>
      </div>

      <n-modal v-model:show="showToolConfirm" preset="card" :title="$t('chat.toolConfirm')" style="max-width: 520px">
        <div style="margin-bottom: 10px; font-size: 14px;">
          <strong>{{ toolConfirmName }}</strong>
          <span style="color:#888; font-size:12px;"> {{ $t('chat.toolConfirmDesc') }}</span>
        </div>
        <div v-if="toolConfirmIsSystemFile" style="background:#fff7e6; border:1px solid #ffd591; border-radius:6px; padding:8px 10px; font-size:12px; margin-bottom:10px; word-break:break-all;">
          <strong>{{ $t('chat.outOfWorkspace') }}</strong><br/>
          {{ toolConfirmPath }}
        </div>
        <div style="background: #f5f5f5; border-radius: 6px; padding: 10px; font-size: 12px; max-height: 160px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;">
          {{ JSON.stringify(toolConfirmArgs, null, 2) }}
        </div>

        <div style="margin-top: 10px;">
          <n-input
            v-model:value="toolConfirmQuestion"
            :placeholder="$t('chat.askExplainPlaceholder')"
            size="small"
          />
          <n-button size="small" style="margin-top: 6px;" :loading="toolConfirmExplaining" @click="requestToolExplanation">
            {{ $t('chat.requestExplain') }}
          </n-button>
          <div v-if="toolConfirmExplanation" style="background:#e6f7ff; border:1px solid #91d5ff; border-radius:6px; padding:8px 10px; font-size:12px; margin-top:8px; white-space:pre-wrap;">
            {{ toolConfirmExplanation }}
          </div>
        </div>

        <template #footer>
          <n-space justify="end" :wrap="false">
            <n-button @click="onToolDecision('deny')">{{ $t('chat.toolReject') }}</n-button>
            <n-button v-if="toolConfirmIsSystemFile" @click="onToolDecision('always')">{{ $t('chat.alwaysAllowDir') }}</n-button>
            <n-button type="primary" @click="onToolDecision('once')">{{ $t('chat.allowOnce') }}</n-button>
          </n-space>
        </template>
      </n-modal>
    </div>

    <div class="param-panel">
      <n-card :title="$t('chat.parameters')" size="small" class="param-card">
        <div class="param-item">
          <label class="param-label">{{ $t('chat.identity') }} <HelpTip>{{ $t('tips.chatIdentity') }}</HelpTip></label>
          <n-input v-model:value="identity" :placeholder="$t('chat.identityPlaceholder')" size="small" />
        </div>

        <div class="param-item">
          <label class="param-label">{{ $t('chat.character') }} <HelpTip>{{ $t('tips.chatCharacter') }}</HelpTip></label>
          <n-select
            v-model:value="character"
            :options="characterOptions"
            @update:value="onCharacterChange"
            :placeholder="$t('chat.selectCharacter')"
          />
        </div>

        <div class="param-item">
          <label class="param-label">{{ $t('chat.temperature') }}: {{ temperature.toFixed(2) }} <HelpTip>{{ $t('tips.chatTemperature') }}</HelpTip></label>
          <n-slider v-model:value="temperature" :min="0" :max="2" :step="0.01" />
        </div>

        <div class="param-item">
          <label class="param-label">{{ $t('chat.topP') }}: {{ topP.toFixed(2) }} <HelpTip>{{ $t('tips.chatTopP') }}</HelpTip></label>
          <n-slider v-model:value="topP" :min="0" :max="1" :step="0.01" />
        </div>

        <div class="param-item">
          <label class="param-label">{{ $t('chat.maxTokens') }} <HelpTip>{{ $t('tips.chatMaxTokens') }}</HelpTip></label>
          <n-input v-model:value="maxTokensStr" placeholder="15000" />
        </div>

        <div class="param-item">
          <div class="switch-row">
            <label class="param-label">{{ $t('chat.enableThinking') }} <HelpTip>{{ $t('tips.chatEnableThinking') }}</HelpTip></label>
            <n-switch v-model:value="enableThinking" />
          </div>
        </div>

        <div class="param-item">
          <div class="switch-row">
            <label class="param-label">{{ $t('chat.onEmbedding') }} <HelpTip>{{ $t('tips.chatOnEmbedding') }}</HelpTip></label>
            <n-switch v-model:value="onEmbedding" />
          </div>
        </div>

        <div class="param-item">
          <label class="param-label">{{ $t('inference.topK') }} <HelpTip>Top-k 采样参数</HelpTip></label>
          <n-input v-model:value="topKStr" placeholder="20" size="small" />
        </div>

        <div class="param-item">
          <label class="param-label">{{ $t('inference.repetitionPenalty') }} <HelpTip>重复惩罚系数</HelpTip></label>
          <n-input v-model:value="repetitionPenaltyStr" placeholder="1.05" size="small" />
        </div>

        <div class="param-item">
          <label class="param-label">{{ $t('inference.presencePenalty') }} <HelpTip>存在惩罚系数</HelpTip></label>
          <n-input v-model:value="presencePenaltyStr" placeholder="1.1" size="small" />
        </div>

        <div class="param-item">
          <n-button type="info" block @click="saveToGlobal">{{ $t('inference.saveToGlobal') }}</n-button>
        </div>

        <div class="param-item">
          <n-button type="error" block @click="clearHistory">{{ $t('chat.clearHistory') }}</n-button>
        </div>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, reactive } from 'vue'
import {
  NCard,
  NInput,
  NButton,
  NSlider,
  NSwitch,
  NSelect,
  NCollapse,
  NCollapseItem,
  NSpin,
  NTag,
  NModal,
  NSpace,
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import HelpTip from '../components/HelpTip.vue'
import { inferenceApi } from '../api/inference'
import { toolsApi } from '../api/tools'

const { t } = useI18n()
const message = useMessage()

interface ChatMessage {
  role: 'user' | 'assistant' | 'tool_call' | 'tool_result'
  content: string
  thought?: string
  timestamp: number
  toolName?: string
  toolArgs?: Record<string, any>
}

interface ContentPart {
  type: 'text' | 'action'
  value: string
}

const messagesRef = ref<HTMLElement | null>(null)
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const streamingSessionId = ref('')

// session management
const sessionId = ref('')
const sessions = ref<Array<{session_id: string; created: string; updated: string; preview: string}>>([])
const sessionCache = reactive<Record<string, ChatMessage[]>>({})
const identity = ref('老师')
const characterOptions = ref<Array<{ label: string; value: string }>>([])
const character = ref('')
// label -> image filename, fetched from the active character's persona.expressions
const expressionMap = ref<Record<string, string>>({})
const temperature = ref(0.6)
const topP = ref(0.95)
const topK = ref(20)
const repetitionPenalty = ref(1.05)
const presencePenalty = ref(1.1)
const maxTokensStr = ref('15000')
const enableThinking = ref(true)
const onEmbedding = ref(true)
const rawStreamText = ref('')

const topKStr = computed({
  get: () => String(topK.value),
  set: (v: string) => { topK.value = Number(v) || 0 },
})
const repetitionPenaltyStr = computed({
  get: () => String(repetitionPenalty.value),
  set: (v: string) => { repetitionPenalty.value = Number(v) || 0 },
})
const presencePenaltyStr = computed({
  get: () => String(presencePenalty.value),
  set: (v: string) => { presencePenalty.value = Number(v) || 0 },
})
const abortController = ref<AbortController | null>(null)
const currentAbortId = ref('')

// Capability-based tool authorization (fetched from backend). A tool call is
// auto-executed when its resolved capability state is "allow"; "ask" shows the
// confirmation modal; "deny" is rejected by the server.
const toolCapabilityStates = ref<Record<string, string>>({})

const _FILE_READ_TOOLS = new Set(['read_file', 'list_directory', 'search_files', 'search_content'])
const _FILE_WRITE_TOOLS = new Set(['write_file', 'edit_file', 'delete_file'])
const _STATIC_CAPABILITY: Record<string, string> = {
  terminal_command: 'shell.exec',
  screenshot: 'desktop.observe', list_windows: 'desktop.observe', get_active_window: 'desktop.observe',
  click: 'desktop.control', type_text: 'desktop.control', scroll: 'desktop.control', press_keys: 'desktop.control', drag: 'desktop.control',
  list_processes: 'process.observe', get_process_info: 'process.observe',
  kill_process: 'process.control',
  list_skills: 'skill.read', read_skill: 'skill.read',
  echo: 'test.run',
}

function resolveCapability(name: string, args: Record<string, any>): string {
  const scope = args?.scope === 'system' ? 'system' : 'workspace'
  if (_FILE_READ_TOOLS.has(name)) return scope === 'system' ? 'file.read.system' : 'file.read.workspace'
  if (_FILE_WRITE_TOOLS.has(name)) return scope === 'system' ? 'file.write.system' : 'file.write.workspace'
  return _STATIC_CAPABILITY[name] || ''
}

async function loadToolCapabilityStates() {
  try {
    const data = await toolsApi.getCapabilities()
    const map: Record<string, string> = {}
    for (const c of data.capabilities) map[c.key] = c.state
    toolCapabilityStates.value = map
  } catch {}
}

const showToolConfirm = ref(false)
const toolConfirmName = ref('')
const toolConfirmArgs = ref<Record<string, any>>({})
const toolConfirmPath = ref('')
const toolConfirmDir = ref('')
const toolConfirmIsSystemFile = ref(false)
const toolConfirmQuestion = ref('')
const toolConfirmExplanation = ref('')
const toolConfirmExplaining = ref(false)
const toolConfirmResolve = ref<((decision: 'once' | 'always' | 'deny') => void) | null>(null)
const toolExecuting = ref(false)
const toolExecutingName = ref('')

const _MAX_TOOL_ROUNDS = 8

async function loadInferenceParams() {
  try {
    const data = await inferenceApi.get()
    const chatParams = data.chat || {}
    if (chatParams.temperature !== undefined) temperature.value = chatParams.temperature
    if (chatParams.top_p !== undefined) topP.value = chatParams.top_p
    if (chatParams.top_k !== undefined) topK.value = chatParams.top_k
    if (chatParams.repetition_penalty !== undefined) repetitionPenalty.value = chatParams.repetition_penalty
    if (chatParams.presence_penalty !== undefined) presencePenalty.value = chatParams.presence_penalty
    if (chatParams.enable_thinking !== undefined) enableThinking.value = chatParams.enable_thinking
    if (chatParams.on_embedding !== undefined) onEmbedding.value = chatParams.on_embedding
  } catch {}
}

async function saveToGlobal() {
  try {
    const current = await inferenceApi.get()
    current.chat = {
      temperature: temperature.value,
      top_p: topP.value,
      top_k: Number(topK.value) || 20,
      repetition_penalty: Number(repetitionPenalty.value) || 1.05,
      presence_penalty: Number(presencePenalty.value) || 1.1,
      enable_thinking: enableThinking.value,
      on_embedding: onEmbedding.value,
    }
    await inferenceApi.save(current)
    message.success(t('inference.saved'))
  } catch (e: any) {
    message.error(e?.message || 'Failed to save')
  }
}

async function loadIdentity() {
  try {
    const res = await fetch('/admin/api/identity')
    const data = await res.json()
    if (data.identity) identity.value = data.identity
  } catch {}
}

let _identitySaveTimer: ReturnType<typeof setTimeout> | null = null
function saveIdentityDebounced() {
  if (_identitySaveTimer) clearTimeout(_identitySaveTimer)
  _identitySaveTimer = setTimeout(async () => {
    try {
      await fetch('/admin/api/identity', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identity: identity.value }),
      })
    } catch {}
  }, 500)
}

function generateId(): string {
  return Math.random().toString(36).substring(2, 15) + Date.now().toString(36)
}

function parseThinkBlock(raw: string, isThinkingEnabled: boolean = false): { thought: string; content: string } {
  if (raw.includes('<think>') && raw.includes('</think>')) {
    const m = raw.match(/<think>([\s\S]*?)<\/think>/)
    const thought = m ? m[1].trim() : ''
    const lastIdx = raw.lastIndexOf('</think>')
    const content = lastIdx >= 0 ? raw.substring(lastIdx + '</think>'.length).trim() : ''
    return { thought, content }
  }
  if (raw.includes('</think>')) {
    const idx = raw.indexOf('</think>')
    return { thought: raw.substring(0, idx).trim(), content: raw.substring(idx + '</think>'.length).trim() }
  }
  if (raw.includes('<think>')) {
    const idx = raw.indexOf('<think>')
    return { thought: raw.substring(idx + '<think>'.length), content: raw.substring(0, idx) }
  }
  if (isThinkingEnabled) {
    return { thought: raw, content: '' }
  }
  return { thought: '', content: raw }
}

const parsedStream = computed(() => parseThinkBlock(rawStreamText.value, enableThinking.value))
const streamingThought = computed(() => parsedStream.value.thought)
const streamingContent = computed(() => parsedStream.value.content)

function stripThinkContent(text: string): string {
  let cleaned = text.replace(/<think>[\s\S]*?<\/think>/g, '')
  if (cleaned.includes('</think>')) {
    cleaned = cleaned.substring(cleaned.indexOf('</think>') + '</think>'.length)
  }
  if (cleaned.includes('<think>')) {
    cleaned = cleaned.substring(0, cleaned.indexOf('<think>'))
  }
  return cleaned
}

const emotionImageMap: Record<string, string> = {
  '认真': 'angry.png', '坚定': 'angry.png', '承诺': 'angry.png',
  '生气': 'angry.png', '急切': 'angry.png', '拒绝': 'angry.png', '警惕': 'angry.png',
  '烦恼': 'screwup.png', '慌张': 'screwup.png',
  '专注': 'awake.png', '诚实': 'awake.png', '回答': 'awake.png',
  '发愣': 'awake.png', '察觉': 'awake.png', '好奇': 'awake.png',
  '期待': 'smile.png', '建议': 'smile.png', '解释': 'smile.png',
  '高兴': 'smile.png', '欢迎': 'smile.png', '崇拜': 'smile.png',
  '愉快': 'smile.png', '贴心': 'smile.png', '赞同': 'smile.png',
  '邀请': 'smile.png', '惊喜': 'smile.png', '理解': 'smile.png', '喜悦': 'smile.png',
  '回忆': 'thinking.png', '思考': 'thinking.png', '沉思': 'thinking.png',
  '否认': 'thinking.png', '睡觉': 'thinking.png', '祈祷': 'thinking.png',
  '自信': 'confident.png', '自豪': 'confident.png', '微笑': 'confident.png',
  '失望': 'awkward.png', '难过': 'awkward.png', '为难': 'awkward.png',
  '紧张': 'awkward.png', '困惑': 'awkward.png', '困扰': 'awkward.png',
  '疑惑': 'awkward.png', '犹豫': 'awkward.png',
  '委屈': 'cry.png', '伤心': 'cry.png',
  '开心': 'happy.png', '兴奋': 'happy.png', '快乐': 'happy.png',
  '可爱': 'happy.png', '俏皮': 'happy.png', '调皮': 'happy.png',
  '卖萌': 'happy.png', '眨眼': 'happy.png',
  '害怕': 'sweating.png', '无奈': 'sweating.png', '担忧': 'sweating.png',
  '流汗': 'sweating.png', '尴尬': 'sweating.png', '震惊': 'sweating.png',
  '惊讶': 'sweating.png', '道歉': 'sweating.png',
  '平和': 'plain.png', '无聊': 'plain.png', '陈述': 'plain.png',
  '害羞': 'shy.png', '羞涩': 'shy.png',
  '感动': 'touching.png', '感激': 'touching.png',
}

function getEmotionAvatar(emotions: string[]): string {
  const label = emotions.length ? emotions[0] : ''
  const img = expressionMap.value[label]
  if (img && character.value) {
    return `/admin/characters/${character.value}/expression/${img}`
  }
  // fallback to the legacy static emoji set when persona has no expressions
  return `/admin/emoji/${emotionImageMap[label] || 'plain.png'}`
}

const userAvatar = '/admin/emoji/sensei.jpg'

function parseEmotions(text: string): string[] {
  const cleaned = stripThinkContent(text)
  const emotions: string[] = []
  const regex = /【\{\s*['"]expression['"]\s*:\s*['"]([^'"]+)['"]\s*\}】/g
  let match
  while ((match = regex.exec(cleaned)) !== null) {
    emotions.push(match[1])
  }
  return emotions
}

function stripEmotions(text: string): string {
  const cleaned = stripThinkContent(text)
  return cleaned.replace(/【\{\s*['"]expression['"]\s*:\s*['"][^'"]+['"]\s*\}】/g, '')
}

function parseAssistantContent(text: string): ContentPart[] {
  const stripped = stripEmotions(text)
  const parts: ContentPart[] = []
  const regex = /（([^）]+)）/g
  let lastIndex = 0
  let match
  while ((match = regex.exec(stripped)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: stripped.substring(lastIndex, match.index) })
    }
    parts.push({ type: 'action', value: match[0] })
    lastIndex = regex.lastIndex
  }
  if (lastIndex < stripped.length) {
    parts.push({ type: 'text', value: stripped.substring(lastIndex) })
  }
  if (parts.length === 0 && stripped) {
    parts.push({ type: 'text', value: stripped })
  }
  return parts
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return `${h}:${m}`
}

function formatSessionTime(ts: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts.slice(0, 10)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return isToday ? `${h}:${m}` : `${(d.getMonth()+1)}/${d.getDate()}`
}

function hippoSid(id?: string): string {
  return `chat:${identity.value || 'default'}:${id || sessionId.value}`
}

function fmtTs(ts: number): string {
  const d = new Date(ts)
  const M = (d.getMonth() + 1).toString().padStart(2, '0')
  const D = d.getDate().toString().padStart(2, '0')
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return `[${M}-${D} ${h}:${m}]`
}

function stripTimestamp(text: string): string {
  return text.replace(/^\s*\[\d{2}-\d{2}\s+\d{2}:\d{2}\]\s*/, '')
}

async function fetchSessions() {
  try {
    const prefix = `chat:${identity.value || 'default'}:`
    const res = await fetch(`/ctx/sessions/list?prefix=${encodeURIComponent(prefix)}`)
    const data = await res.json()
    sessions.value = (data.sessions || []).map((s: any) => ({
      ...s,
      session_id: s.session_id.replace(prefix, ''),
    }))
  } catch { sessions.value = [] }
}

function createSession() {
  const id = crypto.randomUUID()
  sessionId.value = id
  localStorage.setItem('arisu-chat-session', id)
  sessions.value.unshift({ session_id: id, created: new Date().toISOString(), updated: new Date().toISOString(), preview: '' })
  sessionCache[id] = []
  messages.value = sessionCache[id]
  scrollToBottom()
}

async function switchSession(id: string) {
  sessionId.value = id
  localStorage.setItem('arisu-chat-session', id)
  if (!sessionCache[id]) {
    const msgs = await loadSessionHistoryFor(id)
    sessionCache[id] = msgs
  }
  messages.value = sessionCache[id]
  scrollToBottom()
}

async function deleteSession(id: string) {
  const fullId = `chat:${identity.value || 'default'}:${id}`
  try { await fetch(`/ctx/${encodeURIComponent(fullId)}/delete`, { method: 'POST' }) } catch {}
  delete sessionCache[id]
  sessions.value = sessions.value.filter(s => s.session_id !== id)
  if (id === sessionId.value) {
    const next = sessions.value[0]
    if (next) { await switchSession(next.session_id) }
    else { createSession() }
  }
}

async function loadSessionHistoryFor(id: string): Promise<ChatMessage[]> {
  try {
    const fullId = `chat:${identity.value || 'default'}:${id}`
    const res = await fetch(`/ctx/${encodeURIComponent(fullId)}/turn-context?limit=100`)
    const data = await res.json()
    return (data.history || []).map((h: any) => ({
      role: h.role,
      content: h.content || '',
      thought: undefined,
      timestamp: h.timestamp ? new Date(h.timestamp).getTime() : Date.now(),
    }))
  } catch { return [] }
}

async function hippoSave(role: string, content: string, sid?: string) {
  const id = sid || sessionId.value
  if (!id) return
  try {
    await fetch(`/ctx/${encodeURIComponent(hippoSid(id))}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, content, max_history: 40, timestamp: new Date().toISOString() }),
    })
  } catch {}
}

async function hippoClear(sid?: string) {
  try { await fetch(`/ctx/${encodeURIComponent(hippoSid(sid))}/clear`, { method: 'POST' }) } catch {}
}

function storageKey(): string {
  return `arisu-chat-${character.value}`
}

function saveMessages() {
  // persistence is handled by hippoSave() in sendMessage; kept for compat
}

function loadMessages() {
  // kept for compat – no-op with sessionCache
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesRef.value
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    if (nearBottom) {
      el.scrollTop = el.scrollHeight
    }
  })
}

async function fetchCharacters() {
  try {
    const res = await fetch('/admin/api/personas')
    const data = await res.json()
    characterOptions.value = (data.personas || []).map((p: any) => ({
      label: p.character,
      value: p.character,
    }))
    if (characterOptions.value.length > 0 && !character.value) {
      character.value = characterOptions.value[0].value
      fetchExpressions(character.value)
    }
    // restore session on every mount
    if (character.value && !sessionId.value) {
      await fetchSessions()
      const saved = localStorage.getItem('arisu-chat-session')
      if (saved && sessions.value.some(s => s.session_id === saved)) {
        sessionId.value = saved
        if (!sessionCache[saved]) {
          sessionCache[saved] = await loadSessionHistoryFor(saved)
        }
        messages.value = sessionCache[saved]
      } else {
        createSession()
      }
      scrollToBottom()
    }
  } catch {
    characterOptions.value = []
  }
}

async function fetchExpressions(char: string) {
  if (!char) {
    expressionMap.value = {}
    return
  }
  try {
    const res = await fetch(`/admin/api/personas/${char}`)
    const data = await res.json()
    const exprs = data.expressions || {}
    const m: Record<string, string> = {}
    for (const k in exprs) {
      const v = exprs[k]
      if (v && v.image) m[k] = v.image
    }
    expressionMap.value = m
  } catch {
    expressionMap.value = {}
  }
}

function onCharacterChange() {
  fetchExpressions(character.value)
  if (isStreaming.value) return
  loadMessages()
  scrollToBottom()
}

function clearHistory() {
  messages.value = []
  hippoClear()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function isAutoTool(name: string, args: Record<string, any>): boolean {
  const cap = resolveCapability(name, args)
  return toolCapabilityStates.value[cap] === 'allow'
}

async function executeToolCall(
  name: string,
  args: Record<string, any>,
  permissionDecision: '' | 'once' | 'always' = '',
): Promise<any> {
  const res = await fetch('/v1/tools/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tool_name: name,
      arguments: args,
      confirm: true,
      permission_decision: permissionDecision,
    }),
  })
  return res.json()
}

async function requestToolExplanation() {
  toolConfirmExplaining.value = true
  toolConfirmExplanation.value = ''
  try {
    const res = await fetch('/v1/tools/explain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name: toolConfirmName.value,
        arguments: toolConfirmArgs.value,
        question: toolConfirmQuestion.value,
      }),
    })
    const data = await res.json()
    toolConfirmExplanation.value = data.explanation || data.error || '(无解释返回)'
  } catch (e: any) {
    toolConfirmExplanation.value = `解释请求失败：${e?.message || e}`
  } finally {
    toolConfirmExplaining.value = false
  }
}

function requestToolDecision(
  name: string,
  args: Record<string, any>,
  path: string,
  dir: string,
): Promise<'once' | 'always' | 'deny'> {
  return new Promise((resolve) => {
    toolConfirmName.value = name
    toolConfirmArgs.value = args
    toolConfirmPath.value = path
    toolConfirmDir.value = dir
    toolConfirmIsSystemFile.value = !!dir
    toolConfirmQuestion.value = ''
    toolConfirmExplanation.value = ''
    toolConfirmResolve.value = resolve
    showToolConfirm.value = true
  })
}

function onToolDecision(decision: 'once' | 'always' | 'deny') {
  showToolConfirm.value = false
  const resolve = toolConfirmResolve.value
  toolConfirmResolve.value = null
  if (resolve) resolve(decision)
}

async function handleToolCall(
  name: string,
  args: Record<string, any>,
): Promise<string> {
  const runExec = async (perm: '' | 'once' | 'always') => {
    toolExecuting.value = true
    toolExecutingName.value = name
    try {
      const r = await executeToolCall(name, args, perm)
      return r
    } finally {
      toolExecuting.value = false
      toolExecutingName.value = ''
    }
  }

  if (isAutoTool(name, args)) {
    const r = await runExec('')
    return r.success ? r.output : `Error: ${r.error || 'Unknown error'}`
  }

  const cap = resolveCapability(name, args)
  const isSystemFile = cap === 'file.read.system' || cap === 'file.write.system'

  if (isSystemFile) {
    // Probe: an existing rule may auto-allow; otherwise the server returns
    // needs_permission and we prompt the user (once / always-this-dir / deny).
    const probe = await runExec('')
    if (probe.success) return probe.output
    if (probe.needs_permission) {
      const decision = await requestToolDecision(name, args, probe.path, probe.dir)
      if (decision === 'deny') return 'User rejected the operation.'
      const r = await runExec(decision) // 'once' | 'always'
      return r.success ? r.output : `Error: ${r.error || 'Unknown error'}`
    }
    return `Error: ${probe.error || 'Unknown error'}`
  }

  // Ask-capability tool: prompt (once / deny; explanation available).
  const decision = await requestToolDecision(name, args, '', '')
  if (decision === 'deny') return 'User rejected the operation.'
  const r = await runExec('')
  return r.success ? r.output : `Error: ${r.error || 'Unknown error'}`
}

function buildRequestMessages(): any[] {
  const targetMsgs = sessionCache[sessionId.value]
  if (!targetMsgs) return []
  return targetMsgs.map((m) => {
    if (m.role === 'tool_call') {
      return {
        role: 'assistant',
        content: '',
        function_call: {
          name: m.toolName,
          arguments: m.toolArgs ? JSON.stringify(m.toolArgs) : '{}',
        },
      }
    }
    if (m.role === 'tool_result') {
      return { role: 'tool', content: m.content.replace(/\[image,base64=[^\]]+\]/g, '[image removed]') }
    }
    const ts = fmtTs(m.timestamp)
    if (m.role === 'user' && identity.value.trim()) {
      return { role: m.role, content: `${ts} \uFF08${identity.value.trim()}\u8BF4\uFF09${m.content}` }
    }
    return { role: m.role, content: `${ts} ${m.content}` }
  })
}

async function streamChat(messages: any[]): Promise<{ content: string; thought: string; functionCall: { name: string; arguments: string } | null }> {
  const res = await fetch('/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: '',
      character: character.value,
      messages,
      stream: true,
      temperature: temperature.value,
      top_p: topP.value,
      top_k: topK.value ? Number(topK.value) : undefined,
      repetition_penalty: repetitionPenalty.value ? Number(repetitionPenalty.value) : undefined,
      presence_penalty: presencePenalty.value ? Number(presencePenalty.value) : undefined,
      max_tokens: parseInt(maxTokensStr.value) || 15000,
      on_embedding: onEmbedding.value,
      enable_thinking: enableThinking.value,
      abort_id: currentAbortId.value,
      channel: 'chat',
    }),
    signal: abortController.value!.signal,
  })

  if (!res.ok) throw new Error(`HTTP ${res.status}`)

  let functionCall: { name: string; arguments: string } | null = null
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let done = false

  while (!done) {
    const result = await reader.read()
    if (result.done) break

    buffer += decoder.decode(result.value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue
      const payload = trimmed.slice(6).trim()
      if (payload === '[DONE]') {
        done = true
        break
      }
      try {
        const parsed = JSON.parse(payload)
        const token = parsed.choices?.[0]?.delta?.content
        if (token) {
          rawStreamText.value += token
          scrollToBottom()
        }
        const fc = parsed.choices?.[0]?.delta?.function_call
        if (fc && fc.name) {
          functionCall = { name: fc.name, arguments: fc.arguments || '{}', id: fc.id || '' }
        }
      } catch {}
    }
  }

  const { thought, content } = parseThinkBlock(rawStreamText.value, enableThinking.value)
  return { content, thought, functionCall }
}

async function sendNonStreaming(messages: any[]): Promise<{
  content: string
  thought: string
  finishReason: string
  functionCall: { name: string; arguments: string } | null
}> {
  const res = await fetch('/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: '',
      character: character.value,
      messages,
      stream: false,
      temperature: temperature.value,
      top_p: topP.value,
      top_k: topK.value ? Number(topK.value) : undefined,
      repetition_penalty: repetitionPenalty.value ? Number(repetitionPenalty.value) : undefined,
      presence_penalty: presencePenalty.value ? Number(presencePenalty.value) : undefined,
      max_tokens: parseInt(maxTokensStr.value) || 15000,
      on_embedding: onEmbedding.value,
      enable_thinking: enableThinking.value,
      abort_id: currentAbortId.value,
      channel: 'chat',
    }),
    signal: abortController.value!.signal,
  })

  if (!res.ok) throw new Error(`HTTP ${res.status}`)

  const data = await res.json()
  const choice = data.choices?.[0]
  if (!choice) throw new Error('Empty response')

  const msg = choice.message || {}
  return {
    content: msg.content || '',
    thought: choice.thought || '',
    finishReason: choice.finish_reason || 'stop',
    functionCall: msg.function_call || null,
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text) return
  const sid = sessionId.value
  const targetMsgs = sessionCache[sid]
  if (!targetMsgs) return

  if (isStreaming.value) {
    await abortStream()
    isStreaming.value = false
    streamingSessionId.value = ''
    rawStreamText.value = ''
    abortController.value = null
    currentAbortId.value = ''
  }
  streamingSessionId.value = sid

  const userMsg: ChatMessage = {
    role: 'user',
    content: text,
    timestamp: Date.now(),
  }
  targetMsgs.push(userMsg)
  hippoSave('user', text, sid)
  inputText.value = ''

  isStreaming.value = true
  rawStreamText.value = ''
  currentAbortId.value = generateId()
  abortController.value = new AbortController()

  try {
    const apiMessages = buildRequestMessages()
    await runAgentLoop(apiMessages, targetMsgs, sid)
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `[Error: ${e.message || 'Request failed'}]`,
        timestamp: Date.now(),
      }
      targetMsgs.push(errorMsg)
      hippoSave('assistant', errorMsg.content, sid)
    }
  } finally {
    isStreaming.value = false
    streamingSessionId.value = ''
    rawStreamText.value = ''
    abortController.value = null
    currentAbortId.value = ''
    scrollToBottom()
  }
}

async function runAgentLoop(
  apiMessages: any[],
  targetMsgs: ChatMessage[],
  sid: string,
) {
  let currentMessages = apiMessages

  for (let round = 0; round < _MAX_TOOL_ROUNDS; round++) {
    if (round === 0) {
      const { content, thought, functionCall } = await streamChat(currentMessages)

      if (!functionCall) {
        const cleanContent = stripTimestamp(content)
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: cleanContent,
          thought: thought || undefined,
          timestamp: Date.now(),
        }
        targetMsgs.push(assistantMsg)
        hippoSave('assistant', cleanContent, sid)
        return
      }

      if (content) {
        targetMsgs.push({
          role: 'assistant',
          content: stripTimestamp(content),
          thought: thought || undefined,
          timestamp: Date.now(),
        })
      }

      let args: Record<string, any> = {}
      try { args = JSON.parse(functionCall.arguments) } catch { args = {} }

      const toolIdx = targetMsgs.length
      targetMsgs.push({
        role: 'tool_call',
        content: '',
        toolName: functionCall.name,
        toolArgs: args,
        timestamp: Date.now(),
      })

      const toolResult = await handleToolCall(functionCall.name, args)

      const toolMsg = targetMsgs[toolIdx]
      toolMsg.role = 'tool_result'
      toolMsg.content = toolResult

      currentMessages.push({
        role: 'assistant',
        content: content || '',
        function_call: functionCall,
      })
      currentMessages.push({
        role: 'tool',
        content: toolResult,
      })
      rawStreamText.value = ''
    } else {
      const { content, thought, finishReason, functionCall } = await sendNonStreaming(currentMessages)

      if (!functionCall || finishReason !== 'function_call') {
        const cleanContent = stripTimestamp(content || '')
        targetMsgs.push({
          role: 'assistant',
          content: cleanContent,
          thought: thought || undefined,
          timestamp: Date.now(),
        })
        hippoSave('assistant', cleanContent, sid)
        return
      }

      if (content) {
        targetMsgs.push({
          role: 'assistant',
          content: stripTimestamp(content),
          thought: thought || undefined,
          timestamp: Date.now(),
        })
      }

      let args: Record<string, any> = {}
      try { args = JSON.parse(functionCall.arguments) } catch { args = {} }

      const toolIdx = targetMsgs.length
      targetMsgs.push({
        role: 'tool_call',
        content: '',
        toolName: functionCall.name,
        toolArgs: args,
        timestamp: Date.now(),
      })

      const toolResult = await handleToolCall(functionCall.name, args)

      const toolMsg = targetMsgs[toolIdx]
      toolMsg.role = 'tool_result'
      toolMsg.content = toolResult

      currentMessages.push({
        role: 'assistant',
        content: content || '',
        function_call: functionCall,
      })
      currentMessages.push({
        role: 'tool',
        content: toolResult,
      })
    }
  }
}

async function abortStream() {
  if (currentAbortId.value) {
    try {
      await fetch(`/admin/api/abort/${currentAbortId.value}`, { method: 'POST' })
    } catch {
    }
  }
  if (abortController.value) {
    abortController.value.abort()
  }
}

watch(
  () => rawStreamText.value,
  () => scrollToBottom()
)

watch(identity, () => saveIdentityDebounced())

onMounted(() => {
  loadInferenceParams()
  loadIdentity()
  fetchCharacters()
  loadToolCapabilityStates()
})
</script>

<style scoped>
.chat-view {
  display: flex;
  height: calc(100vh - 56px);
  background: #F0F4FA;
  margin: -24px;
}

.tool-msg-row {
  display: flex;
  justify-content: center;
  margin: 4px 0;
}

.tool-msg-row .n-collapse {
  max-width: 85%;
  min-width: 260px;
}

.tool-msg-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.tool-icon {
  font-size: 14px;
}

.tool-running {
  font-size: 11px;
  color: #999;
  margin-left: 4px;
}

.tool-msg-body {
  font-size: 12px;
  background: #f8f8f8;
  border-radius: 4px;
  padding: 8px 10px;
  margin: 0;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-row {
  display: flex;
  width: 100%;
  align-items: flex-start;
  gap: 10px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  margin-top: 2px;
}

.message-bubble-wrap {
  max-width: 65%;
  display: flex;
  flex-direction: column;
}

.message-row.user .message-bubble-wrap {
  align-items: flex-end;
}

.message-row.assistant .message-bubble-wrap {
  align-items: flex-start;
}

.message-bubble {
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}

.message-bubble.user {
  background: #4C8FEC;
  color: #fff;
  border-radius: 16px 16px 4px 16px;
}

.message-bubble.assistant {
  background: #fff;
  color: #333;
  border: 1px solid #E3E8EF;
  border-radius: 16px 16px 16px 4px;
}

.message-time {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
  padding: 0 4px;
}

.action-text {
  font-style: italic;
  color: #888;
}

.emotion-tags {
  margin-top: 6px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.emotion-tag {
  font-size: 11px;
}

.thinking-section {
  margin-bottom: 8px;
  background: #F5F5F5;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
}

.thinking-content {
  font-size: 12px;
  color: #666;
  white-space: pre-wrap;
  line-height: 1.5;
}

.typing-spin {
  display: inline-block;
  margin-left: 4px;
  vertical-align: middle;
}

.input-area {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid #E3E8EF;
}

.chat-input {
  flex: 1;
}

.send-btn {
  flex-shrink: 0;
  height: 36px;
  background: #4C8FEC;
  border-color: #4C8FEC;
}

.stop-btn {
  flex-shrink: 0;
  height: 36px;
}

.param-panel {
  width: 280px;
  flex-shrink: 0;
  padding: 16px 12px;
  overflow-y: auto;
  background: #F0F4FA;
  border-left: 1px solid #E3E8EF;
}

.param-card {
  background: #fff;
  border-radius: 8px;
}

.param-item {
  margin-bottom: 16px;
}

.param-item:last-child {
  margin-bottom: 0;
}

.param-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #555;
  margin-bottom: 6px;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.switch-row .param-label {
  margin-bottom: 0;
}

.chat-view {
  display: flex;
  height: calc(100vh - 60px);
}

.session-sidebar {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--n-border-color);
  display: flex;
  flex-direction: column;
  background: var(--n-color-embedded);
}

.sidebar-header {
  padding: 8px;
  border-bottom: 1px solid var(--n-border-color);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.session-item {
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.session-item:hover { background: var(--n-color-hover); }
.session-item.active { background: rgba(32, 128, 240, 0.12); border-left: 3px solid #2080f0; }

.session-preview {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--n-text-color);
}

.session-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}

.session-time {
  font-size: 11px;
  color: var(--n-text-color-3);
}

.session-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--n-text-color-3);
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
