<template>
  <n-space vertical size="large">
    <n-card :title="$t('monitor.title')">
      <template #header-extra>
        <n-space align="center" :size="16">
          <span style="white-space: nowrap; font-size: 13px">
            {{ $t('monitor.interval') }}: {{ intervalValue }}s <HelpTip>{{ $t('tips.monitorInterval') }}</HelpTip>
          </span>
          <n-slider
            v-model:value="intervalValue"
            :min="0.5"
            :max="30"
            :step="0.5"
            style="width: 200px"
          />
          <n-button @click="fetchLog" :loading="loading">{{ $t('monitor.refreshNow') }}</n-button>
        </n-space>
      </template>
    </n-card>

    <div
      ref="terminalRef"
      class="monitor-terminal"
      v-html="renderedHtml"
    />

    <n-space justify="center" align="center" :size="12" style="padding: 8px 0">
      <n-button size="small" :disabled="currentPage <= 1" @click="goToPage(1)">&laquo;</n-button>
      <n-button size="small" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">&lsaquo;</n-button>
      <span style="font-size: 13px">{{ currentPage }} / {{ totalPages }}</span>
      <n-button size="small" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">&rsaquo;</n-button>
      <n-button size="small" :disabled="currentPage >= totalPages" @click="goToPage(totalPages)">&raquo;</n-button>
      <n-select v-model:value="pageSize" :options="pageSizeOptions" size="small" style="width: 90px" @update:value="onPageSizeChange" />
      <span style="font-size: 12px; color: #999">{{ totalEntries }} entries</span>
    </n-space>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, watch, onActivated, onDeactivated, nextTick } from 'vue'
