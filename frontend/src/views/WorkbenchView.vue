<template>
<div class="min-h-screen" style="position: relative;">

  <div class="mint-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'mint-right-collapsed': isRightPanelCollapsed || currentPage === 'chat', 'mint-shell-chat': currentPage === 'chat', 'is-left-resizing': isLeftResizing, 'settings-blur': showSettings }" :style="{ '--right-panel-width': rightPanelWidth + 'px', '--left-sidebar-width': leftSidebarWidth + 'px' }">

    <!-- ============ 左侧导航 ============ -->
    <SidebarNav
      :current-page="currentPage"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goToEco"
      @new-workflow="onNewWorkflow"
      @open-settings="openSettings"
      @new-chat="handleNewChat"
      @delete-chat="handleDeleteChat"
      @select-work="handleSelectWork"
      @add-work="handleAddWork"
      @create-draft="handleCreateDraft"
      @refresh-works="handleRefreshWorks"
      @select-file="handleSelectFile"
      @select-conversation="handleSelectConversation"
      @new-chat-in-folder="handleNewChatInFolder"
      @select-folder="handleSelectFolder"
      @exit-creation="handleExitCreation"
      @switch-creation-panel="handleSwitchCreationPanel"
    />

    <!-- left sidebar resize handle -->
    <div
      class="mint-left-resize-handle"
      v-show="!isSidebarCollapsed"
      :class="{ 'is-left-resizing': isLeftResizing }"
      title="拖拽调整侧边栏宽度 · 双击恢复默认"
      @mousedown="startLeftResize"
      @dblclick.prevent="resetLeftSidebarWidth"
    >
      <div class="mint-resize-line"></div>
    </div>

    <!-- ============ 中间主工作区 ============ -->
    <main class="wf-page" id="mint-main">

      <!-- ========== 工作流页面 ========== -->
      <div class="wf-content-card-wrapper" v-show="currentPage === 'workflow'">
        <div class="wf-content-card">

        <!-- 登录欢迎语 -->
        <WelcomeGreeting ref="welcomeGreetingRef" :nickname="authStore.user?.nickname" />

        <!-- 通知横幅 -->
        <div v-if="workflowStore.notifications.length > 0" class="wf-notifications">
          <div
            v-for="n in workflowStore.notifications"
            :key="n.id"
            class="wf-notification"
            :class="`wf-notification-${n.type}`"
          >
            <div class="wf-notification-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <div class="wf-notification-body">
              <div class="wf-notification-message">{{ n.message }}</div>
              <div v-if="n.suggestion" class="wf-notification-suggestion">{{ n.suggestion }}</div>
              <a v-if="n.action_url" :href="n.action_url" target="_blank" rel="noopener" class="wf-notification-action">
                {{ n.action_text || '前往处理' }}
              </a>
            </div>
            <button class="wf-notification-close" @click="workflowStore.dismissNotification(n.id)" title="关闭">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>

        <!-- ===== 两栏节点容器（前期 + 后期，各自保留时间线） ===== -->
        <div class="wf-columns-container" ref="nodesContainerRef" @scroll="onContainerScroll">

          <!-- ===== 左栏：前期（搜索 → 分析 → 写作 → 配图规划） ===== -->
          <div class="wf-column wf-column-early">
            <div class="wf-nodes-column">

              <!-- 阶段1：search 节点 -->
              <div class="wf-step" :class="wfStepClass('search')" data-node="search" data-width="normal" @click="onStepClick('search', $event)">
                <div class="wf-step-rail"><div class="wf-step-dot"></div></div>
                <div class="wf-step-content">
                  <SearchCard
                    :keyword="keyword"
                    :creative-brief="creativeBrief"
                    :search-platforms="searchPlatforms"
                    :selected-platform="selectedPlatform"
                    :search-status="searchStatus"
                    :search-results="searchResults"
                    :search-error="searchError"
                    :node-status="getNodeStatus('search')"
                    :node-meta="getNodeMeta('search')"
                    @update:keyword="keyword = $event"
                    @update:creative-brief="creativeBrief = $event"
                    @start-flow="startSearchFlow"
                    @cancel-and-restart="cancelAndRestart"
                    @select-platform="onSelectPlatform"
                    @start-from-result="startFromResult"
                    @search-similar="searchSimilar"
                    @enter-analyze="onEnterAnalyze"
                  />
                </div>
              </div>

              <!-- 阶段2：analyze 节点 -->
              <div class="wf-step" :class="wfStepClass('analyze')" data-node="analyze" data-width="normal" @click="onStepClick('analyze', $event)">
                <div class="wf-step-rail"><div class="wf-step-dot"></div></div>
                <div class="wf-step-content">
                  <AnalyzeCard
                    :node-status="getNodeStatus('analyze')"
                    :node-meta="getNodeMeta('analyze')"
                    :result="getNodeResult('analyze')"
                    :error-message="getNodeError('analyze')"
                    :streaming-text="getNodeStreamingText('analyze')"
                    @enter-copywrite="onEnterCopywrite"
                  />
                </div>
              </div>

              <!-- 阶段3：copywrite 节点 -->
              <div class="wf-step" :class="wfStepClass('copywrite')" data-node="copywrite" data-width="normal" @click="onStepClick('copywrite', $event)">
                <div class="wf-step-rail"><div class="wf-step-dot"></div></div>
                <div class="wf-step-content">
                  <CopywriteCard
                    :node-status="getNodeStatus('copywrite')"
                    :node-meta="getNodeMeta('copywrite')"
                    :result="getNodeResult('copywrite')"
                    :error-message="getNodeError('copywrite')"
                    :streaming-text="getNodeStreamingText('copywrite')"
                    :workflow-id="currentWorkflowId"
                    @continue-to-image="onContinueToImage"
                  />
                </div>
              </div>

              <!-- 阶段4：image_plan 节点 -->
              <div class="wf-step" :class="wfStepClass('image_plan')" data-node="image_plan" data-width="normal" @click="onStepClick('image_plan', $event)">
                <div class="wf-step-rail"><div class="wf-step-dot"></div></div>
                <div class="wf-step-content">
                  <ImagePlanCard
                    :node-status="getNodeStatus('image_plan')"
                    :node-meta="getNodeMeta('image_plan')"
                    :result="getNodeResult('image_plan')"
                    :error-message="getNodeError('image_plan')"
                  />
                </div>
              </div>

            </div>
          </div>

          <!-- ===== 右栏：后期（生图 → 审图 → 发布） ===== -->
          <div class="wf-column wf-column-late">
            <div class="wf-nodes-column">

              <!-- 阶段5：image_gen 节点 -->
              <div class="wf-step" :class="wfStepClass('image_gen')" data-node="image_gen" data-width="normal" @click="onStepClick('image_gen', $event)">
                <div class="wf-step-rail"><div class="wf-step-dot"></div></div>
                <div class="wf-step-content">
                  <ImageGenCard
                    :node-status="getNodeStatus('image_gen')"
                    :node-meta="getNodeMeta('image_gen')"
                    :result="getNodeResult('image_gen')"
                    :error-message="getNodeError('image_gen')"
                    :card-draft="imagePlanCardDraft"
                    :workflow-id="currentWorkflowId"
                    @open-workspace="openImageWorkspace"
                  />
                </div>
              </div>

              <!-- 阶段6：image_review 节点 -->
              <div class="wf-step" :class="wfStepClass('image_review')" data-node="image_review" data-width="normal" @click="onStepClick('image_review', $event)">
                <div class="wf-step-rail"><div class="wf-step-dot"></div></div>
                <div class="wf-step-content">
                  <ImageReviewCard
                    :node-status="getNodeStatus('image_review')"
                    :node-meta="getNodeMeta('image_review')"
                    :result="getNodeResult('image_review')"
                    :error-message="getNodeError('image_review')"
                    :workflow-id="currentWorkflowId"
                  />
                </div>
              </div>

              <!-- 阶段7：发布预览（含合规审核 + 终审 + 发布） -->
              <div class="wf-step" :class="wfStepClass('final_review')" data-node="final_review" data-width="normal" @click="onStepClick('final_review', $event)">
                <div class="wf-step-rail"><div class="wf-step-dot"></div></div>
                <div class="wf-step-content">
                  <FinalReviewCard
                    :audit-status="getNodeStatus('audit')"
                    :audit-meta="getNodeMeta('audit')"
                    :audit-result="getNodeResult('audit')"
                    :audit-error="getNodeError('audit')"
                    :final-review-status="getNodeStatus('final_review')"
                    :final-review-meta="getNodeMeta('final_review')"
                    :final-review-result="getNodeResult('final_review')"
                    :final-review-error="getNodeError('final_review')"
                    :publish-status="getNodeStatus('publish')"
                    :publish-meta="getNodeMeta('publish')"
                    :publish-result="getNodeResult('publish')"
                    :publish-error="getNodeError('publish')"
                    :copywrite-result="getNodeResult('copywrite')"
                    :image-gen-result="getNodeResult('image_gen')"
                    :workflow-id="currentWorkflowId"
                  />
                </div>
              </div>

            </div>
          </div>

        </div>
        </div>
      </div>

      <!-- ========== 其他页面 ========== -->
      <div class="page-container" id="page-history" v-show="currentPage === 'history'">
        <HistoryPage
          :visible="currentPage === 'history'"
          @new-workflow="onNewWorkflow"
          @open-workflow="onOpenWorkflow"
          @restart-workflow="onRestartWorkflow"
          @open-draft="onOpenDraft"
        />
      </div>

      <!-- AI conversation page (DSH-style chat window) -->
      <div class="page-container page-container-chat" id="page-chat" v-show="currentPage === 'chat'">
        <ChatView ref="chatViewRef" :model-settings="modelSettings" @open-image-workspace="onChatOpenImageWorkspace" @start-cover-workflow="onChatStartCoverWorkflow" />
      </div>

    </main>

    <!-- ============ 右侧面板 ============ -->
    <RightPanel v-if="currentPage !== 'chat'"
      :is-sidebar-collapsed="isSidebarCollapsed"
      :selected-platform="selectedPlatform"
      :initial-collapsed="isRightPanelCollapsed"
      @update:width="onRightPanelWidthUpdate"
      @update:is-collapsed="onRightPanelCollapsedUpdate"
      @update:model-settings="onModelSettingsUpdate"
    />

  </div>

  <ImageWorkspace
    v-if="showImageWorkspace && effectiveCardDraft"
    :card-draft="effectiveCardDraft"
    :workflow-id="currentWorkflowId"
    :auto-inject="autoInjectImageWorkspace"
    @close="onCloseImageWorkspace"
  />

  <SettingsView v-if="showSettings" @close="showSettings = false" />
  <AddWorkModal :visible="showAddWork" @close="showAddWork = false" />
