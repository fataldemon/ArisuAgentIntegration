import { get } from './client'
import type { MonitorEntry } from '../types'

export const monitorApi = {
  getLog: (page = -1, pageSize = 20) =>
    get<{
      entries: MonitorEntry[]
      total: number
      page: number
      page_size: number
      total_pages: number
    }>(`/monitor/log?page=${page}&page_size=${pageSize}`),
}
