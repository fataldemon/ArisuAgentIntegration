<template>
  <div class="characters-view">
    <NCard :title="$t('characters.expressionFormat')" class="section-card">
      <NSpace vertical :size="16">
        <NFormItem>
              <template #label>{{ $t('characters.formatTemplate') }} <HelpTip>{{ $t('tips.expressionFormat') }}</HelpTip></template>
          <NInput v-model:value="expression.format" placeholder="e.g. 【{'expression': '{expression}'}】" />
        </NFormItem>
        <NFormItem>
              <template #label>{{ $t('characters.instruction') }} <HelpTip>{{ $t('tips.expressionInstruction') }}</HelpTip></template>
          <NInput
            v-model:value="expression.instruction"
            type="textarea"
            :rows="6"
            placeholder="Expression instruction..."
          />
        </NFormItem>
        <NSpace>
          <NButton type="primary" @click="saveExpression">{{ $t('characters.saveExpression') }}</NButton>
          <NButton @click="loadExpression">{{ $t('common.reload') }}</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NCard :title="$t('characters.personaConfig')" class="section-card">
      <NSpace vertical :size="16">
        <NFormItem>
          <template #label>{{ $t('characters.activeCharacter') }} <HelpTip>{{ $t('tips.activeCharacter') }}</HelpTip></template>
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
              <template #label>{{ $t('characters.characterId') }} <HelpTip>{{ $t('tips.characterId') }}</HelpTip></template>
              <NInput v-model:value="editForm.character" placeholder="character" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>{{ $t('characters.displayName') }} <HelpTip>{{ $t('tips.displayName') }}</HelpTip></template>
              <NInput v-model:value="editForm.display_name" placeholder="display_name" />
            </NFormItem>
          </NGi>
          <NGi :span="2">
            <NFormItem>
              <template #label>{{ $t('characters.settingLabel') }} <HelpTip>{{ $t('tips.setting') }}</HelpTip></template>
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
              <template #label>{{ $t('characters.replyInstruction') }} <HelpTip>{{ $t('tips.replyInstruction') }}</HelpTip></template>
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
              <template #label>{{ $t('characters.imageSetting') }} <HelpTip>{{ $t('tips.imageSetting') }}</HelpTip></template>
              <div class="image-setting-editor">
                <div class="image-setting-toolbar">
                  <input
                    type="file"
                    accept="image/*"
                    style="display:none"
                    ref="imageFileInput"
                    @change="onImageFileSelected"
                  />
                  <n-button size="small" @click="($refs.imageFileInput as HTMLInputElement).click()">
                    {{ $t('characters.uploadImage') }}
                  </n-button>
                </div>
                <NInput
                  v-model:value="editForm.image_setting"
                  type="textarea"
                  :rows="4"
                  :placeholder="$t('characters.imageSettingPlaceholder')"
                  ref="imageSettingTextarea"
                />
                <div v-if="imageSettingPreviews.length" class="image-setting-previews">
                  <div v-for="(img, idx) in imageSettingPreviews" :key="idx" class="preview-item">
                    <img :src="img.url" class="preview-thumb" />
                    <span class="preview-name">{{ img.file }}</span>
                  </div>
                </div>
              </div>
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>{{ $t('characters.maxChatLen') }} <HelpTip>{{ $t('tips.maxChatLen') }}</HelpTip></template>
              <NInputNumber v-model:value="editForm.max_chat_len" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>{{ $t('characters.maxAnalysisLen') }} <HelpTip>{{ $t('tips.maxAnalysisLen') }}</HelpTip></template>
              <NInputNumber v-model:value="editForm.max_analysis_len" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>{{ $t('characters.maxQuickReply') }} <HelpTip>{{ $t('tips.maxQuickReply') }}</HelpTip></template>
              <NInputNumber v-model:value="editForm.max_quick_reply" :min="0" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>{{ $t('characters.defaultTemperature') }} <HelpTip>{{ $t('tips.defaultTemperature') }}</HelpTip></template>
              <NInputNumber v-model:value="editForm.default_temperature" :min="0" :max="2" :step="0.01" style="width: 100%" />
            </NFormItem>
          </NGi>
        </NGrid>

        <NSpace>
          <NButton type="primary" @click="savePersona">{{ $t('common.saveUpdate') }}</NButton>
          <NButton type="error" @click="deletePersona">{{ $t('common.delete') }}</NButton>
          <NButton @click="loadPersonas">{{ $t('common.refresh') }}</NButton>
        </NSpace>

        <NCollapse>
          <NCollapseItem :title="$t('characters.previewPrompt')" name="preview">
            <NSpace vertical :size="12">
              <NFormItem>
                <template #label>{{ $t('characters.userText') }} <HelpTip>{{ $t('tips.previewUserText') }}</HelpTip></template>
                <NInput v-model:value="previewText" :placeholder="$t('characters.userTextPlaceholder')" />
              </NFormItem>
              <NButton type="info" @click="doPreview" :disabled="!editForm.character">{{ $t('characters.renderPreview') }}</NButton>
              <pre v-if="previewResult" class="preview-block">{{ previewResult }}</pre>
            </NSpace>
          </NCollapseItem>
        </NCollapse>
      </NSpace>
    </NCard>

    <NCard :title="$t('characters.knowledgeBase')" class="section-card">
      <NSpace vertical :size="16">
        <NGrid :cols="3" :x-gap="12">
          <NGi>
            <NFormItem>
              <template #label>{{ $t('characters.selectCharacter') }} <HelpTip>{{ $t('tips.kbCharacter') }}</HelpTip></template>
              <NSelect
                v-model:value="kb.character"
                :options="kbCharacterOptions"
                :placeholder="$t('characters.selectCharacter')"
                @update:value="onKbCharacterChange"
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>{{ $t('characters.subject') }} <HelpTip>{{ $t('tips.kbSubject') }}</HelpTip></template>
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
              <template #label>{{ $t('characters.selectFile') }} <HelpTip>{{ $t('tips.kbFile') }}</HelpTip></template>
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
          <template #label>{{ $t('characters.fileContent') }} <HelpTip>{{ $t('tips.kbContent') }}</HelpTip></template>
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
            <template #label>{{ $t('characters.newFileName') }} <HelpTip>{{ $t('tips.kbNewFile') }}</HelpTip></template>
            <NInput v-model:value="kb.newFilename" :placeholder="$t('characters.newFileNamePlaceholder')" style="width: 200px" />
          </NFormItem>
          <NButton @click="kbCreateFile">{{ $t('characters.createFile') }}</NButton>
          <NDivider vertical />
          <NButton type="primary" @click="kbSaveFile">{{ $t('characters.saveFile') }}</NButton>
          <NButton type="error" @click="kbDeleteFile">{{ $t('characters.deleteFile') }}</NButton>
          <NDivider vertical />
          <NButton type="warning" @click="kbRebuild">{{ $t('characters.rebuildIndex') }}</NButton>
          <NButton @click="kbShowStatus">{{ $t('characters.showIndexStatus') }}</NButton>
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
import { useI18n } from 'vue-i18n'
import { personasApi } from '../api/personas'
import { knowledgeApi } from '../api/knowledge'
import type { Persona, ExpressionConfig } from '../types'
import HelpTip from '../components/HelpTip.vue'