</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch, defineAsyncComponent } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import RightPanel from '@/components/workbench/RightPanel.vue'
import WelcomeGreeting from '@/components/workbench/WelcomeGreeting.vue'

const ChatView = defineAsyncComponent(() => import('@/components/chat/ChatView.vue'))
const SettingsView = defineAsyncComponent(() => import('@/views/SettingsView.vue'))
const HistoryPage = defineAsyncComponent(() => import('@/components/workbench/HistoryPage.vue'))
const SearchCard = defineAsyncComponent(() => import('@/components/workbench/SearchCard.vue'))
const AnalyzeCard = defineAsyncComponent(() => import('@/components/workbench/AnalyzeCard.vue'))
const CopywriteCard = defineAsyncComponent(() => import('@/components/workbench/CopywriteCard.vue'))
const ImagePlanCard = defineAsyncComponent(() => import('@/components/workbench/ImagePlanCard.vue'))
const ImageGenCard = defineAsyncComponent(() => import('@/components/workbench/ImageGenCard.vue'))
const ImageWorkspace = defineAsyncComponent(() => import('@/components/workbench/ImageWorkspace.vue'))
const ImageReviewCard = defineAsyncComponent(() => import('@/components/workbench/ImageReviewCard.vue'))
const FinalReviewCard = defineAsyncComponent(() => import('@/components/workbench/FinalReviewCard.vue'))
const AddWorkModal = defineAsyncComponent(() => import('@/components/chat/AddWorkModal.vue'))
import { useAuthStore } from '@/stores/auth'
import { useAccountStore } from '@/stores/account'
import { useWorkflowStore } from '@/stores/workflow'
import { useWorkStore } from '@/stores/work'
import { useChatContextStore } from '@/stores/chatContext'
import { useFileStore } from '@/stores/files'
import { useSearchFlow } from '@/composables/useSearchFlow'
import { searchApi } from '@/api/search'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const accountStore = useAccountStore()
const workflowStore = useWorkflowStore()

