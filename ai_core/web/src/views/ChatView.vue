<template>
  <div class="chat-view">
    <div class="chat-area">
      <div class="messages-container" ref="messagesRef">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          :class="['message-row', msg.role]"
        >
          <div class="message-bubble-wrap">
            <div :class="['message-bubble', msg.role]">
              <template v-if="msg.role === 'assistant'">
                <div v-if="msg.thought" class="thinking-section">
                  <n-collapse :default-expanded-names="[]">
                    <n-collapse-item title="Thinking" name="thinking">
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
        </div>

        <div v-if="isStreaming" class="message-row assistant">
          <div class="message-bubble-wrap">
            <div class="message-bubble assistant">
              <div v-if="streamingThought" class="thinking-section">
                <n-collapse :default-expanded-names="[]">
                  <n-collapse-item title="Thinking" name="thinking">
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
          placeholder="Type a message..."
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
          Send
        </n-button>
        <n-button
          v-if="isStreaming"
          type="error"
          @click="abortStream"
          class="stop-btn"
        >
          Stop generating
        </n-button>
      </div>
    </div>

    <div class="param-panel">
      <n-card title="Parameters" size="small" class="param-card">
        <div class="param-item">
          <label class="param-label">Your Identity</label>
          <n-input v-model:value="identity" placeholder="老师" size="small" />
        </div>

        <div class="param-item">
          <label class="param-label">Character</label>
          <n-select
            v-model:value="character"
            :options="characterOptions"
            @update:value="onCharacterChange"
            placeholder="Select character"
          />
        </div>

        <div class="param-item">
          <label class="param-label">Temperature: {{ temperature.toFixed(2) }}</label>
          <n-slider v-model:value="temperature" :min="0" :max="2" :step="0.01" />
        </div>

        <div class="param-item">
          <label class="param-label">Top-p: {{ topP.toFixed(2) }}</label>
          <n-slider v-model:value="topP" :min="0" :max="1" :step="0.01" />
        </div>

        <div class="param-item">
          <label class="param-label">Max Tokens</label>
          <n-input v-model:value="maxTokensStr" placeholder="15000" />
        </div>

        <div class="param-item">
          <div class="switch-row">
            <label class="param-label">Enable Thinking</label>
            <n-switch v-model:value="enableThinking" />
          </div>
        </div>

        <div class="param-item">
          <div class="switch-row">
            <label class="param-label">On Embedding</label>
            <n-switch v-model:value="onEmbedding" />
          </div>
        </div>

        <div class="param-item">
          <n-button type="error" block @click="clearHistory">Clear History</n-button>
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
} from 'naive-ui'

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
const rawStreamText = ref('')
const characterOptions = ref<Array<{ label: string; value: string }>>([])
const character = ref('')
const temperature = ref(0.6)
const topP = ref(0.95)
const maxTokensStr = ref('15000')
const enableThinking = ref(true)
const onEmbedding = ref(true)
const identity = ref('老师')
const abortController = ref<AbortController | null>(null)
const currentAbortId = ref('')

function saveParams() {
  localStorage.setItem('arisu-chat-params', JSON.stringify({
    temperature: temperature.value,
    topP: topP.value,
    maxTokens: maxTokensStr.value,
    enableThinking: enableThinking.value,
    onEmbedding: onEmbedding.value,
    identity: identity.value,
  }))
}

function loadParams() {
  try {
    const raw = localStorage.getItem('arisu-chat-params')
    if (raw) {
      const p = JSON.parse(raw)
      if (p.temperature !== undefined) temperature.value = p.temperature
      if (p.topP !== undefined) topP.value = p.topP
      if (p.maxTokens !== undefined) maxTokensStr.value = p.maxTokens
      if (p.enableThinking !== undefined) enableThinking.value = p.enableThinking
      if (p.onEmbedding !== undefined) onEmbedding.value = p.onEmbedding
      if (p.identity !== undefined) identity.value = p.identity
    }
  } catch {}
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

function storageKey(): string {
  return `arisu-chat-${character.value}`
}

function saveMessages() {
  if (!character.value) return
  localStorage.setItem(
    storageKey(),
    JSON.stringify(
      messages.value.map((m) => ({
        role: m.role,
        content: m.content,
        thought: m.thought,
        timestamp: m.timestamp,
      }))
    )
  )
}

function loadMessages() {
  if (!character.value) {
    messages.value = []
    return
  }
  try {
    const raw = localStorage.getItem(storageKey())
    if (raw) {
      messages.value = JSON.parse(raw)
    } else {
      messages.value = []
    }
  } catch {
    messages.value = []
  }
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
      loadMessages()
      scrollToBottom()
    }
  } catch {
    characterOptions.value = []
  }
}

function onCharacterChange() {
  loadMessages()
  scrollToBottom()
}

function clearHistory() {
  if (character.value) {
    localStorage.removeItem(storageKey())
  }
  messages.value = []
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
  inputText.value = ''
  scrollToBottom()

  isStreaming.value = true
  rawStreamText.value = ''
  currentAbortId.value = generateId()
  abortController.value = new AbortController()

  try {
    const apiMessages = messages.value.map((m) => {
      if (m.role === 'user' && identity.value.trim()) {
        return { role: m.role, content: `（名叫"${identity.value.trim()}"的人说）${m.content}` }
      }
      return { role: m.role, content: m.content }
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
          // skip malformed JSON
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
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `[Error: ${e.message || 'Request failed'}]`,
        timestamp: Date.now(),
      }
      messages.value.push(errorMsg)
      saveMessages()
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
      // ignore abort request errors
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

watch(
  [temperature, topP, maxTokensStr, enableThinking, onEmbedding, identity],
  () => saveParams(),
  { deep: true }
)

onMounted(() => {
  loadParams()
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
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-bubble-wrap {
  max-width: 70%;
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
</style>
