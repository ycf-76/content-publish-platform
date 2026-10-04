import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  pickFolder as apiPickFolder,
  bindWorkspace as apiBindWorkspace,
  listWorkspaces as apiListWorkspaces,
  unbindWorkspace as apiUnbindWorkspace,
  renameWorkspace as apiRenameWorkspace,
  listFiles as apiListFiles,
  readFile as apiReadFile,
  type WorkspaceInfo,
  type FileEntry,
} from '@/api/workspace'
import { useFileStore, type FolderItem } from '@/stores/files'

const WS_FOLDER_PREFIX = 'ws-'

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspaces = ref<WorkspaceInfo[]>([])
  const activeWorkspaceId = ref<string | null>(null)
  const files = ref<FileEntry[]>([])
  const dirs = ref<FileEntry[]>([])
  const loading = ref(false)
  const binding = ref(false)

  const activeWorkspace = computed(() =>
    workspaces.value.find((w) => w.id === activeWorkspaceId.value) ?? null
  )

  function _syncToFolderStore(wsId: string, name: string, localPath: string) {
    const fileStore = useFileStore()
    const folderId = WS_FOLDER_PREFIX + wsId
    const existing = fileStore.folders.find(f => f.id === folderId)
    if (!existing) {
      const folder = fileStore.addFolder(name, localPath)
      folder.id = folderId
    }
    fileStore.setActiveFolder(folderId)
  }

  function _removeFromFolderStore(wsId: string) {
    const fileStore = useFileStore()
    const folderId = WS_FOLDER_PREFIX + wsId
    const idx = fileStore.folders.findIndex(f => f.id === folderId)
    if (idx !== -1) {
      fileStore.folders.splice(idx, 1)
    }
    if (fileStore.activeFolderId === folderId) {
      fileStore.setActiveFolder(null)
    }
  }

  async function fetchWorkspaces() {
    loading.value = true
    try {
      workspaces.value = await apiListWorkspaces()
      for (const ws of workspaces.value) {
        const fileStore = useFileStore()
        const folderId = WS_FOLDER_PREFIX + ws.id
        if (!fileStore.folders.find(f => f.id === folderId)) {
          const folder = fileStore.addFolder(ws.name, ws.local_path)
          folder.id = folderId
        }
      }
    } catch {
      workspaces.value = []
    } finally {
      loading.value = false
    }
  }

  async function pickAndBind() {
    binding.value = true
    try {
      const picked = await apiPickFolder()
      console.log('[workspace] pickFolder result:', picked)
      if (!picked || !picked.path) return null

      const bound = await apiBindWorkspace(picked.path, picked.name)
      console.log('[workspace] bind result:', bound)
      await fetchWorkspaces()
      activeWorkspaceId.value = bound.id
      _syncToFolderStore(bound.id, picked.name || bound.name, picked.path || bound.local_path)
      return bound
    } catch (e) {
      console.error('[workspace] pickAndBind failed:', e)
      return null
    } finally {
      binding.value = false
    }
  }

  async function bindPath(localPath: string, name?: string) {
    binding.value = true
    try {
      const bound = await apiBindWorkspace(localPath, name)
      await fetchWorkspaces()
      activeWorkspaceId.value = bound.id
      _syncToFolderStore(bound.id, name || bound.name, localPath)
      return bound
    } catch {
      return null
    } finally {
      binding.value = false
    }
  }

  async function unbind(wsId: string) {
    await apiUnbindWorkspace(wsId)
    _removeFromFolderStore(wsId)
    if (activeWorkspaceId.value === wsId) {
      activeWorkspaceId.value = null
      files.value = []
      dirs.value = []
    }
    await fetchWorkspaces()
  }

  async function renameWorkspace(wsId: string, name: string) {
    const trimmed = name.trim()
    if (!trimmed) return
    const ws = workspaces.value.find(w => w.id === wsId)
    if (ws) ws.name = trimmed
    const folderId = WS_FOLDER_PREFIX + wsId
    const fileStore = useFileStore()
    const folder = fileStore.folders.find((f: FolderItem) => f.id === folderId)
    if (folder) folder.name = trimmed
    try {
      await apiRenameWorkspace(wsId, trimmed)
    } catch (e) {
      console.error('[workspace] renameWorkspace failed:', e)
    }
  }

  async function loadFiles(wsId?: string, path = '', depth = 1) {
    const id = wsId ?? activeWorkspaceId.value
    if (!id) return
    try {
      const result = await apiListFiles(id, path, depth)
      files.value = result.files
      dirs.value = result.dirs
    } catch {
      files.value = []
      dirs.value = []
    }
  }

  async function read(wsId: string, path: string) {
    return apiReadFile(wsId, path)
  }

  function setActive(wsId: string | null) {
    activeWorkspaceId.value = wsId
    if (wsId) loadFiles(wsId)
    else {
      files.value = []
      dirs.value = []
    }
  }

  return {
    workspaces,
    activeWorkspaceId,
    activeWorkspace,
    files,
    dirs,
    loading,
    binding,
    fetchWorkspaces,
    pickAndBind,
    bindPath,
    unbind,
    renameWorkspace,
    loadFiles,
    read,
    setActive,
  }
})