const showImageWorkspace = ref(false)
const autoInjectImageWorkspace = ref(false)
const chatCardDraft = ref<any>(null)

const effectiveCardDraft = computed(() => {
  return chatCardDraft.value || imagePlanCardDraft.value
})

function onCloseImageWorkspace() {
  showImageWorkspace.value = false
  autoInjectImageWorkspace.value = false
  chatCardDraft.value = null
}

// ===== 页面切换 =====
const initialPage = (route.query.page as string) || 'chat'
const currentPage = ref<string>(initialPage)

watch(() => route.query.page, (newPage) => {
  if (newPage && typeof newPage === 'string') {
    currentPage.value = newPage
  }
})
const showSettings = ref(false)
const showAddWork = ref(false)
const chatViewRef = ref<any>(null)
const workStore = useWorkStore()
const fileStore = useFileStore()

function handleNewChat() {
  currentPage.value = 'chat'
  nextTick(() => {
    if (chatViewRef.value) {
      chatViewRef.value.newConversation()
    } else {
      setTimeout(() => { chatViewRef.value?.newConversation() }, 300)
    }
  })
}

function handleDeleteChat(convId: string) {
  if (chatViewRef.value) {
    chatViewRef.value.deleteConversation(convId)
  } else {
    setTimeout(() => { chatViewRef.value?.deleteConversation(convId) }, 300)
  }
}
function handleSelectWork(workId: string) {
  workStore.setActiveWork(workId)
  currentPage.value = 'chat'
  const doLink = async () => {
    const ctxStore = useChatContextStore()
    await ctxStore.linkWork(workId)
    if (!ctxStore.sidebarVisible) {
      ctxStore.setSidebarVisible(true)
    }
  }
  nextTick(() => {
    if (chatViewRef.value) {
      chatViewRef.value.showWorkDetail = true
      doLink()
    } else {
      setTimeout(() => {
        if (chatViewRef.value) {
          chatViewRef.value.showWorkDetail = true
          doLink()
        } else {
          setTimeout(() => {
            if (chatViewRef.value) {
              chatViewRef.value.showWorkDetail = true
            }
            doLink()
          }, 500)
        }
      }, 300)
    }
  })
}
function handleAddWork() {
  showAddWork.value = true
}
function handleCreateDraft(contentType: string) {
  workStore.createDraft(contentType)
  currentPage.value = 'chat'
  nextTick(() => {
    if (chatViewRef.value) {
      chatViewRef.value.showWorkDetail = true
      useChatContextStore().setSidebarVisible(true)
    } else {
      setTimeout(() => {
        if (chatViewRef.value) {
          chatViewRef.value.showWorkDetail = true
          useChatContextStore().setSidebarVisible(true)
        }
      }, 300)
    }
  })
}
async function handleRefreshWorks() {
  await Promise.all([workStore.fetchWorks(), workStore.fetchOutputWorks()])
}
function handleSelectFile(fileId: string) {
  currentPage.value = 'chat'
  fileStore.setActiveFile(fileId)
  const sessionId = fileStore.getFileSessionId(fileId)
  nextTick(() => {
    if (chatViewRef.value) {
      if (sessionId) {
        chatViewRef.value.switchToConversation(sessionId)
      } else {
        const file = fileStore.activeFile
        if (file) {
          chatViewRef.value.newConversation(file.folderId)
        }
      }
    }
  })
}
function handleSelectConversation(convId: string) {
  currentPage.value = 'chat'
  nextTick(() => {
    if (chatViewRef.value) {
      chatViewRef.value.switchToConversation(convId)
    } else {
      setTimeout(() => {
        chatViewRef.value?.switchToConversation(convId)
      }, 300)
    }
  })
}
function handleNewChatInFolder(folderId: string) {
  currentPage.value = 'chat'
  nextTick(() => {
    if (chatViewRef.value) {
      chatViewRef.value.newConversation(folderId)
    } else {
      setTimeout(() => { chatViewRef.value?.newConversation(folderId) }, 300)
    }
  })
}
function handleSelectFolder(folderId: string) {
  currentPage.value = 'chat'
  nextTick(() => {
    if (chatViewRef.value) {
      chatViewRef.value.switchToFolder(folderId)
    } else {
      setTimeout(() => { chatViewRef.value?.switchToFolder(folderId) }, 300)
    }
  })
}
function handleExitCreation() {
  workStore.setActiveWork(null)
  fileStore.setActiveFile(null)
  if (chatViewRef.value) {
    chatViewRef.value.resetToInitial()
  } else {
    setTimeout(() => { chatViewRef.value?.resetToInitial() }, 300)
  }
}

