<template>
  <div class="mint-shell tpd-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'cards-transparent': cardsTransparent, 'dark-theme': darkTheme }">

    <!-- ============ LEFT COLUMN ============ -->
    <SidebarNav
      :current-page="'topic-pool'"
      :cards-transparent="cardsTransparent"
      :dark-theme="darkTheme"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @toggle-cards-transparent="toggleCardsTransparent"
      @toggle-theme="toggleTheme"
      @go-eco="goToEco"
    />

    <div
      v-if="!isSidebarCollapsed"
      class="tpd-sidebar-resizer"
      @mousedown="startSidebarResize"
      title="拖动调整侧边栏宽度"
    ><div class="tpd-sidebar-resizer-line"></div></div>

    <!-- ============ MIDDLE COLUMN ============ -->
    <main class="tpd-page">
      <div class="tpd-content-card-wrapper" :class="{ 'has-preview': hasAnyImage }">
        <!-- 左侧图片预览栏（仅有图片时渲染，复刻 cover_img + images，不打断详情卡片内容流） -->
        <aside v-if="hasAnyImage" class="tpd-preview-panel" ref="previewPanel" :style="{ width: previewWidth + 'px' }">
          <div class="tpd-preview-body" ref="previewBody">
            <div class="tpd-preview-main" v-if="detail && detail.cover_img" @click="previewImage(detail.cover_img)">
              <img :src="safeImageUrl(detail.cover_img)" :alt="detail?.title || '封面'" loading="lazy" @error="onImgError($event)" />
              <span class="tpd-preview-badge">封面</span>
            </div>
            <div class="tpd-preview-thumbs" v-if="detail && detail.images && detail.images.length > 0">
              <div
                v-for="(img, idx) in detail.images"
                :key="idx"
                class="tpd-preview-thumb"
                @click="previewImage(img)"
              >
                <img :src="safeImageUrl(img)" :alt="`图${idx + 1}`" loading="lazy" @error="onImgError($event)" />
              </div>
            </div>
            <div class="tpd-preview-empty" v-if="!detail?.cover_img && !(detail?.images && detail.images.length > 0)">
              <Image /><span>暂无图片</span>
            </div>
          </div>
        </aside>
        <div
          v-if="hasAnyImage"
          class="tpd-preview-resizer"
          @mousedown="startPreviewResize"
          title="拖动调整预览栏宽度"
        ><div class="tpd-preview-resizer-line"></div></div>
      <div class="tpd-content-card">
      <div class="tpd-container" ref="scrollContainer">

      <!-- 顶部：返回 + 标题 + 操作 -->
      <section class="tpd-topbar">
        <button class="tpd-back-btn" @click="goBack" type="button">
          <ArrowLeft /><span>返回选题池</span>
        </button>
        <div class="tpd-topbar-spacer"></div>
        <div class="tpd-topbar-actions" v-if="detail">
          <a v-if="detail.url" class="tpd-orig-link" :href="detail.url" target="_blank" rel="noopener noreferrer" title="查看原文">
            <ExternalLink /><span>原文</span>
          </a>
          <button class="tpd-icon-btn" :class="{ 'is-favorited': detail.is_favorited }" @click="toggleFavorite" type="button" :title="detail.is_favorited ? '取消收藏' : '收藏'">
            <Star />
          </button>
          <button class="tpd-workflow-btn" @click="startWorkflowFromTopic" type="button" title="以此选题发起工作流">
            <Play /><span>发起工作流</span>
          </button>
        </div>
      </section>

      <!-- 加载中 -->
      <div v-if="loading" class="tpd-loading">
        <Loader2 class="tpd-spin" />
        <span>加载详情中...</span>
      </div>

      <!-- 加载失败 -->
      <div v-else-if="loadError" class="tpd-empty">
        <AlertCircle />
        <div class="tpd-empty-title">加载失败</div>
        <div class="tpd-empty-desc">{{ loadError }}</div>
        <button class="tpd-retry-btn" @click="loadDetail" type="button">
          <RefreshCw /><span>重试</span>
        </button>
      </div>

      <!-- 详情内容 -->
      <template v-else-if="detail">
        <!-- 元信息行 -->
        <section class="tpd-meta-row">
          <span class="tpd-platform-tag" :style="platformStyle(detail.platform)">{{ platformLabel(detail.platform) }}</span>
          <span class="tpd-meta-item" v-if="detail.author"><User /><span>{{ detail.author }}</span></span>
          <span class="tpd-meta-item" v-if="detail.source_keyword"><Tag /><span>{{ detail.source_keyword }}</span></span>
          <span class="tpd-meta-item" v-if="detail.published_at"><Clock /><span>{{ formatDate(detail.published_at) }}</span></span>
          <span class="tpd-meta-item" v-if="detail.auto_source === 'monitor'" :class="`tpd-heat-status-${heatStatusClass(detail.heat_status)}`">
            <Flame /><span>{{ detail.heat_status }} · {{ detail.heat_score.toFixed(0) }}</span>
          </span>
          <span class="tpd-meta-item tpd-view-count"><Eye /><span>{{ detail.view_count }} 次浏览</span></span>
        </section>

        <!-- 标题 -->
        <h1 class="tpd-title">{{ detail.title }}</h1>

        <!-- 原始摘要（短） -->
        <section class="tpd-summary" v-if="detail.summary">
          <div class="tpd-section-label"><FileText /><span>原始摘要</span></div>
          <p>{{ detail.summary }}</p>
        </section>

        <!-- AI 深度摘要区 -->
        <section class="tpd-ai-summary">
          <div class="tpd-section-label">
            <Sparkles /><span>AI 深度摘要</span>
            <span class="tpd-ai-tag" v-if="detail.ai_summary_generated_at">生成于 {{ formatDate(detail.ai_summary_generated_at) }}</span>
          </div>
          <div v-if="aiSummaryGenerating" class="tpd-ai-generating">
            <Loader2 class="tpd-spin" />
            <span>AI 正在分析内容生成深度摘要...</span>
          </div>
          <div v-else-if="detail.ai_summary" class="tpd-ai-content">
            <p>{{ detail.ai_summary }}</p>
            <div class="tpd-tags" v-if="detail.tags && detail.tags.length > 0">
              <span v-for="tag in detail.tags" :key="tag" class="tpd-tag">{{ tag }}</span>
            </div>
          </div>
          <div v-else class="tpd-ai-empty">
            <Info />
            <span>暂无 AI 摘要</span>
            <button class="tpd-ai-gen-btn" @click="generateAiSummary(false)" type="button" :disabled="aiSummaryGenerating">
              <Sparkles /><span>生成 AI 摘要</span>
            </button>
          </div>
          <div class="tpd-ai-actions" v-if="detail.ai_summary && !aiSummaryGenerating">
            <button class="tpd-ai-refresh-btn" @click="generateAiSummary(true)" type="button" :disabled="aiSummaryGenerating" title="强制重新生成（消耗 token）">
              <RefreshCw /><span>重新生成</span>
            </button>
            <span class="tpd-ai-tip" v-if="lastAiUsage !== null">上次消耗 {{ lastAiUsage }} token</span>
          </div>
        </section>

        <!-- 完整正文 -->
        <section class="tpd-content" v-if="detail.content">
          <div class="tpd-section-label"><AlignLeft /><span>完整内容</span></div>
          <div class="tpd-content-body" v-html="renderContent(detail.content)"></div>
        </section>

        <!-- 图片组 -->
        <section class="tpd-images" v-if="detail.images && detail.images.length > 0">
          <div class="tpd-section-label"><Image /><span>图片（{{ detail.images.length }}）</span></div>
          <div class="tpd-image-grid">
            <div
              v-for="(img, idx) in detail.images"
              :key="idx"
              class="tpd-image-item"
              @click="previewImage(img)"
            >
              <img :src="safeImageUrl(img)" :alt="`图片${idx + 1}`" loading="lazy" @error="onImgError($event)" />
            </div>
          </div>
        </section>

        <!-- 互动数据 -->
        <section class="tpd-metrics-card">
          <div class="tpd-section-label"><BarChart3 /><span>互动数据</span></div>
          <div class="tpd-metrics-grid">
            <div class="tpd-metric-box">
              <Users />
              <div class="tpd-metric-info">
                <div class="tpd-metric-num">{{ formatNum(detail.fans_count) }}</div>
                <div class="tpd-metric-label">粉丝</div>
              </div>
            </div>
            <div class="tpd-metric-box">
              <ThumbsUp />
              <div class="tpd-metric-info">
                <div class="tpd-metric-num">{{ formatNum(detail.likes) }}</div>
                <div class="tpd-metric-label">点赞</div>
              </div>
            </div>
            <div class="tpd-metric-box">
              <Bookmark />
              <div class="tpd-metric-info">
                <div class="tpd-metric-num">{{ formatNum(detail.collects) }}</div>
                <div class="tpd-metric-label">收藏</div>
              </div>
            </div>
            <div class="tpd-metric-box">
              <MessageSquare />
              <div class="tpd-metric-info">
                <div class="tpd-metric-num">{{ formatNum(detail.comments) }}</div>
                <div class="tpd-metric-label">评论</div>
              </div>
            </div>
            <div class="tpd-metric-box">
              <Share2 />
              <div class="tpd-metric-info">
                <div class="tpd-metric-num">{{ formatNum(detail.shares) }}</div>
                <div class="tpd-metric-label">分享</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 维度标签 -->
        <section class="tpd-dims" v-if="detail.dimensions">
          <div class="tpd-section-label"><Layers /><span>内容维度</span></div>
          <div class="tpd-dims-row">
            <span class="tpd-dim-item" v-if="detail.dimensions.emotion">
              <span class="tpd-dim-label">情绪</span>{{ detail.dimensions.emotion }}
            </span>
            <span class="tpd-dim-item" v-if="detail.dimensions.scene">
              <span class="tpd-dim-label">场景</span>{{ detail.dimensions.scene }}
            </span>
            <span class="tpd-dim-item" v-if="detail.dimensions.visual">
              <span class="tpd-dim-label">视觉</span>{{ detail.dimensions.visual }}
            </span>
          </div>
        </section>

        <!-- 关联内容推荐 -->
        <section class="tpd-related" v-if="related.length > 0">
          <div class="tpd-section-label"><Link2 /><span>关联内容推荐</span></div>
          <div class="tpd-related-grid">
            <article
              v-for="item in related"
              :key="item.id"
              class="tpd-related-card"
              @click="goToDetail(item.id)"
            >
              <div class="tpd-related-cover" v-if="item.cover_img">
                <img :src="safeImageUrl(item.cover_img)" :alt="item.title" loading="lazy" @error="onImgError($event)" />
                <span class="tpd-related-platform" :style="platformStyle(item.platform)">{{ platformLabel(item.platform) }}</span>
              </div>
              <div class="tpd-related-body">
                <span class="tpd-related-platform-text" v-if="!item.cover_img" :style="platformStyle(item.platform)">{{ platformLabel(item.platform) }}</span>
                <h4 class="tpd-related-title">{{ item.title }}</h4>
                <p class="tpd-related-summary" v-if="item.summary">{{ item.summary }}</p>
                <div class="tpd-related-meta">
                  <span class="tpd-related-metric" v-if="item.likes > 0"><ThumbsUp />{{ formatNum(item.likes) }}</span>
                  <span class="tpd-related-metric" v-if="item.comments > 0"><MessageSquare />{{ formatNum(item.comments) }}</span>
                </div>
              </div>
            </article>
          </div>
        </section>

      </template>

    </div>
      </div>
      </div>
    </main>

    <!-- 图片预览 -->
    <div class="tpd-lightbox" v-if="lightboxImg" @click="lightboxImg = ''">
      <img :src="safeImageUrl(lightboxImg)" alt="预览" @click.stop />
      <button class="tpd-lightbox-close" @click="lightboxImg = ''" type="button"><X /></button>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createIcons, icons } from 'lucide'
