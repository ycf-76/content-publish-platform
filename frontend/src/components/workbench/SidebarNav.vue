<template>
  <aside class="mint-sidebar">
    <div class="mint-sidebar-main">
      <div class="mint-logo-top" @click="goToHome" title="返回首页" style="cursor:pointer;">
        <transition name="logo-fade" mode="out-in">
          <img v-if="!isCollapsed" key="text" src="/icons/logo2.svg" alt="Pulse Studio" class="mint-logo-text" />
          <img v-else key="crab" src="/icons/logo2.svg" alt="Pulse Studio" class="mint-logo-crab" />
        </transition>
      </div>

      <div class="mint-sidebar-search" v-if="!isCollapsed">
        <Search :size="18" class="mint-sidebar-search-icon" />
        <input
          type="text"
          class="mint-sidebar-search-input"
          placeholder="搜索或新建对话..."
          v-model="searchQuery"
          @keydown.enter="onSearchEnter"
        />
      </div>

      <div class="mint-sidebar-tabs" v-if="!isCollapsed">
        <button
          class="mint-sidebar-tab"
          :class="{ 'mint-sidebar-tab-active': workStore.sidebarTab === 'chat' }"
          @click="switchToChatTab"
        >会话</button>
        <button
          class="mint-sidebar-tab"
          :class="{ 'mint-sidebar-tab-active': workStore.sidebarTab === 'content' }"
          @click="workStore.sidebarTab = 'content'"
        >内容</button>
      </div>

      <!-- ====== 会话 Tab ====== -->
      <nav class="mint-nav" v-show="workStore.sidebarTab === 'chat'" style="margin-top: 8px;">
        <div class="mint-nav-item" data-tooltip="首页" @click="goToHome" :class="{ 'mint-nav-active': isHomeActive }">
          <Home :size="18" />
          <span>首页</span>
        </div>
        <div class="mint-nav-item" id="nav-chat" data-page="chat" data-tooltip="开启新创作" @click="onNewTaskClick">
          <MessageSquarePlus :size="18" />
          <span>开启新创作</span>
        </div>
        <div class="mint-nav-item" data-tooltip="工作流" @click="onWorkflowNavClick" :class="{ 'mint-nav-active': currentPage === 'workflow' }">
          <GitBranch :size="18" />
          <span>工作流</span>
        </div>
        <div class="mint-nav-item" id="nav-topic-pool" data-page="topic-pool" data-tooltip="选题池" @click="goToTopicPool" :class="{ 'mint-nav-active': isTopicPoolActive }">
          <Lightbulb :size="18" />
          <span>选题池</span>
        </div>
        <div class="mint-nav-item" data-tooltip="数据分析" @click="goToMyWorks" :class="{ 'mint-nav-active': isMyWorksActive }">
          <BarChart3 :size="18" />
          <span>数据分析</span>
        </div>
        <div class="mint-nav-item" data-tooltip="任务清单" @click="goToTaskPlans" :class="{ 'mint-nav-active': isTaskPlansActive }">
          <ClipboardList :size="18" />
          <span>任务清单</span>
        </div>
        <div class="mint-nav-item" data-tooltip="作品集" @click="goToPortfolio" :class="{ 'mint-nav-active': isPortfolioActive }">
          <Briefcase :size="18" />
          <span>作品集</span>
        </div>

        <div class="mint-ws-toolbar" v-if="!isCollapsed">
          <span class="mint-ws-toolbar-label">对话</span>
          <div class="mint-ws-toolbar-actions">
            <button class="mint-ws-toolbar-action" @click="onNewTaskClick" title="新建对话">
              <MessageSquarePlus :size="16" :stroke-width="1.5" />
            </button>
          </div>
        </div>
        <div class="mint-conversations-content" v-if="!isCollapsed">
          <div
            v-for="(item, idx) in visibleChatItems"
            :key="item.id"
            class="mint-ws-thread"
            :class="{ 'mint-ws-thread-blurred': idx === 6 && !chatExpanded && filteredChatItems.length > 7 }"
            @click="onChatHistoryClick(item)"
            @contextmenu.prevent="onChatContextMenu($event, item.id)"
          >
            <MessageCircle :size="16" :stroke-width="1.5" />
            <span class="mint-ws-file-name">{{ item.title }}</span>
            <span class="mint-ws-thread-delete" @click.stop="onDeleteChat(item.id)">
              <Trash2 :size="16" :stroke-width="1.5" />
            </span>
          </div>
          <div v-if="filteredChatItems.length > 7 && !chatExpanded" class="mint-chat-show-more" @click="chatExpanded = true">
            <span>还有 {{ filteredChatItems.length - 7 }} 条对话</span>
          </div>
          <div v-if="filteredChatItems.length > 7 && chatExpanded" class="mint-chat-show-more" @click="chatExpanded = false">
            <ChevronUp :size="14" :stroke-width="1.5" />
            <span>收起</span>
          </div>
          <div v-if="filteredChatItems.length === 0" class="mint-conversations-empty">
            暂无对话
          </div>
        </div>

        <div class="mint-ws-toolbar" v-if="!isCollapsed">
          <span class="mint-ws-toolbar-label">工作区</span>
          <div class="mint-ws-toolbar-actions">
            <button class="mint-ws-toolbar-action" @click="onImportFolder" title="导入文件夹">
              <FolderOpen :size="16" :stroke-width="1.5" />
            </button>
          </div>
        </div>
        <div class="mint-ws-content" v-if="!isCollapsed">
          <div v-for="(folder, fIdx) in visibleFolders" :key="folder.id" class="mint-ws-folder" :class="{ 'mint-ws-folder-active': fileStore.activeFolderId === folder.id, 'mint-ws-thread-blurred': fIdx === 6 && !workspaceExpanded && fileStore.folders.length > 7 }">
            <div class="mint-ws-folder-header" @click="onFolderClick(folder.id)">
              <ChevronRight :size="16" :stroke-width="1.5" class="mint-ws-folder-chevron" :class="{ 'mint-ws-folder-chevron-open': folder.isExpanded }" />
              <Folder :size="16" :stroke-width="1.5" />
              <span class="mint-ws-folder-name">{{ folder.name }}</span>
              <span class="mint-ws-folder-action" @click.stop="onNewChatInFolder(folder.id)" title="新建对话">
                <MessageSquarePlus :size="16" :stroke-width="1.5" />
              </span>
              <span class="mint-ws-folder-delete" @click.stop="onDeleteFolder(folder.id)" title="删除文件夹">
                <Trash2 :size="16" :stroke-width="1.5" />
              </span>
            </div>
            <transition name="mint-subgroup" :css="false" @enter="onSubEnter" @leave="onSubLeave">
              <div class="mint-ws-folder-content" v-show="folder.isExpanded">
                <div
                  v-for="file in fileStore.getFilesForFolder(folder.id)"
                  :key="file.id"
                  class="mint-ws-file"
                  :class="{ 'mint-ws-file-active': fileStore.activeFileId === file.id }"
                  @click="onFileClick(file.id)"
                >
                  <component :is="fileIcon(file.type)" :size="16" :stroke-width="1.5" />
                  <span class="mint-ws-file-name">{{ file.name }}</span>
                </div>
                <div
                  v-for="conv in getConversationsForFolder(folder.id)"
                  :key="conv.id"
                  class="mint-ws-thread"
                  @click="onConversationClick(conv.id)"
                >
                  <MessageCircle :size="16" :stroke-width="1.5" />
                  <span class="mint-ws-file-name">{{ conv.title }}</span>
                  <span class="mint-ws-thread-delete" @click.stop="onDeleteConversation(conv.id)">
                    <Trash2 :size="16" :stroke-width="1.5" />
                  </span>
                </div>
                <div v-if="fileStore.getFilesForFolder(folder.id).length === 0 && getConversationsForFolder(folder.id).length === 0" class="mint-ws-folder-empty">
                  <span>空文件夹</span>
                </div>
              </div>
            </transition>
          </div>
          <div v-if="fileStore.folders.length > 7 && !workspaceExpanded" class="mint-chat-show-more" @click="workspaceExpanded = true">
            <span>还有 {{ fileStore.folders.length - 7 }} 个文件夹</span>
          </div>
          <div v-if="fileStore.folders.length > 7 && workspaceExpanded" class="mint-chat-show-more" @click="workspaceExpanded = false">
            <ChevronUp :size="14" :stroke-width="1.5" />
            <span>收起</span>
          </div>
        </div>
      </nav>

      <!-- ====== 内容 Tab ====== -->
      <div class="mint-creation-panel" v-show="workStore.sidebarTab === 'content' && !isCollapsed">
        <div class="mint-creation-toolbar">
          <div class="mint-creation-toolbar-actions">
            <button class="mint-creation-toolbar-btn" @click="$emit('refresh-works')" title="刷新">
              <RefreshCw :size="18" />
            </button>
          </div>
        </div>

        <div class="mint-creation-list">
          <!-- 已发布 -->
          <div class="mint-creation-group">
            <div class="mint-creation-group-header" @click="togglePublishedExpanded">
              <Radio :size="16" class="mint-creation-group-icon" />
              <span>已发布</span>
            </div>
            <div class="mint-creation-group-items mint-scrollable-list" :class="{ 'mint-scroll-fade': publishedWorks.length > 6 && listFadeState.published }" v-show="publishedExpanded" ref="publishedListRef" @scroll="onListScroll($event, 'published')">
              <div
                v-for="(work, idx) in publishedWorks"
                :key="work.id"
                class="mint-work-row"
                :class="{ 'mint-work-active': workStore.activeWorkId === work.id }"
                @click="onSelectWork(work.id)"
              >
                <div class="mint-work-thumb">
                  <img v-if="resolveCover(work)" :src="resolveCover(work)" class="mint-work-thumb-img" />
                  <div v-else-if="resolveFirstPageHtml(work)" class="mint-work-thumb-scaler">
                    <iframe :srcdoc="resolveFirstPageHtml(work)" class="mint-work-thumb-iframe" sandbox="allow-same-origin" />
                  </div>
                  <ImageIcon v-else :size="14" class="mint-work-thumb-fallback" />
                </div>
                <div class="mint-work-info">
                  <div class="mint-work-title">{{ work.title }}</div>
                  <div class="mint-work-meta">{{ work.platform ? workStore.getPlatformLabel(work.platform) + ' · ' : '' }}{{ formatRelativeTime(work.dataCollectedAt) }}</div>
                </div>
                <span class="mint-work-delete" @click.stop="onDeleteWork(work.id)"><Trash2 :size="12" /></span>
              </div>
              <div v-if="publishedWorks.length === 0" class="mint-ws-folder-empty"><span>暂无已发布作品</span></div>
            </div>
          </div>

          <!-- 未发布（按创作类型分类） -->
          <div class="mint-creation-group">
            <div class="mint-creation-group-header" @click="toggleDraftExpanded">
              <Scissors :size="18" class="mint-creation-group-icon" />
              <span>未发布</span>
            </div>
            <div class="mint-creation-group-items mint-scrollable-list" :class="{ 'mint-scroll-fade': draftWorks.length > 6 && listFadeState.draft }" v-show="draftExpanded" ref="draftListRef" @scroll="onListScroll($event, 'draft')">
              <template v-for="(group, typeKey) in draftWorksByType" :key="typeKey">
                <div class="mint-content-subgroup" v-if="group.length > 0">
                  <div class="mint-content-subgroup-header">
                    <component :is="getContentTypeIcon(typeKey)" :size="18" :stroke-width="1.5" />
                    <span>{{ getContentTypeLabel(typeKey) }}</span>
                    <span class="mint-creation-group-count">{{ group.length }}</span>
                  </div>
                  <div
                    v-for="(work, idx) in group"
                    :key="work.id"
                    class="mint-work-row"
                    :class="{ 'mint-work-active': workStore.activeWorkId === work.id }"
                    @click="onSelectWork(work.id)"
                  >
                    <div class="mint-work-thumb">
                      <img v-if="resolveCover(work)" :src="resolveCover(work)" class="mint-work-thumb-img" />
                      <div v-else-if="resolveFirstPageHtml(work)" class="mint-work-thumb-scaler">
                        <iframe :srcdoc="resolveFirstPageHtml(work)" class="mint-work-thumb-iframe" sandbox="allow-same-origin" />
                      </div>
                      <ImageIcon v-else :size="14" class="mint-work-thumb-fallback" />
                    </div>
                    <div class="mint-work-info">
                      <div class="mint-work-title">{{ work.title }}</div>
                      <div class="mint-work-meta">{{ formatRelativeTime(work.dataCollectedAt) }}</div>
                    </div>
                    <span class="mint-work-delete" @click.stop="onDeleteWork(work.id)"><Trash2 :size="12" /></span>
                  </div>
                </div>
              </template>
              <div v-if="draftWorks.length === 0" class="mint-ws-folder-empty"><span>暂无未发布作品</span></div>
            </div>
          </div>

          <!-- 已采集 -->
          <div class="mint-creation-group">
            <div class="mint-creation-group-header" @click="toggleCollectedExpanded">
              <BookOpen :size="18" class="mint-creation-group-icon" />
              <span>已采集</span>
              <button class="mint-creation-toolbar-btn" @click.stop="$emit('add-work')" title="采集链接">
                <Link :size="14" />
              </button>
            </div>
            <div class="mint-creation-group-items mint-scrollable-list" :class="{ 'mint-scroll-fade': collectedWorks.length > 6 && listFadeState.collected }" v-show="collectedExpanded" ref="collectedListRef" @scroll="onListScroll($event, 'collected')">
              <div
                v-for="(work, idx) in collectedWorks"
                :key="work.id"
                class="mint-work-row"
                :class="{ 'mint-work-active': workStore.activeWorkId === work.id }"
                @click="onSelectWork(work.id)"
              >
                <div class="mint-work-thumb">
                  <img v-if="resolveCover(work)" :src="resolveCover(work)" class="mint-work-thumb-img" />
                  <div v-else-if="resolveFirstPageHtml(work)" class="mint-work-thumb-scaler">
                    <iframe :srcdoc="resolveFirstPageHtml(work)" class="mint-work-thumb-iframe" sandbox="allow-same-origin" />
                  </div>
                  <ImageIcon v-else :size="14" class="mint-work-thumb-fallback" />
                </div>
                <div class="mint-work-info">
                  <div class="mint-work-title">{{ work.title }}</div>
                  <div class="mint-work-meta">{{ work.platform ? workStore.getPlatformLabel(work.platform) + ' · ' : '' }}{{ formatRelativeTime(work.dataCollectedAt) }}</div>
                </div>
                <span class="mint-work-delete" @click.stop="onDeleteWork(work.id)"><Trash2 :size="12" /></span>
              </div>
              <div v-if="collectedWorks.length === 0" class="mint-ws-folder-empty"><span>暂无采集数据</span></div>
            </div>
          </div>
        </div>

      </div>
    </div>

    <div class="mint-sidebar-bottom">
      <div class="mint-sidebar-actions">
        <div class="mint-nav-item" data-tooltip="设置" @click="onOpenSettings" style="border-radius: 0; padding: 8px 12px;">
          <Settings :size="18" />
          <span>设置</span>
        </div>
        <button class="mint-sidebar-toggle" id="sidebar-toggle" data-tooltip="收起侧边栏" aria-label="收起侧边栏" @click="$emit('toggle-sidebar')">
          <PanelLeftClose :size="18" />
        </button>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="mint-context-menu"
        :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
        @click.stop
      >
        <button class="mint-context-menu-item mint-context-delete" @click="onDeleteChat(contextMenu.convId)">
          <Trash2 :size="18" />
          <span>删除对话</span>
        </button>
      </div>
      <div v-if="contextMenu.visible" class="mint-context-overlay" @click="closeContextMenu" @contextmenu.prevent="closeContextMenu"></div>
    </Teleport>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  MessageSquarePlus,
  Home,
  GitBranch,
  Lightbulb,
  BarChart3,
  ClipboardList,
  Briefcase,
  Settings,
  PanelLeftClose,
  Search,
  MessageCircle,
  Trash2,
  FolderOpen,
  Folder,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
  RefreshCw,
  Link,
  Mic,
  Video,
  Scissors,
  BookOpen,
  Radio,
  FileText,
  Music,
  Code2,
  Table2,
} from 'lucide-vue-next'
import { useUIState } from '@/composables/useUIState'
import { useChatHistory } from '@/composables/useChatHistory'
import { useWorkStore } from '@/stores/work'
import { useFileStore } from '@/stores/files'

