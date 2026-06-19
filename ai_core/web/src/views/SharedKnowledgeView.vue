<template>
  <div class="shared-knowledge-view">
    <NCard title="Shared Knowledge (_shared/knowledge)" class="section-card">
      <NSpace vertical :size="16">
        <NFormItem label="File">
          <NSelect
            v-model:value="selectedFile"
            :options="fileOptions"
            placeholder="Select .mem file"
            @update:value="onFileChange"
          />
        </NFormItem>

        <NFormItem label="File Content">
          <NInput
            v-model:value="content"
            type="textarea"
            :rows="20"
            placeholder="File content..."
            style="font-family: monospace"
          />
        </NFormItem>

        <NSpace align="center">
          <NInput v-model:value="newFilename" placeholder="new_file.mem" style="width: 200px" />
          <NButton @click="createFile">Create</NButton>
          <NDivider vertical />
          <NButton type="primary" @click="saveFile">Save</NButton>
          <NButton type="error" @click="deleteFile">Delete</NButton>
          <NButton @click="loadFiles">Refresh</NButton>
          <NDivider vertical />
          <NButton type="warning" @click="rebuild">Rebuild FAISS Index</NButton>
          <NButton @click="showStatus">Show Index Status</NButton>
        </NSpace>

        <pre v-if="indexStatus" class="status-block">{{ indexStatus }}</pre>
      </NSpace>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  NCard, NButton, NInput, NSelect, NSpace, NDivider, NFormItem, useMessage,
} from 'naive-ui'
import { knowledgeApi } from '../api/knowledge'

const CHARACTER = '_shared'
const SUBJECT = 'knowledge'

const message = useMessage()

const files = ref<string[]>([])
const selectedFile = ref<string | null>(null)
const content = ref('')
const newFilename = ref('')
const indexStatus = ref('')

const fileOptions = computed(() =>
  files.value.map(f => ({ label: f, value: f }))
)

async function loadFiles() {
  try {
    const data = await knowledgeApi.listFiles(CHARACTER, SUBJECT)
    files.value = data.files
    message.success('Files refreshed')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function onFileChange(filename: string) {
  if (!filename) return
  try {
    const data = await knowledgeApi.readFile(CHARACTER, SUBJECT, filename)
    content.value = data.content
  } catch (e: any) {
    message.error(e.message)
  }
}

async function createFile() {
  if (!newFilename.value) { message.warning('Enter a filename'); return }
  try {
    await knowledgeApi.createFile(CHARACTER, SUBJECT, newFilename.value)
    message.success('File created')
    newFilename.value = ''
    await loadFiles()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function saveFile() {
  if (!selectedFile.value) { message.warning('Select a file first'); return }
  try {
    await knowledgeApi.saveFile(CHARACTER, SUBJECT, selectedFile.value, content.value)
    message.success('File saved')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function deleteFile() {
  if (!selectedFile.value) { message.warning('Select a file first'); return }
  try {
    await knowledgeApi.deleteFile(CHARACTER, SUBJECT, selectedFile.value)
    message.success('File deleted')
    selectedFile.value = null
    content.value = ''
    await loadFiles()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function rebuild() {
  try {
    const data = await knowledgeApi.rebuild(CHARACTER, SUBJECT)
    message.success(data.result || 'Rebuild complete')
  } catch (e: any) {
    message.error(e.message)
  }
}

async function showStatus() {
  try {
    const data = await knowledgeApi.indexStatus(CHARACTER, SUBJECT)
    indexStatus.value = JSON.stringify(data, null, 2)
  } catch (e: any) {
    message.error(e.message)
  }
}

onMounted(() => {
  loadFiles()
})
</script>

<style scoped>
.shared-knowledge-view {
  max-width: 1000px;
}

.section-card {
  background: var(--ba-card);
  border: 1px solid var(--ba-border);
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