import {
  ArrowLeft, Star, Play, ExternalLink, Loader2, AlertCircle, RefreshCw,
  User, Tag, Clock, Flame, Eye, FileText, Sparkles, Info, AlignLeft,
  Image, BarChart3, Users, ThumbsUp, Bookmark, MessageSquare, Share2,
  Layers, Link2, X,
} from 'lucide-vue-next'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import { topicPoolApi, type TopicPoolItem } from '@/api/topic_pool'

const route = useRoute()
const router = useRouter()

// ===== 侧边栏状态（与列表页保持一致） =====
const SK_COLLAPSED = 'mint_sidebar_collapsed'
const isSidebarCollapsed = ref(localStorage.getItem(SK_COLLAPSED) === '1')
const SK_CARDS_TRANSPARENT = 'mint_cards_transparent'
const cardsTransparent = ref(localStorage.getItem(SK_CARDS_TRANSPARENT) === '1')
const SK_DARK_THEME = 'mint_dark_theme'
const darkTheme = ref(localStorage.getItem(SK_DARK_THEME) === '1')

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem(SK_COLLAPSED, isSidebarCollapsed.value ? '1' : '0')
}
function toggleCardsTransparent() {
  cardsTransparent.value = !cardsTransparent.value
  localStorage.setItem(SK_CARDS_TRANSPARENT, cardsTransparent.value ? '1' : '0')
}
function toggleTheme(event: MouseEvent) {
  const x = event.clientX
  const y = event.clientY
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y)
  )
  // @ts-ignore
  if (!document.startViewTransition) {
    darkTheme.value = !darkTheme.value
    localStorage.setItem(SK_DARK_THEME, darkTheme.value ? '1' : '0')
    return
  }
  // @ts-ignore
  const transition = document.startViewTransition(() => {
    darkTheme.value = !darkTheme.value
    localStorage.setItem(SK_DARK_THEME, darkTheme.value ? '1' : '0')
  })
  transition.ready.then(() => {
    document.documentElement.animate(
      {
        clipPath: [
          `circle(0px at ${x}px ${y}px)`,
          `circle(${endRadius}px at ${x}px ${y}px)`,
        ],
      },
      { duration: 500, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', pseudoElement: '::view-transition-new(root)' }
    )
  })
}
function handleNavClick(pageName: string) {
  if (pageName === 'topic-pool') {
    router.push('/topic-pool')
    return
  }
  router.push({ path: '/workbench', query: pageName === 'workflow' ? {} : { page: pageName } })
}
function goToEco() {
  router.push('/eco')
}

