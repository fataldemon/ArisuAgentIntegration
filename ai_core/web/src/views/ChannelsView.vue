<template>
  <n-space vertical size="large" style="padding: 16px; background: #F0F4FA; min-height: 100vh">
    <n-space justify="space-between" align="center">
      <n-h2 style="margin: 0; color: #4C8FEC">{{ $t('channels.title') }}</n-h2>
      <n-button @click="fetchChannels" :loading="loading">{{ $t('common.refreshAll') }}</n-button>
    </n-space>

    <n-text v-if="channels.length === 0 && !loading" depth="3">{{ $t('channels.noChannels') }}</n-text>

    <n-grid :cols="3" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <n-gi v-for="ch in channels" :key="ch.name" span="3 m:1">
        <n-card
          :title="ch.name"
          hoverable
          style="background: #fff; border-radius: 8px"
        >
          <n-space vertical size="medium">
            <n-space align="center" size="small">
              <div
                :style="{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  backgroundColor: statusColor(ch),
                  display: 'inline-block',
                }"
              />
              <n-text :style="{ color: statusColor(ch), fontWeight: 600 }">
                {{ statusLabel(ch) }}
              </n-text>
            </n-space>

            <n-space vertical :size="4">
              <n-text depth="3" v-if="ch.pid">{{ $t('channels.pid') }}: {{ ch.pid }}</n-text>
              <n-text depth="3" v-if="ch.started_at && ch.running">
                {{ $t('channels.uptime') }}: {{ formatUptime(ch.started_at) }}
              </n-text>
              <n-text depth="3">
                {{ $t('channels.restarts') }}: {{ ch.restart_count ?? 0 }}
              </n-text>
            </n-space>

            <n-space>
              <n-button
                type="primary"
                size="small"
                :disabled="ch.running || ch.platform_blocked"
                :loading="actionLoading[ch.name] === 'start'"
                @click="handleStart(ch.name)"
              >
                {{ $t('channels.start') }}
              </n-button>
              <n-button
                type="error"
                size="small"
                :disabled="!ch.running"
                :loading="actionLoading[ch.name] === 'stop'"
                @click="handleStop(ch.name)"
              >
                {{ $t('channels.stop') }}
              </n-button>
              <n-button
                size="small"
                :disabled="!ch.running"
                :loading="actionLoading[ch.name] === 'restart'"
                @click="handleRestart(ch.name)"
              >
                {{ $t('channels.restart') }}
              </n-button>
              <n-button
                size="small"
                text
                tag="a"
                :href="`/admin/logs/${ch.name}`"
                target="_blank"
                type="info"
              >
                {{ $t('channels.viewLog') }}
              </n-button>
            </n-space>

            <n-collapse
              v-if="channelFieldDefs[ch.name]"
              @item-header-click="(data: { name: string | number; expanded: boolean }) => { if (data.expanded && !channelConfigs[ch.name]) loadChannelConfig(ch.name) }"
            >
              <n-collapse-item
                :title="$t('channels.configuration') || 'Configuration'"
                name="config"
              >
                <n-spin :show="configLoading[ch.name] || false">
                  <n-space vertical size="medium" v-if="channelConfigs[ch.name]">
                    <div
                      v-for="field in channelFieldDefs[ch.name]"
                      :key="field.key"
                      style="display: grid; grid-template-columns: 200px 1fr; align-items: center; gap: 8px"
                    >
                      <n-text>{{ $t(field.label) }}</n-text>
                      <n-auto-complete
                        v-model:value="channelConfigs[ch.name][field.key]"
                        :options="getAutoCompleteOptions(channelConfigs[ch.name][field.key])"
                        :type="field.password ? 'password' : 'text'"
                        :placeholder="$t(field.label)"
                      />
                    </div>
                    <template v-if="ch.name === 'unity' && channelConfigs[ch.name]">
                      <div style="display: grid; grid-template-columns: 200px 1fr; align-items: center; gap: 8px">
                        <n-text>{{ $t('channels.ttsModeLabel') }}</n-text>
                        <n-select
                          v-model:value="channelConfigs[ch.name].ttsMode"
                          :options="ttsModeOptions"
                        />
                      </div>
                      <div style="display: grid; grid-template-columns: 200px 1fr; align-items: center; gap: 8px">
                        <n-text>{{ $t('channels.ttsUrl') }}</n-text>
                        <n-auto-complete
                          v-model:value="channelConfigs[ch.name][ttsUrlKey(channelConfigs[ch.name].ttsMode)]"
                          :options="getAutoCompleteOptions(channelConfigs[ch.name][ttsUrlKey(channelConfigs[ch.name].ttsMode)])"
                          :placeholder="$t('channels.ttsUrl')"
                        />
                      </div>
                    </template>
                    <n-text depth="3" style="font-size: 12px">
                      {{ $t('channels.restartRequired') }}
                    </n-text>
                    <n-space>
                      <n-button
                        type="primary"
                        :loading="configSaving[ch.name] === 'save'"
                        @click="saveChannelConfig(ch.name)"
                      >
                        {{ $t('channels.saveConfig') || 'Save Config' }}
                      </n-button>
                      <n-button
                        type="warning"
                        :loading="configSaving[ch.name] === 'saveRestart'"
                        @click="saveAndRestartChannel(ch.name)"
                      >
                        {{ $t('channels.saveAndRestart') || 'Save & Restart' }}
                      </n-button>
                    </n-space>
                  </n-space>
                </n-spin>
              </n-collapse-item>
            </n-collapse>

            <n-text v-else-if="!channelFieldDefs[ch.name]" depth="3" style="font-size: 12px; font-style: italic">
              {{ $t('channels.noConfig') }}
            </n-text>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  NSpace,
  NCard,
  NButton,
  NGrid,
  NGi,
  NText,
  NH2,
  NCollapse,
  NCollapseItem,
  NAutoComplete,
  NSelect,
  NSpin,
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { channelsApi } from '../api/channels'
import { globalsApi } from '../api/globals'
import type { ChannelStatus } from '../types'

