import { authFetch } from './client'

export interface ChatFileItem {
  id: string
  session_id: string
  name: string
  file_type: string
  size: number
  url: string
  folder_id: string
  content_text: string | null
  meta: Record<string, any> | null
  created_at: string | null
}

export async function createFile(payload: {
  session_id: string
  name: string
  file_type?: string
  size?: number
  url?: string
  folder_id?: string
  content_text?: string | null
  meta?: Record<string, any> | null
}): Promise<ChatFileItem> {
  const res = await authFetch('/api/chat/files', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`createFile failed: ${res.status}`)
  const data = await res.json()
  return data.data
}

export async function listFilesForSession(sessionId: string): Promise<ChatFileItem[]> {
  const res = await authFetch(`/api/chat/files/session/${sessionId}`)
  if (!res.ok) return []
  const data = await res.json()
  return data.data || []
}

export async function listFilesForUser(): Promise<ChatFileItem[]> {
  const res = await authFetch('/api/chat/files/user')
  if (!res.ok) return []
  const data = await res.json()
  return data.data || []
}

export async function getFile(fileId: string): Promise<ChatFileItem | null> {
  const res = await authFetch(`/api/chat/files/${fileId}`)
  if (!res.ok) return null
  const data = await res.json()
  return data.data || null
}

export async function deleteFile(fileId: string): Promise<boolean> {
  const res = await authFetch(`/api/chat/files/${fileId}`, { method: 'DELETE' })
  if (!res.ok) return false
  const data = await res.json()
  return data.data === true
}