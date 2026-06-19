<template>
  <n-space vertical size="large" style="padding: 16px; background: #F0F4FA; min-height: 100vh">
    <n-space justify="space-between" align="center">
      <n-h2 style="margin: 0; color: #4C8FEC">Channels</n-h2>
      <n-button @click="fetchChannels" :loading="loading">Refresh All</n-button>
    </n-space>

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
              <n-text depth="3" v-if="ch.pid">PID: {{ ch.pid }}</n-text>
              <n-text depth="3" v-if="ch.started_at && ch.running">
                Uptime: {{ formatUptime(ch.started_at) }}
              </n-text>
              <n-text depth="3">
                Restarts: {{ ch.restart_count ?? 0 }}
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
                Start
              </n-button>
              <n-button
                type="error"
                size="small"
                :disabled="!ch.running"
                :loading="actionLoading[ch.name] === 'stop'"
                @click="handleStop(ch.name)"
              >
                Stop
              </n-button>
              <n-button
                size="small"
                :disabled="!ch.running"
                :loading="actionLoading[ch.name] === 'restart'"
                @click="handleRestart(ch.name)"
              >
                Restart
              </n-button>
              <n-button
                size="small"
                text
                tag="a"
                :href="`/admin/logs/${ch.name}`"
                target="_blank"
                type="info"
              >
                View Log
              </n-button>
            </n-space>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import {
  NSpace,
  NCard,
  NButton,
  NGrid,
  NGi,
  NText,
  NH2,
  useMessage,
} from 'naive-ui'
import { channelsApi } from '../api/channels'
import type { ChannelStatus } from '../types'

const message = useMessage()
const channels = ref<ChannelStatus[]>([])
const loading = ref(false)
const actionLoading = ref<Record<string, string>>({})
let refreshTimer: ReturnType<typeof setInterval> | null = null

function statusColor(ch: ChannelStatus): string {
  if (ch.platform_blocked) return '#999'
  return ch.running ? '#18a058' : '#d03050'
}

function statusLabel(ch: ChannelStatus): string {
  if (ch.platform_blocked) return 'Blocked'
  return ch.running ? 'Running' : 'Stopped'
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

onMounted(() => {
  fetchChannels()
  refreshTimer = setInterval(fetchChannels, 3000)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>
