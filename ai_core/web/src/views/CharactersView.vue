<template>
  <div class="characters-view">
    <NCard title="Expression Format (Global)" class="section-card">
      <NSpace vertical :size="16">
        <NFormItem>
          <template #label>Format Template <HelpTip>输出模板。{expression} 是占位符，会被替换为实际情感标签。修改后 AI 输出的情感标记格式同步变更</HelpTip></template>
          <NInput v-model:value="expression.format" placeholder="e.g. 【{'expression': '{expression}'}】" />
        </NFormItem>
        <NFormItem>
          <template #label>Instruction <HelpTip>注入到所有角色 system prompt 末尾的格式规范。告诉 LLM 如何正确输出情感标记（含示例）</HelpTip></template>
          <NInput
            v-model:value="expression.instruction"
            type="textarea"
            :rows="6"
            placeholder="Expression instruction..."
          />
        </NFormItem>
        <NSpace>
          <NButton type="primary" @click="saveExpression">Save</NButton>
          <NButton @click="loadExpression">Reload</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NCard title="Persona Configuration" class="section-card">
      <NSpace vertical :size="16">
        <NFormItem>
          <template #label>Active Character <HelpTip>切换活跃角色。选择后自动加载该角色的 persona 配置并设为当前使用角色</HelpTip></template>
          <NRadioGroup v-model:value="activeCharacter" @update:value="onActivateCharacter">
            <NSpace>
              <NRadio v-for="p in personas" :key="p.character" :value="p.character">
                {{ p.display_name || p.character }}
              </NRadio>
            </NSpace>
          </NRadioGroup>
        </NFormItem>

        <NDataTable
          :columns="personaColumns"
          :data="personas"
          :row-key="(r: Persona) => r.character"
          :row-class-name="(r: Persona) => r.character === editForm.character ? 'row-selected' : ''"
          size="small"
          :bordered="false"
          @update:checked-row-keys="() => {}"
        />

        <NDivider />

        <NGrid :cols="2" :x-gap="16" :y-gap="12">
          <NGi>
            <NFormItem>
              <template #label>Character ID <HelpTip>embedding/ 下的目录名。每个角色的 persona.json 和知识库文件都放在对应目录下</HelpTip></template>
              <NInput v-model:value="editForm.character" placeholder="character" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>Display Name <HelpTip>前端展示的昵称。例如 天童爱丽丝</HelpTip></template>
              <NInput v-model:value="editForm.display_name" placeholder="display_name" />
            </NFormItem>
          </NGi>
          <NGi :span="2">
            <NFormItem>
              <template #label>Setting (supports {embeddings} placeholder) <HelpTip>角色的世界观和性格设定（system prompt 主体）。支持 {embeddings} 占位符，运行时会动态注入 RAG 检索到的知识库文本</HelpTip></template>
              <NInput
                v-model:value="editForm.setting"
                type="textarea"
                :rows="12"
                placeholder="Persona setting..."
                style="font-family: monospace"
              />
            </NFormItem>
          </NGi>
          <NGi :span="2">
            <NFormItem>
              <template #label>Reply Instruction <HelpTip>追加在 system prompt 末尾的回复规范</HelpTip></template>
              <NInput
                v-model:value="editForm.reply_instruction"
                type="textarea"
                :rows="4"
                placeholder="Reply instruction..."
              />
            </NFormItem>
          </NGi>
          <NGi :span="2">
            <NFormItem>
              <template #label>Image Setting <HelpTip>角色的形象描述（含图片占位符）。以 user 角色消息而非 system 消息注入</HelpTip></template>
              <NInput
                v-model:value="editForm.image_setting"
                type="textarea"
                :rows="4"
                placeholder="Image setting..."
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>Max Chat Length <HelpTip>普通对话请求的 max_tokens 上限。留空则使用全局配置</HelpTip></template>
              <NInputNumber v-model:value="editForm.max_chat_len" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>Max Analysis Length <HelpTip>assistant 端点分析请求的 max_tokens 上限。留空则使用全局配置</HelpTip></template>
              <NInputNumber v-model:value="editForm.max_analysis_len" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>Max Quick Reply <HelpTip>WebSocket 快速回复请求的 max_tokens 上限。留空则使用全局配置</HelpTip></template>
              <NInputNumber v-model:value="editForm.max_quick_reply" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>Default Temperature <HelpTip>该角色的默认采样温度。范围 0~2，越高回复越随机</HelpTip></template>
              <NInputNumber v-model:value="editForm.default_temperature" :min="0" :max="2" :step="0.01" style="width: 100%" />
            </NFormItem>
          </NGi>
        </NGrid>

        <NSpace>
          <NButton type="primary" @click="savePersona">Save</NButton>
          <NButton type="error" @click="deletePersona">Delete</NButton>
          <NButton @click="loadPersonas">Refresh</NButton>
        </NSpace>

        <NCollapse>
          <NCollapseItem title="Preview System Prompt" name="preview">
            <NSpace vertical :size="12">
              <NFormItem>
                <template #label>User Text <HelpTip>模拟用户消息文本。用于触发 process_embedding 展示 RAG 检索结果在渲染后的 system prompt 中的效果</HelpTip></template>
                <NInput v-model:value="previewText" placeholder="Enter user text for preview..." />
              </NFormItem>
              <NButton type="info" @click="doPreview" :disabled="!editForm.character">Preview</NButton>
              <pre v-if="previewResult" class="preview-block">{{ previewResult }}</pre>
            </NSpace>
          </NCollapseItem>
        </NCollapse>
      </NSpace>
    </NCard>

    <NCard title="Knowledge Base" class="section-card">
      <NSpace vertical :size="16">
        <NGrid :cols="3" :x-gap="12">
          <NGi>
            <NFormItem>
              <template #label>Character <HelpTip>选择要管理的角色知识库</HelpTip></template>
              <NSelect
                v-model:value="kb.character"
                :options="kbCharacterOptions"
                placeholder="Select character"
                @update:value="onKbCharacterChange"
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>Subject <HelpTip>知识类别。setting: 世界观补充。knowledge: 动态学到的知识。expression: 情感标签库</HelpTip></template>
              <NSelect
                v-model:value="kb.subject"
                :options="kbSubjectOptions"
                placeholder="Select subject"
                @update:value="onKbSubjectChange"
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>File <HelpTip>选择知识库文件进行查看/编辑。.mem 是纯文本格式</HelpTip></template>
              <NSelect
                v-model:value="kb.selectedFile"
                :options="kbFileOptions"
                placeholder="Select .mem file"
                @update:value="onKbFileChange"
              />
            </NFormItem>
          </NGi>
        </NGrid>

        <NFormItem>
          <template #label>File Content <HelpTip>.mem 文件内容。每个段落以空行分隔，可用 ##tag 后缀为段落添加标签</HelpTip></template>
          <NInput
            v-model:value="kb.content"
            type="textarea"
            :rows="20"
            placeholder="File content..."
            style="font-family: monospace"
          />
        </NFormItem>

        <NSpace align="center">
          <NFormItem>
            <template #label>New file name <HelpTip>新文件名（.mem 后缀自动添加）</HelpTip></template>
            <NInput v-model:value="kb.newFilename" placeholder="new_file.mem" style="width: 200px" />
          </NFormItem>
          <NButton @click="kbCreateFile">Create</NButton>
          <NDivider vertical />
          <NButton type="primary" @click="kbSaveFile">Save File</NButton>
          <NButton type="error" @click="kbDeleteFile">Delete File</NButton>
          <NDivider vertical />
          <NButton type="warning" @click="kbRebuild">Rebuild FAISS Index</NButton>
          <NButton @click="kbShowStatus">Show Index Status</NButton>
        </NSpace>

        <pre v-if="kb.indexStatus" class="status-block">{{ kb.indexStatus }}</pre>
      </NSpace>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, h } from 'vue'