const props = defineProps<{
  currentPage: string
  isCollapsed?: boolean
}>()

const emit = defineEmits<{
  'nav-click': [page: string]
  'toggle-sidebar': []
  'go-eco': []
  'new-workflow': []
  'open-settings': []
  'new-chat': []
  'delete-chat': [id: string]
  'select-work': [workId: string]
  'add-work': []
  'create-draft': [contentType: string]
  'refresh-works': []
  'select-file': [fileId: string]
  'select-conversation': [convId: string]
  'new-chat-in-folder': [folderId: string]
  'select-folder': [folderId: string]
  'exit-creation': []
  'switch-creation-panel': [typeKey: string]
}>()

const router = useRouter()
const route = useRoute()
const workStore = useWorkStore()
const fileStore = useFileStore()

const { workflowExpanded, toggleWorkflowExpanded } = useUIState()
const { history: chatHistory, removeConversation: removeChatHistory, getConversationsForFolder: getFolderConversations } = useChatHistory()

const searchQuery = ref('')
const draftExpanded = ref(true)
const collectedExpanded = ref(true)
const publishedExpanded = ref(false)
const chatExpanded = ref(false)
const workspaceExpanded = ref(false)

const publishedListRef = ref<HTMLElement | null>(null)
const draftListRef = ref<HTMLElement | null>(null)
const collectedListRef = ref<HTMLElement | null>(null)
const listFadeState = ref<Record<string, number>>({ published: 1, draft: 1, collected: 1 })

