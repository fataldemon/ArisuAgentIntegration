const BASE = '/admin/api'

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE}${path}`
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(url, { ...options, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const err = await res.json()
      detail = err.detail || JSON.stringify(err)
    } catch {}
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

export function get<T = any>(path: string): Promise<T> {
  return request<T>(path)
}

export function put<T = any>(path: string, body: any): Promise<T> {
  return request<T>(path, { method: 'PUT', body: JSON.stringify(body) })
}

export function post<T = any>(path: string, body?: any): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

export function del<T = any>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}
