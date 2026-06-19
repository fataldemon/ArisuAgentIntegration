import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { routes } from './router'
import './styles/global.css'

const router = createRouter({
  history: createWebHistory('/admin/'),
  routes,
})

const app = createApp(App)
app.use(router)
app.mount('#app')
