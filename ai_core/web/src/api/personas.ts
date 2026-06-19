import { get, put, post, del } from './client'
import type { Persona, ExpressionConfig } from '../types'

export const personasApi = {
  list: () => get<{ personas: Persona[] }>('/personas'),
  detail: (character: string) => get<Persona>(`/personas/${character}`),
  upsert: (character: string, body: Partial<Persona>) => put(`/personas/${character}`, body),
  remove: (character: string) => del(`/personas/${character}`),
  preview: (character: string, userText: string) =>
    post<{ system_prompt: any; embeddings_text: string }>(`/personas/${character}/preview`, { user_text: userText }),
  getActiveCharacter: () => get<{ character: string }>('/characters/active'),
  activateCharacter: (character: string) => post('/characters/activate', { character }),
  getExpression: () => get<ExpressionConfig>('/expression'),
  setExpression: (format: string, instruction: string) => put('/expression', { format, instruction }),
}