const { t } = useI18n()
const message = useMessage()
const channels = ref<ChannelStatus[]>([])
const loading = ref(false)
const actionLoading = ref<Record<string, string>>({})
const channelConfigs = ref<Record<string, Record<string, any>>>({})
const configLoading = ref<Record<string, boolean>>({})
const configSaving = ref<Record<string, string>>({})
const globalVarNames = ref<string[]>([])
let refreshTimer: ReturnType<typeof setInterval> | null = null

const channelFieldDefs: Record<string, Array<{ key: string; label: string; password?: boolean }>> = {
  qq_bot: [
    { key: 'ONEBOT_WS_URLS', label: 'channels.onebotWsUrls' },
    { key: 'master_id', label: 'channels.masterQqId' },
    { key: 'bot_user_id', label: 'channels.botQqId' },
    { key: 'baidu_trans_appid', label: 'channels.baiduAppid', password: true },
    { key: 'baidu_trans_apikey', label: 'channels.baiduApikey', password: true },
    { key: 'QWEATHER_APIKEY', label: 'channels.weatherApikey', password: true },
    { key: 'AI_CORE_URL', label: 'channels.aiCoreUrl' },
  ],
  bilibili: [
    { key: 'ACCESS_KEY_ID', label: 'channels.accessKeyId', password: true },
    { key: 'ACCESS_KEY_SECRET', label: 'channels.accessKeySecret', password: true },
    { key: 'APP_ID', label: 'channels.appId' },
    { key: 'ROOM_OWNER_AUTH_CODE', label: 'channels.roomAuthCode', password: true },
  ],
  unity: [
    { key: 'websocketUrl', label: 'channels.websocketUrl' },
    { key: 'translationAppId', label: 'channels.baiduAppid', password: true },
    { key: 'translationKey', label: 'channels.baiduApikey', password: true },
    { key: 'msgMaxWidth', label: 'channels.bubbleWidth' },
    { key: 'msgHeight', label: 'channels.bubbleHeight' },
  ],
}

const ttsModeOptions = computed(() => [
  { label: t('channels.ttsModeGptSovits'), value: '0' },
  { label: t('channels.ttsModeGradio'), value: '1' },
  { label: t('channels.ttsModeSimpleVits'), value: '2' },
])

function ttsUrlKey(mode: any): string {
  const m = Number(mode)
  if (m === 1) return 'gradioUrl'
  if (m === 2) return 'simpleVitsUrl'
  return 'gptSovitsUrl'
}