function handleSwitchCreationPanel(typeKey: string) {
  workStore.activeCreationType = typeKey as any

  const existingDraft = workStore.works.find(
    (w: any) => w.isDraft && w.contentType === typeKey
  )
  if (existingDraft) {
    workStore.setActiveWork(existingDraft.id)
  } else {
    workStore.createDraft(typeKey)
  }

  currentPage.value = 'chat'
  nextTick(() => {
    if (chatViewRef.value) {
      chatViewRef.value.showWorkDetail = true
    } else {
      setTimeout(() => {
        if (chatViewRef.value) chatViewRef.value.showWorkDetail = true
      }, 300)
    }
  })
}

function handleNavClick(page: string) {
  if (page === 'topic-pool' || page === 'my-works' || page === 'task-plans' || page === 'portfolio') {
    router.push(`/${page}`).catch(() => {})
    return
  }
  currentPage.value = page
}
function goToEco() {
  router.push('/eco')
}
function openSettings() {
  showSettings.value = true
}

// ===== 工作流历史页面事件 =====
function onNewWorkflow() {
  currentPage.value = 'workflow'
  nextTick(() => {
    const searchInput = document.querySelector('.wf-search-input') as HTMLInputElement | null
    searchInput?.focus()
  })
}

/** 搜索完成后，用户点击"进入分析"，resume 工作流让 analyze 开始执行 */
async function onEnterAnalyze() {
  try {
    await workflowStore.resumeWorkflow()
    scrollToNode('analyze')
  } catch (e: any) {
    console.error('[WorkbenchView] resumeWorkflow (enter-analyze) failed:', e)
  }
}

/** 创作点：analyze 完成后，用户选方向，resume 工作流让 copywrite 开始执行 */
async function onEnterCopywrite() {
  try {
    await workflowStore.resumeWorkflow()
  } catch (e: any) {
    console.error('[WorkbenchView] resumeWorkflow (enter-copywrite) failed:', e)
  }
}

/** 创作点：copywrite 完成后，用户确认文案，resume 工作流让 image_plan 开始执行 */
async function onContinueToImage() {
  try {
    await workflowStore.resumeWorkflow()
  } catch (e: any) {
    console.error('[WorkbenchView] resumeWorkflow (continue-to-image) failed:', e)
  }
}

async function onOpenWorkflow(workflowId: string) {
  const ok = await workflowStore.switchToWorkflow(workflowId)
  if (!ok) {
    workflowStore.pushNotification({
      type: 'workflow_error',
      message: '工作流打开失败，请稍后重试',
    })
    return
  }

  showImageWorkspace.value = false
  currentPage.value = 'workflow'
  try {
    if (route.params.workflowId !== workflowId || route.query.page !== 'workflow') {
      await router.replace({ path: `/workbench/${workflowId}`, query: { page: 'workflow' } })
    }
  } catch (e) {
    console.error('[WorkbenchView] sync workflow route failed:', e)
  }
}

 async function onOpenDraft(workflowId: string) {
  const ok = await workflowStore.switchToWorkflow(workflowId)
  if (!ok) {
    workflowStore.pushNotification({
      type: 'workflow_error',
      message: '工作流打开失败，请稍后重试',
    })
    return
  }

  currentPage.value = 'workflow'
  try {
    if (route.params.workflowId !== workflowId || route.query.page !== 'workflow') {
      await router.replace({ path: `/workbench/${workflowId}`, query: { page: 'workflow' } })
    }
  } catch (e) {
    console.error('[WorkbenchView] sync workflow route failed:', e)
  }

  await nextTick()
  await new Promise(resolve => setTimeout(resolve, 300))

  const draft = imagePlanCardDraft.value
  if (draft && Array.isArray(draft.pages) && draft.pages.length > 0) {
    showImageWorkspace.value = true
  } else {
    workflowStore.pushNotification({
      type: 'workflow_info',
      message: '草稿数据加载中，请稍后点击"在图片工作区编辑"',
    })
  }
}

function openImageWorkspace() {
  const draft = imagePlanCardDraft.value
  if (!draft || !Array.isArray(draft.pages) || draft.pages.length === 0) {
    workflowStore.pushNotification({
      type: 'workflow_error',
      message: '图片草稿尚未生成，请等待图片规划完成后再编辑',
    })
    return
  }
  showImageWorkspace.value = true
}

