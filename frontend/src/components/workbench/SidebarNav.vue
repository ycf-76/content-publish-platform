<template>
  <aside class="mint-sidebar">
    <div class="mint-sidebar-main">
      <div class="mint-logo-top" @click="goToEco" title="点击查看生态展示" style="cursor:pointer;">
        <transition name="logo-fade" mode="out-in">
          <img v-if="!isCollapsed" key="text" src="/icons/logo3.svg" alt="Pulse Studio" class="mint-logo-text" />
          <svg v-else key="crab" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 180" width="32" height="29" class="mint-logo-crab">
          <defs>
            <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
              <feDropShadow dx="0" dy="3" stdDeviation="2.5" flood-color="#000" flood-opacity="0.15"/>
            </filter>
          </defs>
          <path d="M52,86 Q36,76 30,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <path d="M148,86 Q164,76 170,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <g filter="url(#shadow)">
            <ellipse cx="26" cy="56" rx="18" ry="11" transform="rotate(-45 26 56)" fill="#E8655A"/>
            <ellipse cx="42" cy="80" rx="16" ry="10" transform="rotate(15 42 80)" fill="#E8655A"/>
          </g>
          <g filter="url(#shadow)">
            <ellipse cx="174" cy="56" rx="18" ry="11" transform="rotate(45 174 56)" fill="#E8655A"/>
            <ellipse cx="158" cy="80" rx="16" ry="10" transform="rotate(-15 158 80)" fill="#E8655A"/>
          </g>
          <ellipse cx="100" cy="105" rx="58" ry="48" fill="#E8655A" filter="url(#shadow)"/>
          <path d="M55,110 Q30,118 22,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <path d="M52,125 Q28,136 18,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <path d="M62,138 Q48,152 42,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <path d="M145,110 Q170,118 178,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <path d="M148,125 Q172,136 182,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <path d="M138,138 Q152,152 158,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
          <circle cx="30" cy="68" r="8" fill="#D94F44"/>
          <circle cx="170" cy="68" r="8" fill="#D94F44"/>
          <circle cx="78" cy="62" r="16" fill="white" filter="url(#shadow)"/>
          <circle cx="80" cy="62" r="8" fill="#1a1a1a"/>
          <circle cx="83" cy="59" r="3" fill="white"/>
          <circle cx="122" cy="62" r="16" fill="white" filter="url(#shadow)"/>
          <circle cx="120" cy="62" r="8" fill="#1a1a1a"/>
          <circle cx="123" cy="59" r="3" fill="white"/>
        </svg>
        </transition>
      </div>

      <nav class="mint-nav" style="margin-top: 20px;">
        <a class="mint-nav-item" id="nav-chat" data-page="chat" data-tooltip="AI 对话" @click="toggleChatExpanded" :class="{ 'mint-nav-active': currentPage === 'chat' }">
          <Bot :size="16" :stroke-width="1.8" />
          <span>AI 对话</span>
          <span class="mint-nav-new-chat" @click.stop="$emit('new-chat')" title="新建对话">
            <Plus :size="14" :stroke-width="2.2" />
          </span>
          <span v-if="chatDisplayItems.length > 0" class="mint-nav-chevron" :class="{ 'mint-nav-chevron-rotated': chatExpanded }">
            <ChevronDown :size="14" :stroke-width="2" />
          </span>
        </a>
        <transition name="mint-subgroup"
          :css="false"
          @enter="onChatEnter"
          @leave="onChatLeave">
          <div class="mint-nav-subgroup mint-chat-history-group" v-show="chatExpanded && chatDisplayItems.length > 0" style="border-left: none !important;">
            <a
              v-for="(item, idx) in chatDisplayItems"
              :key="item.id"
              class="mint-nav-sub mint-chat-history-item"
              :class="{ 'mint-chat-history-fade': chatHasMore && !chatAllExpanded && idx === chatDisplayItems.length - 1 }"
              @click="onChatHistoryClick(item.id)"
              @contextmenu.prevent="onChatContextMenu($event, item.id)"
            >
              <MessageSquare :size="12" :stroke-width="1.8" />
              <span class="mint-chat-history-title">{{ item.title }}</span>
            </a>
            <a v-if="chatHasMore && !chatAllExpanded" class="mint-nav-sub mint-chat-more" @click="chatToggleExpand">
              <span>查看更多</span>
            </a>
            <a v-if="chatHasMore && chatAllExpanded" class="mint-nav-sub mint-chat-more" @click="chatToggleExpand">
              <span>收起</span>
            </a>
          </div>
        </transition>
        <a class="mint-nav-item mint-nav-collapsible" data-tooltip="开启工作流" @click="toggleWorkflowExpanded" :class="{ 'mint-nav-active': currentPage === 'workflow' || isWorkflowTemplatesActive }">
          <Sparkles :size="16" :stroke-width="1.8" />
          <span>开启工作流</span>
          <span class="mint-nav-chevron" :class="{ 'mint-nav-chevron-rotated': workflowExpanded }">
            <ChevronDown :size="14" :stroke-width="2" />
          </span>
        </a>
        <transition name="mint-subgroup"
          :css="false"
          @enter="onWorkflowEnter"
          @leave="onWorkflowLeave">
          <div class="mint-nav-subgroup" v-show="workflowExpanded" style="border-left: none !important;">
            <a class="mint-nav-sub" data-tooltip="快速启动" @click="onWorkflowQuickStart" :class="{ 'mint-nav-active': currentPage === 'workflow' }">
              <Rocket :size="14" :stroke-width="1.8" />
              <span>快速启动</span>
            </a>
            <a class="mint-nav-sub" data-tooltip="动态编排" @click="goToWorkflowTemplates" :class="{ 'mint-nav-active': isWorkflowTemplatesActive }">
              <RouteIcon :size="14" :stroke-width="1.8" />
              <span>动态编排</span>
            </a>
            <a class="mint-nav-sub" data-tooltip="历史" @click="$emit('nav-click', 'history')" :class="{ 'mint-nav-active': currentPage === 'history' }">
              <Clock :size="14" :stroke-width="1.8" />
              <span>历史</span>
            </a>
          </div>
        </transition>
        <a class="mint-nav-item" id="nav-topic-pool" data-page="topic-pool" data-tooltip="选题池" @click="goToTopicPool" :class="{ 'mint-nav-active': isTopicPoolActive }">
          <BookOpen :size="16" :stroke-width="1.8" />
          <span>选题池</span>
        </a>
        <a class="mint-nav-item" data-tooltip="Esther工厂" @click="goToEstherFactory" :class="{ 'mint-nav-active': isEstherFactoryActive }">
          <Cpu :size="16" :stroke-width="1.8" />
          <span>Esther工厂</span>
        </a>
        <a class="mint-nav-item" href="#" data-tooltip="设置" @click.prevent="onOpenSettings">
          <Settings :size="16" :stroke-width="1.8" />
          <span>设置</span>
        </a>
      </nav>
    </div>

    <div class="mint-sidebar-bottom">
      <div class="mint-sidebar-actions">
        <button class="mint-sidebar-toggle" id="sidebar-toggle" data-tooltip="收起侧边栏" aria-label="收起侧边栏" @click="$emit('toggle-sidebar')">
          <PanelLeftClose :size="16" :stroke-width="1.8" />
          <span>收起侧栏</span>
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
          <Trash2 :size="13" :stroke-width="1.8" />
          <span>删除对话</span>
        </button>
      </div>
      <div v-if="contextMenu.visible" class="mint-context-overlay" @click="closeContextMenu" @contextmenu.prevent="closeContextMenu"></div>
    </Teleport>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  Bot,
  Sparkles,
  ChevronDown,
  Rocket,
  Route as RouteIcon,
  Clock,
  BookOpen,
  Cpu,
  Settings,
  PanelLeftClose,
  MessageSquare,
  Plus,
  Trash2
} from 'lucide-vue-next'
import { useUIState } from '@/composables/useUIState'
import { useChatHistory } from '@/composables/useChatHistory'