function getAutoCompleteOptions(currentValue: any): Array<{ label: string; value: string }> {
  const str = String(currentValue ?? '')
  if (!str.includes('${')) return []
  const lastDollar = str.lastIndexOf('${')
  const prefix = str.substring(0, lastDollar)
  const partial = str.substring(lastDollar + 2).replace('}', '')
  return globalVarNames.value
    .filter(name => name.toLowerCase().includes(partial.toLowerCase()))
    .map(name => ({
      label: name,
      value: prefix + '${' + name + '}'
    }))
}

function statusColor(ch: ChannelStatus): string {
  if (ch.platform_blocked) return '#999'
  return ch.running ? '#18a058' : '#d03050'
}

function statusLabel(ch: ChannelStatus): string {
  if (ch.platform_blocked) return t('channels.blocked')
  return ch.running ? t('channels.running') : t('channels.stopped')
}

function formatUptime(startedAt: string): string {
  const start = new Date(startedAt).getTime()
  const now = Date.now()
  let diff = Math.floor((now - start) / 1000)
  if (diff < 0) return '0s'
  const days = Math.floor(diff / 86400)
  diff %= 86400
  const hours = Math.floor(diff / 3600)
  diff %= 3600
  const minutes = Math.floor(diff / 60)
  const seconds = diff % 60
  const parts: string[] = []
  if (days > 0) parts.push(`${days}d`)
  if (hours > 0) parts.push(`${hours}h`)
  if (minutes > 0) parts.push(`${minutes}m`)
  parts.push(`${seconds}s`)
  return parts.join(' ')
}

async function fetchChannels() {
  loading.value = true
  try {
    const res = await channelsApi.list()
    channels.value = res.channels
  } catch (e: any) {
    message.error(e?.message || 'Failed to load channels')
  } finally {
    loading.value = false
  }
}

async function handleStart(name: string) {
  actionLoading.value[name] = 'start'
  try {
    await channelsApi.start(name)
    message.success(`Channel "${name}" started`)
    window.open(`/admin/logs/${name}`, '_blank')
    await fetchChannels()
  } catch (e: any) {
    message.error(e?.message || 'Failed to start channel')
  } finally {
    delete actionLoading.value[name]
  }
}

async function handleStop(name: string) {
  actionLoading.value[name] = 'stop'
  try {
    await channelsApi.stop(name)
    message.success(`Channel "${name}" stopped`)
    await fetchChannels()
  } catch (e: any) {
    message.error(e?.message || 'Failed to stop channel')
  } finally {
    delete actionLoading.value[name]
  }
}

async function handleRestart(name: string) {
  actionLoading.value[name] = 'restart'
  try {
    await channelsApi.restart(name)
    message.success(`Channel "${name}" restarted`)
    await fetchChannels()
  } catch (e: any) {
    message.error(e?.message || 'Failed to restart channel')
  } finally {
    delete actionLoading.value[name]
  }
}

async function loadChannelConfig(name: string) {
  configLoading.value[name] = true
  try {
    const res = await channelsApi.getConfig(name)
    const stringified: Record<string, any> = {}
    for (const [k, v] of Object.entries(res.config)) {
      if (typeof v === 'string') stringified[k] = v
      else stringified[k] = String(v ?? '')
    }
    channelConfigs.value[name] = stringified
  } catch (e: any) {
    message.error(e?.message || 'Failed to load config')
  } finally {
    configLoading.value[name] = false
  }
}

async function saveChannelConfig(name: string) {
  configSaving.value[name] = 'save'
  try {
    await channelsApi.saveConfig(name, channelConfigs.value[name])
    message.success(`Config for "${name}" saved`)
  } catch (e: any) {
    message.error(e?.message || 'Failed to save config')
  } finally {
    delete configSaving.value[name]
  }
}

async function saveAndRestartChannel(name: string) {
  configSaving.value[name] = 'saveRestart'
  try {
    await channelsApi.saveConfig(name, channelConfigs.value[name])
    message.success(`Config for "${name}" saved`)
    await channelsApi.restart(name)
    message.success(`Channel "${name}" restarted`)
    await fetchChannels()
  } catch (e: any) {
    message.error(e?.message || 'Failed to save config or restart channel')
  } finally {
    delete configSaving.value[name]
  }
}

onMounted(() => {
  fetchChannels()
  refreshTimer = setInterval(fetchChannels, 3000)
  globalsApi.getFlat().then(data => {
    globalVarNames.value = Object.keys(data.variables)
  }).catch(() => {})
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>
