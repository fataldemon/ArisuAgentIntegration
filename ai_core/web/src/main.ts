import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { routes } from './router'
import i18n from './locales'
import './styles/global.css'

const router = createRouter({
  history: createWebHistory('/admin/'),
  routes,
})

const app = createApp(App)
app.use(router)
app.use(i18n)
app.mount('#app')
