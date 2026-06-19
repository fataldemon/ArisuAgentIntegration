import { get, put, post, del } from './client'
import type { MCPServer } from '../types'

export const mcpApi = {
  list: () => get<{ tool_call_mode: string; tool_call_timeout: number; servers: MCPServer[] }>('/mcp/servers'),
  detail: (name: string) => get<MCPServer>(`/mcp/servers/${name}`),
  upsert: (name: string, body: Partial<MCPServer>) => put(`/mcp/servers/${name}`, body),
  remove: (name: string) => del(`/mcp/servers/${name}`),
  setMode: (mode: string) => post('/mcp/mode', { mode }),
  setMaxToolRounds: (rounds: number) => post('/mcp/max-tool-rounds', { rounds }),
  health: () => get<Record<string, { connected: boolean; tools: number }>>('/mcp/health'),
}