import { NSpace, NCard, NButton, NSlider, NSelect, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { monitorApi } from '../api/monitor'
import HelpTip from '../components/HelpTip.vue'
import type { MonitorEntry } from '../types'

const { t } = useI18n()
const message = useMessage()
const entries = ref<MonitorEntry[]>([])
const loading = ref(false)
const intervalValue = ref(3)
const terminalRef = ref<HTMLDivElement | null>(null)
let timer: ReturnType<typeof setInterval> | null = null
let resizeObserver: ResizeObserver | null = null

const currentPage = ref(1)
const totalPages = ref(0)
const pageSize = ref(20)
const totalEntries = ref(0)
const trackLatest = ref(true)
const wasScrolledUp = ref(false)

const pageSizeOptions = [
  { label: '10', value: 10 },
  { label: '20', value: 20 },
  { label: '50', value: 50 },
  { label: '100', value: 100 },
]

const SEP = '\u2500'.repeat(120)
const SEP_SHORT = '\u2500'.repeat(60)

function esc(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function s(color: string, text: string, bold = false): string {
  const fw = bold ? ';font-weight:bold' : ''
  return `<span style="color:${color}${fw}">${esc(text)}</span>`
}

function sRaw(color: string, html: string, bold = false): string {
  const fw = bold ? ';font-weight:bold' : ''
  return `<span style="color:${color}${fw}">${html}</span>`
}

function msgText(msg: any): string {
  const content = msg?.content
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const pieces: string[] = []
    for (const item of content) {
      if (typeof item === 'object' && item !== null) {
        const t = item.text || ''
        if (t) pieces.push(t)
        else if (['image_url', 'video_url', 'audio_url'].includes(item.type))
          pieces.push(`[${(item.type as string).replace('_url', '')}]`)
      }
    }
    return pieces.join('')
  }
  return content ? String(content) : ''
}

function compactThink(text: string): string {
  if (!text) return text
  // Collapse newlines only inside <think>...</think> blocks so the model's
  // reasoning stays on one line (easier to scan); leave the rest verbatim.
  return text.replace(/<think>[\s\S]*?<\/think>/g, (m) => m.replace(/\n/g, '\\n'))
}

function fmtToolDef(t: any, idx: number): string {
  const fn = t.function || t
  const name = fn.name || '?'
  const desc = fn.description || ''
  const params = fn.parameters || {}
  const props = params.properties || {}
  const paramParts: string[] = []
  if (typeof props === 'object') {
    for (const [pn, pv] of Object.entries(props)) {
      const pt = (pv as any)?.type || '?'
      paramParts.push(`${pn}:${pt}`)
    }
  }
  const paramsStr = paramParts.join(', ')
  let line = `    [${idx}] ${name}(${paramsStr})`
  if (desc) line += `  \u2192  ${desc.substring(0, 120)}`
  return line
}

function renderEntry(entry: MonitorEntry): string {
  const lines: string[] = []
  const C_SEP = '#555555'
  const C_META = '#8b8b8b'
  const C_HEAD = '#3b8eea'
  const C_RESP = '#16c60c'
  const C_ERR = '#e74856'
  const C_TEXT = '#cccccc'
  const C_TOOL = '#c19c00'
  const C_RAW = '#6a9955'

  const ts = (entry.ts || '').substring(0, 19).replace('T', ' ')
  const reqType = entry.type || ''

  if (reqType === 'mcp_tool_execution' || entry.tool_name) {
    const toolName = entry.tool_name || '?'
    const args = typeof entry.arguments === 'string'
      ? entry.arguments.substring(0, 120)
      : JSON.stringify(entry.arguments || '').substring(0, 120)
    const result = typeof entry.result === 'string'
      ? entry.result.substring(0, 300)
      : JSON.stringify(entry.result || '').substring(0, 300)
    lines.push(sRaw(C_SEP, esc(SEP)))
    lines.push(
      sRaw(C_HEAD, '&gt;&gt;&gt; TOOL EXECUTION', true) +
      '  ' + sRaw(C_META, `[${esc(ts)}]`) +
      '  ' + s(C_TOOL, toolName)
    )
    lines.push(sRaw(C_META, '    args:') + '  ' + s(C_TEXT, args))
    lines.push(sRaw(C_META, '    result:') + '  ' + s(C_TEXT, result))
    lines.push(sRaw(C_SEP, esc(SEP)))
    return lines.join('\n')
  }

  const character = entry.character || ''
  const provider = entry.provider || ''
  const model = entry.model || ''
  const req = entry.request || {}
  const resp = entry.response || {}

  lines.push(sRaw(C_SEP, esc(SEP)))
  lines.push(
    sRaw(C_META, '[') + esc(ts) +
    sRaw(C_META, ']  character=') + esc(character) +
    sRaw(C_META, '  provider=') + esc(provider) +
    sRaw(C_META, '  model=') + esc(model) +
    sRaw(C_META, '  type=') + esc(reqType)
  )

  const sampling = req.sampling || {}
  const extraBody = req.extra_body || {}
  const extraInner = extraBody.chat_template_kwargs || {}
  const enableThinking = extraInner.enable_thinking

  const sampParts: string[] = []
  for (const k of ['temperature', 'top_p', 'top_k', 'max_tokens', 'presence_penalty', 'repetition_penalty']) {
    const v = sampling[k]
    if (v !== undefined && v !== null) sampParts.push(`${k}=${v}`)
  }
  if (enableThinking !== undefined && enableThinking !== null) {
    sampParts.push(`enable_thinking=${enableThinking}`)
  }
  const stop = sampling.stop
  if (stop) sampParts.push(`stop=${JSON.stringify(stop).substring(0, 40)}`)

  lines.push(sRaw(C_HEAD, '&gt;&gt;&gt; SAMPLING', true))
  if (sampParts.length > 0) {
    lines.push(s(C_TEXT, '    ' + sampParts.join('  ')))
  } else {
    lines.push(sRaw(C_META, '    (no sampling params)'))
  }

  const tools: any[] = req.tools || []
  lines.push(sRaw(C_HEAD, '&gt;&gt;&gt; TOOLS', true))
  if (tools.length > 0) {
    for (let i = 0; i < tools.length; i++) {
      lines.push(s(C_TEXT, fmtToolDef(tools[i], i + 1)))
    }
  } else {
    lines.push(sRaw(C_META, '    no tools defined'))
  }

  const messages: any[] = req.messages || []
  // LATEST = the last message in the context (any role) — i.e. what the model
  // is actually responding to. Previously this picked the last *user* message,
  // which in a multi-tool turn was the original question, not the tool result.
  const latestMsg = messages.length > 0 ? messages[messages.length - 1] : null
  const historyMsgs = latestMsg ? messages.slice(0, messages.length - 1) : messages

  lines.push(sRaw(C_HEAD, '&gt;&gt;&gt; HISTORY', true))
  if (historyMsgs.length > 0) {
    for (const msg of historyMsgs) {
      const role = msg.role || '?'
      const toolCalls: any[] = msg.tool_calls || []
      const fnCall = msg.function_call
      const text = compactThink(msgText(msg))
      if (toolCalls.length > 0) {
        for (const tc of toolCalls) {
          const fc = tc.function || {}
          const tcArgs = typeof fc.arguments === 'string' ? fc.arguments : JSON.stringify(fc.arguments || '')
          lines.push(
            sRaw(C_TOOL, `    [${esc(role)} \u2192 tool_call: ${esc(fc.name || '?')}]`) +
            '  ' + s(C_TEXT, tcArgs)
          )
        }
      } else if (fnCall) {
        const tcArgs = typeof fnCall.arguments === 'string' ? fnCall.arguments : JSON.stringify(fnCall.arguments || '')
        lines.push(
          sRaw(C_TOOL, `    [${esc(role)} \u2192 tool_call: ${esc(fnCall.name || '?')}]`) +
          '  ' + s(C_TEXT, tcArgs)
        )
      }
      if (text) {
        // Indent continuation lines so multi-line content stays aligned under
        // the [role] label instead of wrapping to column 0.
        const indented = text.split('\n').join('\n    ')
        lines.push(sRaw(C_META, `    [${esc(role)}]`) + '  ' + s(C_TEXT, indented))
      }
    }
  } else {
    lines.push(sRaw(C_META, '    (no history)'))
  }

  if (latestMsg) {
    const roleLabel = latestMsg.role || '?'
    const latestText = compactThink(msgText(latestMsg))
    lines.push(sRaw(C_HEAD, '&gt;&gt;&gt; LATEST MESSAGE', true))
    const lToolCalls: any[] = latestMsg.tool_calls || []
    const lFnCall = latestMsg.function_call
    if (lToolCalls.length > 0) {
      for (const tc of lToolCalls) {
        const fc = tc.function || {}
        const tcArgs = typeof fc.arguments === 'string' ? fc.arguments : JSON.stringify(fc.arguments || '')
        lines.push(
          sRaw(C_TOOL, `    [${esc(roleLabel)} \u2192 tool_call: ${esc(fc.name || '?')}]`) +
          '  ' + s(C_TEXT, tcArgs)
        )
      }
    } else if (lFnCall) {
      const tcArgs = typeof lFnCall.arguments === 'string' ? lFnCall.arguments : JSON.stringify(lFnCall.arguments || '')
      lines.push(
        sRaw(C_TOOL, `    [${esc(roleLabel)} \u2192 tool_call: ${esc(lFnCall.name || '?')}]`) +
        '  ' + s(C_TEXT, tcArgs)
      )
    }
    if (latestText) {
      const indented = latestText.split('\n').join('\n    ')
      lines.push(sRaw(C_META, `    [${esc(roleLabel)}]`) + '  ' + s(C_TEXT, indented))
    }
  }

  lines.push(sRaw(C_SEP, esc(SEP_SHORT)))

  const finish = resp.finish_reason || ''
  const respColor = finish === 'error' ? C_ERR : C_RESP
  lines.push(sRaw(respColor, '&lt;&lt;&lt; RESPONSE', true))

  const tokens = resp.tokens || {}
  if (tokens.prompt !== undefined || tokens.completion !== undefined) {
    lines.push(sRaw(C_META,
      `    finish_reason=${esc(finish)}  ` +
      `prompt_tk=${tokens.prompt ?? '?'}  ` +
      `completion_tk=${tokens.completion ?? '?'}`
    ))
  } else {
    lines.push(sRaw(C_META, `    finish_reason=${esc(finish)}`))
  }

  const rawText = resp.raw_text || ''
  if (rawText) {
    const indented = rawText.split('\n').join('\n    ')
    lines.push(s(C_TEXT, '    ' + indented))
  } else {
    lines.push(sRaw(C_META, '    (empty response body)'))
  }

  const functionCalls: any[] = resp.function_calls || []
  if (functionCalls.length > 0) {
    lines.push(sRaw(C_TOOL, '    --- function_calls ---'))
    for (const fc of functionCalls) {
      const fcName = fc.name || '?'
      const fcArgs = typeof fc.arguments === 'string'
        ? fc.arguments
        : JSON.stringify(fc.arguments || '')
      lines.push(s(C_TOOL, `    \u2192 ${fcName}(${fcArgs})`))
    }
  }

  const rawEvents: any[] = resp.raw_events || []
  if (rawEvents.length > 0) {
    lines.push('')
    lines.push('<details>')
    lines.push(
      `<summary style="cursor:pointer;color:${C_RAW};font-weight:bold">` +
      `    \u2500\u2500 RAW SSE EVENTS (${rawEvents.length} chunks) \u2500\u2500` +
      '</summary>'
    )
    for (let i = 0; i < rawEvents.length; i++) {
      const evStr = JSON.stringify(rawEvents[i], null, 0)
      lines.push(sRaw(C_META, `    [${i + 1}]`) + '  ' + s(C_RAW, evStr))
    }
    lines.push('</details>')
  }

  lines.push(sRaw(C_SEP, esc(SEP)))
  return lines.join('\n')
}

const renderedHtml = computed(() => {
  if (entries.value.length === 0) {
    return sRaw('#8b8b8b', esc(t('monitor.noEntries')))
  }
  return entries.value.map(renderEntry).join('\n')
})

function scrollToBottom() {
  nextTick(() => {
    requestAnimationFrame(() => {
      const el = terminalRef.value
      if (!el) return
      el.scrollTop = el.scrollHeight
      wasScrolledUp.value = false
    })
  })
}

async function fetchLog() {
  loading.value = true
  try {
    const reqPage = trackLatest.value ? -1 : currentPage.value
    const res = await monitorApi.getLog(reqPage, pageSize.value)
    entries.value = res.entries
    currentPage.value = res.page
    totalPages.value = res.total_pages
    totalEntries.value = res.total
    if (trackLatest.value && !wasScrolledUp.value) {
      scrollToBottom()
    }
  } catch (e: any) {
    message.error(e?.message || 'Failed to fetch monitor log')
  } finally {
    loading.value = false
  }
}

function goToPage(page: number) {
  trackLatest.value = page >= totalPages.value
  currentPage.value = page
  fetchLog()
}

function onPageSizeChange() {
  currentPage.value = 1
  trackLatest.value = true
  fetchLog()
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

function onScroll() {
  const el = terminalRef.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
  wasScrolledUp.value = !atBottom
}

onActivated(() => {
  fetchLog()
  startPolling()
  if (terminalRef.value) {
    terminalRef.value.addEventListener('scroll', onScroll)
    // ResizeObserver catches the exact moment the browser finishes laying out
    // new content, then scrolls to bottom — more reliable than nextTick+RAF
    // for the heavy verbatim DOM.
    resizeObserver = new ResizeObserver(() => {
      if (trackLatest.value && !wasScrolledUp.value && terminalRef.value) {
        terminalRef.value.scrollTop = terminalRef.value.scrollHeight
      }
    })
    resizeObserver.observe(terminalRef.value)
  }
})

onDeactivated(() => {
  stopPolling()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (terminalRef.value) {
    terminalRef.value.removeEventListener('scroll', onScroll)
  }
})
</script>

<style scoped>
.monitor-terminal {
  background: #0c0c0c;
  color: #cccccc;
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.55;
  padding: 12px;
  max-height: 80vh;
  overflow: auto;
  border: 1px solid #333;
  border-radius: 4px;
  white-space: pre;
  word-wrap: normal;
}
</style>