function onChatOpenImageWorkspace(draft?: any) {
  if (draft && draft.pages && Array.isArray(draft.pages) && draft.pages.length > 0) {
    chatCardDraft.value = draft
    if (!showImageWorkspace.value) {
      showImageWorkspace.value = true
    }
    return
  }
  if (showImageWorkspace.value) return
  const existingDraft = imagePlanCardDraft.value
  if (existingDraft && Array.isArray(existingDraft.pages) && existingDraft.pages.length > 0) {
    showImageWorkspace.value = true
  } else {
    workflowStore.pushNotification({
      type: 'workflow_info',
      message: '正在准备封面草稿，请稍候...',
    })
  }
}

async function onChatStartCoverWorkflow(topic: string) {
  currentPage.value = 'workflow'
  keyword.value = topic
  await nextTick()
  startSearchFlow()
}

function onRestartWorkflow(wf: any) {
  if (workflowStore.isStreaming) {
    if (!confirm('当前有工作流正在执行，是否取消并以此主题发起新工作流？')) return
    cancelAndRestart()
  }
  keyword.value = wf.topic || ''
  currentPage.value = 'workflow'
}

// ===== 侧边栏折叠（使用全局 UI 状态） =====
import { useUIState } from '@/composables/useUIState'
const {
  isSidebarCollapsed,
  toggleSidebar
} = useUIState()


// ===== left sidebar resize =====
import { useResizeHandle } from '@/composables/useResizeHandle'
const {
  width: leftSidebarWidth,
  isResizing: isLeftResizing,
  startResize: startLeftResize,
  resetWidth: resetLeftSidebarWidth,
} = useResizeHandle({
  direction: 'left',
  minWidth: 170,
  maxWidth: 520,
  storageKey: 'mint-left-sidebar-width-v2',
})
// ===== 右侧面板 =====
const isRightPanelCollapsed = ref(false)
function calcDefaultRightWidth() {
  return Math.max(200, Math.min(560, Math.floor(window.innerWidth / 3)))
}
const rightPanelWidth = ref(Number(localStorage.getItem('mint-right-panel-width-v2')) || calcDefaultRightWidth())
function onRightPanelWidthUpdate(w: number) {
  rightPanelWidth.value = w
  localStorage.setItem('mint-right-panel-width-v2', String(w))
}
function onRightPanelCollapsedUpdate(c: boolean) { isRightPanelCollapsed.value = c }

// ===== 模型设置 =====
const modelSettings = ref<Record<string, any>>({})
function onModelSettingsUpdate(s: Record<string, any>) { modelSettings.value = s }

// ===== search 节点状态 =====
const keyword = ref('')
const creativeBrief = ref('')
const selectedPlatform = ref('')
const searchPlatforms = ref<{ name: string; label: string; desc?: string; locked?: boolean; requires_auth?: boolean; auth_met?: boolean }[]>([])
const pendingReference = ref<Record<string, any> | null>(null)

const {
  searchStatus,
  searchResults,
  searchError,
  startSearchFlow,
  cancelAndRestart,
} = useSearchFlow(
  keyword,
  selectedPlatform,
  searchPlatforms,
  modelSettings,
  pendingReference,
  creativeBrief,
)

function onSelectPlatform(name: string) {
  const platform = searchPlatforms.value.find(p => p.name === name)
  if (platform?.locked) return
  selectedPlatform.value = name
}

// ===== 从搜索结果/推荐热点发起分析或搜索同款 =====
function startFromResult(note: any) {
  if (workflowStore.isStreaming) {
    if (!confirm('当前有工作流正在执行，是否取消并以此内容为参考发起新分析？')) return
    cancelAndRestart()
  }
  pendingReference.value = {
    title: note.title,
    summary: note.summary,
    url: note.url,
    platform: note.platform,
    author: note.author,
    likes: note.likes,
    source_keyword: note.title,
  }
  keyword.value = note.title || note.summary || ''
  nextTick(async () => {
    await startSearchFlow()
    scrollToNode('analyze')
  })
}

function startFromTopic(item: any) {
  if (workflowStore.isStreaming) {
    if (!confirm('当前有工作流正在执行，是否取消并以此内容为参考发起新分析？')) return
    cancelAndRestart()
  }
  pendingReference.value = {
    title: item.title,
    summary: item.summary,
    url: item.url,
    platform: item.platform,
    author: item.author,
    likes: item.likes,
    comments: item.comments,
    collects: item.collects,
    shares: item.shares,
    source_keyword: item.source_keyword || item.title,
  }
  keyword.value = item.source_keyword || item.title || ''
  nextTick(() => startSearchFlow())
}

function searchSimilar(kw: string) {
  if (!kw) return
  if (workflowStore.isStreaming) {
    if (!confirm('当前有工作流正在执行，是否取消并搜索同款内容？')) return
    cancelAndRestart()
  }
  pendingReference.value = null
  keyword.value = kw
  nextTick(() => startSearchFlow())
}

// ===== 节点容器 ref（用于滚动定位） =====
const nodesContainerRef = ref<HTMLElement | null>(null)

