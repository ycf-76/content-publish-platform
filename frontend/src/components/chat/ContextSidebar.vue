<template>
  <aside class="ctx-sidebar" :style="{ width: ctxStore.sidebarWidth + 'px' }">
    <!-- ===== 顶部栏 ===== -->
    <div class="ctx-topbar">
      <button v-if="activePanel" class="ctx-back" @click="activePanel = null" title="返回导航">
        <ChevronLeft :size="16" :stroke-width="2" />
      </button>
      <div class="ctx-topbar-title-wrap">
        <component v-if="currentPanelIcon" :is="currentPanelIcon" :size="15" :stroke-width="1.8" class="ctx-topbar-icon" />
        <span class="ctx-topbar-title">{{ activePanel ? panelTitle : '工具箱' }}</span>
      </div>
      <button class="ctx-close" @click="ctxStore.setSidebarVisible(false)" title="收起面板">
        <PanelRightClose :size="18" :stroke-width="1.8" />
      </button>
    </div>

    <!-- ===== 导航中心（默认视图） ===== -->
    <div v-if="!activePanel" class="ctx-nav-center">
      <div class="ctx-nav-group">
        <span class="ctx-nav-group-label">从这里开始</span>
        <button v-for="nav in navItems" :key="nav.key" class="ctx-nav-row" @click="activePanel = nav.key">
          <component :is="nav.icon" :size="16" :stroke-width="1.6" />
          <span>{{ nav.label }}</span>
        </button>
      </div>

      <div class="ctx-nav-group">
        <span class="ctx-nav-group-label">快捷入口</span>
        <button class="ctx-nav-row" @click="onChatAction('xhs_note_creator')">
          <Sparkles :size="16" :stroke-width="1.6" />
          <span>生成笔记</span>
        </button>
        <button class="ctx-nav-row" @click="onChatAction('publish_checklist')">
          <Rocket :size="16" :stroke-width="1.6" />
          <span>发布检查</span>
        </button>
      </div>
    </div>

    <!-- ===== 子面板: 浏览器 ===== -->
    <div v-if="activePanel === 'browser'" class="ctx-sub ctx-sub-browser">
      <div class="ctx-br">
        <!-- 工具栏: 后退 | 前进 | 刷新 | 地址栏 | 模式切换 -->
        <div class="ctx-br-toolbar">
          <button class="ctx-br-btn" :disabled="!canGoBack" @click="goBack" title="后退"><ChevronLeft :size="16" /></button>
          <button class="ctx-br-btn" :disabled="!canGoForward" @click="goForward" title="前进"><ChevronRight :size="16" /></button>
          <button class="ctx-br-btn" @click="refreshIframe" title="刷新"><RefreshCw :size="14" :class="{ 'ctx-br-spin': isRefreshing || isLoadingPage }" /></button>
          <div class="ctx-br-addr-wrap">
            <Lock v-if="currentUrl" :size="11" class="ctx-br-lock" />
            <input
              ref="addrInputRef"
              v-model="addressInput"
              class="ctx-br-addr"
              placeholder="搜索或输入网址"
              @keydown.enter="navigateTo"
              @focus="($event.target as HTMLInputElement).select()"
            />
          </div>
          <button class="ctx-br-btn" :class="{ 'ctx-br-btn-active': browserMode === 'remote' }" @click="toggleBrowserMode" :title="browserMode === 'remote' ? '切换到iframe模式' : '切换到远程浏览器'">
            <Monitor :size="14" />
          </button>
          <button class="ctx-br-btn" @click="openInNewWindow" :disabled="!currentUrl" title="新窗口打开"><ExternalLink :size="14" /></button>
        </div>
        <!-- 视口 -->
        <div class="ctx-br-viewport">
          <!-- 远程浏览器模式：Playwright 截图交互 -->
          <template v-if="browserMode === 'remote'">
            <div v-if="isLoadingPage" class="ctx-br-loading">
              <RefreshCw :size="24" class="ctx-br-spin" />
              <span>加载中…</span>
            </div>
            <img
              v-else-if="remoteScreenshot"
              :src="'data:image/jpeg;base64,' + remoteScreenshot"
              class="ctx-br-screenshot"
              @click="onScreenshotClick"
              @wheel.prevent="onScreenshotWheel"
            />
            <div v-else class="ctx-br-home">
              <Monitor :size="48" :stroke-width="1" />
              <span>远程浏览器就绪</span>
            </div>
            <div v-if="remoteScreenshot && !isLoadingPage" class="ctx-br-remote-bar">
              <input
                v-model="remoteInputText"
                class="ctx-br-remote-text"
                placeholder="点击页面输入框后，在此输入文字，Enter 发送"
                @keydown.enter="sendRemoteText"
              />
            </div>
            <div v-if="publishStatus" class="ctx-br-publish-status" :class="`ctx-br-publish-${publishStatus.status}`">
              <span class="ctx-br-publish-status-text">{{ publishStatus.message }}</span>
              <button v-if="publishStatus.status === 'awaiting_manual'" class="ctx-br-publish-confirm" @click="publishStatus = null">知道了</button>
              <button v-if="publishStatus.status === 'failed'" class="ctx-br-publish-confirm" @click="publishStatus = null">关闭</button>
            </div>
          </template>
          <!-- iframe 模式 -->
          <template v-else>
            <div v-if="iframeLoadError" class="ctx-br-error">
              <Globe :size="32" :stroke-width="1" />
              <span>iframe 加载失败</span>
              <button class="ctx-br-error-btn" @click="switchToRemote">切换到远程浏览器</button>
              <button class="ctx-br-error-btn ctx-br-error-btn-sub" @click="openInNewWindow">新窗口打开</button>
            </div>
            <iframe
              v-if="currentUrl && !iframeLoadError"
              ref="brIframeRef"
              :src="proxyUrl"
              class="ctx-br-iframe"
              allow="clipboard-read; clipboard-write"
              referrerpolicy="no-referrer"
              @load="onIframeLoad"
              @error="onIframeError"
            ></iframe>
            <div v-else class="ctx-br-home">
              <Globe :size="48" :stroke-width="1" />
              <span>输入网址开始浏览</span>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- ===== 子面板: 素材库 ===== -->
    <div v-if="activePanel === 'assets'" class="ctx-sub">
      <div class="ctx-section">
        <div class="ctx-section-head">
          <span class="ctx-section-label">作品素材</span>
          <span class="ctx-section-count">{{ workStore.works.length }}</span>
        </div>
        <div v-if="workStore.works.length === 0" class="ctx-section-empty">
          <FolderOpen :size="16" :stroke-width="1.2" /><span>暂无作品</span>
        </div>
        <div v-for="work in workStore.works" :key="work.id" class="ctx-asset-item" @click="openWorkPreview(work)">
          <div class="ctx-asset-cover">
            <img v-if="resolveAssetCover(work)" :src="resolveAssetCover(work)" alt="" class="ctx-asset-img" />
            <iframe v-else-if="resolveAssetFirstPageHtml(work)" :srcdoc="resolveAssetFirstPageHtml(work)" class="ctx-asset-iframe" sandbox="allow-same-origin" />
            <FileText v-else :size="16" class="ctx-asset-placeholder" />
          </div>
          <div class="ctx-asset-info">
            <span class="ctx-asset-title">{{ work.title }}</span>
            <span class="ctx-asset-meta">{{ workStore.getContentTypeLabel(work.contentType) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 子面板: 上下文 ===== -->
    <div v-if="activePanel === 'context'" class="ctx-sub">
      <div class="ctx-section">
        <div class="ctx-section-head">
          <span class="ctx-section-label">AI 正在读取</span>
          <span class="ctx-section-count">{{ ctxStore.contextTrack.length }}</span>
        </div>
        <div v-if="ctxStore.contextTrack.length === 0" class="ctx-section-empty">
          <Eye :size="16" :stroke-width="1.2" /><span>暂无关联内容</span>
        </div>
        <div v-for="item in ctxStore.contextTrack" :key="item.id" class="ctx-item" :class="{ 'ctx-item-pinned': item.pinned }" @click="selectPreview(item)">
          <div class="ctx-item-icon" :class="`ctx-item-icon-${item.type}`">
            <component :is="typeIcon(item.type)" :size="13" :stroke-width="1.8" />
          </div>
          <div class="ctx-item-info">
            <span class="ctx-item-label">{{ item.label }}</span>
            <span class="ctx-item-summary">{{ item.summary }}</span>
          </div>
          <div class="ctx-item-actions">
            <button class="ctx-item-btn" @click.stop="ctxStore.togglePin(item.id)" :title="item.pinned ? '暂停读取' : '恢复读取'">
              <Eye v-if="item.pinned" :size="12" class="ctx-pin-active" />
              <EyeOff v-else :size="12" />
            </button>
            <button class="ctx-item-btn" @click.stop="ctxStore.removeContextItem(item.id)" title="移除"><X :size="11" /></button>
          </div>
        </div>
      </div>
      <div class="ctx-section">
        <div class="ctx-section-head"><span class="ctx-section-label">上下文用量</span></div>
        <ContextRing />
      </div>
    </div>

    <!-- ===== 子面板: 作品预览 ===== -->
    <div v-if="activePanel === 'preview'" class="ctx-sub">
      <div v-if="previewWork" class="ctx-preview-block">
        <NotePreview v-if="previewRenderer === 'note'" :work="previewWork" />
        <MarkdownView v-else-if="previewRenderer === 'markdown'" :content="previewWork.contentText || ''" :title="previewWork.title" :meta="previewWorkMeta" />
        <ScriptView v-else-if="previewRenderer === 'script'" :script-text="previewWork.scriptText || ''" :title="previewWork.title" :meta="previewWorkMeta" />
        <WorkDetailPanel v-else :work="previewWork" :visible="true" @close="ctxStore.unlinkWork()" @chat-action="onChatAction" />
        <PublishPlatforms v-if="previewWork.isDraft" :work="previewWork" @chat-action="onChatAction" />
      </div>
      <div v-else class="ctx-empty">
        <FileText :size="32" :stroke-width="1.2" />
        <span class="ctx-empty-title">选择作品预览</span>
        <span class="ctx-empty-desc">从素材库中选择作品</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, watch, defineAsyncComponent, onMounted } from 'vue'
import {
  X, FileText, ChevronLeft, ChevronRight,
  BarChart3, FolderOpen, Eye, EyeOff,
  Globe, BookOpen, Brain, LayoutList,
  PanelRightClose, Monitor, RefreshCw, ExternalLink, Lock,
  Image, Sparkles, Rocket
} from 'lucide-vue-next'
import { useChatContextStore } from '@/stores/chatContext'
import { useWorkStore } from '@/stores/work'
import { browserNavigate, publishNavigate, publishSubmit, browserInteractApi } from '@/api/browser'
import NotePreview from './NotePreview.vue'
import MarkdownView from './MarkdownView.vue'
import ScriptView from './ScriptView.vue'
import ContextRing from './ContextRing.vue'

const WorkDetailPanel = defineAsyncComponent(() => import('./WorkDetailPanel.vue'))
const PublishPlatforms = defineAsyncComponent(() => import('./PublishPlatforms.vue'))

const ctxStore = useChatContextStore()
const workStore = useWorkStore()

const emit = defineEmits<{ 'chat-action': [action: string] }>()

type PanelKey = 'browser' | 'assets' | 'context' | 'preview' | null
const activePanel = ref<PanelKey>(null)

const navItems = [
  { key: 'browser' as const, label: '浏览器', icon: Globe },
  { key: 'assets' as const, label: '素材库', icon: Image },
  { key: 'context' as const, label: '上下文', icon: LayoutList },
] as const

const panelTitle = computed(() => { const map: Record<string, string> = { browser: '浏览器', assets: '素材库', context: '上下文', preview: '作品预览' }; return activePanel.value ? (map[activePanel.value] || '') : '' })

const panelIconMap: Record<string, any> = { browser: Globe, assets: Image, context: LayoutList, preview: FileText }
const currentPanelIcon = computed(() => activePanel.value ? (panelIconMap[activePanel.value] || null) : null)

const addressInput = ref('')
const currentUrl = ref('')
const isRefreshing = ref(false)
const historyStack = ref<string[]>([])
const historyIndex = ref(-1)
const addrInputRef = ref<HTMLInputElement>()
const brIframeRef = ref<HTMLIFrameElement>()

const browserMode = ref<'iframe' | 'remote'>('remote')
const remoteScreenshot = ref('')
const isLoadingPage = ref(false)
const remoteInputText = ref('')
const iframeLoadError = ref(false)

const proxyUrl = computed(() => {
  if (!currentUrl.value) return ''
  return `/api/browser/proxy/${encodeURIComponent(currentUrl.value)}`
})

function onIframeLoad() {
  iframeLoadError.value = false
}

function onIframeError() {
  iframeLoadError.value = true
}

function switchToRemote() {
  iframeLoadError.value = false
  browserMode.value = 'remote'
  if (currentUrl.value) {
    isLoadingPage.value = true
    browserNavigate(currentUrl.value)
      .then(result => {
        if (result.ok) {
          remoteScreenshot.value = result.screenshot_base64 || ''
          if (result.url) { currentUrl.value = result.url; addressInput.value = result.url }
        } else { remoteScreenshot.value = '' }
      })
      .catch(() => { remoteScreenshot.value = '' })
      .finally(() => { isLoadingPage.value = false })
  }
}

const PUBLISHER_URLS: Record<string, string> = {
  xiaohongshu: 'https://creator.xiaohongshu.com/publish/publish',
  douyin: 'https://creator.douyin.com/creator-micro/content/upload',
  kuaishou: 'https://creator.kuaishou.com/publish/video',
  bilibili: 'https://member.bilibili.com/platform/upload/video/frame',
  zhihu: 'https://www.zhihu.com/creator/writer',
  wechat: 'https://channels.weixin.qq.com/platform/post',
  wechat_video: 'https://channels.weixin.qq.com/platform/post',
}

const PLATFORM_NAMES: Record<string, string> = {
  xiaohongshu: '小红书',
  douyin: '抖音',
  kuaishou: '快手',
  bilibili: 'B站',
  zhihu: '知乎',
  wechat: '视频号',
  wechat_video: '视频号',
}

const canGoBack = computed(() => historyIndex.value > 0)
const canGoForward = computed(() => historyIndex.value < historyStack.value.length - 1)

function navigateTo() {
  let url = addressInput.value.trim()
  if (!url) return
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url
  pushHistory(url)
  currentUrl.value = url
  addressInput.value = url
  iframeLoadError.value = false

  if (browserMode.value === 'remote') {
    isLoadingPage.value = true
    browserNavigate(url)
      .then(result => {
        if (result.ok) {
          remoteScreenshot.value = result.screenshot_base64 || ''
          if (result.url) { currentUrl.value = result.url; addressInput.value = result.url }
        } else { remoteScreenshot.value = '' }
      })
      .catch(() => { remoteScreenshot.value = '' })
      .finally(() => { isLoadingPage.value = false })
  }
}

function pushHistory(url: string) {
  if (historyStack.value[historyIndex.value] === url) return
  historyStack.value = historyStack.value.slice(0, historyIndex.value + 1)
  historyStack.value.push(url)
  historyIndex.value = historyStack.value.length - 1
}

function goBack() {
  if (!canGoBack.value) return
  historyIndex.value--
  currentUrl.value = historyStack.value[historyIndex.value]
  addressInput.value = currentUrl.value

  if (browserMode.value === 'remote') {
    isLoadingPage.value = true
    browserInteractApi('back', {})
      .then(result => { if (result.ok && result.screenshot_base64) remoteScreenshot.value = result.screenshot_base64 })
      .catch(() => {})
      .finally(() => { isLoadingPage.value = false })
  }
}

function goForward() {
  if (!canGoForward.value) return
  historyIndex.value++
  currentUrl.value = historyStack.value[historyIndex.value]
  addressInput.value = currentUrl.value

  if (browserMode.value === 'remote') {
    isLoadingPage.value = true
    browserInteractApi('forward', {})
      .then(result => { if (result.ok && result.screenshot_base64) remoteScreenshot.value = result.screenshot_base64 })
      .catch(() => {})
      .finally(() => { isLoadingPage.value = false })
  }
}

function refreshIframe() {
  if (browserMode.value === 'remote') {
    if (!currentUrl.value || isLoadingPage.value) return
    isLoadingPage.value = true
    browserNavigate(currentUrl.value)
      .then(result => { if (result.ok) remoteScreenshot.value = result.screenshot_base64 || '' })
      .catch(() => {})
      .finally(() => { isLoadingPage.value = false })
    return
  }
  if (!currentUrl.value || isRefreshing.value) return
  isRefreshing.value = true
  const u = currentUrl.value
  currentUrl.value = ''
  setTimeout(() => { currentUrl.value = u; setTimeout(() => { isRefreshing.value = false }, 500) }, 50)
}

function openInNewWindow() { if (currentUrl.value) window.open(currentUrl.value, '_blank') }

function resolveAssetCover(work: any): string {
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

function resolveAssetFirstPageHtml(work: any): string {
  if (work.firstPageHtml) return work.firstPageHtml
  if (work.cardDraft?.pages?.length > 0) {
    const first = work.cardDraft.pages[0]
    if (first?.content?.htmlContent) return first.content.htmlContent
    if (first?.htmlContent) return first.htmlContent
  }
  return ''
}

const previewWork = computed(() => {
  const item = ctxStore.previewItem
  if (item && item.type === 'work') {
    const refId = item.meta.refId
    const found = workStore.works.find(w => w.id === refId) || workStore.outputWorks.find(w => w.id === refId)
    if (found) return found
  }
  if (workStore.activeWork) return workStore.activeWork
  return null
})

const previewRenderer = computed(() => {
  const work = previewWork.value
  if (!work) return 'detail'
  if (work.isDraft) return 'detail'
  const ct = work.contentType
  if (ct === 'image_text' || ct === 'image_gallery') return 'note'
  if (ct === 'long_article') return 'markdown'
  if (['short_video', 'long_video', 'ai_edit', 'voiceover', 'live_clip'].includes(ct)) return 'script'
  return 'detail'
})

const previewWorkMeta = computed(() => {
  const work = previewWork.value
  return work ? `${workStore.getPlatformLabel(work.platform)} · ${workStore.getContentTypeLabel(work.contentType)}` : ''
})

function typeIcon(type: string) {
  const map: Record<string, any> = { work: FileText, analysis: BarChart3, file: FolderOpen, url: Globe, rule: BookOpen, memory: Brain }
  return map[type] || FileText
}

function selectPreview(item: any) { ctxStore.previewItem = item; activePanel.value = 'preview' }
function openWorkPreview(work: any) { ctxStore.linkWork(work.id); activePanel.value = 'preview' }
const publishStatus = ref<{ platform: string; status: string; message: string } | null>(null)

function onChatAction(action: string) {
  if (action.startsWith('publish_')) {
    const platform = action.replace('publish_', '')
    submitPublish(platform)
    return
  }
  emit('chat-action', action)
}

async function submitPublish(platform: string) {
  const work = previewWork.value
  const title = work?.title || ''
  let content = work?.contentText || work?.scriptText || ''
  const tags = work?.tags || []

  if (!content && work?.cardDraft?.pages?.length) {
    const textParts: string[] = []
    for (const p of work.cardDraft.pages) {
      const page = p as any
      const html: string = page?.content?.htmlContent || page?.htmlContent || ''
      if (html) {
        const div = document.createElement('div')
        div.innerHTML = html
        const text = div.textContent?.trim() || ''
        if (text) textParts.push(text)
      }
    }
    content = textParts.join('\n\n')
  }

  if (!title && !content) {
    emit('chat-action', `publish_${platform}`)
    return
  }

  const images_base64: string[] = []
  const images_urls: string[] = []
  if (work?.images && Array.isArray(work.images)) {
    for (const img of work.images) {
      if (typeof img === 'string' && img.startsWith('data:')) {
        const b64 = img.split(',')[1]
        if (b64) images_base64.push(b64)
      } else if (typeof img === 'string' && (img.startsWith('http://') || img.startsWith('https://') || img.startsWith('/'))) {
        images_urls.push(img)
      } else if (typeof img === 'object' && (img as any).base64) {
        images_base64.push((img as any).base64)
      }
    }
  }
  if (work?.coverUrl && !images_urls.includes(work.coverUrl) && !images_base64.length) {
    if (work.coverUrl.startsWith('http://') || work.coverUrl.startsWith('https://')) {
      images_urls.push(work.coverUrl)
    }
  }

  activePanel.value = 'browser'
  browserMode.value = 'remote'
  isLoadingPage.value = true
  publishStatus.value = { platform, status: 'submitting', message: `正在发布到 ${PLATFORM_NAMES[platform] || platform}...` }

  const url = PUBLISHER_URLS[platform] || ''
  currentUrl.value = url
  addressInput.value = url
  if (url) pushHistory(url)

  try {
    const result = await publishSubmit({
      platform,
      title,
      content,
      tags,
      images_base64,
      images_urls,
      auto_submit: false,
    })

    if (result.ok) {
      remoteScreenshot.value = result.screenshot_base64 || ''
      if (result.url) { currentUrl.value = result.url; addressInput.value = result.url }
      publishStatus.value = {
        platform,
        status: result.status || 'awaiting_manual',
        message: result.message || '内容已填写，请在浏览器中确认发布',
      }
    } else {
      remoteScreenshot.value = ''
      publishStatus.value = {
        platform,
        status: 'failed',
        message: result.error || result.message || '发布失败',
      }
    }
  } catch (e: any) {
    remoteScreenshot.value = ''
    publishStatus.value = {
      platform,
      status: 'failed',
      message: e?.message || '发布请求失败',
    }
  } finally {
    isLoadingPage.value = false
  }
}

async function navigateToPublish(platform: string) {
  const url = PUBLISHER_URLS[platform]
  if (!url) { emit('chat-action', `publish_${platform}`); return }

  activePanel.value = 'browser'
  browserMode.value = 'remote'
  isLoadingPage.value = true
  currentUrl.value = url
  addressInput.value = url
  pushHistory(url)

  try {
    const result = await publishNavigate(platform)
    if (result.ok) {
      remoteScreenshot.value = result.screenshot_base64 || ''
      if (result.url) { currentUrl.value = result.url; addressInput.value = result.url }
    } else { remoteScreenshot.value = '' }
  } catch { remoteScreenshot.value = '' }
  finally { isLoadingPage.value = false }
}

function onScreenshotClick(e: MouseEvent) {
  if (!remoteScreenshot.value || isLoadingPage.value) return
  const img = e.target as HTMLImageElement
  const rect = img.getBoundingClientRect()
  const x = Math.round((e.clientX - rect.left) * (img.naturalWidth / rect.width))
  const y = Math.round((e.clientY - rect.top) * (img.naturalHeight / rect.height))

  isLoadingPage.value = true
  browserInteractApi('click', { x, y })
    .then(result => {
      if (result.ok && result.screenshot_base64) remoteScreenshot.value = result.screenshot_base64
      if (result.url) { currentUrl.value = result.url; addressInput.value = result.url }
    })
    .catch(() => {})
    .finally(() => { isLoadingPage.value = false })
}

function onScreenshotWheel(e: WheelEvent) {
  if (!remoteScreenshot.value || isLoadingPage.value) return
  isLoadingPage.value = true
  browserInteractApi('scroll', { x: 0, y: 0, deltaY: Math.round(e.deltaY) })
    .then(result => { if (result.ok && result.screenshot_base64) remoteScreenshot.value = result.screenshot_base64 })
    .catch(() => {})
    .finally(() => { isLoadingPage.value = false })
}

function sendRemoteText() {
  if (!remoteInputText.value.trim() || isLoadingPage.value) return
  isLoadingPage.value = true
  const text = remoteInputText.value
  browserInteractApi('type', { text })
    .then(result => { if (result.ok && result.screenshot_base64) remoteScreenshot.value = result.screenshot_base64 })
    .catch(() => {})
    .finally(() => { isLoadingPage.value = false; remoteInputText.value = '' })
}

function toggleBrowserMode() {
  if (browserMode.value === 'iframe') {
    browserMode.value = 'remote'
    if (currentUrl.value) {
      isLoadingPage.value = true
      browserNavigate(currentUrl.value)
        .then(result => { if (result.ok) remoteScreenshot.value = result.screenshot_base64 || '' })
        .catch(() => {})
        .finally(() => { isLoadingPage.value = false })
    }
  } else {
    browserMode.value = 'iframe'
    remoteScreenshot.value = ''
  }
}

watch(() => ctxStore.pendingSignals.length, () => {
  const signal = ctxStore.consumeSignal()
  if (!signal) return
  if (signal.type === 'show-work' && signal.payload.workId && typeof signal.payload.workId === 'string') {
    ctxStore.linkWork(signal.payload.workId)
    activePanel.value = 'preview'
  }
})
watch(() => ctxStore.previewItem, (val) => { if (val) activePanel.value = 'preview' })
watch(() => workStore.activeWorkId, (id) => { if (id && activePanel.value !== 'preview') activePanel.value = 'preview' })
onMounted(() => {
  if (workStore.activeWorkId && activePanel.value !== 'preview') {
    activePanel.value = 'preview'
  }
})

function navigateToUrl(url: string) {
  activePanel.value = 'browser'
  browserMode.value = 'remote'
  pushHistory(url)
  currentUrl.value = url
  addressInput.value = url
  iframeLoadError.value = false
  isLoadingPage.value = true
  browserNavigate(url)
    .then(result => {
      if (result.ok) {
        remoteScreenshot.value = result.screenshot_base64 || ''
        if (result.url) { currentUrl.value = result.url; addressInput.value = result.url }
      } else { remoteScreenshot.value = '' }
    })
    .catch(() => { remoteScreenshot.value = '' })
    .finally(() => { isLoadingPage.value = false })
}

defineExpose({ navigateToUrl })
</script>

<style scoped>
.ctx-sidebar { height: 100%; display: flex; flex-direction: column; background: #fff; border-radius: 0 12px 12px 0; flex-shrink: 0; overflow: hidden; }

.ctx-topbar { flex: none; display: flex; align-items: center; padding: 0 6px; height: 38px; border-bottom: 1px solid rgba(0,0,0,0.06); gap: 4px; }
.ctx-back { display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; border: none; background: none; border-radius: 6px; color: #666; cursor: pointer; flex-shrink: 0; }
.ctx-back:hover { background: rgba(0,0,0,0.05); color: #333; }
.ctx-topbar-title-wrap { flex: 1; display: flex; align-items: center; gap: 5px; min-width: 0; }
.ctx-topbar-icon { color: #6366f1; flex-shrink: 0; }
.ctx-topbar-title { font-size: 13px; font-weight: 600; color: #1a1a1a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ctx-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: none; border-radius: 8px; color: #888; cursor: pointer; flex-shrink: 0; }
.ctx-close:hover { background: rgba(0,0,0,0.05); color: #333; }

.ctx-nav-center { flex: 1; overflow-y: auto; padding: 16px 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.ctx-nav-group { margin-bottom: 24px; width: 100%; display: flex; flex-direction: column; align-items: center; }
.ctx-nav-group:last-child { margin-bottom: 0; }
.ctx-nav-group-label { display: block; font-size: 10px; font-weight: 600; color: #bbb; padding: 0 14px; margin-bottom: 5px; letter-spacing: 0.5px; text-align: center; text-transform: uppercase; }
.ctx-nav-row { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; max-width: 220px; padding: 10px 14px; border: none; background: none; border-radius: 8px; color: #444; font-size: 13px; font-weight: 500; cursor: pointer; text-align: center; transition: background 0.12s, color 0.12s; line-height: 1.2; }
.ctx-nav-row:hover { background: rgba(0,0,0,0.05); color: #1a1a1a; }

.ctx-sub { flex: 1; min-height: 0; overflow-y: auto; overflow-x: clip; scrollbar-width: thin; scrollbar-color: rgba(0,0,0,0.12) transparent; }
.ctx-sub::-webkit-scrollbar { width: 4px; }
.ctx-sub::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 2px; }

.ctx-sub-browser { padding: 0; overflow: hidden; background: #fff; }

/* ===== 浏览器: Chrome/Edge 风格 ===== */
.ctx-br { display: flex; flex-direction: column; height: 100%; }
.ctx-br-toolbar { flex: none; display: flex; align-items: center; gap: 2px; padding: 5px 6px; background: #f1f1f1; border-bottom: 1px solid #d9d9d9; }
.ctx-br-btn { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; background: none; color: #555; border-radius: 6px; cursor: pointer; flex-shrink: 0; transition: background 0.12s, color 0.12s; }
.ctx-br-btn:hover:not(:disabled) { background: rgba(0,0,0,0.08); color: #222; }
.ctx-br-btn:disabled { opacity: 0.35; cursor: default; }
.ctx-br-spin { animation: ctx-br-rotate 0.8s linear infinite; }
@keyframes ctx-br-rotate { to { transform: rotate(360deg); } }

.ctx-br-addr-wrap { flex: 1; display: flex; align-items: center; gap: 5px; padding: 4px 9px; background: #fff; border-radius: 18px; border: 1px solid #cfcfcf; min-width: 0; transition: border-color 0.15s, box-shadow 0.15s; }
.ctx-br-addr-wrap:focus-within { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.15); }
.ctx-br-lock { color: #22c55e; flex-shrink: 0; }
.ctx-br-addr { flex: 1; border: none; background: none; outline: none; font-size: 12.5px; color: #222; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-width: 0; line-height: 1.25; }
.ctx-br-addr::placeholder { color: #aaa; }

.ctx-br-viewport { flex: 1; position: relative; background: #fff; overflow: hidden; }
.ctx-br-iframe { width: 100%; height: 100%; border: none; display: block; }
.ctx-br-home { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; background: #fff; color: #ccc; }
.ctx-br-home span { font-size: 13px; color: #999; font-weight: 500; }
.ctx-br-error { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; background: #fff; color: #999; }
.ctx-br-error span { font-size: 13px; color: #888; font-weight: 500; }
.ctx-br-error-btn { padding: 6px 16px; border: 1px solid #ddd; border-radius: 6px; background: #f5f5f5; color: #444; font-size: 12px; cursor: pointer; transition: background 0.15s; }
.ctx-br-error-btn:hover { background: #eee; }
.ctx-br-error-btn-sub { background: transparent; border-color: transparent; color: #999; }
.ctx-br-error-btn-sub:hover { color: #666; }
.ctx-br-btn-active { background: rgba(99,102,241,0.12); color: #6366f1; }
.ctx-br-screenshot { width: 100%; height: 100%; object-fit: contain; cursor: crosshair; user-select: none; -webkit-user-drag: none; }
.ctx-br-loading { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; background: rgba(255,255,255,0.92); color: #999; z-index: 2; }
.ctx-br-loading span { font-size: 12px; }
.ctx-br-remote-bar { position: absolute; bottom: 0; left: 0; right: 0; padding: 6px 8px; background: rgba(255,255,255,0.96); border-top: 1px solid rgba(0,0,0,0.06); display: flex; gap: 4px; z-index: 3; }
.ctx-br-remote-text { flex: 1; border: 1px solid #ddd; border-radius: 6px; padding: 5px 10px; font-size: 12px; outline: none; background: #fff; color: #333; }
.ctx-br-remote-text:focus { border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99,102,241,0.12); }
.ctx-br-publish-status { position: absolute; top: 8px; left: 8px; right: 8px; padding: 8px 12px; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; gap: 8px; z-index: 4; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.ctx-br-publish-submitting { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.ctx-br-publish-awaiting_manual { background: #fefce8; color: #a16207; border: 1px solid #fde68a; }
.ctx-br-publish-submitted { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.ctx-br-publish-failed { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
.ctx-br-publish-status-text { flex: 1; line-height: 1.4; }
.ctx-br-publish-confirm { flex-shrink: 0; padding: 3px 10px; border-radius: 4px; border: 1px solid rgba(0,0,0,0.12); background: #fff; color: #333; font-size: 11px; cursor: pointer; transition: background 0.15s; }
.ctx-br-publish-confirm:hover { background: #f5f5f5; }

.ctx-asset-item { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.ctx-asset-item:hover { background: rgba(0,0,0,0.03); }
.ctx-asset-cover { width: 36px; height: 36px; border-radius: 6px; background: #f3f4f6; display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; }
.ctx-asset-img { width: 100%; height: 100%; object-fit: cover; }
.ctx-asset-iframe { width: 1080px; height: 1440px; transform: scale(0.0333); transform-origin: top left; border: none; pointer-events: none; }
.ctx-asset-placeholder { color: #ccc; }
.ctx-asset-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.ctx-asset-title { font-size: 12.5px; font-weight: 500; color: #1a1a1a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.3; }
.ctx-asset-meta { font-size: 10.5px; color: #999; }

.ctx-section { padding: 10px; display: flex; flex-direction: column; gap: 6px; border-bottom: 1px solid rgba(0,0,0,0.04); }
.ctx-section:last-child { border-bottom: none; }
.ctx-section-head { display: flex; align-items: center; justify-content: space-between; }
.ctx-section-label { font-size: 10px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.4px; }
.ctx-section-count { font-size: 9.5px; font-weight: 600; color: #aaa; background: rgba(0,0,0,0.04); border-radius: 8px; padding: 1px 5px; min-width: 16px; text-align: center; }
.ctx-section-empty { display: flex; align-items: center; gap: 5px; font-size: 11.5px; color: #bbb; padding: 6px 0; }

.ctx-item { display: flex; align-items: flex-start; gap: 7px; padding: 7px; border-radius: 6px; border: 1px solid rgba(0,0,0,0.04); background: #fafafa; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
.ctx-item:hover { border-color: rgba(0,0,0,0.08); background: #f5f5f5; }
.ctx-item-pinned { border-color: rgba(59,130,246,0.2); background: rgba(59,130,246,0.02); }
.ctx-item-icon { flex: none; width: 24px; height: 24px; border-radius: 5px; display: flex; align-items: center; justify-content: center; color: #666; background: rgba(0,0,0,0.04); }
.ctx-item-icon-work { color: #4a90d9; background: rgba(74,144,217,0.08); }
.ctx-item-icon-analysis { color: #f97316; background: rgba(249,115,22,0.08); }
.ctx-item-icon-file { color: #8b5cf6; background: rgba(139,92,246,0.08); }
.ctx-item-icon-url { color: #06b6d4; background: rgba(6,182,212,0.08); }
.ctx-item-icon-rule { color: #10b981; background: rgba(16,185,129,0.08); }
.ctx-item-icon-memory { color: #ec4899; background: rgba(236,72,153,0.08); }
.ctx-item-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.5px; }
.ctx-item-label { font-size: 11.5px; font-weight: 500; color: #1a1a1a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.3; }
.ctx-item-summary { font-size: 9.5px; color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ctx-item-actions { flex: none; display: flex; gap: 2px; opacity: 0; transition: opacity 0.15s; }
.ctx-item:hover .ctx-item-actions { opacity: 1; }
.ctx-item-btn { display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; border: none; background: none; border-radius: 4px; color: #aaa; cursor: pointer; }
.ctx-item-btn:hover { background: rgba(0,0,0,0.06); color: #555; }
.ctx-pin-active { color: #3b82f6; }

.ctx-preview-block { padding: 0; }

.ctx-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 36px 20px; color: #bbb; text-align: center; }
.ctx-empty-title { font-size: 13px; font-weight: 500; color: #888; }
.ctx-empty-desc { font-size: 11.5px; color: #bbb; }

.ctx-sidebar.is-dark { background: #1e1e1e; }
.ctx-sidebar.is-dark .ctx-topbar { border-bottom-color: rgba(255,255,255,0.08); }
.ctx-sidebar.is-dark .ctx-back { color: #777; }
.ctx-sidebar.is-dark .ctx-back:hover { background: rgba(255,255,255,0.06); color: #ccc; }
.ctx-sidebar.is-dark .ctx-topbar-icon { color: #818cf8; }
.ctx-sidebar.is-dark .ctx-topbar-title { color: #e0e0e0; }
.ctx-sidebar.is-dark .ctx-close { color: #777; }
.ctx-sidebar.is-dark .ctx-close:hover { background: rgba(255,255,255,0.06); color: #ccc; }
.ctx-sidebar.is-dark .ctx-nav-group-label { color: #555; }
.ctx-sidebar.is-dark .ctx-nav-row { color: #aaa; }
.ctx-sidebar.is-dark .ctx-nav-row:hover { background: rgba(255,255,255,0.06); color: #e0e0e0; }
.ctx-sidebar.is-dark .ctx-section { border-bottom-color: rgba(255,255,255,0.04); }
.ctx-sidebar.is-dark .ctx-section-label { color: #777; }
.ctx-sidebar.is-dark .ctx-section-count { color: #666; background: rgba(255,255,255,0.06); }
.ctx-sidebar.is-dark .ctx-section-empty { color: #555; }
.ctx-sidebar.is-dark .ctx-item { border-color: rgba(255,255,255,0.06); background: rgba(255,255,255,0.04); }
.ctx-sidebar.is-dark .ctx-item:hover { border-color: rgba(255,255,255,0.1); background: rgba(255,255,255,0.07); }
.ctx-sidebar.is-dark .ctx-item-label { color: #e0e0e0; }
.ctx-sidebar.is-dark .ctx-item-summary { color: #777; }
.ctx-sidebar.is-dark .ctx-item-btn { color: #666; }
.ctx-sidebar.is-dark .ctx-item-btn:hover { background: rgba(255,255,255,0.08); color: #bbb; }
.ctx-sidebar.is-dark .ctx-empty { color: #555; }
.ctx-sidebar.is-dark .ctx-empty-title { color: #888; }
.ctx-sidebar.is-dark .ctx-empty-desc { color: #555; }
.ctx-sidebar.is-dark .ctx-asset-item:hover { background: rgba(255,255,255,0.06); }
.ctx-sidebar.is-dark .ctx-asset-title { color: #e0e0e0; }
.ctx-sidebar.is-dark .ctx-asset-meta { color: #666; }
.ctx-sidebar.is-dark .ctx-asset-cover { background: rgba(255,255,255,0.06); }
.ctx-sidebar.is-dark .ctx-sub-browser { background: #1e1e1e; }
.ctx-sidebar.is-dark .ctx-br-toolbar { background: #2a2a2e; border-bottom-color: rgba(255,255,255,0.08); }
.ctx-sidebar.is-dark .ctx-br-btn { color: #aaa; }
.ctx-sidebar.is-dark .ctx-br-btn:hover:not(:disabled) { background: rgba(255,255,255,0.08); color: #fff; }
.ctx-sidebar.is-dark .ctx-br-addr-wrap { background: #1e1e1e; border-color: rgba(255,255,255,0.12); }
.ctx-sidebar.is-dark .ctx-br-addr-wrap:focus-within { border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,0.2); }
.ctx-sidebar.is-dark .ctx-br-addr { color: #e0e0e0; }
.ctx-sidebar.is-dark .ctx-br-addr::placeholder { color: #666; }
.ctx-sidebar.is-dark .ctx-br-viewport { background: #121212; }
.ctx-sidebar.is-dark .ctx-br-home { background: #1e1e1e; }
.ctx-sidebar.is-dark .ctx-br-home span { color: #666; }
.ctx-sidebar.is-dark .ctx-br-error { background: #1e1e1e; }
.ctx-sidebar.is-dark .ctx-br-error span { color: #666; }
.ctx-sidebar.is-dark .ctx-br-error-btn { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.12); color: #aaa; }
.ctx-sidebar.is-dark .ctx-br-error-btn:hover { background: rgba(255,255,255,0.10); }
</style>