const { t } = useI18n()
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
const imageFileInput = ref<HTMLInputElement | null>(null)
const imageSettingTextarea = ref<InstanceType<typeof NInput> | null>(null)

const imageSettingPreviews = computed(() => {
  const text = editForm.image_setting || ''
  const re = /\[image,file=([^\]]+)\]/g
  const result: Array<{ file: string; url: string }> = []
  let m
  while ((m = re.exec(text)) !== null) {
    result.push({
      file: m[1],
      url: `/admin/characters/${editForm.character}/image/${m[1]}`,
    })
  }
  return result
})

async function onImageFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !editForm.character) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await fetch(`/admin/api/personas/${editForm.character}/image`, {
      method: 'POST',
      body: formData,
    })
    const data = await res.json()
    if (data.ok) {
      const placeholder = `[image,file=${data.filename}]`
      const current = editForm.image_setting || ''
      editForm.image_setting = current ? current + '\n' + placeholder : placeholder
    } else {
      message.error('上传失败')
    }
  } catch { message.error('上传失败') }
  input.value = ''
}
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
    title: t('characters.characterId'),
    key: 'character',
    render: (row) => h('a', {
      style: 'color: var(--ba-primary); cursor: pointer; text-decoration: none;',
      onClick: () => loadPersonaDetail(row.character),
    }, row.character),
  },
  { title: t('characters.displayName'), key: 'display_name' },
  {
    title: t('characters.hasSetting'),
    key: 'setting',
    render: (row) => h(NTag, { size: 'small', type: row.setting ? 'success' : 'default' }, () => row.setting ? 'Yes' : 'No'),
  },
  {
    title: t('characters.hasReplyInstr'),
    key: 'reply_instruction',
    render: (row) => h(NTag, { size: 'small', type: row.reply_instruction ? 'success' : 'default' }, () => row.reply_instruction ? 'Yes' : 'No'),
  },
  {
    title: t('characters.hasImageSetting'),
    key: 'image_setting',
    render: (row) => h(NTag, { size: 'small', type: row.image_setting ? 'success' : 'default' }, () => row.image_setting ? 'Yes' : 'No'),
  },
]

