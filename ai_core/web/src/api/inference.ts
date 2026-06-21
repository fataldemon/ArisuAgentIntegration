import { get, put } from './client'

export const inferenceApi = {
  get: () => get<Record<string, any>>('/inference'),
  save: (config: Record<string, any>) => put<Record<string, any>>('/inference', config),
}