// 用户手动滚动后，停止自动跟随节点（不锁定位置、不强制恢复）
const _userScrolled = ref(false)
const _scrolledNodes = new Set<string>()
// 程序滚动的误判防护：scroll 事件异步派发，boolean 标志在 nextTick 复位太早，
// 改用时间戳——程序滚动后 250ms 内的 scroll 事件不算用户滚动
let _lastProgrammaticScrollAt = 0

function scrollToNode(nodeId: string) {
  if (_userScrolled.value) return
  _lastProgrammaticScrollAt = Date.now()
  nextTick(() => {
    const el = document.getElementById(`card-${nodeId}`)
    const container = nodesContainerRef.value
    if (el && container) {
      const elRect = el.getBoundingClientRect()
      const containerRect = container.getBoundingClientRect()
      const target = container.scrollTop + (elRect.top - containerRect.top) - 24
      container.scrollTo({ top: Math.max(0, target), behavior: 'instant' })
    }
  })
}

// 监听用户手动滚动：仅停止自动跟随，绝不锁定/恢复位置
// （强制恢复会与流式输出的 DOM 增长互相打架，表现为滚动被弹回）
function onContainerScroll() {
  if (Date.now() - _lastProgrammaticScrollAt > 250) {
    _userScrolled.value = true
  }
}

// 新工作流开始时恢复自动跟随
watch(() => workflowStore.currentWorkflow?.status, (s, old) => {
  if (s === 'running' && old !== 'running') {
    _userScrolled.value = false
    _scrolledNodes.clear()
  }
  if (!s || s === 'idle') {
    _userScrolled.value = false
    _scrolledNodes.clear()
  }
})
watch(() => getNodeStatus('copywrite'), (s) => { if (s === 'running' && !_scrolledNodes.has('copywrite')) { _scrolledNodes.add('copywrite'); scrollToNode('copywrite') } })
watch(() => getNodeStatus('image_plan'), (s) => { if (s === 'running' && !_scrolledNodes.has('image_plan')) { _scrolledNodes.add('image_plan'); scrollToNode('image_plan') } })
watch(() => getNodeStatus('image_gen'), (s) => { if (s === 'running' && !_scrolledNodes.has('image_gen')) { _scrolledNodes.add('image_gen'); scrollToNode('image_gen') } })
watch(() => getNodeStatus('image_review'), (s) => { if (s === 'running' && !_scrolledNodes.has('image_review')) { _scrolledNodes.add('image_review'); scrollToNode('image_review') } })
watch(() => getNodeStatus('audit'), (s) => { if (s === 'running' && !_scrolledNodes.has('final_review')) { _scrolledNodes.add('final_review'); scrollToNode('final_review') } })
watch(() => getNodeStatus('final_review'), (s) => { if (s === 'running' && !_scrolledNodes.has('final_review')) { _scrolledNodes.add('final_review'); scrollToNode('final_review') } })
watch(() => getNodeStatus('publish'), (s) => { if (s === 'running' && !_scrolledNodes.has('final_review')) { _scrolledNodes.add('final_review'); scrollToNode('final_review') } })

// ===== 主题/卡片透明（已使用全局 useUIState） =====

// ===== 欢迎语 =====
const welcomeGreetingRef = ref<InstanceType<typeof WelcomeGreeting> | null>(null)

// ===== 节点状态查询工具函数（所有节点卡片共用） =====
function getNode(nodeId: string) {
  return workflowStore.nodes.find(n => n.node_id === nodeId)
}
function getNodeStatus(nodeId: string): string {
  return getNode(nodeId)?.status || 'idle'
}
function getNodeResult(nodeId: string): any {
  const node = getNode(nodeId) as any
  if (nodeId === 'analyze' && node) {
  }
  if (!node) return null
  // 合并 output 字段和平铺字段。
  // 后端 node_completed 事件把 output dict 平铺到 payload 顶层（results/patterns/insights/layer1_stats/_model_used 等），
  // 而 getNodes / workflow_snapshot 接口可能返回嵌套的 output 字段。
  // 两者都可能出现，合并后返回最完整的数据，平铺字段优先（事件是最新的）。
  const out: Record<string, any> = { ...(node.output || {}) }
  const flatKeys = [
    'results', 'patterns', 'insights', 'layer1_stats', 'filter_stats',
    '_model_used', '_duration_ms', '_token_usage', '_error', '_skipped',
    'title_patterns', 'content_structures', 'emotion_triggers',
    'trend_signals', 'recommendations',
    // copywrite 节点字段
    'title', 'content', 'tags', 'key_points', 'structured_items', 'review_feedback', 'prompt_source',
    // image_plan 节点字段
    'content_plan', 'copywrite_passthrough', '_source',
    'suggested_template', 'custom_accent', 'suggested_decoration', 'copywrite_context', 'brand',
    'format_plan', 'image_plan', 'is_asset_mode',
    // image_gen 节点字段
    'images_base64', 'image_urls', 'image_count', 'image_details', 'image_prompts', 'style', 'validation', 'plan_context', 'card_draft_summary',
    // image_review / final_review 节点字段
    'review_status', 'feedback', 'selected_indices', 'blueprint', 'is_blueprint_mode',
    // audit 节点字段
    'passed', 'issues', 'suggestions', 'audit_method', '_skill',
    // publish 节点字段
    'post_id', 'status', 'message',
  ]
  for (const k of flatKeys) {
    if (node[k] !== undefined) out[k] = node[k]
  }
  if (Object.keys(out).length > 0) return out
  return node.result || null
}
function getNodeError(nodeId: string): string {
  const node = getNode(nodeId) as any
  if (!node) return ''
  // 兼容平铺结构：_error 可能直接挂在节点顶层
  return node.error || node._error || node.output?._error || ''
}
function getNodeStreamingText(nodeId: string): string {
  const node = getNode(nodeId) as any
  if (!node) return ''
  return node.agent_thinking || ''
}
function getNodeMeta(nodeId: string): { duration: string; model: string; tokens: string } | null {
  const n = getNode(nodeId) as any
  if (!n) return null
  // 兼容平铺结构：_duration_ms/_model_used/_token_usage 可能直接挂在节点顶层
  const out: any = n.output || n
  return {
    duration: out._duration_ms ? `${out._duration_ms}ms` : '-',
    model: out._model_used || '-',
    tokens: out._token_usage?.total != null ? String(out._token_usage.total) : '-',
  }
}