import {
  NCard, NDataTable, NButton, NInput, NInputNumber, NSelect,
  NRadioGroup, NRadio, NSpace, NTag, NDivider, NGrid, NGi,
  NFormItem, NCollapse, NCollapseItem, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { personasApi } from '../api/personas'
import { knowledgeApi } from '../api/knowledge'
import type { Persona, ExpressionConfig } from '../types'
import HelpTip from '../components/HelpTip.vue'

const message = useMessage()

const expression = reactive<ExpressionConfig>({ format: '', instruction: '' })
const personas = ref<Persona[]>([])
const activeCharacter = ref('')
const editForm = reactive<Persona>({
  character: '',
  display_name: '',
  setting: '',
  reply_instruction: '',
  image_setting: '',
  max_chat_len: undefined,
  max_analysis_len: undefined,
  max_quick_reply: undefined,
  default_temperature: undefined,
})
const previewText = ref('')
const previewResult = ref('')

const kb = reactive({
  character: null as string | null,
  subject: null as string | null,
  selectedFile: null as string | null,
  content: '',
  newFilename: '',
  characters: [] as string[],
  files: [] as string[],
  indexStatus: '',
})

const kbCharacterOptions = computed(() =>
  kb.characters.map(c => ({ label: c, value: c }))
)

const kbSubjectOptions = computed(() => {
  return [
    { label: 'setting', value: 'setting' },
    { label: 'expression', value: 'expression' },
    { label: 'knowledge', value: 'knowledge' },
  ]
})

const kbFileOptions = computed(() =>
  kb.files.map(f => ({ label: f, value: f }))
)

const personaColumns: DataTableColumns<Persona> = [
  {
    title: 'Character',
    key: 'character',
    render: (row) => h('a', {
      style: 'color: var(--ba-primary); cursor: pointer; text-decoration: none;',
      onClick: () => loadPersonaDetail(row.character),
    }, row.character),
  },
  { title: 'Display Name', key: 'display_name' },
  {
    title: 'Has Setting',
    key: 'setting',
    render: (row) => h(NTag, { size: 'small', type: row.setting ? 'success' : 'default' }, () => row.setting ? 'Yes' : 'No'),
  },
  {
    title: 'Has Reply Instr.',
    key: 'reply_instruction',
    render: (row) => h(NTag, { size: 'small', type: row.reply_instruction ? 'success' : 'default' }, () => row.reply_instruction ? 'Yes' : 'No'),
  },
  {
    title: 'Has Image Setting',
    key: 'image_setting',
    render: (row) => h(NTag, { size: 'small', type: row.image_setting ? 'success' : 'default' }, () => row.image_setting ? 'Yes' : 'No'),
  },
]

async function loadExpression() {
  try {
    const data = await personasApi.getExpression()
    expression.format = data.format || ''
    expression.instruction = data.instruction || ''
    message.success('Expression loaded')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function saveExpression() {
  try {
    await personasApi.setExpression(expression.format, expression.instruction)
    message.success('Expression saved')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function loadPersonas() {
  try {
    const data = await personasApi.list()
    personas.value = data.personas
    const active = await personasApi.getActiveCharacter()
    activeCharacter.value = active.character
  } catch (e: any) {
    message.error(e.message)
  }
}

async function loadPersonaDetail(character: string) {
  try {
    const data = await personasApi.detail(character)
    Object.assign(editForm, {
      character: data.character,
      display_name: data.display_name || '',
      setting: data.setting || '',
      reply_instruction: data.reply_instruction || '',
      image_setting: data.image_setting || '',
      max_chat_len: data.max_chat_len,
      max_analysis_len: data.max_analysis_len,
      max_quick_reply: data.max_quick_reply,
      default_temperature: data.default_temperature,
    })
  } catch (e: any) {
    message.error(e.message)
  }
}

async function onActivateCharacter(char: string) {
  try {
    await personasApi.activateCharacter(char)
    activeCharacter.value = char
    message.success(`Activated: ${char}`)
    await loadPersonaDetail(char)
  } catch (e: any) {
    message.error(e.message)
  }
}

async function savePersona() {
  if (!editForm.character) { message.warning('Character ID required'); return }
  try {
    const { character, ...body } = editForm
    await personasApi.upsert(character, body)
    message.success('Persona saved')
    await loadPersonas()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function deletePersona() {
  if (!editForm.character) { message.warning('No character selected'); return }
  try {
    await personasApi.remove(editForm.character)
    message.success('Persona deleted')
    Object.assign(editForm, { character: '', display_name: '', setting: '', reply_instruction: '', image_setting: '', max_chat_len: undefined, max_analysis_len: undefined, max_quick_reply: undefined, default_temperature: undefined })
    await loadPersonas()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function doPreview() {
  if (!editForm.character) return
  try {
    const data = await personasApi.preview(editForm.character, previewText.value)
    previewResult.value = typeof data.system_prompt === 'string'
      ? data.system_prompt
      : JSON.stringify(data.system_prompt, null, 2)
  } catch (e: any) {
    message.error(e.message)
  }
}

async function loadKbCharacters() {
  try {
    const data = await knowledgeApi.listCharacters()
    kb.characters = data.characters
  } catch (e: any) {
    message.error(e.message)
  }
}

async function onKbCharacterChange() {
  kb.subject = null
  kb.selectedFile = null
  kb.files = []
  kb.content = ''
  kb.indexStatus = ''
}

async function onKbSubjectChange() {
  kb.selectedFile = null
  kb.content = ''
  kb.indexStatus = ''
  if (!kb.character || !kb.subject) return
  try {
    const data = await knowledgeApi.listFiles(kb.character, kb.subject)
    kb.files = data.files
  } catch (e: any) {
    message.error(e.message)
  }
}

async function onKbFileChange(filename: string) {
  if (!kb.character || !kb.subject || !filename) return
  try {
    const data = await knowledgeApi.readFile(kb.character, kb.subject, filename)
    kb.content = data.content
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbCreateFile() {
  if (!kb.character || !kb.subject || !kb.newFilename) { message.warning('Fill character, subject, and filename'); return }
  try {
    await knowledgeApi.createFile(kb.character, kb.subject, kb.newFilename)
    message.success('File created')
    kb.newFilename = ''
    await onKbSubjectChange()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbSaveFile() {
  if (!kb.character || !kb.subject || !kb.selectedFile) { message.warning('Select a file first'); return }
  try {
    await knowledgeApi.saveFile(kb.character, kb.subject, kb.selectedFile, kb.content)
    message.success('File saved')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbDeleteFile() {
  if (!kb.character || !kb.subject || !kb.selectedFile) { message.warning('Select a file first'); return }
  try {
    await knowledgeApi.deleteFile(kb.character, kb.subject, kb.selectedFile)
    message.success('File deleted')
    kb.selectedFile = null
    kb.content = ''
    await onKbSubjectChange()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbRebuild() {
  if (!kb.character || !kb.subject) { message.warning('Select character and subject'); return }
  try {
    const data = await knowledgeApi.rebuild(kb.character, kb.subject)
    message.success(data.result || 'Rebuild complete')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbShowStatus() {
  if (!kb.character || !kb.subject) { message.warning('Select character and subject'); return }
  try {
    const data = await knowledgeApi.indexStatus(kb.character, kb.subject)
    kb.indexStatus = JSON.stringify(data, null, 2)
  } catch (e: any) {
    message.error(e.message)
  }
}

onMounted(() => {
  loadExpression()
  loadPersonas()
  loadKbCharacters()
})
</script>

<style scoped>
.characters-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
}

.section-card {
  background: var(--ba-card);
  border: 1px solid var(--ba-border);
}

.preview-block {
  width: 100%;
  padding: 16px;
  background: #1a2333;
  color: #e0e8f0;
  border-radius: 8px;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
  max-height: 500px;
  overflow-y: auto;
}

.status-block {
  width: 100%;
  padding: 12px 16px;
  background: #f5f7fa;
  border: 1px solid var(--ba-border);
  border-radius: 8px;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}
</style>
