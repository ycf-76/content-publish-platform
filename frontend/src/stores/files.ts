import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as chatFilesApi from '@/api/chatFiles'

export interface FileItem {
  id: string
  name: string
  type: string
  size: number
  url: string
  folderId: string
  createdAt: number
  sessionId?: string
  contentText?: string | null
}

export interface FolderItem {
  id: string
  name: string
  path: string
  isExpanded: boolean
  createdAt: number
}

const CHAT_FOLDER_ID = 'chat-files'

export const useFileStore = defineStore('files', () => {
  const folders = ref<FolderItem[]>([])
  const files = ref<FileItem[]>([])
  const activeFileId = ref<string | null>(null)
  const activeFolderId = ref<string | null>(null)
  const loaded = ref(false)

  const activeFile = computed(() =>
    files.value.find(f => f.id === activeFileId.value) || null
  )

  const activeFolder = computed(() =>
    folders.value.find(f => f.id === activeFolderId.value) || null
  )

  function getFilesForFolder(folderId: string) {
    return files.value.filter(f => f.folderId === folderId)
  }

  function _ensureChatFolder() {
    // '对话文件' 仅作为文件存储的内部标识，不再作为侧边栏可见文件夹，
    // 避免与“从本地导入的文件夹”混淆（导航逻辑调整：不允许未归档对话）。
    return CHAT_FOLDER_ID
  }

  async function loadFromBackend() {
    if (loaded.value) return
    _ensureChatFolder()
    try {
      const backendFiles = await chatFilesApi.listFilesForUser()
      const chatFolderId = CHAT_FOLDER_ID
      for (const bf of backendFiles) {
        const exists = files.value.find(f => f.id === bf.id)
        if (!exists) {
          files.value.push({
            id: bf.id,
            name: bf.name,
            type: bf.file_type || 'application/octet-stream',
            size: bf.size || 0,
            url: bf.url || '',
            folderId: bf.folder_id || chatFolderId,
            createdAt: bf.created_at ? new Date(bf.created_at).getTime() : Date.now(),
            sessionId: bf.session_id,
            contentText: bf.content_text,
          })
        }
      }
      loaded.value = true
    } catch {
      loaded.value = true
    }
  }

  async function loadFilesForSession(sessionId: string) {
    try {
      const backendFiles = await chatFilesApi.listFilesForSession(sessionId)
      const chatFolderId = _ensureChatFolder()
      for (const bf of backendFiles) {
        const exists = files.value.find(f => f.id === bf.id)
        if (!exists) {
          files.value.push({
            id: bf.id,
            name: bf.name,
            type: bf.file_type || 'application/octet-stream',
            size: bf.size || 0,
            url: bf.url || '',
            folderId: bf.folder_id || chatFolderId,
            createdAt: bf.created_at ? new Date(bf.created_at).getTime() : Date.now(),
            sessionId: bf.session_id,
            contentText: bf.content_text,
          })
        }
      }
    } catch {
      // silent
    }
  }

  function addFolder(name: string, path: string = '') {
    const folder: FolderItem = {
      id: 'folder-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
      name,
      path,
      isExpanded: true,
      createdAt: Date.now(),
    }
    folders.value.unshift(folder)
    return folder
  }

  function removeFolder(folderId: string) {
    const idx = folders.value.findIndex(f => f.id === folderId)
    if (idx !== -1) folders.value.splice(idx, 1)
    files.value = files.value.filter(f => f.folderId !== folderId)
    if (activeFolderId.value === folderId) activeFolderId.value = null
  }

  function renameFolder(folderId: string, name: string) {
    const folder = folders.value.find(f => f.id === folderId)
    if (folder && name.trim()) {
      folder.name = name.trim()
    }
  }

  function toggleFolder(folderId: string) {
    const folder = folders.value.find(f => f.id === folderId)
    if (folder) folder.isExpanded = !folder.isExpanded
  }

  function setActiveFolder(folderId: string | null) {
    activeFolderId.value = folderId
  }

  function addFile(file: Omit<FileItem, 'id' | 'createdAt'>) {
    const item: FileItem = {
      ...file,
      type: file.type || 'application/octet-stream',
      size: file.size ?? 0,
      id: 'file-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
      createdAt: Date.now(),
    }
    files.value.push(item)
    return item
  }

  function addBackendFile(bf: chatFilesApi.ChatFileItem) {
    const chatFolderId = _ensureChatFolder()
    const exists = files.value.find(f => f.id === bf.id)
    if (exists) return exists
    const item: FileItem = {
      id: bf.id,
      name: bf.name,
      type: bf.file_type || 'application/octet-stream',
      size: bf.size || 0,
      url: bf.url || '',
      folderId: bf.folder_id || chatFolderId,
      createdAt: bf.created_at ? new Date(bf.created_at).getTime() : Date.now(),
      sessionId: bf.session_id,
      contentText: bf.content_text,
    }
    files.value.push(item)
    return item
  }

  function removeFile(fileId: string) {
    const idx = files.value.findIndex(f => f.id === fileId)
    if (idx !== -1) files.value.splice(idx, 1)
    if (activeFileId.value === fileId) activeFileId.value = null
    chatFilesApi.deleteFile(fileId).catch(() => {})
  }

  function setActiveFile(fileId: string | null) {
    activeFileId.value = fileId
  }

  function getFileSessionId(fileId: string): string | null {
    const f = files.value.find(f => f.id === fileId)
    return f?.sessionId || null
  }

  async function _uploadToBackend(file: File): Promise<string> {
    const formData = new FormData()
    formData.append('files', file)
    const token = localStorage.getItem('token')
    const res = await fetch('/api/assets', {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      body: formData,
    })
    if (!res.ok) throw new Error(`upload failed: ${res.status}`)
    const data = await res.json()
    const asset = data.data?.[0]
    return asset?.original_url || asset?.thumbnail_url || ''
  }

  function _readAsDataURL(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }

  function _readAsText(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = reject
      reader.readAsText(file)
    })
  }

  async function _resolveFileUrl(file: File): Promise<{ url: string; contentText?: string | null }> {
    const isImage = file.type.startsWith('image/')
    const isVideo = file.type.startsWith('video/')
    const isAudio = file.type.startsWith('audio/')
    const isMedia = isImage || isVideo || isAudio
    const isText = file.type.startsWith('text/') ||
      /\.(txt|md|json|csv|log|py|js|ts|vue|html|css|xml|yaml|yml|toml|ini|sh|bat)$/i.test(file.name)

    if (isMedia) {
      try {
        const persistentUrl = await _uploadToBackend(file)
        if (persistentUrl) return { url: persistentUrl }
      } catch (e) {
        console.warn('[files] 上传后端失败，回退到 data URL:', e)
      }
      try {
        const dataUrl = await _readAsDataURL(file)
        return { url: dataUrl }
      } catch {
        return { url: URL.createObjectURL(file) }
      }
    }

    if (isText) {
      try {
        const text = await _readAsText(file)
        const dataUrl = await _readAsDataURL(file)
        return { url: dataUrl, contentText: text }
      } catch {
        return { url: URL.createObjectURL(file) }
      }
    }

    try {
      const dataUrl = await _readAsDataURL(file)
      return { url: dataUrl }
    } catch {
      return { url: URL.createObjectURL(file) }
    }
  }

  async function importLocalFile(folderId: string) {
    return new Promise<FileItem | null>((resolve) => {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.txt,.md,.json,.csv,.pdf,.doc,.docx,.png,.jpg,.jpeg,.gif,.webp,.mp4,.mp3'
      input.onchange = async () => {
        const file = input.files?.[0]
        if (!file) { resolve(null); return }
        try {
          const { url, contentText } = await _resolveFileUrl(file)
          const item = addFile({
            name: file.name,
            type: file.type || 'application/octet-stream',
            size: file.size,
            url,
            folderId,
            contentText,
          })
          resolve(item)
        } catch (e) {
          console.error('[files] importLocalFile failed:', e)
          const url = URL.createObjectURL(file)
          const item = addFile({
            name: file.name,
            type: file.type || 'application/octet-stream',
            size: file.size,
            url,
            folderId,
          })
          resolve(item)
        }
      }
      input.click()
    })
  }

  async function importFolder() {
    return new Promise<FolderItem | null>((resolve) => {
      const input = document.createElement('input')
      input.type = 'file'
      ;(input as any).webkitdirectory = true
      input.onchange = async () => {
        const fileList = input.files
        if (!fileList || fileList.length === 0) {
          resolve(null)
          return
        }
        const firstPath = (fileList[0] as any).webkitRelativePath || ''
        const folderName = firstPath.split('/')[0] || '未命名文件夹'
        const folder = addFolder(folderName, folderName)

        const tasks: Promise<void>[] = []
        for (let i = 0; i < fileList.length; i++) {
          const file = fileList[i]
          tasks.push(
            _resolveFileUrl(file).then(({ url, contentText }) => {
              addFile({
                name: file.name,
                type: file.type || 'application/octet-stream',
                size: file.size,
                url,
                folderId: folder.id,
                contentText,
              })
            }).catch(() => {
              addFile({
                name: file.name,
                type: file.type || 'application/octet-stream',
                size: file.size,
                url: URL.createObjectURL(file),
                folderId: folder.id,
              })
            })
          )
        }
        await Promise.all(tasks)
        resolve(folder)
      }
      input.click()
    })
  }

  function formatFileSize(bytes?: number): string {
    if (bytes == null) return '0 B'
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  function getFileIcon(type?: string): string {
    if (!type) return 'file'
    if (type.startsWith('image/')) return 'image'
    if (type.startsWith('video/')) return 'video'
    if (type.startsWith('audio/')) return 'audio'
    if (type.includes('pdf')) return 'pdf'
    if (type.includes('json')) return 'code'
    if (type.includes('csv')) return 'table'
    return 'file'
  }

  return {
    folders,
    files,
    activeFileId,
    activeFolderId,
    activeFile,
    activeFolder,
    loaded,
    addFolder,
    removeFolder,
    renameFolder,
    toggleFolder,
    addFile,
    addBackendFile,
    removeFile,
    setActiveFile,
    setActiveFolder,
    getFilesForFolder,
    getFileSessionId,
    loadFromBackend,
    loadFilesForSession,
    importLocalFile,
    importFolder,
    formatFileSize,
    getFileIcon,
  }
})