// ===== 详情页状态 =====
const detail = ref<TopicPoolItem | null>(null)
const related = ref<TopicPoolItem[]>([])
const loading = ref(false)
const loadError = ref('')
const aiSummaryGenerating = ref(false)
const lastAiUsage = ref<number | null>(null)
const lightboxImg = ref('')
const scrollContainer = ref<HTMLElement | null>(null)

// ===== 图片预览栏状态 =====
import { computed } from 'vue'
const previewWidth = ref(280)  // 默认宽度 280px
const previewPanel = ref<HTMLElement | null>(null)
const previewBody = ref<HTMLElement | null>(null)
const SK_PREVIEW_WIDTH = 'tpd_preview_width'

// 是否有任何图片（cover_img 或 images）
const hasAnyImage = computed(() => {
  if (!detail.value) return false
  return !!(detail.value.cover_img || (detail.value.images && detail.value.images.length > 0))
})

// 所有图片列表（封面 + 内容图，去重）
const allImages = computed(() => {
  if (!detail.value) return [] as string[]
  const list: string[] = []
  if (detail.value.cover_img) list.push(detail.value.cover_img)
  if (detail.value.images && detail.value.images.length > 0) {
    for (const img of detail.value.images) {
      if (img && !list.includes(img)) list.push(img)
    }
  }
  return list
})

