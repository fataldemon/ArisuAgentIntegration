<template>
  <n-space vertical :size="20">
    <n-card v-if="activeProvider" class="active-card" :bordered="true">
      <n-space align="center" :size="16">
        <n-tag type="info" size="large" round>Active</n-tag>
        <span class="active-name">{{ activeProvider.name }}</span>
        <n-tag>{{ activeProvider.model }}</n-tag>
        <n-tag>{{ activeProvider.type }}</n-tag>
      </n-space>
    </n-card>

    <n-card title="Providers" :bordered="true">
      <template #header-extra>
        <n-button @click="fetchProviders" quaternary circle>
          <template #icon>↻</template>
        </n-button>
      </template>
      <n-data-table
        :columns="columns"
        :data="providers"
        :row-props="rowProps"
        :bordered="false"
        size="small"
        max-height="360"
      />
    </n-card>

    <n-card :bordered="true">
      <template #header>Active Provider <HelpTip>切换活跃 provider。所有对话请求都会路由到选中的活跃 provider</HelpTip></template>
      <n-radio-group v-model:value="selectedActive" @update:value="handleActivate">
        <n-space>
          <n-radio v-for="p in providers" :key="p.name" :value="p.name">
            {{ p.name }}
          </n-radio>
        </n-space>
      </n-radio-group>
    </n-card>

    <n-card :title="form.name ? `Edit: ${form.name}` : 'Create Provider'" :bordered="true">
      <n-grid :cols="2" :x-gap="16" :y-gap="12">
        <n-gi>
          <n-form-item>
            <template #label>name <HelpTip>唯一标识符，用于识别该 provider。例如 local_vllm</HelpTip></template>
            <n-input v-model:value="form.name" placeholder="provider-name" />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>type <HelpTip>后端类型。目前固定为 openai_compatible</HelpTip></template>
            <n-input v-model:value="form.type" placeholder="openai_compatible" />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>base_url <HelpTip>LLM 服务的完整地址（含 /v1 前缀），例如 http://localhost:8001/v1</HelpTip></template>
            <n-input v-model:value="form.base_url" placeholder="https://api.openai.com/v1" />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>model <HelpTip>发送给 upstream 的模型名称。vLLM 的 --served-model-name 参数映射到此字段</HelpTip></template>
            <n-input v-model:value="form.model" placeholder="gpt-4o" />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>api_key <HelpTip>API 密钥。如不需要鉴权可留空</HelpTip></template>
            <n-input
              v-model:value="form.api_key"
              type="password"
              show-password-on="click"
              placeholder="sk-..."
            />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item>
            <template #label>description <HelpTip>用于文档展示，不影响运行逻辑</HelpTip></template>
            <n-input v-model:value="form.description" placeholder="Optional description" />
          </n-form-item>
        </n-gi>
        <n-gi :span="2">
          <n-space :size="24">
            <n-form-item label-placement="left">
              <template #label>supports vision <HelpTip>勾选后图片 URL/data-uri 会传给模型。不勾选则替换为 [图片已省略] 占位文本</HelpTip></template>
              <n-switch v-model:value="form.supports_vision" />
            </n-form-item>
            <n-form-item label-placement="left">
              <template #label>supports audio <HelpTip>勾选后音频内容传给模型。不勾选则替换为 [音频已省略] 占位文本</HelpTip></template>
              <n-switch v-model:value="form.supports_audio" />
            </n-form-item>
            <n-form-item label-placement="left">
              <template #label>supports video <HelpTip>勾选后视频内容传给模型。不勾选则替换为 [视频已省略] 占位文本</HelpTip></template>
              <n-switch v-model:value="form.supports_video" />
            </n-form-item>
            <n-form-item label-placement="left">
              <template #label>prefetch media <HelpTip>开启后 HTTP(S) 媒体 URL 会被后台预取内联为 data: URI 再发给模型。解决 vLLM 无法访问 CDN 签名 URL 的问题</HelpTip></template>
              <n-switch v-model:value="form.prefetch_media" />
            </n-form-item>
          </n-space>
        </n-gi>
        <n-gi :span="2">
          <n-form-item>
            <template #label>extra_body (JSON) <HelpTip>额外请求体参数（JSON），会合并到每次 LLM 调用中。例如 {"chat_template_kwargs": {"enable_thinking": false}}</HelpTip></template>
            <n-input
              v-model:value="extraBodyText"
              type="textarea"
              :rows="3"
              placeholder='{"key": "value"}'
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
  NSpace, NCard, NDataTable, NButton, NInput, NSwitch, NRadioGroup,
  NRadio, NTag, NDivider, NGrid, NGi, NFormItem, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { providersApi } from '../api/providers'
import type { Provider } from '../types'
import HelpTip from '../components/HelpTip.vue'

