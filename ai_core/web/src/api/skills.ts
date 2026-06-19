import { get, put, post, del } from './client'
import type { Skill } from '../types'

export const skillsApi = {
  list: () => get<{ skills: Skill[] }>('/skills'),
  readBody: (name: string) => get<{ name: string; body: string }>(`/skills/${name}`),
  readRaw: (name: string) => get<{ name: string; raw: string }>(`/skills/${name}/raw`),
  write: (name: string, body: string) => put(`/skills/${name}`, { body }),
  remove: (name: string) => del(`/skills/${name}`),
  create: (name: string, body?: string) => post('/skills', { name, body }),
  reload: () => post<{ ok: boolean; skills: Skill[] }>('/skills/reload'),
}