// 图片预览栏拖拽调宽
function startPreviewResize(e: MouseEvent) {
  e.preventDefault()
  const wrapper = document.querySelector('.tpd-content-card-wrapper') as HTMLElement | null
  if (wrapper) wrapper.classList.add('tpd-resizing')
  const startX = e.clientX
  const startW = previewPanel.value ? previewPanel.value.offsetWidth : previewWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX
    const newW = Math.min(500, Math.max(200, startW + delta))
    previewWidth.value = newW
  }
  const onUp = () => {
    if (wrapper) wrapper.classList.remove('tpd-resizing')
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    localStorage.setItem(SK_PREVIEW_WIDTH, String(previewWidth.value))
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ===== 加载详情 =====
async function loadDetail() {
  const itemId = route.params.id as string
  if (!itemId) {
    loadError.value = '缺少条目 ID'
    return
  }
  loading.value = true
  loadError.value = ''
  detail.value = null
  related.value = []
  try {
    const resp = await topicPoolApi.getDetail(itemId, 8)
    detail.value = resp.detail
    related.value = resp.related || []
  } catch (e: any) {
    console.error('加载详情失败:', e)
    loadError.value = e?.response?.data?.detail || e?.message || '未知错误'
  } finally {
    loading.value = false
  }
}

// ===== 切换收藏 =====
async function toggleFavorite() {
  if (!detail.value) return
  const prev = detail.value.is_favorited
  detail.value.is_favorited = !prev
  try {
    const resp = await topicPoolApi.toggleFavorite(detail.value.id)
    detail.value.is_favorited = resp.is_favorited
  } catch (e) {
    console.error('切换收藏失败:', e)
    detail.value.is_favorited = prev
  }
}

// ===== AI 摘要生成 =====
async function generateAiSummary(force: boolean) {
  if (!detail.value || aiSummaryGenerating.value) return
  aiSummaryGenerating.value = true
  try {
    const resp = await topicPoolApi.generateAiSummary(detail.value.id, force)
    if (resp.success) {
      detail.value.ai_summary = resp.ai_summary
      detail.value.tags = resp.tags
      detail.value.ai_summary_generated_at = new Date().toISOString()
      lastAiUsage.value = resp.token_usage
    }
  } catch (e: any) {
    console.error('AI 摘要生成失败:', e)
    alert(`AI 摘要生成失败：${e?.response?.data?.detail || e?.message || '未知错误'}`)
  } finally {
    aiSummaryGenerating.value = false
  }
}

// ===== 从详情页发起新工作流 =====
function startWorkflowFromTopic() {
  if (!detail.value) return
  const item = detail.value
  const reference = {
    title: item.title,
    summary: item.summary || '',
    url: item.url || '',
    platform: item.platform,
    author: item.author || '',
    likes: item.likes || 0,
    comments: item.comments || 0,
    collects: item.collects || 0,
    shares: item.shares || 0,
    source_keyword: item.source_keyword || '',
  }
  sessionStorage.setItem('pending_topic_reference', JSON.stringify(reference))
  router.push('/workbench')
}

// ===== 跳转到关联条目详情 =====
function goToDetail(id: string) {
  router.push(`/topic-pool/${id}`)
  if (scrollContainer.value) scrollContainer.value.scrollTop = 0
}

// ===== 返回选题池列表 =====
function goBack() {
  router.push('/topic-pool')
}

// ===== 工具函数 =====
function formatNum(n: number): string {
  if (n == null || isNaN(n)) return '0'
  if (n >= 100000000) return (n / 100000000).toFixed(1).replace(/\.0$/, '') + '亿'
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + '万'
  return String(n)
}

function formatDate(s: string): string {
  if (!s) return ''
  try {
    const d = new Date(s)
    if (isNaN(d.getTime())) return s
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return s
  }
}

function platformStyle(platform: string) {
  const p = (platform || '').toLowerCase()
  let color = '#64748B'
  if (p === 'xiaohongshu') color = '#FF2442'
  else if (p === 'hackernews') color = '#FF6600'
  else if (p === 'reddit') color = '#FF4500'
  else if (p === 'tavily') color = '#FF2442'
  else if (p === 'github') color = '#24292E'
  const r = parseInt(color.slice(1, 3), 16)
  const g = parseInt(color.slice(3, 5), 16)
  const b = parseInt(color.slice(5, 7), 16)
  return { color, backgroundColor: `rgba(${r}, ${g}, ${b}, 0.12)` }
}

function platformLabel(platform: string) {
  const p = (platform || '').toLowerCase()
  if (p === 'xiaohongshu') return '小红书'
  if (p === 'hackernews') return 'HackerNews'
  if (p === 'reddit') return 'Reddit'
  if (p === 'tavily') return 'Tavily'
  if (p === 'github') return 'GitHub'
  return platform || '未知'
}

function heatStatusClass(status: string): string {
  if (status === '活跃') return 'active'
  if (status === '衰退') return 'decay'
  return 'expired'
}

function safeImageUrl(url: string): string {
  if (!url) return ''
  const u = url.trim()
  if (u.startsWith('data:image')) return u
  return u.replace(/^http:/, 'https:')
}

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}

