import { get, put } from './client'

export interface CapabilityInfo {
  key: string
  display: string
  domain: string
  description: string
  default_state: string
  state: string
  tools: string[]
}

export interface CapabilitiesData {
  domains: string[]
  capabilities: CapabilityInfo[]
  channels: Record<string, string[]>
}

export const toolsApi = {
  getCapabilities: () => get<CapabilitiesData>('/tools/capabilities'),
  setCapabilities: (states: Record<string, string>) => put('/tools/capabilities', { states }),
  setChannelCapabilities: (channel: string, capabilities: string[]) =>
    put(`/tools/channels/${channel}`, { capabilities }),
  getRegistry: () => get<{ tools: any[] }>('/tools/registry'),
}
