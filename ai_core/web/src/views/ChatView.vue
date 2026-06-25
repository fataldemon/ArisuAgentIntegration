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
          <div class="message-bubble-wrap">
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
        </div>

        <div v-if="isStreaming" class="message-row assistant">
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
          :disabled="isStreaming"
          @keydown="handleKeydown"
          class="chat-input"
        />
        <n-button
          type="primary"
          :disabled="isStreaming || !inputText.trim()"
          @click="sendMessage"
          class="send-btn"
        >
          {{ $t('chat.send') }}
        </n-button>
        <n-button
          v-if="isStreaming"
          type="error"
          @click="abortStream"
          class="stop-btn"
        >
          {{ $t('chat.stopGenerating') }}
        </n-button>
      </div>
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
import { ref, computed, onMounted, watch, nextTick } from 'vue'
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
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import HelpTip from '../components/HelpTip.vue'
import { inferenceApi } from '../api/inference'

const { t } = useI18n()
const message = useMessage()

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  thought?: string
  timestamp: number
}

interface ContentPart {
  type: 'text' | 'action'
  value: string
}

const messagesRef = ref<HTMLElement | null>(null)
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isStreaming = ref(false)

// session management
const sessionId = ref('')
const sessions = ref<Array<{session_id: string; created: string; updated: string; preview: string}>>([])
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

function hippoSid(): string {
  return `chat:${identity.value || 'default'}:${sessionId.value}`
}

function fmtTs(ts: number): string {
  const d = new Date(ts)
  const M = (d.getMonth() + 1).toString().padStart(2, '0')
  const D = d.getDate().toString().padStart(2, '0')
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return `[${M}-${D} ${h}:${m}]`
}

async function fetchSessions() {
  try {
    const prefix = `chat:${identity.value || 'default'}:`
    const res = await fetch(`/ctx/sessions/list?prefix=${encodeURIComponent(prefix)}`)
    const data = await res.json()
    sessions.value = data.sessions || []
  } catch { sessions.value = [] }
}

function createSession() {
  const id = crypto.randomUUID()
  sessionId.value = id
  localStorage.setItem('arisu-chat-session', id)
  sessions.value.unshift({ session_id: id, created: new Date().toISOString(), updated: new Date().toISOString(), preview: '' })
  messages.value = []
  scrollToBottom()
}

async function switchSession(id: string) {
  sessionId.value = id
  localStorage.setItem('arisu-chat-session', id)
  await loadSessionHistory()
  scrollToBottom()
}

async function deleteSession(id: string) {
  try { await fetch(`/ctx/${encodeURIComponent(id)}/clear`, { method: 'POST' }) } catch {}
  if (id === sessionId.value) {
    createSession()
    return
  }
  sessions.value = sessions.value.filter(s => s.session_id !== id)
}

async function loadSessionHistory() {
  if (!sessionId.value) { messages.value = []; return }
  try {
    const res = await fetch(`/ctx/${encodeURIComponent(sessionId.value)}/turn-context?limit=100`)
    const data = await res.json()
    messages.value = (data.history || []).map((h: any) => ({
      role: h.role,
      content: h.content || '',
      thought: undefined,
      timestamp: h.timestamp ? new Date(h.timestamp).getTime() : Date.now(),
    }))
  } catch { messages.value = [] }
}

async function hippoSave(role: string, content: string) {
  if (!sessionId.value) return
  try {
    await fetch(`/ctx/${encodeURIComponent(sessionId.value)}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, content, max_history: 40, timestamp: new Date().toISOString() }),
    })
  } catch {}
}

async function hippoClear() {
  try { await fetch(`/ctx/${encodeURIComponent(sessionId.value)}/clear`, { method: 'POST' }) } catch {}
}

function storageKey(): string {
  return `arisu-chat-${character.value}`
}

function saveMessages() {
  // persistence is handled by hippoSave() in sendMessage; kept for compat
}

function loadMessages() {
  // replaced by loadSessionHistory(); kept for compat
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
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
      // restore last session or create new one
      const saved = localStorage.getItem('arisu-chat-session')
      await fetchSessions()
      if (saved && sessions.value.some(s => s.session_id === saved)) {
        sessionId.value = saved
        await loadSessionHistory()
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

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  const userMsg: ChatMessage = {
    role: 'user',
    content: text,
    timestamp: Date.now(),
  }
  messages.value.push(userMsg)
  saveMessages()
  hippoSave('user', text)
  inputText.value = ''
  scrollToBottom()

  isStreaming.value = true
  rawStreamText.value = ''
  currentAbortId.value = generateId()
  abortController.value = new AbortController()

  try {
    const apiMessages = messages.value.map((m) => {
      const ts = fmtTs(m.timestamp)
      if (m.role === 'user' && identity.value.trim()) {
        return { role: m.role, content: `${ts} （${identity.value.trim()}说）${m.content}` }
      }
      return { role: m.role, content: `${ts} ${m.content}` }
    })

    const res = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: '',
        character: character.value,
        messages: apiMessages,
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
      }),
      signal: abortController.value.signal,
    })

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

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
        } catch {
        }
      }
    }

    const { thought, content } = parseThinkBlock(rawStreamText.value, enableThinking.value)
    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: content,
      thought: thought || undefined,
      timestamp: Date.now(),
    }
    messages.value.push(assistantMsg)
    saveMessages()
    hippoSave('assistant', content)
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `[Error: ${e.message || 'Request failed'}]`,
        timestamp: Date.now(),
      }
      messages.value.push(errorMsg)
      saveMessages()
      hippoSave('assistant', errorMsg.content)
    } else if (rawStreamText.value) {
      const { thought, content } = parseThinkBlock(rawStreamText.value, enableThinking.value)
      const partialMsg: ChatMessage = {
        role: 'assistant',
        content: content || '[Aborted]',
        thought: thought || undefined,
        timestamp: Date.now(),
      }
      messages.value.push(partialMsg)
      saveMessages()
      hippoSave('assistant', content || '[Aborted]')
    }
  } finally {
    isStreaming.value = false
    rawStreamText.value = ''
    abortController.value = null
    currentAbortId.value = ''
    scrollToBottom()
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
})
</script>

<style scoped>
.chat-view {
  display: flex;
  height: calc(100vh - 56px);
  background: #F0F4FA;
  margin: -24px;
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
.session-item.active { background: var(--n-color-pressed); }

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
