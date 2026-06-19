import { ref, onMounted, onUnmounted } from 'vue'

export function usePolling(fn: () => Promise<void>, intervalMs: number = 3000) {
  const loading = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  const execute = async () => {
    loading.value = true
    try {
      await fn()
    } finally {
      loading.value = false
    }
  }

  const start = () => {
    if (timer) return
    timer = setInterval(execute, intervalMs)
  }

  const stop = () => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onMounted(() => {
    execute()
    start()
  })

  onUnmounted(() => {
    stop()
  })

  return { loading, execute, start, stop }
}