function onListScroll(e: Event, key: string) {
  const el = e.target as HTMLElement
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8
  listFadeState.value[key] = atBottom ? 0 : 1
}

const isTopicPoolActive = computed(() => route.path === '/topic-pool' || route.path.startsWith('/topic-pool/'))
const isMyWorksActive = computed(() => route.path === '/my-works')
const isTaskPlansActive = computed(() => route.path === '/task-plans')
const isPortfolioActive = computed(() => route.path === '/portfolio' || route.path.startsWith('/portfolio/'))
const isHomeActive = computed(() => route.path === '/')

const filteredChatItems = computed(() => {
  if (!searchQuery.value.trim()) return chatHistory.value
  const q = searchQuery.value.trim().toLowerCase()
  return chatHistory.value.filter(item => item.title.toLowerCase().includes(q))
})

const visibleChatItems = computed(() => {
  if (chatExpanded.value || filteredChatItems.value.length <= 7) return filteredChatItems.value
  return filteredChatItems.value.slice(0, 7)
})

const visibleFolders = computed(() => {
  if (workspaceExpanded.value || fileStore.folders.length <= 7) return fileStore.folders
  return fileStore.folders.slice(0, 7)
})

const creationTypes: Array<{ key: typeof workStore.activeCreationType; label: string; icon: Component }> = [
  { key: 'image_text' as const, label: '图文', icon: ImageIcon },
  { key: 'voiceover' as const, label: '口播', icon: Mic },
  { key: 'short_video' as const, label: '短视频', icon: Video },
  { key: 'ai_edit' as const, label: 'AI剪辑', icon: Scissors },
  { key: 'long_article' as const, label: '长文', icon: BookOpen },
  { key: 'live_clip' as const, label: '直播切片', icon: Radio },
]