function previewImage(url: string) {
  lightboxImg.value = url
}

// 渲染正文：把 \n 转为 <br>，简单转义 HTML
function renderContent(content: string): string {
  if (!content) return ''
  const escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped.replace(/\n/g, '<br>')
}

// ===== 路由参数变化时重新加载 =====
watch(() => route.params.id, (newId) => {
  if (newId) {
    loadDetail()
    if (scrollContainer.value) scrollContainer.value.scrollTop = 0
  }
})

// ===== 侧边栏拖拽 =====
const SK_SIDEBAR_WIDTH = 'mint_sidebar_width'
function applySidebarWidth(w: number) {
  const el = document.querySelector('.tpd-shell .mint-sidebar') as HTMLElement | null
  if (el) el.style.width = w + 'px'
}
function startSidebarResize(e: MouseEvent) {
  e.preventDefault()
  const shell = document.querySelector('.tpd-shell') as HTMLElement | null
  if (shell) shell.classList.add('tpd-resizing')
  const startX = e.clientX
  const sidebarEl = document.querySelector('.tpd-shell .mint-sidebar') as HTMLElement | null
  const startW = sidebarEl ? sidebarEl.offsetWidth : 192
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX
    const newW = Math.min(600, Math.max(170, startW + delta))
    applySidebarWidth(newW)
  }
  const onUp = () => {
    if (shell) shell.classList.remove('tpd-resizing')
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    const cur = (document.querySelector('.tpd-shell .mint-sidebar') as HTMLElement | null)?.offsetWidth || 192
    localStorage.setItem(SK_SIDEBAR_WIDTH, String(cur))
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ===== 初始化 =====
onMounted(() => {
  loadDetail()
  nextTick(() => createIcons({ icons }))
  const savedW = localStorage.getItem(SK_SIDEBAR_WIDTH)
  if (savedW && !isSidebarCollapsed.value) applySidebarWidth(Number(savedW))
  // 恢复图片预览栏宽度
  const savedPW = localStorage.getItem(SK_PREVIEW_WIDTH)
  if (savedPW) previewWidth.value = Number(savedPW)
})
</script>

<style scoped>
.tpd-page {
  --ma-blue-50: #FFF1F3;
  --ma-blue-100: #FFE4E8;
  --ma-blue-200: #FFCDD5;
  --ma-blue-300: #FF9AA7;
  --ma-blue-400: #FF2442;
  --ma-blue-500: #FF2442;
  --ma-blue-600: #FF2442;
  --ma-blue-700: #FF2442;
  --ma-blue-800: #FF2442;
  --ma-blue-900: #FF2442;
  --ma-accent: #FFF1F3;
  --ma-accent-foreground: #FF2442;
  flex: 1;
  min-width: 0;
  height: 100%;
  background: var(--ma-bg-subtle);
  font-family: var(--ma-font-sans);
  color: var(--ma-text-primary);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 56px 20px 16px;
}
.tpd-content-card-wrapper {
  display: flex;
  flex-direction: row;  /* 有图片时：预览栏 + 拖拽条 + 详情卡片 横向排列 */
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  gap: 0;
}

/* ===== 图片预览栏（无卡片包裹，图片裸露按原图比例呈现） ===== */
.tpd-preview-panel {
  flex-shrink: 0;
  height: 100%;
  /* 无边框、无背景、无圆角：图片直接裸露呈现，不包裹 */
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tpd-preview-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overscroll-behavior: contain;
}
/* 封面主图：按原图比例完整渲染，不裁剪不限制高度 */
.tpd-preview-main {
  position: relative;
  width: 100%;
  cursor: pointer;
  transition: opacity 0.2s ease;
  border-radius: 6px;
  overflow: hidden;
}
.tpd-preview-main:hover { opacity: 0.92; }
.tpd-preview-main img {
  width: 100%;
  height: auto;  /* 按原图比例，不裁剪 */
  display: block;
}
.tpd-preview-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 2px 8px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 10px;
  font-weight: 500;
  border-radius: 3px;
  backdrop-filter: blur(4px);
}
/* 缩略图：按原图比例，不固定正方形 */
.tpd-preview-thumbs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tpd-preview-thumb {
  position: relative;
  width: 100%;
  cursor: pointer;
  transition: opacity 0.2s ease;
  border-radius: 6px;
  overflow: hidden;
}
.tpd-preview-thumb:hover { opacity: 0.92; }
.tpd-preview-thumb img {
  width: 100%;
  height: auto;  /* 按原图比例，不裁剪 */
  display: block;
}
.tpd-preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--ma-text-tertiary);
  font-size: 13px;
}
.tpd-preview-empty svg { width: 32px; height: 32px; opacity: 0.5; }

