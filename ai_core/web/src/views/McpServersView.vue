<template>
  <n-space vertical :size="20">
    <n-card class="status-bar" :bordered="true">
      <n-space align="center" :size="16">
        <n-tag type="info" size="large" round>MCP Status</n-tag>
        <span class="status-label">Mode:</span>
        <n-tag>{{ toolCallMode }}</n-tag>
        <span class="status-label">Timeout:</span>
        <n-tag>{{ toolCallTimeout }}s</n-tag>
      </n-space>
    </n-card>

    <n-card title="Servers" :bordered="true">
      <template #header-extra>
        <n-button @click="fetchAll" quaternary circle>
          <template #icon>↻</template>
        </n-button>
      </template>
      <n-data-table
        :columns="columns"
        :data="servers"
        :row-props="rowProps"
        :bordered="false"
        size="small"
        max-height="360"
      />
    </n-card>

    <n-card title="Global Settings" :bordered="true">
      <n-grid :cols="2" :x-gap="16" :y-gap="12">
        <n-gi>
          <n-form-item>
            <template #label>Tool Call Mode <HelpTip>passthrough: MCP tools 不注入给 LLM。server_side: MCP tools 注入给 LLM 并在后端循环执行</HelpTip></template>
            <n-radio-group v-model:value="toolCallMode" @update:value="handleSetMode">
              <n-space>
                <n-radio value="passthrough">Passthrough</n-radio>
                <n-radio value="server_side">Server Side</n-radio>
              </n-space>
            </n-radio-group>
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>Max Tool Rounds <HelpTip>LLM 调用 MCP 工具的最大往返轮数。每轮 LLM 调一次工具，看到结果后决定是否再调用。防止无限循环</HelpTip></template>
            <n-input-number
              v-model:value="maxToolRounds"
              :min="1"
              :max="20"
              @update:value="handleSetMaxRounds"
              style="width: 160px"
            />
          </n-form-item>
        </n-gi>
      </n-grid>
    </n-card>

    <n-card title="Quick Setup" :bordered="true">
      <n-form-item>
        <template #label>Paste MCP Server JSON <HelpTip>粘贴完整的 MCP server JSON 配置。必须包含 enabled/transport/command/args 等字段</HelpTip></template>
        <n-input
          v-model:value="quickJson"
          type="textarea"
          :rows="5"
          placeholder='{"mcpServers": {"server-name": {"command": "npx", "args": ["-y", "..."]}}}'
        />
      </n-form-item>
      <n-button type="primary" @click="handleParseJson" ghost>Parse &amp; Fill</n-button>
    </n-card>

    <n-card :title="form.name ? `Edit: ${form.name}` : 'Create Server'" :bordered="true">
      <n-grid :cols="2" :x-gap="16" :y-gap="12">
        <n-gi>
          <n-form-item>
            <template #label>Name <HelpTip>唯一标识符，用于识别和查找该 MCP 服务器</HelpTip></template>
            <n-input v-model:value="form.name" placeholder="server-name" />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>Enabled <HelpTip>勾选后 MCP 服务器生效。取消勾选后即使 tool_call_mode=server_side 该服务器工具也不可见</HelpTip></template>
            <n-switch v-model:value="form.enabled" />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>Transport <HelpTip>stdio: 子进程标准输入输出通信。sse/streamable_http: 连接远程 HTTP MCP 服务器</HelpTip></template>
            <n-select
              v-model:value="form.transport"
              :options="transportOptions"
              style="width: 100%"
            />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>Description <HelpTip>用于文档展示，不影响运行逻辑</HelpTip></template>
            <n-input v-model:value="form.description" placeholder="Optional description" />
          </n-form-item>
        </n-gi>
        <n-gi v-if="form.transport === 'stdio'">
          <n-form-item>
            <template #label>Command <HelpTip>仅 stdio 模式生效。要启动的进程命令，如 npx / python / uvx</HelpTip></template>
            <n-input v-model:value="form.command" placeholder="npx" />
          </n-form-item>
        </n-gi>
        <n-gi v-if="form.transport === 'stdio'">
          <n-form-item>
            <template #label>Args (one per line) <HelpTip>仅 stdio 模式生效。每行一个命令行参数，例如 -y 和包名</HelpTip></template>
            <n-input
              v-model:value="argsText"
              type="textarea"
              :rows="3"
              placeholder="-y&#10;@modelcontextprotocol/server"
            />
          </n-form-item>
        </n-gi>
        <n-gi v-if="form.transport !== 'stdio'" :span="2">
          <n-form-item>
            <template #label>URL <HelpTip>仅 sse/streamable_http 模式生效。远程 MCP 服务器的 HTTP 地址</HelpTip></template>
            <n-input v-model:value="form.url" placeholder="http://localhost:3000/sse" />
          </n-form-item>
        </n-gi>
        <n-gi :span="2">
          <n-form-item>
            <template #label>Headers (JSON) <HelpTip>仅远程模式生效。JSON 格式的 HTTP 请求头，如 {"Authorization": "Bearer xxx"}</HelpTip></template>
            <n-input
              v-model:value="headersText"
              type="textarea"
              :rows="2"
              placeholder='{"Authorization": "Bearer ..."}'
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-divider />

      <n-space>
        <n-button type="primary" @click="handleSave" :loading="saving">
          {{ isEditing ? 'Update' : 'Save' }}
        </n-button>
        <n-button type="error" @click="handleDelete" :disabled="!isEditing" :loading="deleting">
          Delete
        </n-button>
        <n-button @click="resetForm" quaternary>Clear</n-button>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted } from 'vue'