const activeTypeLabel = computed(() => {
  const ct = creationTypes.find(c => c.key === workStore.activeCreationType)
  return ct ? ct.label : '图文'
})

const draftWorks = computed(() => {
  const combined = [...workStore.worksByStatus.draft]
  const existingIds = new Set(combined.map(w => w.id))
  for (const w of workStore.outputWorks) {
    if (!existingIds.has(w.id)) {
      combined.push(w)
    }
  }
  return combined
})
const collectedWorks = computed(() => workStore.worksByStatus.collected)
const publishedWorks = computed(() => workStore.worksByStatus.published)

const draftWorksByType = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const w of draftWorks.value) {
    const key = w.contentType || 'image_text'
    if (!groups[key]) groups[key] = []
    groups[key].push(w)
  }
  return groups
})

function getContentTypeIcon(typeKey: string): Component {
  const map: Record<string, Component> = {
    image_text: ImageIcon,
    voiceover: Mic,
    short_video: Video,
    ai_edit: Scissors,
    long_article: BookOpen,
    live_clip: Radio,
  }
  return map[typeKey] || FileText
}

function getContentTypeLabel(typeKey: string): string {
  const map: Record<string, string> = {
    image_text: '图文',
    voiceover: '口播',
    short_video: '短视频',
    ai_edit: 'AI剪辑',
    long_article: '长文',
    live_clip: '直播切片',
  }
  return map[typeKey] || typeKey
}

