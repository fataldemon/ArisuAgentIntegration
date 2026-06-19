<template>
  <n-space vertical size="large">
    <n-card title="Skills Management">
      <template #header-extra>
        <n-space>
          <n-tag type="info">{{ skills.length }} skills loaded</n-tag>
          <n-button @click="handleReload" :loading="reloading">Reload from disk</n-button>
        </n-space>
      </template>

      <n-space vertical size="large">
        <n-space align="center">
          <span style="font-size: 14px">Skill name <HelpTip>skills/ 目录下的子文件夹名。每个 skill 是一个文件夹，内含 SKILL.md 文件</HelpTip></span>
          <n-input
            v-model:value="newSkillName"
            placeholder="New skill name"
            style="width: 240px"
          />
          <n-button type="primary" @click="handleCreate" :disabled="!newSkillName.trim()">
            Create new skill
          </n-button>
        </n-space>

        <n-data-table
          :columns="columns"
          :data="skills"
          :loading="loading"
          :row-props="rowProps"
          size="small"
          striped
        />
      </n-space>
    </n-card>

    <n-card v-if="selectedSkill" :title="`Editing: ${selectedSkill}`">
      <n-space vertical size="medium">
        <n-input
          v-model:value="editorContent"
          type="textarea"
          :autosize="false"
          :rows="20"
          placeholder="SKILL.md content (YAML front matter + markdown body)"
          style="font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', Consolas, monospace"
        />
        <n-space>
          <n-button type="primary" @click="handleSave" :loading="saving">
            Save / Update
          </n-button>
          <n-button type="error" @click="handleDelete" :loading="deleting">
            Delete
          </n-button>
        </n-space>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import {
  NSpace,
  NCard,
  NButton,
  NInput,
  NDataTable,
  NTag,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { skillsApi } from '../api/skills'
import HelpTip from '../components/HelpTip.vue'
import type { Skill } from '../types'

const message = useMessage()
const skills = ref<Skill[]>([])
const loading = ref(false)
const reloading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const selectedSkill = ref<string | null>(null)
const editorContent = ref('')
const newSkillName = ref('')

const columns: DataTableColumns<Skill> = [
  { title: 'Name', key: 'name', sorter: 'default' },
  { title: 'Version', key: 'version', width: 100 },
  {
    title: 'Auto Inject',
    key: 'auto_inject',
    width: 120,
    render(row) {
      return h(
        NTag,
        { type: row.auto_inject ? 'success' : 'default', size: 'small' },
        { default: () => (row.auto_inject ? 'Yes' : 'No') }
      )
    },
  },
  { title: 'Description', key: 'description', ellipsis: { tooltip: true } },
]

function rowProps(row: Skill) {
  return {
    style: 'cursor: pointer',
    onClick: () => loadSkill(row.name),
  }
}

async function fetchSkills() {
  loading.value = true
  try {
    const res = await skillsApi.list()
    skills.value = res.skills
  } catch (e: any) {
    message.error(e?.message || 'Failed to load skills')
  } finally {
    loading.value = false
  }
}

async function loadSkill(name: string) {
  try {
    const res = await skillsApi.readRaw(name)
    selectedSkill.value = res.name
    editorContent.value = res.raw
  } catch (e: any) {
    message.error(e?.message || 'Failed to load skill')
  }
}

async function handleSave() {
  if (!selectedSkill.value) return
  saving.value = true
  try {
    await skillsApi.write(selectedSkill.value, editorContent.value)
    message.success(`Skill "${selectedSkill.value}" saved`)
    await fetchSkills()
  } catch (e: any) {
    message.error(e?.message || 'Failed to save skill')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!selectedSkill.value) return
  deleting.value = true
  try {
    await skillsApi.remove(selectedSkill.value)
    message.success(`Skill "${selectedSkill.value}" deleted`)
    selectedSkill.value = null
    editorContent.value = ''
    await fetchSkills()
  } catch (e: any) {
    message.error(e?.message || 'Failed to delete skill')
  } finally {
    deleting.value = false
  }
}

async function handleCreate() {
  const name = newSkillName.value.trim()
  if (!name) return
  try {
    await skillsApi.create(name)
    message.success(`Skill "${name}" created`)
    newSkillName.value = ''
    await fetchSkills()
    await loadSkill(name)
  } catch (e: any) {
    message.error(e?.message || 'Failed to create skill')
  }
}

async function handleReload() {
  reloading.value = true
  try {
    const res = await skillsApi.reload()
    skills.value = res.skills
    message.success('Skills reloaded from disk')
  } catch (e: any) {
    message.error(e?.message || 'Failed to reload skills')
  } finally {
    reloading.value = false
  }
}

onMounted(fetchSkills)
</script>
