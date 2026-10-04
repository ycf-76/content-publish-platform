import { authFetch } from './client'

export interface ChatSessionItem {
  id: string
  user_id: string
  work_id: string | null
  folder_id?: string | null
  title: string
  created_at: string | null
  updated_at: string | null
}

export interface ChatMessageItem {
  id: string
  session_id: string
  role: string
  content: string
  agent_meta: Record<string, any> | null
  created_at: string | null
}

export async function createSession(title: string = '新会话', workId?: string | null, folderId?: string | null): Promise<ChatSessionItem> {
  const res = await authFetch('/api/chat/sessions', {
    method: 'POST',
    body: JSON.stringify({ title, work_id: workId || null, folder_id: folderId || '' }),
  })
  if (!res.ok) throw new Error(`createSession failed: ${res.status}`)
  const data = await res.json()
  return data.data
}

export async function listSessions(workId?: string | null): Promise<ChatSessionItem[]> {
  const params = workId ? `?work_id=${encodeURIComponent(workId)}` : ''
  const res = await authFetch(`/api/chat/sessions${params}`)
  if (!res.ok) return []
  const data = await res.json()
  return data.data || []
}

export async function listMessages(sessionId: string): Promise<ChatMessageItem[]> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}/messages`)
  if (!res.ok) return []
  const data = await res.json()
  return data.data || []
}

export async function addMessage(
  sessionId: string,
  role: string,
  content: string,
  agentMeta?: Record<string, any> | null,
): Promise<ChatMessageItem> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ role, content, agent_meta: agentMeta || null }),
  })
  if (!res.ok) throw new Error(`addMessage failed: ${res.status}`)
  const data = await res.json()
  return data.data
}

export async function updateSession(sessionId: string, title?: string): Promise<ChatSessionItem> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
  if (!res.ok) throw new Error(`updateSession failed: ${res.status}`)
  const data = await res.json()
  return data.data
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`deleteSession failed: ${res.status}`)
}

export interface LLMCircuitStatus {
  state: 'closed' | 'open' | 'half_open'
  failure_count: number
  total_calls: number
  total_failures: number
  last_error: string
  open_reason: string
  recovery_timeout: number
}

export async function getLLMCircuitStatus(): Promise<LLMCircuitStatus> {
  const res = await authFetch('/api/v1/chat/llm-circuit/status')
  if (!res.ok) return { state: 'closed', failure_count: 0, total_calls: 0, total_failures: 0, last_error: '', open_reason: '', recovery_timeout: 0 }
  return await res.json()
}

export async function resetLLMCircuit(): Promise<{ success: boolean; message: string }> {
  const res = await authFetch('/api/v1/chat/llm-circuit/reset', { method: 'POST' })
  if (!res.ok) throw new Error(`resetLLMCircuit failed: ${res.status}`)
  return await res.json()
}

export async function probeLLMCircuit(): Promise<{ ok: boolean; recovered: boolean; state: string; detail: string }> {
  const res = await authFetch('/api/v1/chat/llm-circuit/probe', { method: 'POST' })
  if (!res.ok) return { ok: false, recovered: false, state: 'unknown', detail: `probe failed: ${res.status}` }
  return await res.json()
}