function resolveCover(work: any): string {
  if (work.coverUrl) return work.coverUrl
  if (work.images?.length > 0) return work.images[0]
  if (work.cardDraft?.pages?.length > 0) {
    const withImage = work.cardDraft.pages.find((p: any) => p?.imageUrl)
    if (withImage?.imageUrl) return withImage.imageUrl
    const first = work.cardDraft.pages[0]
    if (first?.pngUrls?.length > 0) return first.pngUrls[0]
  }
  return ''
}

function resolveFirstPageHtml(work: any): string {
  if (work.firstPageHtml) return work.firstPageHtml
  const pages = work.cardDraft?.pages
  if (pages && pages.length > 0) {
    const first = pages[0]
    const html = first?.content?.htmlContent || first?.htmlContent || ''
    if (html) return html
  }
  console.warn('[SidebarNav] resolveFirstPageHtml: no html found for work', work.id, {
    firstPageHtml: work.firstPageHtml,
    hasCardDraft: !!work.cardDraft,
    pagesLength: work.cardDraft?.pages?.length,
    firstPageKeys: work.cardDraft?.pages?.[0] ? Object.keys(work.cardDraft.pages[0]) : [],
  })
  return ''
}

function goToEco() { emit('go-eco') }

function goToHome() {
  if (route.path === '/') return
  router.push('/').catch(() => {})
}

