import { get } from './client'
import type { MonitorEntry } from '../types'

export const monitorApi = {
  getLog: () => get<{ entries: MonitorEntry[] }>('/monitor/log'),
}