// ===== 时间线步骤：折叠/展开状态 =====
const expandedSteps = ref<Set<string>>(new Set())

// 可折叠/展开的状态；search 是工作流入口，idle/pending 时始终保持展开
function isStepToggleable(nodeId: string): boolean {
  const status = getNodeStatus(nodeId)
  if (status === 'completed') return true
  if (status === 'idle' || status === 'pending') return nodeId !== 'search'
  return false
}

function wfStepClass(nodeId: string): Record<string, boolean> {
  const status = getNodeStatus(nodeId)
  const cls: Record<string, boolean> = {
    [`wf-step-${status}`]: true,
  }
  if (isStepToggleable(nodeId) && expandedSteps.value.has(nodeId)) {
    cls['wf-step-expanded'] = true
  }
  return cls
}

function toggleStepExpand(nodeId: string) {
  if (!isStepToggleable(nodeId)) return
  const next = new Set(expandedSteps.value)
  if (next.has(nodeId)) {
    next.delete(nodeId)
  } else {
    next.add(nodeId)
  }
  expandedSteps.value = next
}

function onStepClick(nodeId: string, event: MouseEvent) {
  if (!isStepToggleable(nodeId)) return
  const target = event.target as HTMLElement
  if (target.closest('.mint-wf-header') || target.closest('.wf-node-summary')) {
    toggleStepExpand(nodeId)
  }
}

// ===== ImageGenCard 需要的额外数据 =====
// 从 image_plan 节点结果中提取 content_plan，并合并顶层关键字段
// 后端 content_plan 只含 {pages:[...]}，suggested_template/custom_accent 等在 output 顶层
const imagePlanCardDraft = computed(() => {
  const result = getNodeResult('image_plan')
  if (!result) return null
  // 优先从 _draft 恢复（用户保存的草稿）
  const draft = result._draft
  if (draft && draft.pages && Array.isArray(draft.pages) && draft.pages.length > 0) {
    return draft
  }
  // 回退到 content_plan（AI 生成的原始数据）
  const cp = result.content_plan
  if (!cp || !Array.isArray(cp.pages) || cp.pages.length === 0) return null
  const merged = { ...cp }
  const topKeys = ['suggested_template', 'custom_accent', 'suggested_decoration', 'copywrite_context', 'brand']
  for (const k of topKeys) {
    if (result[k] !== undefined && merged[k] === undefined) {
      merged[k] = result[k]
    }
  }
  return merged
})

// 当前工作流 ID
const currentWorkflowId = computed(() => {
  return workflowStore.currentWorkflow?.workflow_id || ''
})

// ===== 自动触发图片生成注入 =====
// 当 image_gen 节点变为 awaiting_review 且 review_type=card_editor 时，
// 自动打开 ImageWorkspace 并设置 autoInject=true
watch(
  () => {
    const imageGenNode = workflowStore.nodes.find(
      n => n.node_id === 'image_gen' || n.node_type === 'image_gen'
    )
    return {
      status: imageGenNode?.status,
      reviewType: imageGenNode?.output?.review_type,
    }
  },
  (newVal, oldVal) => {
    if (
      newVal.status === 'awaiting_review' &&
      newVal.reviewType === 'card_editor' &&
      oldVal?.status !== 'awaiting_review' &&
      !showImageWorkspace.value
    ) {
      const draft = imagePlanCardDraft.value
      if (draft && Array.isArray(draft.pages) && draft.pages.length > 0) {
        console.log('[WorkbenchView] image_gen awaiting_review + card_editor: auto opening ImageWorkspace with autoInject')
        autoInjectImageWorkspace.value = true
        showImageWorkspace.value = true
      }
    }
  },
  { deep: true },
)

// ===== 加载搜索平台列表 =====
async function loadSearchPlatforms() {
  try {
    const res = await searchApi.getPlatforms()
    const list = (res as any).data || res || []
    searchPlatforms.value = [
      { name: '', label: '全部', desc: '并发搜索所有已启用平台' },
      ...(Array.isArray(list) ? list.map((p: any) => ({
        name: p.name,
        label: p.label,
        desc: p.desc,
        locked: p.locked || false,
        requires_auth: p.requires_auth || false,
        auth_met: p.auth_met !== false,
      })) : []),
    ]
  } catch (e) {
    searchPlatforms.value = [{ name: '', label: '全部', desc: '并发搜索所有已启用平台' }]
  }
}

watch(() => workStore.sidebarTab, (tab) => {
  if (tab === 'content') {
    workStore.fetchWorks().catch(() => {})
    workStore.fetchOutputWorks().catch(() => {})
  }
})