function switchToChatTab() {
  if (workStore.sidebarTab === 'content') {
    emit('exit-creation')
  }
  workStore.sidebarTab = 'chat'
}

function onNewTaskClick() {
  emit('nav-click', 'chat')
  emit('new-chat')
}

function onWorkflowNavClick() {
  emit('nav-click', 'workflow')
  emit('new-workflow')
}

function goToTopicPool() {
  if (route.path === '/topic-pool' || route.path.startsWith('/topic-pool/')) return
  router.push('/topic-pool').catch(() => {})
}
function goToMyWorks() {
  if (route.path === '/my-works') return
  router.push('/my-works').catch(() => {})
}
function goToTaskPlans() {
  if (route.path === '/task-plans') return
  router.push('/task-plans').catch(() => {})
}
function goToPortfolio() {
  if (route.path === '/portfolio') return
  router.push('/portfolio').catch(() => {})
}

function onOpenSettings() {
  window.dispatchEvent(new Event('open-settings'))
  emit('open-settings')
}

function onChatHistoryClick(item: { id: string }) {
  emit('nav-click', 'chat')
  emit('select-conversation', item.id)
}

function onSearchEnter() {
  if (searchQuery.value.trim()) {
    emit('new-chat')
    searchQuery.value = ''
  }
}

const _FILE_ICON_MAP: Record<string, Component> = {
  image: ImageIcon,
  video: Video,
  audio: Music,
  pdf: FileText,
  code: Code2,
  table: Table2,
  file: FileText,
}

function fileIcon(type?: string): Component {
  const key = fileStore.getFileIcon(type)
  return _FILE_ICON_MAP[key] || FileText
}

function onFolderClick(folderId: string) {
  fileStore.toggleFolder(folderId)
  emit('select-folder', folderId)
}

function onNewChatInFolder(folderId: string) { emit('new-chat-in-folder', folderId) }

function onFileClick(fileId: string) {
  fileStore.setActiveFile(fileId)
  emit('nav-click', 'chat')
  emit('select-file', fileId)
}

function onConversationClick(convId: string) {
  emit('nav-click', 'chat')
  emit('select-conversation', convId)
}

function onDeleteConversation(convId: string) {
  removeChatHistory(convId)
  emit('delete-chat', convId)
}

function onDeleteFolder(folderId: string) {
  fileStore.removeFolder(folderId)
}

function onCreationTypeClick(typeKey: string) {
  workStore.activeCreationType = typeKey as any
  emit('switch-creation-panel', typeKey)
}

function onSelectWork(workId: string) {
  workStore.setActiveWork(workId)
  emit('select-work', workId)
}

function onDeleteWork(workId: string) {
  workStore.deleteWork(workId)
}

async function onImportFolder() {
  const folder = await fileStore.importFolder()
  if (folder) {
    fileStore.setActiveFolder(folder.id)
    emit('select-folder', folder.id)
  }
}

function onNewFolderChat() {
  const folderId = fileStore.activeFolderId
  if (folderId) {
    emit('new-chat-in-folder', folderId)
  }
}

function getConversationsForFolder(folderId: string) {
  return getFolderConversations(folderId)
}

