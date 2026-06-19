<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo">S</div>
      <div class="sidebar-title">
        <div class="sidebar-title-main">{{ $t('sidebar.title') }}</div>
        <div class="sidebar-title-sub">{{ $t('sidebar.subtitle') }}</div>
      </div>
    </div>
    <nav class="sidebar-nav">
      <router-link
        v-for="item in menuItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: route.path === item.path }"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-label">{{ item.label }}</span>
      </router-link>
    </nav>
    <div class="sidebar-footer">
      <div class="lang-switch">
        <button
          :class="['lang-btn', { active: currentLocale === 'zh' }]"
          @click="switchLang('zh')"
        >{{ $t('sidebar.langZh') }}</button>
        <button
          :class="['lang-btn', { active: currentLocale === 'en' }]"
          @click="switchLang('en')"
        >{{ $t('sidebar.langEn') }}</button>
      </div>
      <div class="sidebar-version">{{ $t('sidebar.footer') }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setLocale, getLocale } from '../../locales'

const route = useRoute()
const { t } = useI18n()
const currentLocale = ref(getLocale())

const menuItems = computed(() => [
  { path: '/chat', icon: '\uD83D\uDCAC', label: t('sidebar.chat') },
  { path: '/providers', icon: '\u2699\uFE0F', label: t('sidebar.providers') },
  { path: '/mcp', icon: '\uD83D\uDD0C', label: t('sidebar.mcp') },
  { path: '/skills', icon: '\uD83D\uDCE6', label: t('sidebar.skills') },
  { path: '/characters', icon: '\uD83D\uDC64', label: t('sidebar.characters') },
  { path: '/shared-knowledge', icon: '\uD83D\uDCDA', label: t('sidebar.sharedKnowledge') },
  { path: '/monitor', icon: '\uD83D\uDCCA', label: t('sidebar.monitor') },
  { path: '/channels', icon: '\uD83D\uDCE1', label: t('sidebar.channels') },
])

function switchLang(lang: 'zh' | 'en') {
  setLocale(lang)
  currentLocale.value = lang
}
</script>

<style scoped>
.sidebar {
  width: 240px;
  min-width: 240px;
  height: 100vh;
  background: var(--ba-sidebar-bg);
  display: flex;
  flex-direction: column;
  color: #fff;
  user-select: none;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

.sidebar-logo {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: bold;
  backdrop-filter: blur(4px);
}

.sidebar-title-main {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 2px;
}

.sidebar-title-sub {
  font-size: 11px;
  opacity: 0.7;
  margin-top: 2px;
}

.sidebar-nav {
  flex: 1;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.8);
  text-decoration: none;
  font-size: 14px;
  transition: all 0.15s ease;
  position: relative;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}

.nav-item.active {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-weight: 600;
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 2px;
  background: #FFD700;
}

.nav-icon {
  font-size: 18px;
  width: 24px;
  text-align: center;
}

.nav-label {
  white-space: nowrap;
}

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
}

.lang-switch {
  display: flex;
  justify-content: center;
  gap: 4px;
  margin-bottom: 8px;
}

.lang-btn {
  padding: 3px 12px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 4px;
  background: transparent;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.lang-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.lang-btn.active {
  background: rgba(255, 255, 255, 0.2);
  color: #FFD700;
  border-color: #FFD700;
}

.sidebar-version {
  font-size: 11px;
  opacity: 0.5;
  text-align: center;
}
</style>
