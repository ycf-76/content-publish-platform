<template>
<div class="min-h-screen" style="position: relative;">
  <div class="mint-shell da-shell" :class="{ 'mint-collapsed': isSidebarCollapsed }" :style="{ '--left-sidebar-width': leftSidebarWidth + 'px' }">
    <SidebarNav
      :current-page="'chat'"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goToEco"
      @open-settings="goToSettings"
      @new-workflow="goToHome"
      @new-chat="handleNewChat"
      @delete-chat="handleDeleteChat"
      @select-conversation="handleSelectConversation"
      @new-chat-in-folder="handleNewChatInFolder"
      @select-file="handleSelectFile"
      @select-folder="handleSelectFolder"
    />
    <div v-if="!isSidebarCollapsed" class="da-sidebar-resizer" @mousedown="startLeftResize"><div class="da-sidebar-resizer-line"></div></div>
    <main class="wf-page">
      <div class="page-container page-container-chat">
        <ChatView ref="chatRef" />
      </div>
    </main>
  </div>
</div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import ChatView from '@/components/chat/ChatView.vue'
import { useUIState } from '@/composables/useUIState'
import { useResizeHandle } from '@/composables/useResizeHandle'
import { useFileStore } from '@/stores/files'

const router = useRouter()
const { isSidebarCollapsed, toggleSidebar: toggleSidebarBase } = useUIState()
const chatRef = ref<InstanceType<typeof ChatView> | null>(null)
const fileStore = useFileStore()

function toggleSidebar() { toggleSidebarBase() }

const {
  width: leftSidebarWidth,
  startResize: startLeftResize,
} = useResizeHandle({
  direction: 'left',
  minWidth: 170,
  maxWidth: 520,
  storageKey: 'mint-left-sidebar-width-v2',
})

function handleNewChat() {
  nextTick(() => {
    if (chatRef.value) {
      chatRef.value.newConversation()
    } else {
      setTimeout(() => { chatRef.value?.newConversation() }, 300)
    }
  })
}

function handleDeleteChat(convId: string) {
  if (chatRef.value) {
    chatRef.value.deleteConversation(convId)
  } else {
    setTimeout(() => { chatRef.value?.deleteConversation(convId) }, 300)
  }
}

function handleSelectConversation(convId: string) {
  nextTick(() => {
    if (chatRef.value) {
      chatRef.value.switchToConversation(convId)
    } else {
      setTimeout(() => { chatRef.value?.switchToConversation(convId) }, 300)
    }
  })
}

function handleNewChatInFolder(folderId: string) {
  nextTick(() => {
    if (chatRef.value) {
      chatRef.value.newConversation(folderId)
    } else {
      setTimeout(() => { chatRef.value?.newConversation(folderId) }, 300)
    }
  })
}

function handleSelectFile(fileId: string) {
  fileStore.setActiveFile(fileId)
  const sessionId = fileStore.getFileSessionId(fileId)
  nextTick(() => {
    if (chatRef.value) {
      if (sessionId) {
        chatRef.value.switchToConversation(sessionId)
      } else {
        const file = fileStore.activeFile
        if (file) {
          chatRef.value.newConversation(file.folderId)
        }
      }
    }
  })
}

function handleSelectFolder(folderId: string) {
  nextTick(() => {
    if (chatRef.value) {
      chatRef.value.switchToFolder(folderId)
    } else {
      setTimeout(() => { chatRef.value?.switchToFolder(folderId) }, 300)
    }
  })
}

function handleNavClick(pageName: string) {
  if (pageName === 'chat') return
  if (pageName === 'home') { router.push('/').catch(() => {}); return }
  if (pageName === 'my-works') { router.push('/my-works').catch(() => {}); return }
  if (pageName === 'portfolio') { router.push('/portfolio').catch(() => {}); return }
  if (pageName === 'topic-pool') { router.push('/topic-pool').catch(() => {}); return }
  if (pageName === 'task-plans') { router.push('/task-plans').catch(() => {}); return }
  router.push({ path: '/', query: { page: pageName } })
}

function goToEco() { router.push('/eco') }
function goToSettings() { router.push('/settings') }
function goToHome() { router.push('/') }
</script>

<style scoped>
.da-shell { grid-template-columns: auto auto 1fr !important; }
.da-shell.mint-collapsed { grid-template-columns: 56px 1fr !important; }
.da-sidebar-resizer { position: relative; width: 0; cursor: col-resize; flex-shrink: 0; align-self: stretch; z-index: 5; overflow: visible; }
.da-sidebar-resizer::before { content: ''; position: absolute; top: 0; bottom: 0; left: 0; right: -3px; z-index: 1; }
.da-sidebar-resizer-line { display: none !important; }
.da-sidebar-resizer:hover { background: rgba(0, 0, 0, 0.08); }

.wf-page { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; padding: 56px 20px 16px; }
.page-container { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; overflow: hidden; }
.page-container-chat { max-width: none; align-items: stretch; gap: 0; padding: 0; height: 100%; box-sizing: border-box; border-radius: 16px 0 0 16px; }
</style>