async function loadExpression() {
  try {
    const data = await personasApi.getExpression()
    expression.format = data.format || ''
    expression.instruction = data.instruction || ''
    message.success(t('characters.loaded'))
  } catch (e: any) {
    message.error(e.message)
  }
}

async function saveExpression() {
  try {
    await personasApi.setExpression(expression.format, expression.instruction)
    message.success(t('characters.saved'))
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
    message.success(t('characters.activated', { char }))
    await loadPersonaDetail(char)
  } catch (e: any) {
    message.error(e.message)
  }
}

async function savePersona() {
  if (!editForm.character) { message.warning(t('characters.characterIdRequired')); return }
  try {
    const { character, ...body } = editForm
    await personasApi.upsert(character, body)
    message.success(t('characters.saved'))
    await loadPersonas()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function deletePersona() {
  if (!editForm.character) { message.warning(t('characters.noCharacterSelected')); return }
  try {
    await personasApi.remove(editForm.character)
    message.success(t('characters.deleted'))
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
  if (!kb.character || !kb.subject || !kb.newFilename) { message.warning(t('characters.fillRequired')); return }
  try {
    await knowledgeApi.createFile(kb.character, kb.subject, kb.newFilename)
    message.success(t('characters.fileCreated'))
    kb.newFilename = ''
    await onKbSubjectChange()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbSaveFile() {
  if (!kb.character || !kb.subject || !kb.selectedFile) { message.warning(t('characters.selectFileFirst')); return }
  try {
    await knowledgeApi.saveFile(kb.character, kb.subject, kb.selectedFile, kb.content)
    message.success(t('characters.fileSaved'))
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbDeleteFile() {
  if (!kb.character || !kb.subject || !kb.selectedFile) { message.warning(t('characters.selectFileFirst')); return }
  try {
    await knowledgeApi.deleteFile(kb.character, kb.subject, kb.selectedFile)
    message.success(t('characters.fileDeleted'))
    kb.selectedFile = null
    kb.content = ''
    await onKbSubjectChange()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbRebuild() {
  if (!kb.character || !kb.subject) { message.warning(t('characters.selectCharacterAndSubject')); return }
  try {
    const data = await knowledgeApi.rebuild(kb.character, kb.subject)
    message.success(data.result || t('characters.rebuildComplete'))
  } catch (e: any) {
    message.error(e.message)
  }
}

async function kbShowStatus() {
  if (!kb.character || !kb.subject) { message.warning(t('characters.selectCharacterAndSubject')); return }
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

.image-setting-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.image-setting-toolbar {
  display: flex;
  justify-content: flex-end;
}

.image-setting-previews {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.preview-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.preview-thumb {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--n-border-color);
}

.preview-name {
  font-size: 11px;
  color: var(--n-text-color-3);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