defineProps<{
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
}>()

const router = useRouter()

function goToEco() {
  emit('go-eco')
}

const route = useRoute()
const isTopicPoolActive = computed(() => route.path === '/topic-pool')
const isWorkflowTemplatesActive = computed(() => route.path === '/workflow-templates' || route.path === '/workflow-editor')
const isEstherFactoryActive = computed(() => route.path === '/esther-factory')

function goToTopicPool() {
  router.push('/topic-pool')
}

function goToWorkflowTemplates() {
  router.push('/workflow-templates')
}

function goToEstherFactory() {
  router.push('/esther-factory')
}


function onOpenSettings() {
  window.dispatchEvent(new Event('open-settings'))
  emit('open-settings')
}

function onWorkflowQuickStart() {
  emit('nav-click', 'workflow')
}

const { workflowExpanded, toggleWorkflowExpanded } = useUIState()
const { displayItems: chatDisplayItems, hasMore: chatHasMore, allExpanded: chatAllExpanded, toggleExpand: chatToggleExpand, removeConversation: removeChatHistory } = useChatHistory()

const chatExpanded = ref(true)

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

function closeContextMenu() {
  contextMenu.value.visible = false
}

function onDeleteChat(convId: string) {
  removeChatHistory(convId)
  emit('delete-chat', convId)
  closeContextMenu()
}

function toggleChatExpanded() {
  if (chatDisplayItems.value.length > 0) {
    chatExpanded.value = !chatExpanded.value
  } else {
    emit('nav-click', 'chat')
  }
}

