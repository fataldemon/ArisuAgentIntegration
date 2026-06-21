import { get, put } from './client'

export const globalsApi = {
  getAll: () => get<{ endpoints: Record<string, any>; variables: Record<string, any> }>('/globals'),
  save: (variables: Record<string, any>) => put('/globals', { variables }),
  getFlat: () => get<{ variables: Record<string, string> }>('/globals/flat'),
}
