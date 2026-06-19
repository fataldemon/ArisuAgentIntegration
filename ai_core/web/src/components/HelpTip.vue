<template>
  <n-tooltip trigger="hover" :style="{ maxWidth: '320px' }">
    <template #trigger>
      <span class="help-tip">?</span>
    </template>
    <slot />
  </n-tooltip>
</template>

<script setup lang="ts">
import { NTooltip } from 'naive-ui'
</script>

<style scoped>
.help-tip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #c0c8d4;
  color: #fff;
  font-size: 10px;
  font-weight: bold;
  cursor: help;
  margin-left: 4px;
  vertical-align: middle;
  line-height: 1;
  user-select: none;
}
.help-tip:hover {
  background: #4C8FEC;
}
</style>
