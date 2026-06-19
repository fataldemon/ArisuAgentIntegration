import { get, post } from './client'
import type { ChannelStatus } from '../types'

export const channelsApi = {
  list: () => get<{ channels: ChannelStatus[] }>('/channels'),
  start: (name: string) => post(`/channels/${name}/start`),
  stop: (name: string) => post(`/channels/${name}/stop`),
  restart: (name: string) => post(`/channels/${name}/restart`),
  logTail: (name: string, lines = 200) => get<{ name: string; log: string }>(`/channels/${name}/log?lines=${lines}`),
}