function toggleDraftExpanded() { draftExpanded.value = !draftExpanded.value }
function toggleCollectedExpanded() { collectedExpanded.value = !collectedExpanded.value }
function togglePublishedExpanded() { publishedExpanded.value = !publishedExpanded.value }

function formatRelativeTime(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = now - then
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  if (diff < 604800000) return Math.floor(diff / 86400000) + '天前'
  return new Date(dateStr).toLocaleDateString()
}

const contextMenu = ref<{ visible: boolean; x: number; y: number; convId: string }>({
  visible: false,
  x: 0,
  y: 0,
  convId: ''
})

function onChatContextMenu(e: MouseEvent, convId: string) {
  const x = Math.min(e.clientX, window.innerWidth - 140)
  const y = Math.min(e.clientY, window.innerHeight - 40)
  contextMenu.value = { visible: true, x, y, convId }
}

function closeContextMenu() { contextMenu.value.visible = false }

function onDeleteChat(convId: string) {
  removeChatHistory(convId)
  emit('delete-chat', convId)
  closeContextMenu()
}

function onSubEnter(el: Element, done: () => void) {
  const container = el as HTMLElement
  container.style.height = '0'
  container.style.overflow = 'hidden'
  container.style.transition = 'height 0.25s cubic-bezier(0.16, 1, 0.3, 1)'
  void container.offsetHeight
  container.style.height = container.scrollHeight + 'px'
  setTimeout(() => {
    container.style.height = ''
    container.style.overflow = ''
    container.style.transition = ''
    done()
  }, 260)
}

function onSubLeave(el: Element, done: () => void) {
  const container = el as HTMLElement
  container.style.height = container.offsetHeight + 'px'
  container.style.overflow = 'hidden'
  void container.offsetHeight
  container.style.transition = 'height 0.2s cubic-bezier(0.4, 0, 1, 1)'
  container.style.height = '0'
  setTimeout(() => {
    container.style.height = ''
    container.style.overflow = ''
    container.style.transition = ''
    done()
  }, 210)
}
</script>

<style>
.mint-sidebar svg {
  color: #1F2937 !important;
  stroke: #1F2937 !important;
}
.mint-sidebar-toggle svg {
  color: #666 !important;
  stroke: #666 !important;
}
.mint-sidebar-search {
  background: #E5E7EB !important;
  border-radius: 8px !important;
  padding: 8px 12px !important;
  margin: 4px 8px !important;
}
.mint-logo-top:hover {
  outline: none !important;
  border: none !important;
  box-shadow: none !important;
}
.mint-logo-top:focus,
.mint-logo-top:active {
  outline: none !important;
  border: none !important;
  box-shadow: none !important;
}
.mint-nav {
  gap: 2px !important;
}
.mint-nav > .mint-nav-item {
  padding-top: 7px !important;
  padding-bottom: 7px !important;
}
.mint-nav-item:hover {
  background: #E8E8E8 !important;
  color: #1F2937 !important;
}
.mint-nav-item:hover svg {
  color: #374151 !important;
}
.mint-nav-active {
  background: #E5E7EB !important;
  color: #1F2937 !important;
  font-weight: 700 !important;
  border-left: 3px solid #9CA3AF !important;
}
.mint-nav-active svg {
  color: #1F2937 !important;
}
.mint-content-subgroup {
  margin-bottom: 4px;
}
.mint-content-subgroup-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px 2px 20px;
  font-size: 11px;
  color: var(--mint-text-secondary, #888);
  font-weight: 500;
}
.mint-ws-thread-blurred {
  filter: blur(1.5px);
  opacity: 0.5;
  pointer-events: none;
  user-select: none;
}
.mint-chat-show-more {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--mint-text-secondary, #888);
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s ease, color 0.15s ease;
}
.mint-chat-show-more:hover {
  background: rgba(0, 0, 0, 0.04);
  color: #374151;
}
.mint-scrollable-list {
  max-height: 360px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.15) transparent;
  position: relative;
}
.mint-scrollable-list::-webkit-scrollbar {
  width: 5px;
}
.mint-scrollable-list::-webkit-scrollbar-track {
  background: transparent;
}
.mint-scrollable-list::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}
.mint-scrollable-list::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.25);
}
.mint-scroll-fade::after {
  content: '';
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  display: block;
  height: 48px;
  background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,1));
  pointer-events: none;
  margin-top: -48px;
  transition: opacity 0.2s ease;
}
</style>