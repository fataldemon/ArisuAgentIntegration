<template>
  <div class="characters-view">
    <NCard title="Expression Format (Global)" class="section-card">
      <NSpace vertical :size="16">
        <NFormItem label="Format Template">
          <NInput v-model:value="expression.format" placeholder="e.g. 【{'expression': '{expression}'}】" />
        </NFormItem>
        <NFormItem label="Instruction">
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
        <NFormItem label="Active Character">
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
            <NFormItem label="Character ID">
              <NInput v-model:value="editForm.character" placeholder="character" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="Display Name">
              <NInput v-model:value="editForm.display_name" placeholder="display_name" />
            </NFormItem>
          </NGi>
          <NGi :span="2">
            <NFormItem label="Setting (supports {embeddings} placeholder)">
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
            <NFormItem label="Reply Instruction">
              <NInput
                v-model:value="editForm.reply_instruction"
                type="textarea"
                :rows="4"
                placeholder="Reply instruction..."
              />
            </NFormItem>
          </NGi>
          <NGi :span="2">
            <NFormItem label="Image Setting">
              <NInput
                v-model:value="editForm.image_setting"
                type="textarea"
                :rows="4"
                placeholder="Image setting..."
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="Max Chat Length">
              <NInputNumber v-model:value="editForm.max_chat_len" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="Max Analysis Length">
              <NInputNumber v-model:value="editForm.max_analysis_len" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="Max Quick Reply">
              <NInputNumber v-model:value="editForm.max_quick_reply" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="Default Temperature">
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
              <NFormItem label="User Text">
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
            <NFormItem label="Character">
              <NSelect
                v-model:value="kb.character"
                :options="kbCharacterOptions"
                placeholder="Select character"
                @update:value="onKbCharacterChange"
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="Subject">
              <NSelect
                v-model:value="kb.subject"
                :options="kbSubjectOptions"
                placeholder="Select subject"
                @update:value="onKbSubjectChange"
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="File">
              <NSelect
                v-model:value="kb.selectedFile"
                :options="kbFileOptions"
                placeholder="Select .mem file"
                @update:value="onKbFileChange"
              />
            </NFormItem>
          </NGi>
        </NGrid>

        <NFormItem label="File Content">
          <NInput
            v-model:value="kb.content"
            type="textarea"
            :rows="20"
            placeholder="File content..."
            style="font-family: monospace"
          />
        </NFormItem>

        <NSpace align="center">
          <NInput v-model:value="kb.newFilename" placeholder="new_file.mem" style="width: 200px" />
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
