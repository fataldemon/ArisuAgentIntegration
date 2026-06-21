<template>
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
            :type="v.sensitive ? 'password' : 'text'"
            :show-password-on="v.sensitive ? 'click' : undefined"
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
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  NSpace, NCard, NInput, NSwitch, NButton, NText, NDivider, useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { globalsApi } from '../api/globals'

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

const ENDPOINT_NAMES = [
  'AI_CORE_URL',
  'CHAT_ENDPOINT',
  'ASSISTANT_ENDPOINT',
  'WS_ENDPOINT',
  'ADMIN_URL',
]

const { t } = useI18n()
const message = useMessage()
const variables = ref<GlobalVar[]>([])
const endpointList = ref<EndpointEntry[]>([])
const saving = ref(false)

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

onMounted(fetchData)
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
</style>