import {
  NSpace, NCard, NDataTable, NButton, NInput, NInputNumber, NSwitch,
  NSelect, NRadioGroup, NRadio, NTag, NDivider, NGrid, NGi, NFormItem,
  useMessage,
} from 'naive-ui'
import type { DataTableColumns, SelectOption } from 'naive-ui'
import { mcpApi } from '../api/mcp'
import HelpTip from '../components/HelpTip.vue'
import type { MCPServer } from '../types'

const message = useMessage()
const servers = ref<MCPServer[]>([])
const healthMap = ref<Record<string, { connected: boolean; tools: number }>>({})
const toolCallMode = ref('passthrough')
const toolCallTimeout = ref(0)
const maxToolRounds = ref(5)
const saving = ref(false)
const deleting = ref(false)
const quickJson = ref('')

const transportOptions: SelectOption[] = [
  { label: 'stdio', value: 'stdio' },
  { label: 'sse', value: 'sse' },
  { label: 'streamable_http', value: 'streamable_http' },
]

const defaultForm = (): Partial<MCPServer> & { enabled: boolean; transport: string } => ({
  name: '',
  enabled: true,
  transport: 'stdio',
  command: '',
  args: [],
  url: '',
  headers: undefined,
  description: '',
})

const form = ref(defaultForm())
const argsText = ref('')
const headersText = ref('')
const editingOriginalName = ref('')

const isEditing = computed(() => !!editingOriginalName.value)

const columns: DataTableColumns<MCPServer> = [
  { title: 'Name', key: 'name', width: 150 },
  {
    title: 'Enabled',
    key: 'enabled',
    width: 80,
    render(row) {
      return h(NTag, { size: 'small', type: row.enabled ? 'success' : 'default', bordered: false }, () => row.enabled ? 'On' : 'Off')
    },
  },
  { title: 'Transport', key: 'transport', width: 120 },
  {
    title: 'Command / URL',
    key: 'endpoint',
    ellipsis: { tooltip: true },
    render(row) {
      return row.transport === 'stdio' ? (row.command || '') : (row.url || '')
    },
  },
  {
    title: 'Status',
    key: 'connected',
    width: 80,
    render(row) {
      const h_info = healthMap.value[row.name]
      const connected = h_info?.connected ?? false
      return h('span', {
        style: `display:inline-block;width:10px;height:10px;border-radius:50%;background:${connected ? '#18a058' : '#ccc'}`,
      })
    },
  },
  {
    title: 'Tools',
    key: 'tools',
    width: 70,
    render(row) {
      const h_info = healthMap.value[row.name]
      return h(NTag, { size: 'small', bordered: false }, () => String(h_info?.tools ?? 0))
    },
  },
  { title: 'Description', key: 'description', ellipsis: { tooltip: true } },
]

