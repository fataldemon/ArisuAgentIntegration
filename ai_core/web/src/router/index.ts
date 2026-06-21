import type { RouteRecordRaw } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: '/chat' },
      { path: 'chat', name: 'Chat', component: () => import('../views/ChatView.vue') },
      { path: 'providers', name: 'Providers', component: () => import('../views/ProvidersView.vue') },
      { path: 'mcp', name: 'MCP', component: () => import('../views/McpServersView.vue') },
      { path: 'skills', name: 'Skills', component: () => import('../views/SkillsView.vue') },
      { path: 'characters', name: 'Characters', component: () => import('../views/CharactersView.vue') },
      { path: 'shared-knowledge', name: 'SharedKnowledge', component: () => import('../views/SharedKnowledgeView.vue') },
      { path: 'monitor', name: 'Monitor', component: () => import('../views/MonitorView.vue') },
      { path: 'globals', name: 'Globals', component: () => import('../views/GlobalsView.vue') },
      { path: 'channels', name: 'Channels', component: () => import('../views/ChannelsView.vue') },
    ],
  },
]