/* 预览栏拖拽条 */
.tpd-preview-resizer {
  position: relative;
  width: 6px;
  cursor: col-resize;
  flex-shrink: 0;
  align-self: stretch;
  z-index: 5;
  transition: background 0.15s ease;
}
.tpd-preview-resizer-line {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 40px;
  border-radius: 2px;
  background: #D1D5DB;
  transition: background 0.15s ease, height 0.15s ease;
}
.tpd-preview-resizer:hover { background: rgba(59, 108, 246, 0.08); }
.tpd-preview-resizer:hover .tpd-preview-resizer-line {
  background: #3B6CF6;
  height: 60px;
}

.tpd-content-card {
  flex: 1;
  min-height: 0;
  min-width: 0;
  background: #FFFFFF;
  border-radius: 16px;
  border: 1px solid var(--ma-border-default);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* 预览栏无包裹，详情卡片保持完整圆角和边框 */
.tpd-content-card-wrapper.has-preview .tpd-content-card {
  border-radius: 16px;
}

.tpd-container {
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 32px 40px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}

/* ===== 顶部栏 ===== */
.tpd-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.tpd-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: 8px;
  color: var(--ma-text-secondary);
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}
.tpd-back-btn:hover {
  border-color: var(--ma-blue-500);
  color: var(--ma-blue-500);
}
.tpd-back-btn svg { width: 16px; height: 16px; }
.tpd-topbar-spacer { flex: 1; }
.tpd-topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tpd-orig-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 14px;
  border: 1px solid var(--ma-border-default);
  border-radius: 8px;
  color: var(--ma-text-secondary);
  font-size: 14px;
  text-decoration: none;
  transition: border-color 0.15s, color 0.15s;
}
.tpd-orig-link:hover {
  border-color: var(--ma-blue-500);
  color: var(--ma-blue-500);
}
.tpd-orig-link svg { width: 15px; height: 15px; }
.tpd-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--ma-border-default);
  border-radius: 8px;
  background: var(--ma-bg-base);
  color: var(--ma-text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
}
.tpd-icon-btn:hover {
  border-color: #F59E0B;
  color: #F59E0B;
}
.tpd-icon-btn svg { width: 16px; height: 16px; }
.tpd-icon-btn.is-favorited {
  color: #F59E0B;
  border-color: #F59E0B;
}
.tpd-workflow-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: var(--ma-blue-500);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s ease;
}
.tpd-workflow-btn:hover { background: var(--ma-blue-600); }
.tpd-workflow-btn svg { width: 15px; height: 15px; }

