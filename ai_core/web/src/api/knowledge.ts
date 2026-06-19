import { get, put, post, del } from './client'

export const knowledgeApi = {
  listCharacters: () => get<{ characters: string[] }>('/kb/characters'),
  listFiles: (character: string, subject: string) =>
    get<{ files: string[] }>(`/kb/${character}/${subject}/files`),
  readFile: (character: string, subject: string, filename: string) =>
    get<{ filename: string; content: string }>(`/kb/${character}/${subject}/files/${filename}`),
  saveFile: (character: string, subject: string, filename: string, content: string) =>
    put(`/kb/${character}/${subject}/files/${filename}`, { content }),
  createFile: (character: string, subject: string, filename: string) =>
    post(`/kb/${character}/${subject}/files`, { filename }),
  deleteFile: (character: string, subject: string, filename: string) =>
    del(`/kb/${character}/${subject}/files/${filename}`),
  rebuild: (character: string, subject: string) =>
    post<{ ok: boolean; result: string }>(`/kb/${character}/${subject}/rebuild`),
  indexStatus: (character: string, subject: string) =>
    get<{ vectors: number; materials: number; index_file: string | null }>(`/kb/${character}/${subject}/index-status`),
}