function rowProps(row: MCPServer) {
  return {
    style: 'cursor: pointer',
    onClick() {
      fillForm(row)
    },
  }
}

function fillForm(s: MCPServer) {
  form.value = { ...defaultForm(), ...s }
  editingOriginalName.value = s.name
  argsText.value = s.args?.join('\n') ?? ''
  headersText.value = s.headers ? JSON.stringify(s.headers, null, 2) : ''
}

function resetForm() {
  form.value = defaultForm()
  editingOriginalName.value = ''
  argsText.value = ''
  headersText.value = ''
}

async function fetchAll() {
  try {
    const [listData, healthData] = await Promise.all([mcpApi.list(), mcpApi.health()])
    servers.value = listData.servers
    toolCallMode.value = listData.tool_call_mode
    toolCallTimeout.value = listData.tool_call_timeout
    healthMap.value = healthData
  } catch (e: any) {
    message.error(e.message || 'Failed to load MCP servers')
  }
}

async function handleSave() {
  const name = form.value.name?.trim()
  if (!name) {
    message.warning('Name is required')
    return
  }
  saving.value = true
  try {
    let headers: Record<string, string> | undefined
    if (headersText.value.trim()) {
      try {
        headers = JSON.parse(headersText.value)
      } catch {
        message.error('Invalid JSON in Headers')
        saving.value = false
        return
      }
    }
    const args = form.value.transport === 'stdio'
      ? argsText.value.split('\n').map(s => s.trim()).filter(Boolean)
      : undefined
    const body: Partial<MCPServer> = {
      enabled: form.value.enabled,
      transport: form.value.transport,
      command: form.value.transport === 'stdio' ? form.value.command : undefined,
      args,
      url: form.value.transport !== 'stdio' ? form.value.url : undefined,
      headers,
      description: form.value.description || undefined,
    }
    await mcpApi.upsert(name, body)
    message.success(isEditing.value ? 'Server updated' : 'Server created')
    resetForm()
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || 'Failed to save server')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!editingOriginalName.value) return
  deleting.value = true
  try {
    await mcpApi.remove(editingOriginalName.value)
    message.success('Server deleted')
    resetForm()
    await fetchAll()
  } catch (e: any) {
    message.error(e.message || 'Failed to delete server')
  } finally {
    deleting.value = false
  }
}

async function handleSetMode(mode: string) {
  try {
    await mcpApi.setMode(mode)
    message.success(`Mode set to ${mode}`)
  } catch (e: any) {
    message.error(e.message || 'Failed to set mode')
    await fetchAll()
  }
}

async function handleSetMaxRounds(val: number | null) {
  if (val == null) return
  try {
    await mcpApi.setMaxToolRounds(val)
    message.success(`Max tool rounds set to ${val}`)
  } catch (e: any) {
    message.error(e.message || 'Failed to set max rounds')
    await fetchAll()
  }
}

function handleParseJson() {
  try {
    const parsed = JSON.parse(quickJson.value)
    const serversObj = parsed.mcpServers || parsed.servers || parsed
    const entries = Object.entries(serversObj)
    if (entries.length === 0) {
      message.warning('No servers found in JSON')
      return
    }
    const [name, config] = entries[0] as [string, any]
    form.value = {
      ...defaultForm(),
      name,
      enabled: true,
      transport: config.transport || (config.command ? 'stdio' : config.url ? 'sse' : 'stdio'),
      command: config.command || '',
      url: config.url || '',
      description: config.description || '',
    }
    argsText.value = Array.isArray(config.args) ? config.args.join('\n') : ''
    headersText.value = config.headers ? JSON.stringify(config.headers, null, 2) : ''
    editingOriginalName.value = ''
    message.success(`Parsed server: ${name}`)
  } catch {
    message.error('Invalid JSON')
  }
}

onMounted(fetchAll)
</script>

<style scoped>
.status-bar {
  background: linear-gradient(135deg, #e8f1fd 0%, #f0f6ff 100%);
  border: 2px solid #4C8FEC;
}

.status-label {
  font-weight: 600;
  color: #555;
}
</style>