const message = useMessage()
const providers = ref<Provider[]>([])
const activeName = ref('')
const selectedActive = ref('')
const saving = ref(false)
const deleting = ref(false)

const defaultForm = (): Partial<Provider> => ({
  name: '',
  type: 'openai_compatible',
  base_url: '',
  model: '',
  api_key: '',
  description: '',
  supports_vision: false,
  supports_audio: false,
  supports_video: false,
  prefetch_media: false,
  extra_body: undefined,
})

const form = ref<Partial<Provider>>(defaultForm())
const extraBodyText = ref('')
const editingOriginalName = ref('')

const isEditing = computed(() => !!editingOriginalName.value)

const activeProvider = computed(() =>
  providers.value.find(p => p.name === activeName.value)
)

const columns: DataTableColumns<Provider> = [
  {
    title: '✓',
    key: 'active',
    width: 40,
    render(row) {
      return row.name === activeName.value ? h('span', { style: 'color: #4C8FEC; font-weight: bold' }, '✓') : ''
    },
  },
  { title: 'Name', key: 'name', width: 140 },
  { title: 'Type', key: 'type', width: 120 },
  { title: 'Model', key: 'model', width: 160 },
  { title: 'Base URL', key: 'base_url', ellipsis: { tooltip: true }, width: 200 },
  {
    title: 'Vision',
    key: 'supports_vision',
    width: 70,
    render(row) {
      return h(NTag, { size: 'small', type: row.supports_vision ? 'success' : 'default', bordered: false }, () => row.supports_vision ? 'Yes' : 'No')
    },
  },
  {
    title: 'Audio',
    key: 'supports_audio',
    width: 70,
    render(row) {
      return h(NTag, { size: 'small', type: row.supports_audio ? 'success' : 'default', bordered: false }, () => row.supports_audio ? 'Yes' : 'No')
    },
  },
  {
    title: 'Video',
    key: 'supports_video',
    width: 70,
    render(row) {
      return h(NTag, { size: 'small', type: row.supports_video ? 'success' : 'default', bordered: false }, () => row.supports_video ? 'Yes' : 'No')
    },
  },
  {
    title: 'Prefetch',
    key: 'prefetch_media',
    width: 80,
    render(row) {
      return h(NTag, { size: 'small', type: row.prefetch_media ? 'info' : 'default', bordered: false }, () => row.prefetch_media ? 'Yes' : 'No')
    },
  },
  { title: 'Description', key: 'description', ellipsis: { tooltip: true } },
]

function rowProps(row: Provider) {
  return {
    style: 'cursor: pointer',
    onClick() {
      fillForm(row)
    },
  }
}

function fillForm(p: Provider) {
  form.value = { ...p }
  editingOriginalName.value = p.name
  extraBodyText.value = p.extra_body ? JSON.stringify(p.extra_body, null, 2) : ''
}

function resetForm() {
  form.value = defaultForm()
  editingOriginalName.value = ''
  extraBodyText.value = ''
}

async function fetchProviders() {
  try {
    const data = await providersApi.list()
    providers.value = data.providers
    activeName.value = data.active
    selectedActive.value = data.active
  } catch (e: any) {
    message.error(e.message || 'Failed to load providers')
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
    let extraBody: Record<string, any> | undefined
    if (extraBodyText.value.trim()) {
      try {
        extraBody = JSON.parse(extraBodyText.value)
      } catch {
        message.error('Invalid JSON in Extra Body')
        saving.value = false
        return
      }
    }
    const body: Partial<Provider> = {
      ...form.value,
      extra_body: extraBody,
    }
    delete (body as any).name
    await providersApi.upsert(name, body)
    message.success(isEditing.value ? 'Provider updated' : 'Provider created')
    resetForm()
    await fetchProviders()
  } catch (e: any) {
    message.error(e.message || 'Failed to save provider')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!editingOriginalName.value) return
  deleting.value = true
  try {
    await providersApi.remove(editingOriginalName.value)
    message.success('Provider deleted')
    resetForm()
    await fetchProviders()
  } catch (e: any) {
    message.error(e.message || 'Failed to delete provider')
  } finally {
    deleting.value = false
  }
}

async function handleActivate(name: string) {
  try {
    await providersApi.activate(name)
    activeName.value = name
    message.success(`Activated: ${name}`)
  } catch (e: any) {
    selectedActive.value = activeName.value
    message.error(e.message || 'Failed to activate provider')
  }
}

onMounted(fetchProviders)
</script>

<style scoped>
.active-card {
  background: linear-gradient(135deg, #e8f1fd 0%, #f0f6ff 100%);
  border: 2px solid #4C8FEC;
}

.active-name {
  font-size: 18px;
  font-weight: 600;
  color: #2B6BC7;
}
</style>
