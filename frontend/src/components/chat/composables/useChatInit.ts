import type { Ref } from 'vue'
import type { Conversation } from '../cell-types'
import * as chatSessionsApi from '@/api/chatSessions'
import { agentsApi } from '@/api/agents'
import { workflowApi } from '@/api/workflow'

export interface ChatInitDeps {
  conversations: Ref<Conversation[]>
  activeConvId: Ref<string>
  heroMode: Ref<boolean>
  chatHistoryLoaded: Ref<boolean>
  crabVisible: Ref<boolean>
  sse: any
  fileStore: any
  pluginStore: any
  workspaceStore: any
  pickers: any
  addConversation: (id: string, title: string, folderId: string, sessionId: string, workId?: string) => void
  mergeLoadedHistory: (conv: Conversation, msgs: any[]) => void
  startNotificationSSE: () => void
  onDocumentClick: (e: MouseEvent) => void
  CRAB_PLUGIN_ID: string
}

export function useChatInit(deps: ChatInitDeps) {
  const {
    conversations, activeConvId, heroMode, chatHistoryLoaded, crabVisible,
    sse, fileStore, pluginStore, workspaceStore, pickers,
    addConversation, mergeLoadedHistory, startNotificationSSE, onDocumentClick, CRAB_PLUGIN_ID,
  } = deps

  async function init() {
    try {
      const sessions = await chatSessionsApi.listSessions()
      await fileStore.loadFromBackend()

      if (sessions.length > 0) {
        for (const sess of sessions) {
          const exists = conversations.value.find(c => c.id === sess.id)
          if (!exists) {
            const conv: Conversation = {
              id: sess.id,
              title: sess.title || '新会话',
              messages: [],
              createdAt: sess.created_at ? new Date(sess.created_at).getTime() : Date.now(),
            }
            conversations.value.push(conv)
          }
          addConversation(sess.id, sess.title || '新会话', sess.folder_id || 'chat-files', sess.id, sess.work_id || undefined)
        }
        conversations.value.sort((a, b) => b.createdAt - a.createdAt)

        const latest = conversations.value[0]
        if (latest) {
          activeConvId.value = latest.id
          sse.activeSessionId.value = latest.id
          try {
            const msgs = await chatSessionsApi.listMessages(latest.id)
            mergeLoadedHistory(latest, msgs)
          } catch {
          }
        }
        heroMode.value = false
        chatHistoryLoaded.value = true
      } else {
        heroMode.value = true
        chatHistoryLoaded.value = true
      }
    } catch {
      heroMode.value = true
      chatHistoryLoaded.value = true
    }

    await pluginStore.loadInstalledPlugins().catch(() => {})

    const BUILTIN_PLUGIN_IDS = [
      CRAB_PLUGIN_ID,
      'cat-companion',
      'spongebob-companion',
    ]
    for (const id of BUILTIN_PLUGIN_IDS) {
      if (!pluginStore.isEnabled(id)) {
        pluginStore.enabledPlugins.value.add(id)
      }
    }

    workspaceStore.fetchWorkspaces().catch(() => {})
    crabVisible.value = true
    console.log('[ChatView] crabVisible=true, isEnabled(crab-companion)=', pluginStore.isEnabled(CRAB_PLUGIN_ID))

    agentsApi.list().then(list => {
      const agents = Array.isArray(list) ? list : (Array.isArray((list as any)?.data) ? (list as any).data : [])
      console.log('[ChatInit] agentsApi.list loaded:', agents.length, 'agents')
      pickers.availableAgents.value = agents
    }).catch(e => {
      console.error('[ChatInit] agentsApi.list failed:', e)
    })

    workflowApi.listSkills().then((map: Record<string, any[]>) => {
      const skillsMap = (map && typeof map === 'object' && !Array.isArray(map)) ? map : ((map as any)?.data && typeof (map as any).data === 'object' ? (map as any).data : {})
      const flat: { node_type: string; name: string; display_name: string; description: string }[] = []
      for (const [nodeType, skills] of Object.entries(skillsMap)) {
        for (const s of (skills || [])) {
          flat.push({ node_type: nodeType, name: s.name, display_name: s.display_name, description: s.description })
        }
      }
      console.log('[ChatInit] workflowApi.listSkills loaded:', flat.length, 'skills across', Object.keys(skillsMap).length, 'node types')
      pickers.allSkills.value = flat
    }).catch(e => {
      console.error('[ChatInit] workflowApi.listSkills failed:', e)
    })
    document.addEventListener('click', onDocumentClick)

    startNotificationSSE()
  }

  return { init }
}