// ===== 生命周期 =====
onMounted(async () => {
  await nextTick()
  welcomeGreetingRef.value?.trigger()
  try { await accountStore.fetchAccounts() } catch (e) { /* fetchAccounts failed */ }
  workStore.fetchWorks().catch(() => {})
  await loadSearchPlatforms()
  const workflowId = Array.isArray(route.params.workflowId)
    ? route.params.workflowId[0]
    : route.params.workflowId
  if (workflowId) {
    currentPage.value = 'workflow'
    try {
      await workflowStore.switchToWorkflow(workflowId)
    } catch (e) {
      /* switchToWorkflow from route failed */
    }
    return
  }
  try {
    await workflowStore.restoreWorkflow()
  } catch (e) {
    // 静默失败
  }
})

// 节点数据变化时重建图标（防抖，避免流式输出时频繁触发导致滚动跳动）
let _iconTimer: ReturnType<typeof setTimeout> | null = null
watch(() => workflowStore.nodes, () => {
  if (_iconTimer) clearTimeout(_iconTimer)
  _iconTimer = null
}, { deep: true })

// search 节点完成时自动滚动到 analyze 卡片（analyze 已无 interrupt，会自动执行）
watch(() => getNodeStatus('search'), (newStatus) => {
  if (newStatus === 'completed') {
    setTimeout(() => {
      if (!_scrolledNodes.has('analyze')) { _scrolledNodes.add('analyze'); scrollToNode('analyze') }
    }, 300)
  }
})
// analyze 开始执行时也滚动一次（保险）
watch(() => getNodeStatus('analyze'), (newStatus) => {
  if (newStatus === 'running' && !_scrolledNodes.has('analyze')) {
    _scrolledNodes.add('analyze')
    scrollToNode('analyze')
  }
})
</script>

<style scoped>
.mint-shell.settings-blur {
  filter: blur(3px);
  transition: filter 0.25s ease;
}

/* 工作流页面主容器：与选题池 .tp-page 完全一致 */
.wf-page {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 56px 20px 16px;
}

/* 工作流内容卡片包装层：与选题池 .tp-content-card-wrapper 一致 */
.wf-content-card-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

/* 工作流内容卡片：与选题池 .tp-content-card 一致 */
.wf-content-card {
  flex: 1;
  min-height: 0;
  min-width: 0;
  background: #FFFFFF;
  border-radius: 16px;
  border: 1px solid var(--ma-border-default, #EDEDED);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-container-chat {
  max-width: none;
  align-items: stretch;
  gap: 0;
  padding: 0;
  height: 100%;
  box-sizing: border-box;
  border-radius: 16px 0 0 16px;
  border-right: none;
}
.mint-shell.mint-shell-chat {
  overflow: hidden;
}
.mint-shell.mint-shell-chat .wf-page {
  padding-top: 44px;
}


/* 两栏节点容器 */
.wf-columns-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px 24px;
  scrollbar-width: thin;
  scrollbar-color: #E5E7EB transparent;
  width: 100%;
}
.wf-columns-container::-webkit-scrollbar { width: 6px; }
.wf-columns-container::-webkit-scrollbar-track { background: transparent; }
.wf-columns-container::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
.wf-columns-container::-webkit-scrollbar-thumb:hover { background: #9CA3AF; }

/* 单栏容器 */
.wf-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  min-width: 0;
}


/* 栏内节点列（保留时间线） */
.wf-nodes-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-left: 36px;
  padding-right: 4px;
  scrollbar-width: none;
}
.wf-nodes-column::-webkit-scrollbar { display: none; }
.wf-nodes-column::-webkit-scrollbar-track { background: transparent; }
.wf-nodes-column::-webkit-scrollbar-thumb { background: transparent; border-radius: 3px; }

/* 搜索行：搜索卡片 + 推荐卡片并排 */
.wf-search-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.wf-search-row-main {
  flex: 1;
  min-width: 0;
}

.wf-nodes-column::-webkit-scrollbar-thumb:hover { background: transparent; }

/* 通知横幅 */
.wf-notifications {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wf-notification {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 15px;
}
.wf-notification-arrearage,
.wf-notification-config_error,
.wf-notification-workflow_failed,
.wf-notification-workflow_error {
  background: #FEF2F2;
  color: #DC2626;
}
.wf-notification-search_degraded {
  background: #FFFBEB;
  color: #D97706;
}
.wf-notification-icon { flex-shrink: 0; margin-top: 1px; }
.wf-notification-body { flex: 1; min-width: 0; }
.wf-notification-message { font-weight: 500; }
.wf-notification-suggestion { margin-top: 2px; font-size: 14px; opacity: 0.85; }
.wf-notification-action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 14px;
  text-decoration: underline;
}
.wf-notification-close {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  color: inherit;
  opacity: 0.6;
}
.wf-notification-close:hover { opacity: 1; background: rgba(0,0,0,0.06); }


@keyframes wfBreathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ---- Dark theme for card shell & columns ---- */
.mint-shell.dark-theme .wf-content-card {
  background: rgba(30, 30, 30, 0.92);
  border-color: rgba(80, 80, 80, 0.3);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.mint-shell.dark-theme .wf-column-label {
  color: #E2E8F0;
}
.mint-shell.dark-theme .wf-column-sub {
  color: #64748B;
}

/* ---- Responsive: narrow screen fallback to single column ---- */
@media (max-width: 900px) {
  .wf-columns-container {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}
</style>