function onChatHistoryClick(id: string) {
  emit('nav-click', 'chat')
}

function onChatEnter(el: Element, done: () => void) {
  const container = el as HTMLElement
  const items = Array.from(container.querySelectorAll('.mint-nav-sub')) as HTMLElement[]

  container.style.height = '0'
  container.style.opacity = '0'
  container.style.overflow = 'hidden'
  items.forEach((item) => {
    item.style.opacity = '0'
    item.style.transform = 'translateX(-12px)'
  })

  void container.offsetHeight

  const targetHeight = container.scrollHeight
  container.style.transition = 'height 0.32s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.28s ease'
  container.style.height = targetHeight + 'px'
  container.style.opacity = '1'

  items.forEach((item, i) => {
    const delay = 60 + i * 50
    item.style.transition = `opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms, transform 0.3s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms`
  })

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      items.forEach((item) => {
        item.style.opacity = '1'
        item.style.transform = 'translateX(0)'
      })
    })
  })

  const total = 300 + 60 + Math.max(0, items.length - 1) * 50 + 300 + 50
  window.setTimeout(() => {
    container.style.height = ''
    container.style.overflow = ''
    container.style.transition = ''
    container.style.opacity = ''
    items.forEach((item) => {
      item.style.transition = ''
      item.style.transform = ''
      item.style.opacity = ''
    })
    done()
  }, total)
}

function onChatLeave(el: Element, done: () => void) {
  const container = el as HTMLElement
  const items = Array.from(container.querySelectorAll('.mint-nav-sub')) as HTMLElement[]

  const currentHeight = container.offsetHeight
  container.style.height = currentHeight + 'px'
  container.style.overflow = 'hidden'

  items.forEach((item, i) => {
    const reverseDelay = (items.length - 1 - i) * 35
    item.style.transition = `opacity 0.18s ease ${reverseDelay}ms, transform 0.18s ease ${reverseDelay}ms`
    item.style.opacity = '0'
    item.style.transform = 'translateX(-8px)'
  })

  void container.offsetHeight
  const collapseDelay = items.length * 35 + 50
  container.style.transition = `height 0.24s cubic-bezier(0.4, 0, 1, 1) ${collapseDelay}ms, opacity 0.2s ease ${collapseDelay}ms`
  container.style.height = '0'
  container.style.opacity = '0'

  const total = collapseDelay + 240 + 25
  window.setTimeout(() => {
    done()
  }, total)
}

function onWorkflowEnter(el: Element, done: () => void) {
  const container = el as HTMLElement
  const items = Array.from(container.querySelectorAll('.mint-nav-sub')) as HTMLElement[]

  container.style.height = '0'
  container.style.opacity = '0'
  container.style.overflow = 'hidden'
  items.forEach((item) => {
    item.style.opacity = '0'
    item.style.transform = 'translateX(-12px)'
  })

  void container.offsetHeight

  const targetHeight = container.scrollHeight
  container.style.transition = 'height 0.32s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.28s ease'
  container.style.height = targetHeight + 'px'
  container.style.opacity = '1'

  items.forEach((item, i) => {
    const delay = 90 + i * 70
    item.style.transition = `opacity 0.34s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms, transform 0.34s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms`
  })

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      items.forEach((item) => {
        item.style.opacity = '1'
        item.style.transform = 'translateX(0)'
      })
    })
  })

  const total = 320 + 90 + Math.max(0, items.length - 1) * 70 + 340 + 60
  window.setTimeout(() => {
    container.style.height = ''
    container.style.overflow = ''
    container.style.transition = ''
    container.style.opacity = ''
    items.forEach((item) => {
      item.style.transition = ''
      item.style.transform = ''
      item.style.opacity = ''
    })
    done()
  }, total)
}

function onWorkflowLeave(el: Element, done: () => void) {
  const container = el as HTMLElement
  const items = Array.from(container.querySelectorAll('.mint-nav-sub')) as HTMLElement[]

  const currentHeight = container.offsetHeight
  container.style.height = currentHeight + 'px'
  container.style.overflow = 'hidden'

  items.forEach((item, i) => {
    const reverseDelay = (items.length - 1 - i) * 45
    item.style.transition = `opacity 0.2s ease ${reverseDelay}ms, transform 0.2s ease ${reverseDelay}ms`
    item.style.opacity = '0'
    item.style.transform = 'translateX(-8px)'
  })

  void container.offsetHeight
  const collapseDelay = items.length * 45 + 60
  container.style.transition = `height 0.28s cubic-bezier(0.4, 0, 1, 1) ${collapseDelay}ms, opacity 0.24s ease ${collapseDelay}ms`
  container.style.height = '0'
  container.style.opacity = '0'

  const total = collapseDelay + 280 + 30
  window.setTimeout(() => {
    done()
  }, total)
}
</script>