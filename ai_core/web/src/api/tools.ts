import { get, put, post, del } from './client'

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
  file_rules: { read: { allow: string[]; deny: string[] }; write: { allow: string[]; deny: string[] } }
}

export const toolsApi = {
  getCapabilities: () => get<CapabilitiesData>('/tools/capabilities'),
  setCapabilities: (states: Record<string, string>) => put('/tools/capabilities', { states }),
  addFileRule: (op: string, decision: string, directory: string) =>
    post('/tools/file-rules', { op, decision, directory }),
  removeFileRule: (op: string, decision: string, directory: string) =>
    del('/tools/file-rules', { op, decision, directory }),
  getRegistry: () => get<{ tools: any[] }>('/tools/registry'),
}

