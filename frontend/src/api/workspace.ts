import apiClient from './client'

export interface WorkspaceInfo {
  id: string
  name: string
  local_path: string
  bound_at?: string
  accessible?: boolean
}

export interface FileEntry {
  name: string
  path: string
  size?: number
  is_dir?: boolean
}

export async function pickFolder(): Promise<{ path: string; name: string } | null> {
  try {
    const res: any = await apiClient.post('/workspace/pick-folder', null, { timeout: 180000 })
    console.log('[workspace API] pickFolder raw response:', res)
    return res?.data ?? res ?? null
  } catch (e) {
    console.error('[workspace API] pickFolder error:', e)
    return null
  }
}

export async function bindWorkspace(localPath: string, name?: string): Promise<{ id: string; name: string; local_path: string; file_count: number }> {
  const res: any = await apiClient.post('/workspace/bind', { local_path: localPath, name })
  return res?.data ?? res
}

export async function listWorkspaces(): Promise<WorkspaceInfo[]> {
  const res: any = await apiClient.get('/workspace')
  return (res?.data ?? res)?.workspaces ?? []
}

export async function unbindWorkspace(workspaceId: string): Promise<void> {
  await apiClient.delete(`/workspace/${workspaceId}`)
}

export async function renameWorkspace(workspaceId: string, name: string): Promise<{ id: string; name: string; local_path: string }> {
  const res: any = await apiClient.patch(`/workspace/${workspaceId}`, { name })
  return res?.data ?? res
}

export async function listFiles(workspaceId: string, path = '', depth = 1): Promise<{ files: FileEntry[]; dirs: FileEntry[]; root: string }> {
  const res: any = await apiClient.get(`/workspace/${workspaceId}/list`, { params: { path, depth } })
  return res?.data ?? res
}

export async function readFile(workspaceId: string, path: string): Promise<{ path: string; content: string; size: number; binary?: boolean; content_base64?: string }> {
  const res: any = await apiClient.post(`/workspace/${workspaceId}/read`, { path })
  return res?.data ?? res
}

export async function writeFile(workspaceId: string, path: string, content: string): Promise<{ path: string; size: number }> {
  const res: any = await apiClient.post(`/workspace/${workspaceId}/write`, { path, content })
  return res?.data ?? res
}

export async function deleteFile(workspaceId: string, path: string): Promise<void> {
  await apiClient.delete(`/workspace/${workspaceId}/delete`, { params: { path } })
}

export async function searchFiles(workspaceId: string, pattern = '*', maxResults = 50): Promise<{ results: FileEntry[]; count: number }> {
  const res: any = await apiClient.post(`/workspace/${workspaceId}/search`, { pattern, max_results: maxResults })
  return res?.data ?? res
}