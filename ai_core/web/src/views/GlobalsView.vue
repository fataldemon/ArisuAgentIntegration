<template>
  <n-tabs type="line" animated>
    <n-tab-pane name="settings" :tab="$t('globals.settingsTab')">
      <n-space vertical :size="20">
        <n-card :title="$t('globals.endpoints')" :bordered="true">
          <template #header-extra>
            <n-button @click="fetchData" quaternary circle>
              <template #icon>↻</template>
            </n-button>
          </template>
          <n-text depth="3" style="display: block; margin-bottom: 12px">
            {{ $t('globals.endpointsDesc') }}
          </n-text>
          <div class="endpoints-grid">
            <template v-for="ep in endpointList" :key="ep.name">
              <div class="ep-name">{{ ep.name }}</div>
              <div class="ep-value">{{ ep.value }}</div>
            </template>
          </div>
        </n-card>

        <n-card :title="$t('inference.title')" :bordered="true">
          <n-text depth="3" style="display: block; margin-bottom: 16px">
            {{ $t('inference.desc') }}
          </n-text>

          <n-grid :cols="2" :x-gap="24" :y-gap="0">
            <n-gi v-for="mode in (['chat', 'assistant'] as const)" :key="mode">
              <n-card
                :title="mode === 'chat' ? $t('inference.chatParams') : $t('inference.assistantParams')"
                size="small"
                style="margin-bottom: 16px"
              >
                <div class="param-grid">
                  <n-text>{{ $t('inference.temperature') }}: {{ inference[mode].temperature.toFixed(2) }}</n-text>
                  <n-slider v-model:value="inference[mode].temperature" :min="0" :max="2" :step="0.01" />

                  <n-text>{{ $t('inference.topP') }}: {{ inference[mode].top_p.toFixed(2) }}</n-text>
                  <n-slider v-model:value="inference[mode].top_p" :min="0" :max="1" :step="0.01" />

                  <n-text>{{ $t('inference.topK') }}</n-text>
                  <n-input-number v-model:value="inference[mode].top_k" :min="0" size="small" style="width: 100%" />

                  <n-text>{{ $t('inference.repetitionPenalty') }}</n-text>
                  <n-input-number v-model:value="inference[mode].repetition_penalty" :min="0" :step="0.01" size="small" style="width: 100%" />

                  <n-text>{{ $t('inference.presencePenalty') }}</n-text>
                  <n-input-number v-model:value="inference[mode].presence_penalty" :min="0" :step="0.01" size="small" style="width: 100%" />

                  <n-text>{{ $t('inference.enableThinking') }}</n-text>
                  <n-switch v-model:value="inference[mode].enable_thinking" />

                  <n-text>{{ $t('inference.onEmbedding') }}</n-text>
                  <n-switch v-model:value="inference[mode].on_embedding" />
                </div>
              </n-card>
            </n-gi>
          </n-grid>

          <n-card :title="$t('inference.globalParams')" size="small" style="margin-bottom: 16px">
            <div class="param-grid">
              <n-text>{{ $t('inference.maxHistory') }}</n-text>
              <n-input-number v-model:value="inference.max_history" :min="1" size="small" style="width: 200px" />

              <n-text>{{ $t('inference.maxToolRounds') }}</n-text>
              <n-input-number v-model:value="inference.max_tool_rounds" :min="1" :max="20" size="small" style="width: 200px" />
            </div>
          </n-card>

          <n-button type="primary" @click="saveInference" :loading="savingInference">
            {{ $t('inference.save') }}
          </n-button>
        </n-card>

        <n-card :title="$t('globals.sharedVars')" :bordered="true">
          <n-text depth="3" style="display: block; margin-bottom: 12px">
            {{ $t('globals.sharedVarsDesc') }}
          </n-text>

          <n-space vertical :size="12">
            <div v-for="(v, idx) in variables" :key="idx" class="var-row">
              <n-input
                v-model:value="v.name"
                :placeholder="$t('common.name')"
                style="width: 180px"
              />
              <n-input
                v-model:value="v.value"
                :type="v.sensitive ? 'password' : (v.value && v.value.length > 40 ? 'textarea' : 'text')"
                :show-password-on="v.sensitive ? 'click' : undefined"
                :autosize="(v.value && v.value.length > 40) ? { minRows: 2, maxRows: 6 } : undefined"
                placeholder="Value"
                style="width: 240px"
              />
              <n-input
                v-model:value="v.description"
                :placeholder="$t('common.description')"
                style="width: 200px"
              />
              <n-space align="center" :size="4" :wrap="false">
                <n-text depth="3" style="font-size: 12px">Sensitive</n-text>
                <n-switch v-model:value="v.sensitive" size="small" />
              </n-space>
              <n-button type="error" quaternary size="small" @click="removeVariable(idx)">
                ✕
              </n-button>
            </div>
          </n-space>

          <n-divider />

          <n-space>
            <n-button @click="addVariable">{{ $t('globals.addVariable') }}</n-button>
            <n-button type="primary" @click="handleSave" :loading="saving">
              {{ $t('common.saveUpdate') }}
            </n-button>
          </n-space>

          <n-text depth="3" style="display: block; margin-top: 12px; font-size: 12px">
            {{ $t('globals.hint') }}
          </n-text>
        </n-card>
      </n-space>
    </n-tab-pane>

    <n-tab-pane name="tools" :tab="$t('globals.toolsTab')">
      <n-card :title="$t('tools.title')" :bordered="true">
        <template #header-extra>
          <n-button @click="fetchTools" quaternary circle>
            <template #icon>↻</template>
          </n-button>
        </template>
        <n-text depth="3" style="display: block; margin-bottom: 12px">
          {{ $t('tools.desc') }}
        </n-text>

        <div v-for="domain in domains" :key="domain" class="cap-domain">
          <div class="cap-domain-title">{{ domain }}</div>
          <div v-for="cap in capsByDomain(domain)" :key="cap.key" class="cap-row">
            <div class="cap-info">
              <div class="cap-display">
                {{ cap.display }}
                <n-text depth="3" class="cap-key">{{ cap.key }}</n-text>
              </div>
              <div class="cap-desc">{{ cap.description }}</div>
              <div class="cap-tools">
                <n-tag v-for="tn in cap.tools" :key="tn" size="small" round>{{ tn }}</n-tag>
              </div>
            </div>
            <div class="cap-controls">
              <n-radio-group v-model:value="cap.state" size="small">
                <n-radio value="allow">{{ $t('tools.stateAllow') }}</n-radio>
                <n-radio value="ask">{{ $t('tools.stateAsk') }}</n-radio>
                <n-radio value="deny">{{ $t('tools.stateDeny') }}</n-radio>
              </n-radio-group>
              <n-checkbox v-model:checked="cap.chatEnabled" size="small">
                {{ $t('tools.enableChat') }}
              </n-checkbox>
            </div>
          </div>
        </div>

        <n-divider />
        <n-button type="primary" @click="saveTools" :loading="savingTools">
          {{ $t('tools.save') }}
        </n-button>
      </n-card>
    </n-tab-pane>
  </n-tabs>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import {
  NSpace, NCard, NInput, NSwitch, NButton, NText, NDivider,
  NSlider, NInputNumber, NGrid, NGi, NTabs, NTabPane, NTag,
  NRadioGroup, NRadio, NCheckbox, useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { globalsApi } from '../api/globals'
import { inferenceApi } from '../api/inference'
import { toolsApi, type CapabilityInfo } from '../api/tools'

interface GlobalVar {
  name: string
  value: string
  sensitive: boolean
  description: string
}

interface EndpointEntry {
  name: string
  value: string
}

interface ToolCap extends CapabilityInfo {
  chatEnabled: boolean
}

const ENDPOINT_NAMES = [
  'AI_CORE_URL',
  'CHAT_ENDPOINT',
  'ASSISTANT_ENDPOINT',
  'WS_ENDPOINT',
  'ADMIN_URL',
  'DB_URL',
]

const { t } = useI18n()
const message = useMessage()
const variables = ref<GlobalVar[]>([])
const endpointList = ref<EndpointEntry[]>([])
const saving = ref(false)
const savingInference = ref(false)

const inference = reactive({
  chat: {
    temperature: 0.6,
    top_p: 0.95,
    top_k: 20,
    repetition_penalty: 1.05,
    presence_penalty: 1.1,
    enable_thinking: true,
    on_embedding: true,
  },
  assistant: {
    temperature: 0.6,
    top_p: 0.95,
    top_k: 20,
    repetition_penalty: 1.05,
    presence_penalty: 1.1,
    enable_thinking: true,
    on_embedding: true,
  },
  max_history: 40,
  max_tool_rounds: 6,
})

// ----- tool capabilities -----
const toolCaps = ref<ToolCap[]>([])
const domains = ref<string[]>([])
const savingTools = ref(false)

function capsByDomain(domain: string): ToolCap[] {
  return toolCaps.value.filter(c => c.domain === domain)
}

async function fetchTools() {
  try {
    const data = await toolsApi.getCapabilities()
    domains.value = data.domains
    const chatCaps = new Set(data.channels.chat || [])
    toolCaps.value = data.capabilities.map(c => ({ ...c, chatEnabled: chatCaps.has(c.key) }))
  } catch (e: any) {
    message.error(e?.message || 'Failed to load tool capabilities')
  }
}

async function saveTools() {
  savingTools.value = true
  try {
    const states: Record<string, string> = {}
    const chatEnabled: string[] = []
    for (const c of toolCaps.value) {
      states[c.key] = c.state
      if (c.chatEnabled) chatEnabled.push(c.key)
    }
    await toolsApi.setCapabilities(states)
    await toolsApi.setChannelCapabilities('chat', chatEnabled)
    message.success(t('tools.saved'))
  } catch (e: any) {
    message.error(e?.message || 'Failed to save tool capabilities')
  } finally {
    savingTools.value = false
  }
}

async function fetchData() {
  try {
    const data = await globalsApi.getAll()

    endpointList.value = ENDPOINT_NAMES
      .filter(name => data.endpoints && data.endpoints[name])
      .map(name => ({
        name,
        value: data.endpoints[name]?.value ?? data.endpoints[name] ?? '',
      }))

    if (data.variables) {
      variables.value = Object.entries(data.variables).map(([name, v]: [string, any]) => ({
        name,
        value: v.value ?? '',
        sensitive: v.sensitive ?? false,
        description: v.description ?? '',
      }))
    } else {
      variables.value = []
    }
  } catch (e: any) {
    message.error(e?.message || 'Failed to load globals')
  }
}

async function loadInference() {
  try {
    const data = await inferenceApi.get()
    if (data.chat) Object.assign(inference.chat, data.chat)
    if (data.assistant) Object.assign(inference.assistant, data.assistant)
    if (data.max_history !== undefined) inference.max_history = data.max_history
    if (data.max_tool_rounds !== undefined) inference.max_tool_rounds = data.max_tool_rounds
  } catch {}
}

async function saveInference() {
  savingInference.value = true
  try {
    await inferenceApi.save({
      chat: { ...inference.chat },
      assistant: { ...inference.assistant },
      max_history: inference.max_history,
      max_tool_rounds: inference.max_tool_rounds,
    })
    message.success(t('inference.saved'))
  } catch (e: any) {
    message.error(e?.message || 'Failed to save')
  } finally {
    savingInference.value = false
  }
}

function addVariable() {
  variables.value.push({ name: '', value: '', sensitive: false, description: '' })
}

function removeVariable(idx: number) {
  variables.value.splice(idx, 1)
}

async function handleSave() {
  const record: Record<string, any> = {}
  for (const v of variables.value) {
    const name = v.name.trim()
    if (!name) continue
    record[name] = {
      value: v.value,
      sensitive: v.sensitive,
      description: v.description,
    }
  }
  saving.value = true
  try {
    await globalsApi.save(record)
    message.success(t('common.saveUpdate') + ' ✓')
    await fetchData()
  } catch (e: any) {
    message.error(e?.message || 'Failed to save variables')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchData()
  loadInference()
  fetchTools()
})
</script>

<style scoped>
.endpoints-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 20px;
  align-items: center;
}

.ep-name {
  font-weight: 600;
  color: #2B6BC7;
  font-size: 13px;
}

.ep-value {
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  color: #555;
  user-select: all;
  background: #f4f8fe;
  padding: 4px 10px;
  border-radius: 4px;
}

.var-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
}

.param-grid {
  display: grid;
  grid-template-columns: 180px 1fr;
  align-items: center;
  gap: 10px 16px;
}

.cap-domain {
  margin-bottom: 20px;
}

.cap-domain-title {
  font-weight: 600;
  font-size: 15px;
  color: #2B6BC7;
  margin-bottom: 10px;
  padding-bottom: 4px;
  border-bottom: 1px solid #eee;
}

.cap-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 10px 0;
}

.cap-info {
  flex: 1;
  min-width: 0;
}

.cap-display {
  font-weight: 600;
  font-size: 14px;
}

.cap-key {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 11px;
  font-weight: normal;
  margin-left: 8px;
}

.cap-desc {
  font-size: 12px;
  color: #666;
  margin-top: 2px;
}

.cap-tools {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cap-controls {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}
</style>
