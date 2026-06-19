import { get, put, post, del } from './client'
import type { Provider } from '../types'

export const providersApi = {
  list: () => get<{ active: string; providers: Provider[] }>('/providers'),
  detail: (name: string) => get<Provider>(`/providers/${name}`),
  upsert: (name: string, body: Partial<Provider>) => put(`/providers/${name}`, body),
  remove: (name: string) => del(`/providers/${name}`),
  activate: (name: string) => post(`/providers/${name}/activate`),
}
