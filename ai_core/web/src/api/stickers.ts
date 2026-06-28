import { get, post, del } from './client'
import type { AxiosProgressEvent } from 'axios'

export interface Sticker {
  name: string
  url: string
}

export const stickersApi = {
  list: () => get<{ stickers: Sticker[] }>('/stickers'),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return fetch('/admin/api/stickers', { method: 'POST', body: form }).then(r => r.json())
  },
  remove: (name: string) => del(`/stickers/${name}`),
}
