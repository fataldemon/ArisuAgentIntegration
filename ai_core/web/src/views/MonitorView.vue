<template>
  <n-space vertical size="large">
    <n-card title="Request Monitor">
      <template #header-extra>
        <n-space align="center" :size="16">
          <span style="white-space: nowrap; font-size: 13px">
            Interval: {{ intervalValue }}s
          </span>
          <n-slider
            v-model:value="intervalValue"
            :min="0.5"
            :max="30"
            :step="0.5"
            style="width: 200px"
          />
          <n-button @click="fetchLog" :loading="loading">Refresh now</n-button>
        </n-space>
      </template>
    </n-card>

    <div
      ref="terminalRef"
      class="monitor-terminal"
      v-html="renderedHtml"
    />
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { NSpace, NCard, NButton, NSlider, useMessage } from 'naive-ui'
import { monitorApi } from '../api/monitor'
import type { MonitorEntry } from '../types'

const message = useMessage()
const entries = ref<MonitorEntry[]>([])
const loading = ref(false)
const intervalValue = ref(3)
const terminalRef = ref<HTMLDivElement | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function span(color: string, text: string, bold = false): string {
  const s = `color:${color}${bold ? ';font-weight:bold' : ''}`
  return `<span style="${s}">${escapeHtml(text)}</span>`
}

function renderEntry(entry: MonitorEntry): string {
  const lines: string[] = []

  lines.push(span('#555555', '\u2500'.repeat(100)))

  if (entry.tool_name) {
    if (entry.ts) {
      lines.push(span('#8b8b8b', 'ts: ') + span('#cccccc', entry.ts))
    }
    lines.push(span('#3b8eea', '>>> MCP TOOL EXECUTION', true))
    lines.push(span('#c19c00', `tool: ${entry.tool_name}`))
    if (entry.arguments !== undefined) {
      const argsStr = typeof entry.arguments === 'string'
        ? entry.arguments
        : JSON.stringify(entry.arguments, null, 2)
      lines.push(span('#8b8b8b', 'args: ') + span('#c19c00', argsStr))
    }
    if (entry.result !== undefined) {
      const resultStr = typeof entry.result === 'string'
        ? entry.result
        : JSON.stringify(entry.result, null, 2)
      lines.push(span('#8b8b8b', 'result: ') + span('#16c60c', resultStr))
    }
    return lines.join('\n')
  }

  const metaParts: [string, string][] = []
  if (entry.ts) metaParts.push(['ts', entry.ts])
  if (entry.character) metaParts.push(['character', entry.character])
  if (entry.provider) metaParts.push(['provider', entry.provider])
  if (entry.model) metaParts.push(['model', entry.model])
  if (entry.type) metaParts.push(['type', entry.type])
  for (const [k, v] of metaParts) {
    lines.push(span('#8b8b8b', k + ': ') + span('#cccccc', v))
  }

  if (entry.request) {
    const req = entry.request

    lines.push('')
    lines.push(span('#3b8eea', '>>> SAMPLING', true))
    const samplingKeys = ['temperature', 'top_p', 'top_k', 'max_tokens', 'enable_thinking']
    for (const k of samplingKeys) {
      if (req[k] !== undefined) {
        lines.push(span('#8b8b8b', `  ${k}: `) + span('#cccccc', String(req[k])))
      }
    }

    if (Array.isArray(req.tools) && req.tools.length > 0) {
      lines.push('')
      lines.push(span('#3b8eea', '>>> TOOLS', true))
      for (const tool of req.tools) {
        const name = tool.function?.name || tool.name || 'unknown'
        const params = tool.function?.parameters || tool.parameters
        const paramNames = params?.properties
          ? Object.keys(params.properties).join(', ')
          : ''
        lines.push(
          span('#c19c00', `  ${name}`) +
          (paramNames ? span('#8b8b8b', ` (${paramNames})`) : '')
        )
      }
    }

    if (Array.isArray(req.messages) && req.messages.length > 0) {
      lines.push('')
      lines.push(span('#3b8eea', '>>> HISTORY', true))
      const msgs = req.messages
      const historyMsgs = msgs.length > 1 ? msgs.slice(0, -1) : msgs
      for (const msg of historyMsgs) {
        const raw = typeof msg.content === 'string'
          ? msg.content
          : JSON.stringify(msg.content)
        const summary = raw.length > 120
          ? raw.substring(0, 120) + '...'
          : raw
        lines.push(
          span('#8b8b8b', `  [${msg.role}] `) +
          span('#cccccc', summary.replace(/\n/g, ' '))
        )
      }

      if (msgs.length > 1) {
        const last = msgs[msgs.length - 1]
        const content = typeof last.content === 'string'
          ? last.content
          : JSON.stringify(last.content, null, 2)
        lines.push('')
        lines.push(span('#3b8eea', '>>> LATEST MESSAGE', true))
        lines.push(span('#8b8b8b', `  [${last.role}] `) + span('#cccccc', content))
      }
    }
  }

  if (entry.response) {
    const r = entry.response
    lines.push('')
    lines.push(span('#3b8eea', '>>> RESPONSE', true))

    if (r.finish_reason) {
      lines.push(span('#8b8b8b', '  finish_reason: ') + span('#cccccc', r.finish_reason))
    }
    if (r.usage) {
      const prompt = r.usage.prompt_tokens ?? 0
      const completion = r.usage.completion_tokens ?? 0
      lines.push(
        span('#8b8b8b', '  tokens: ') +
        span('#cccccc', `prompt=${prompt} completion=${completion}`)
      )
    }

    const isError = r.finish_reason === 'error' || !!r.error
    const color = isError ? '#e74856' : '#16c60c'
    const text = r.text || r.content || r.error || ''
    if (text) {
      const textStr = typeof text === 'string' ? text : JSON.stringify(text, null, 2)
      lines.push(span(color, textStr))
    }

    if (r.raw_events) {
      const eventsJson = JSON.stringify(r.raw_events, null, 2)
      lines.push('')
      lines.push(
        `<details><summary style="color:#3b8eea;font-weight:bold;cursor:pointer">\u25B6 RAW SSE EVENTS (click to expand)</summary>` +
        span('#6a9955', eventsJson) +
        `</details>`
      )
    }
  }

  return lines.join('\n')
}

const renderedHtml = computed(() => {
  if (entries.value.length === 0) {
    return span('#8b8b8b', 'No entries yet. Waiting for requests...')
  }
  return entries.value.map(renderEntry).join('\n')
})

function scrollToBottom() {
  nextTick(() => {
    if (terminalRef.value) {
      terminalRef.value.scrollTop = terminalRef.value.scrollHeight
    }
  })
}

async function fetchLog() {
  loading.value = true
  try {
    const res = await monitorApi.getLog()
    const prevLen = entries.value.length
    entries.value = res.entries
    if (res.entries.length !== prevLen) {
      scrollToBottom()
    }
  } catch (e: any) {
    message.error(e?.message || 'Failed to fetch monitor log')
  } finally {
    loading.value = false
  }
}

function startPolling() {
  stopPolling()
  timer = setInterval(fetchLog, intervalValue.value * 1000)
}

function stopPolling() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

watch(intervalValue, () => {
  startPolling()
})

onMounted(() => {
  fetchLog()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.monitor-terminal {
  background: #0c0c0c;
  color: #cccccc;
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  padding: 16px;
  max-height: 80vh;
  overflow: auto;
  border: 1px solid #333;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