/* ===== 加载/空状态 ===== */
.tpd-loading, .tpd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 80px 0;
  color: var(--ma-text-secondary);
  font-size: 14px;
}
.tpd-loading svg, .tpd-empty svg { width: 40px; height: 40px; color: var(--ma-text-tertiary); }
.tpd-empty-title { font-size: 16px; font-weight: 600; color: var(--ma-text-secondary); }
.tpd-empty-desc { font-size: 13px; color: var(--ma-text-tertiary); }
.tpd-retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 16px;
  border: 1px solid var(--ma-blue-500);
  border-radius: 8px;
  background: var(--ma-blue-500);
  color: #fff;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
}
.tpd-retry-btn svg { width: 14px; height: 14px; }
.tpd-spin { animation: tpd-spin 1s linear infinite; }
@keyframes tpd-spin { to { transform: rotate(360deg); } }

/* ===== 元信息行 ===== */
.tpd-meta-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.tpd-platform-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
.tpd-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--ma-text-tertiary);
}
.tpd-meta-item svg { width: 13px; height: 13px; }
.tpd-heat-status-active { color: #047857; }
.tpd-heat-status-decay { color: #B45309; }
.tpd-heat-status-expired { color: #6B7280; }
.tpd-view-count { color: var(--ma-text-secondary); }

/* ===== 标题 ===== */
.tpd-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--ma-text-primary);
  line-height: 1.4;
  margin: 0;
  letter-spacing: -0.01em;
  flex-shrink: 0;
}

/* ===== 封面图（头图） ===== */
.tpd-cover {
  width: 100%;
  max-height: 440px;
  border-radius: 12px;
  overflow: hidden;
  background: var(--ma-bg-subtle);
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}
.tpd-cover:hover { transform: scale(1.005); }
.tpd-cover img {
  width: 100%;
  max-height: 440px;
  object-fit: cover;
  display: block;
}

/* ===== 区块通用 ===== */
.tpd-section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ma-text-primary);
  margin-bottom: 10px;
}
.tpd-section-label svg { width: 16px; height: 16px; color: var(--ma-blue-500); }

/* ===== 原始摘要 ===== */
.tpd-summary {
  padding: 14px 16px;
  background: var(--ma-bg-subtle);
  border-radius: 10px;
  flex-shrink: 0;
}
.tpd-summary p {
  margin: 0;
  font-size: 14px;
  color: var(--ma-text-secondary);
  line-height: 1.7;
}

/* ===== AI 摘要 ===== */
.tpd-ai-summary {
  padding: 16px 18px;
  background: linear-gradient(135deg, rgba(59, 108, 246, 0.04), rgba(139, 92, 246, 0.04));
  border: 1px solid rgba(59, 108, 246, 0.15);
  border-radius: 12px;
  flex-shrink: 0;
}
.tpd-ai-tag {
  margin-left: auto;
  font-size: 12px;
  font-weight: 400;
  color: var(--ma-text-tertiary);
}
.tpd-ai-generating {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 0;
  color: var(--ma-blue-500);
  font-size: 14px;
}
.tpd-ai-generating svg { width: 18px; height: 18px; }
.tpd-ai-content p {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: var(--ma-text-primary);
  line-height: 1.8;
}
.tpd-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.tpd-tag {
  padding: 3px 10px;
  background: rgba(59, 108, 246, 0.1);
  color: #3B6CF6;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.tpd-ai-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  color: var(--ma-text-tertiary);
  font-size: 14px;
}
.tpd-ai-empty svg { width: 16px; height: 16px; }
.tpd-ai-gen-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  padding: 6px 14px;
  border: none;
  border-radius: 8px;
  background: #3B6CF6;
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s ease;
}
.tpd-ai-gen-btn:hover:not(:disabled) { background: #2B5AE0; }
.tpd-ai-gen-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.tpd-ai-gen-btn svg { width: 14px; height: 14px; }
.tpd-ai-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed rgba(59, 108, 246, 0.15);
}
.tpd-ai-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--ma-border-default);
  border-radius: 6px;
  background: var(--ma-bg-base);
  color: var(--ma-text-secondary);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.tpd-ai-refresh-btn:hover:not(:disabled) {
  border-color: var(--ma-blue-500);
  color: var(--ma-blue-500);
}
.tpd-ai-refresh-btn svg { width: 12px; height: 12px; }
.tpd-ai-tip { font-size: 12px; color: var(--ma-text-tertiary); }

