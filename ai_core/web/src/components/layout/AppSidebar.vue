<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo">S</div>
      <div class="sidebar-title">
        <div class="sidebar-title-main">SCHALE</div>
        <div class="sidebar-title-sub">Arisu Admin Panel</div>
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
      <div class="sidebar-version">QwenAIServiceCore</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const menuItems = [
  { path: '/chat', icon: '\uD83D\uDCAC', label: 'Chat' },
  { path: '/providers', icon: '\u2699\uFE0F', label: 'LLM Providers' },
  { path: '/mcp', icon: '\uD83D\uDD0C', label: 'MCP Servers' },
  { path: '/skills', icon: '\uD83D\uDCE6', label: 'Skills' },
  { path: '/characters', icon: '\uD83D\uDC64', label: 'Characters' },
  { path: '/shared-knowledge', icon: '\uD83D\uDCDA', label: 'Shared Knowledge' },
  { path: '/monitor', icon: '\uD83D\uDCCA', label: 'Request Monitor' },
  { path: '/channels', icon: '\uD83D\uDCE1', label: 'Channels' },
]
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

.sidebar-version {
  font-size: 11px;
  opacity: 0.5;
  text-align: center;
}
</style>
