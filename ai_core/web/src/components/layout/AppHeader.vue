<template>
  <div class="app-header">
    <div class="header-title">
      <h1>{{ pageTitle }}</h1>
    </div>
    <div class="header-status">
      <n-tag v-if="activeProvider" type="info" size="small" round>
        Provider: {{ activeProvider }}
      </n-tag>
      <n-tag v-if="activeCharacter" type="success" size="small" round>
        Character: {{ activeCharacter }}
      </n-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { NTag } from 'naive-ui'
import { providersApi } from '../../api/providers'

const route = useRoute()
const activeProvider = ref('')
const activeCharacter = ref('')

const titleMap: Record<string, string> = {
  '/chat': 'Chat',
  '/providers': 'LLM Providers',
  '/mcp': 'MCP Servers',
  '/skills': 'Skills',
  '/characters': 'Characters',
  '/shared-knowledge': 'Shared Knowledge',
  '/monitor': 'Request Monitor',
  '/channels': 'Channels',
}

const pageTitle = computed(() => titleMap[route.path] || 'Admin')

const fetchStatus = async () => {
  try {
    const data = await providersApi.list()
    activeProvider.value = data.active || ''
    const { personasApi } = await import('../../api/personas')
    const charData = await personasApi.getActiveCharacter()
    activeCharacter.value = charData.character || ''
  } catch {}
}

onMounted(fetchStatus)
</script>

<style scoped>
.app-header {
  height: 56px;
  min-height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--ba-card);
  border-bottom: 1px solid var(--ba-border);
}

.header-title h1 {
  font-size: 18px;
  font-weight: 600;
  color: var(--ba-text);
}

.header-status {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