/* ===== 完整内容 ===== */
.tpd-content {
  flex-shrink: 0;
}
.tpd-content-body {
  font-size: 15px;
  color: var(--ma-text-primary);
  line-height: 1.85;
  white-space: normal;
  word-break: break-word;
}

/* ===== 图片组 ===== */
.tpd-images { flex-shrink: 0; }
.tpd-image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.tpd-image-item {
  position: relative;
  aspect-ratio: 1;
  border-radius: 10px;
  overflow: hidden;
  background: var(--ma-bg-subtle);
  cursor: pointer;
  transition: transform 0.2s ease;
}
.tpd-image-item:hover { transform: scale(1.03); }
.tpd-image-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* ===== 互动数据 ===== */
.tpd-metrics-card {
  padding: 16px 18px;
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: 12px;
  flex-shrink: 0;
}
.tpd-metrics-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
@media (max-width: 720px) {
  .tpd-metrics-grid { grid-template-columns: repeat(3, 1fr); }
}
.tpd-metric-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--ma-bg-subtle);
  border-radius: 8px;
}
.tpd-metric-box svg {
  width: 20px;
  height: 20px;
  color: var(--ma-blue-500);
  flex-shrink: 0;
}
.tpd-metric-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.tpd-metric-num {
  font-size: 18px;
  font-weight: 700;
  color: var(--ma-text-primary);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.tpd-metric-label {
  font-size: 11px;
  color: var(--ma-text-tertiary);
}

/* ===== 维度标签 ===== */
.tpd-dims { flex-shrink: 0; }
.tpd-dims-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.tpd-dim-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--ma-bg-subtle);
  border-radius: 16px;
  font-size: 13px;
  color: var(--ma-text-primary);
}
.tpd-dim-label {
  font-size: 11px;
  color: var(--ma-text-tertiary);
  font-weight: 500;
}

/* ===== 关联推荐 ===== */
.tpd-related { flex-shrink: 0; }
.tpd-related-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.tpd-related-card {
  display: flex;
  flex-direction: column;
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.tpd-related-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(17, 24, 39, 0.1);
  border-color: rgba(59, 108, 246, 0.3);
}
.tpd-related-cover {
  position: relative;
  aspect-ratio: 16 / 10;
  background: var(--ma-bg-subtle);
  overflow: hidden;
}
.tpd-related-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.3s ease;
}
.tpd-related-card:hover .tpd-related-cover img { transform: scale(1.05); }
.tpd-related-platform {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 2px 7px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  backdrop-filter: blur(4px);
}
.tpd-related-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 10px 12px;
}
.tpd-related-platform-text {
  align-self: flex-start;
  padding: 2px 7px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
}
.tpd-related-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ma-text-primary);
  line-height: 1.4;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tpd-related-summary {
  font-size: 12px;
  color: var(--ma-text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tpd-related-meta {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}
.tpd-related-metric {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--ma-text-tertiary);
}
.tpd-related-metric svg { width: 11px; height: 11px; }

/* ===== 图片预览 ===== */
.tpd-lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  cursor: zoom-out;
}
.tpd-lightbox img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  cursor: default;
}
.tpd-lightbox-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.tpd-lightbox-close svg { width: 20px; height: 20px; }
.tpd-lightbox-close:hover { background: rgba(255, 255, 255, 0.25); }

/* ===== 壳层（与列表页一致） ===== */
.tpd-shell {
  grid-template-columns: auto auto 1fr !important;
}
.tpd-shell.mint-collapsed {
  grid-template-columns: 56px 1fr !important;
}
.tpd-sidebar-resizer {
  position: relative;
  width: 6px;
  cursor: col-resize;
  flex-shrink: 0;
  align-self: stretch;
  z-index: 5;
  transition: background 0.15s ease;
}
.tpd-sidebar-resizer-line {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 40px;
  border-radius: 2px;
  background: #D1D5DB;
  transition: background 0.15s ease, height 0.15s ease;
}
.tpd-sidebar-resizer:hover { background: rgba(59, 108, 246, 0.08); }
.tpd-sidebar-resizer:hover .tpd-sidebar-resizer-line {
  background: #3B6CF6;
  height: 60px;
}
</style>
