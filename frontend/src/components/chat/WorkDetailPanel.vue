<template>
  <aside class="wdp" v-if="work">
    <div class="wdp-header">
      <div class="wdp-header-info">
        <span class="wdp-header-title">{{ work.title }}</span>
      </div>
      <button class="wdp-close" @click="$emit('close')" title="关闭">
        <X :size="16" :stroke-width="1.8" />
      </button>
    </div>

    <nav class="wdp-tabs">
      <a
        v-for="tab in currentTabs"
        :key="tab.key"
        class="wdp-tab"
        :class="{ 'wdp-tab-active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <component :is="tab.icon" :size="13" :stroke-width="1.8" />
        <span>{{ tab.label }}</span>
      </a>
    </nav>

    <div class="wdp-body">
      <!-- ===== 未发布（草稿）模式：横向图文 + 发布平台 ===== -->
      <template v-if="isDraft">
        <div class="wdp-draft-gallery" v-if="allPageHtmls.length > 1">
          <div class="wdp-draft-gallery-track" ref="galleryRef" @scroll="onGalleryScroll" style="display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;padding:8px 6px;align-items:stretch;">
            <div v-for="(html, i) in allPageHtmls" :key="i" class="wdp-draft-html-card" style="flex:0 0 auto;width:180px;height:240px;border-radius:8px;overflow:hidden;border:1px solid rgba(0,0,0,0.08);scroll-snap-align:start;background:#fff;position:relative;">
              <iframe :srcdoc="html" style="width:1080px;height:1440px;transform:scale(0.1667);transform-origin:top left;pointer-events:none;border:none;" sandbox="allow-same-origin" />
              <span style="position:absolute;bottom:4px;right:6px;font-size:10px;color:#999;background:rgba(255,255,255,0.85);padding:1px 4px;border-radius:3px;">{{ i + 1 }}</span>
            </div>
          </div>
          <span class="wdp-draft-gallery-indicator">{{ currentImageIndex + 1 }} / {{ allPageHtmls.length }}</span>
        </div>
        <div class="wdp-draft-gallery" v-else-if="allImages.length">
          <div class="wdp-draft-gallery-track" ref="galleryRef" @scroll="onGalleryScroll" style="display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding:8px 10px;align-items:center;">
            <div v-for="(img, i) in allImages" :key="i" class="wdp-draft-gallery-card" style="flex:0 0 auto;width:120px;height:160px;border-radius:6px;overflow:hidden;border:1px solid rgba(0,0,0,0.08);scroll-snap-align:start;background:#fff;">
              <img :src="img" :alt="`${work.title} - ${i + 1}`" style="width:100%;height:100%;object-fit:cover;display:block;" @error="onImageError($event, img)" />
            </div>
          </div>
          <span class="wdp-draft-gallery-indicator" v-if="allImages.length > 1">{{ currentImageIndex + 1 }} / {{ allImages.length }}</span>
        </div>
        <div v-else-if="firstPageHtml" class="wdp-draft-gallery wdp-draft-html-preview">
          <iframe :srcdoc="firstPageHtml" class="wdp-draft-iframe" sandbox="allow-same-origin" />
        </div>
        <div v-else class="wdp-draft-gallery-empty">
          <ImageIcon :size="32" :stroke-width="1.2" />
          <span>暂无图片，可通过对话生成</span>
        </div>

        <div class="wdp-section">
          <div class="wdp-section-title">作品信息</div>
          <div class="wdp-meta">
            <span class="wdp-meta-chip wdp-type-chip">{{ contentTypeLabel }}</span>
            <span class="wdp-meta-chip">{{ work.title || '未命名' }}</span>
          </div>
          <div class="wdp-tags" v-if="work.tags?.length">
            <span class="wdp-tag" v-for="tag in work.tags.slice(0, 8)" :key="tag">#{{ tag }}</span>
          </div>
          <div class="wdp-content-text" v-if="work.contentText" style="max-height: 120px; overflow-y: auto;">{{ work.contentText }}</div>
        </div>

        <div class="wdp-section">
          <div class="wdp-section-title">快捷操作</div>
          <div class="wdp-actions">
            <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'xhs_note_creator')">
              <Sparkles :size="14" /> AI生成笔记
            </button>
            <button class="wdp-action-btn" @click="$emit('chat-action', 'copywriting')">
              <PenLine :size="14" /> 撰写文案
            </button>
            <button class="wdp-action-btn" @click="$emit('chat-action', 'optimize_title')">
              <Type :size="14" /> 优化标题
            </button>
            <button class="wdp-action-btn" @click="$emit('chat-action', 'design_cover')">
              <ImageIcon :size="14" /> 设计封面
            </button>
          </div>
        </div>

        <div class="wdp-section wdp-publish-platforms">
          <div class="wdp-section-title">发布到</div>
          <div class="wdp-platform-grid">
            <button class="wdp-platform-btn" @click="$emit('chat-action', 'publish_xiaohongshu')">
              <span class="wdp-platform-icon wdp-platform-xhs">📕</span>
              <span class="wdp-platform-name">小红书</span>
            </button>
            <button class="wdp-platform-btn" @click="$emit('chat-action', 'publish_douyin')">
              <span class="wdp-platform-icon wdp-platform-dy">🎵</span>
              <span class="wdp-platform-name">抖音</span>
            </button>
            <button class="wdp-platform-btn" @click="$emit('chat-action', 'publish_kuaishou')">
              <span class="wdp-platform-icon wdp-platform-ks">🎬</span>
              <span class="wdp-platform-name">快手</span>
            </button>
            <button class="wdp-platform-btn" @click="$emit('chat-action', 'publish_bilibili')">
              <span class="wdp-platform-icon wdp-platform-bl">📺</span>
              <span class="wdp-platform-name">B站</span>
            </button>
            <button class="wdp-platform-btn" @click="$emit('chat-action', 'publish_zhihu')">
              <span class="wdp-platform-icon wdp-platform-zh">💡</span>
              <span class="wdp-platform-name">知乎</span>
            </button>
            <button class="wdp-platform-btn" @click="$emit('chat-action', 'publish_wechat')">
              <span class="wdp-platform-icon wdp-platform-wx">💬</span>
              <span class="wdp-platform-name">视频号</span>
            </button>
          </div>
        </div>
      </template>

      <!-- ===== 已有作品模式 ===== -->
      <template v-else>
        <!-- 预览 Tab（含数据） -->
        <template v-if="activeTab === 'preview'">
          <div class="wdp-gallery" v-if="allImages.length">
            <button class="wdp-gallery-nav wdp-gallery-prev" v-if="allImages.length > 1" @click="scrollGallery(-1)" :class="{ 'wdp-gallery-nav-hidden': !canScrollPrev }">
              <ChevronLeft :size="16" :stroke-width="2" />
            </button>
            <div class="wdp-gallery-track" ref="galleryRef" @scroll="onGalleryScroll" style="display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding:8px 10px;align-items:center;">
              <div v-for="(img, i) in allImages" :key="i" class="wdp-gallery-card" style="flex:0 0 auto;width:120px;height:160px;border-radius:6px;overflow:hidden;border:1px solid rgba(0,0,0,0.08);scroll-snap-align:start;background:#fff;">
                <img :src="img" :alt="`${work.title} - ${i + 1}`" style="width:100%;height:100%;object-fit:cover;display:block;" @error="onImageError($event, img)" />
              </div>
            </div>
            <button class="wdp-gallery-nav wdp-gallery-next" v-if="allImages.length > 1" @click="scrollGallery(1)" :class="{ 'wdp-gallery-nav-hidden': !canScrollNext }">
              <ChevronRight :size="16" :stroke-width="2" />
            </button>
            <span class="wdp-gallery-indicator" v-if="allImages.length > 1">{{ currentImageIndex + 1 }} / {{ allImages.length }}</span>
          </div>
          <div class="wdp-section">
            <div class="wdp-meta">
              <span class="wdp-meta-chip wdp-platform-chip">{{ platformLabel }}</span>
              <span class="wdp-meta-chip wdp-type-chip">{{ contentTypeLabel }}</span>
              <span class="wdp-meta-chip" v-if="work.publishedAt">{{ formatDate(work.publishedAt) }}</span>
            </div>
            <div class="wdp-tags" v-if="work.tags?.length">
              <span class="wdp-tag" v-for="tag in work.tags.slice(0, 8)" :key="tag">#{{ tag }}</span>
            </div>
          </div>
          <div class="wdp-section">
            <div class="wdp-metrics">
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ fmtNum(work.views || work.playCount || 0) }}</span>
                <span class="wdp-metric-label">{{ isVideo ? '播放' : '浏览' }}</span>
              </div>
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ fmtNum(work.likes) }}</span>
                <span class="wdp-metric-label">点赞</span>
              </div>
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ fmtNum(work.collects) }}</span>
                <span class="wdp-metric-label">收藏</span>
              </div>
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ fmtNum(work.comments) }}</span>
                <span class="wdp-metric-label">评论</span>
              </div>
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ fmtNum(work.shares) }}</span>
                <span class="wdp-metric-label">分享</span>
              </div>
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ (work.interactionRate * 100).toFixed(1) }}%</span>
                <span class="wdp-metric-label">互动率</span>
              </div>
              <div class="wdp-metric" v-if="work.completionRate != null">
                <span class="wdp-metric-value">{{ (work.completionRate * 100).toFixed(0) }}%</span>
                <span class="wdp-metric-label">完播率</span>
              </div>
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ work.viralScore }}</span>
                <span class="wdp-metric-label">传播分</span>
              </div>
            </div>
            <div class="wdp-viral-type" v-if="work.viralType">{{ viralTypeLabel }}</div>
          </div>
          <div class="wdp-section" v-if="work.contentText || work.scriptText">
            <div class="wdp-section-title">{{ work.contentType === 'image_text' ? '正文' : '脚本' }}</div>
            <div class="wdp-content-text">{{ work.contentText || work.scriptText }}</div>
          </div>
        </template>

        <!-- 分析 Tab -->
        <template v-if="activeTab === 'analysis'">
          <div class="wdp-section" v-if="work.aiDiagnosis">
            <div class="wdp-diagnosis">
              <div class="wdp-diagnosis-reason">{{ work.aiDiagnosis.performanceReason }}</div>
              <div class="wdp-diagnosis-group" v-if="work.aiDiagnosis.boostFactors?.length">
                <div class="wdp-diagnosis-label wdp-boost">加分因子</div>
                <div class="wdp-diagnosis-item" v-for="(f, i) in work.aiDiagnosis.boostFactors" :key="i">
                  <span class="wdp-diagnosis-factor">{{ f.factor }}</span>
                  <span class="wdp-diagnosis-evidence">{{ f.evidence }}</span>
                </div>
              </div>
              <div class="wdp-diagnosis-group" v-if="work.aiDiagnosis.dragFactors?.length">
                <div class="wdp-diagnosis-label wdp-drag">扣分因子</div>
                <div class="wdp-diagnosis-item" v-for="(f, i) in work.aiDiagnosis.dragFactors" :key="i">
                  <span class="wdp-diagnosis-factor">{{ f.factor }}</span>
                  <span class="wdp-diagnosis-evidence">{{ f.evidence }}</span>
                </div>
              </div>
              <div class="wdp-diagnosis-action" v-if="work.aiDiagnosis.nextAction">
                <span class="wdp-diagnosis-label wdp-action">下一步</span>
                {{ work.aiDiagnosis.nextAction }}
              </div>
            </div>
          </div>
          <div class="wdp-empty" v-else>
            <span>暂无 AI 诊断数据</span>
            <button class="wdp-action-btn" @click="$emit('chat-action', 'analyze')">
              <BarChart3 :size="14" /> 开始归因分析
            </button>
          </div>
        </template>

        <!-- 修改 Tab -->
        <template v-if="activeTab === 'edit'">
          <div class="wdp-section">
            <div class="wdp-section-title">导入已完成作品</div>
            <p class="wdp-hint">从已采集的作品中导入内容作为改写基础</p>
            <button class="wdp-action-btn" @click="showImportPanel = !showImportPanel">
              <Download :size="14" /> {{ showImportPanel ? '收起列表' : '选择作品导入' }}
            </button>
            <div class="wdp-import-list" v-if="showImportPanel && importableWorks.length">
              <a
                v-for="iw in importableWorks"
                :key="iw.id"
                class="wdp-similar-item wdp-import-item"
                @click="importFromWork(iw)"
              >
                <span class="wdp-work-mini-cover" :style="iw.coverUrl ? { backgroundImage: `url(${iw.coverUrl})` } : {}">
                  <span v-if="!iw.coverUrl" class="wdp-cover-placeholder">{{ iw.title.charAt(0) }}</span>
                </span>
                <div class="wdp-similar-info">
                  <span class="wdp-similar-title">{{ iw.title }}</span>
                  <span class="wdp-similar-meta">{{ workStore.getPlatformLabel(iw.platform) }} · {{ iw.performanceTier }}级</span>
                </div>
              </a>
            </div>
            <div class="wdp-import-empty" v-if="showImportPanel && !importableWorks.length">
              <span>暂无可导入的作品，请先采集</span>
            </div>
          </div>
          <div class="wdp-section">
            <div class="wdp-section-title">快捷操作</div>
            <div class="wdp-actions">
              <button class="wdp-action-btn" @click="$emit('chat-action', 'optimize_title')">
                <Type :size="14" /> 优化标题
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'rewrite')">
                <PenLine :size="14" /> 改写内容
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'design_cover')">
                <ImageIcon :size="14" /> 设计封面
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'evolve')">
                <Dna :size="14" /> 进化提炼
              </button>
            </div>
          </div>
        </template>

        <!-- 操作 Tab（已发布专属） -->
        <template v-if="activeTab === 'action'">
          <div class="wdp-section">
            <div class="wdp-section-title">二次创作</div>
            <p class="wdp-hint">基于已发布作品创建新版本草稿</p>
            <div class="wdp-actions">
              <button class="wdp-action-btn wdp-action-primary" @click="onForkAsDraft">
                <Sparkles :size="14" /> 复制为草稿
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'evolve')">
                <Dna :size="14" /> 进化提炼
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'rewrite')">
                <PenLine :size="14" /> 改写内容
              </button>
            </div>
          </div>
          <div class="wdp-section">
            <div class="wdp-section-title">优化</div>
            <div class="wdp-actions">
              <button class="wdp-action-btn" @click="$emit('chat-action', 'optimize_title')">
                <Type :size="14" /> 优化标题
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'design_cover')">
                <ImageIcon :size="14" /> 设计封面
              </button>
            </div>
          </div>
          <div class="wdp-section" v-if="work.url">
            <div class="wdp-section-title">原文链接</div>
            <a :href="work.url" target="_blank" rel="noopener" class="wdp-original-link">
              <Search :size="12" />
              <span>{{ work.url.length > 50 ? work.url.slice(0, 47) + '…' : work.url }}</span>
            </a>
          </div>
          <div class="wdp-section">
            <div class="wdp-section-title">数据刷新</div>
            <p class="wdp-hint">重新采集最新数据指标</p>
            <div class="wdp-actions">
              <button class="wdp-action-btn" @click="$emit('chat-action', 'analyze')">
                <BarChart3 :size="14" /> 归因分析
              </button>
            </div>
          </div>
        </template>

        <!-- 视频 Tab -->
        <template v-if="activeTab === 'video'">
          <div class="wdp-section">
            <div class="wdp-section-title">视频数据</div>
            <div class="wdp-metrics">
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ fmtNum(work.playCount || work.views || 0) }}</span>
                <span class="wdp-metric-label">播放量</span>
              </div>
              <div class="wdp-metric" v-if="work.completionRate != null">
                <span class="wdp-metric-value">{{ (work.completionRate * 100).toFixed(0) }}%</span>
                <span class="wdp-metric-label">完播率</span>
              </div>
              <div class="wdp-metric">
                <span class="wdp-metric-value">{{ (work.interactionRate * 100).toFixed(1) }}%</span>
                <span class="wdp-metric-label">互动率</span>
              </div>
            </div>
          </div>
          <div class="wdp-section" v-if="work.scriptText">
            <div class="wdp-section-title">脚本</div>
            <div class="wdp-content-text">{{ work.scriptText }}</div>
          </div>
          <div class="wdp-section">
            <div class="wdp-section-title">视频操作</div>
            <div class="wdp-actions">
              <button class="wdp-action-btn" @click="$emit('chat-action', 'analyze')">
                <BarChart3 :size="14" /> 归因分析
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'rewrite')">
                <PenLine :size="14" /> 改写脚本
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'design_cover')">
                <ImageIcon :size="14" /> 设计封面
              </button>
              <button class="wdp-action-btn" @click="$emit('chat-action', 'evolve')">
                <Dna :size="14" /> 进化提炼
              </button>
            </div>
          </div>
        </template>
      </template>
    </div>
  </aside>
</template>

<script setup lang="ts">
import './creation/panel-shared.css'
import { computed, ref, watch, nextTick, type Component } from 'vue'
import {
  X, Eye, BarChart3, PenLine, Type, Image as ImageIcon, Dna,
  Lightbulb, Sparkles, Send, Search, ChevronLeft, ChevronRight,
  Download, Wand2
} from 'lucide-vue-next'
import { useWorkStore, type WorkItem } from '@/stores/work'

interface TabDef {
  key: string
  label: string
  icon: Component
}

const props = defineProps<{
  work: WorkItem | null
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  'chat-action': [action: string]
}>()

const workStore = useWorkStore()
const activeTab = ref('discover')
const showImportPanel = ref(false)

const allImages = computed(() => {
  if (!props.work) return []
  const imgs = props.work.images?.filter(Boolean) || []
  if (imgs.length > 0) return imgs
  const pages = props.work.cardDraft?.pages
  if (pages && pages.length > 0) {
    const pageImages: string[] = []
    for (const p of pages) {
      const page = p as any
      if (page?.imageUrl) pageImages.push(page.imageUrl)
      if (Array.isArray(page?.pngUrls)) pageImages.push(...page.pngUrls.filter(Boolean))
      if (page?.content?.imageUrl) pageImages.push(page.content.imageUrl)
      if (Array.isArray(page?.content?.pngUrls)) pageImages.push(...page.content.pngUrls.filter(Boolean))
    }
    if (pageImages.length > 0) return pageImages
  }
  const pngUrls = props.work.cardDraft?.pngUrls
  if (Array.isArray(pngUrls) && pngUrls.length > 0) return pngUrls.filter(Boolean)
  if (props.work.coverUrl) return [props.work.coverUrl]
  return []
})

const firstPageHtml = computed(() => {
  if (!props.work) return ''
  if (props.work.firstPageHtml) return props.work.firstPageHtml
  const pages = props.work.cardDraft?.pages
  if (pages && pages.length > 0) {
    const first = pages[0] as any
    if (first?.content?.htmlContent) return first.content.htmlContent
    if (first?.htmlContent) return first.htmlContent
  }
  return ''
})

const allPageHtmls = computed(() => {
  if (!props.work) return []
  if (props.work.allPageHtmls && props.work.allPageHtmls.length > 0) return props.work.allPageHtmls
  const pages = props.work.cardDraft?.pages
  if (pages && pages.length > 0) {
    const htmls: string[] = []
    for (const p of pages) {
      const page = p as any
      const html = page?.content?.htmlContent || page?.htmlContent || ''
      if (html) htmls.push(html)
    }
    if (htmls.length > 0) return htmls
  }
  return []
})

const galleryRef = ref<HTMLElement | null>(null)
const canScrollPrev = ref(false)
const canScrollNext = ref(false)
const currentImageIndex = ref(0)

function scrollGallery(dir: number) {
  const el = galleryRef.value
  if (!el) return
  const scrollAmount = el.clientWidth * 0.8
  el.scrollBy({ left: dir * scrollAmount, behavior: 'smooth' })
}

function onGalleryScroll() {
  const el = galleryRef.value
  if (!el) return
  canScrollPrev.value = el.scrollLeft > 2
  canScrollNext.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 2
  const cardWidth = el.firstElementChild ? (el.firstElementChild as HTMLElement).offsetWidth + 8 : 1
  currentImageIndex.value = Math.round(el.scrollLeft / cardWidth)
}

const isDraft = computed(() => props.work?.isDraft === true)

const isPublished = computed(() => {
  if (!props.work) return false
  const status = (props.work as any).contentStatus as string | undefined
  return status === 'published' || (!status && !props.work.isDraft && !!props.work.publishedAt)
})

const isVideo = computed(() => {
  if (props.work) return ['short_video', 'long_video', 'live_clip'].includes(props.work.contentType)
  return workStore.activeCreationType === 'short_video'
})

const creationType = computed(() => {
  if (props.work) {
    const ct = props.work.contentType
    if (ct === 'image_text' || ct === 'image_gallery') return 'image_text'
    if (ct === 'short_video') return 'short_video'
    if (ct === 'long_video') return 'voiceover'
    if (ct === 'ai_edit') return 'ai_edit'
    if (ct === 'live_clip') return 'live_clip'
    if (ct === 'long_article') return 'long_article'
    return 'image_text'
  }
  return workStore.activeCreationType
})

const FIVE_LAYER_TABS: TabDef[] = [
  { key: 'discover', label: '发现', icon: Eye },
  { key: 'plan', label: '策划', icon: Lightbulb },
  { key: 'produce', label: '制作', icon: Wand2 },
  { key: 'publish', label: '发布', icon: Send },
  { key: 'attribute', label: '归因', icon: BarChart3 },
]

const ANALYSIS_TABS: TabDef[] = [
  { key: 'preview', label: '预览', icon: Eye },
  { key: 'analysis', label: '分析', icon: BarChart3 },
  { key: 'edit', label: '修改', icon: PenLine },
]

const VIDEO_ANALYSIS_TABS: TabDef[] = [
  { key: 'preview', label: '预览', icon: Eye },
  { key: 'video', label: '视频', icon: ImageIcon },
  { key: 'analysis', label: '分析', icon: BarChart3 },
  { key: 'edit', label: '修改', icon: PenLine },
]

const PUBLISHED_TABS: TabDef[] = [
  { key: 'preview', label: '数据', icon: Eye },
  { key: 'analysis', label: '诊断', icon: BarChart3 },
  { key: 'action', label: '操作', icon: PenLine },
]

const PUBLISHED_VIDEO_TABS: TabDef[] = [
  { key: 'preview', label: '数据', icon: Eye },
  { key: 'video', label: '视频', icon: ImageIcon },
  { key: 'analysis', label: '诊断', icon: BarChart3 },
  { key: 'action', label: '操作', icon: PenLine },
]

const currentTabs = computed(() => {
  if (isDraft.value) return []
  if (isPublished.value) return isVideo.value ? PUBLISHED_VIDEO_TABS : PUBLISHED_TABS
  return isVideo.value ? VIDEO_ANALYSIS_TABS : ANALYSIS_TABS
})

const importableWorks = computed(() => {
  return workStore.worksByStatus.collected.filter(w =>
    w.id !== props.work?.id &&
    (w.contentText || w.coverUrl || w.tags?.length)
  )
})

function importFromWork(source: WorkItem) {
  if (!props.work) return
  const updates: Partial<WorkItem> = {}
  if (source.title && (!props.work.title || props.work.title === '未命名创作')) {
    updates.title = source.title
  }
  if (source.contentText && !props.work.contentText) {
    updates.contentText = source.contentText
  }
  if (source.coverUrl && !props.work.coverUrl) {
    updates.coverUrl = source.coverUrl
  }
  if (source.images?.length && !props.work.images?.length) {
    updates.images = source.images
  }
  if (source.tags?.length && (!props.work.tags || props.work.tags.length === 0)) {
    updates.tags = [...source.tags]
  }
  if (source.platform && props.work.isDraft) {
    updates.platform = source.platform
  }
  if (Object.keys(updates).length > 0) {
    workStore.updateDraft(props.work.id, updates)
  }
  showImportPanel.value = false
}

function onForkAsDraft() {
  if (!props.work) return
  const draft = workStore.createDraft(props.work.contentType || 'image_text')
  workStore.updateDraft(draft.id, {
    title: props.work.title ? props.work.title + '（副本）' : '未命名创作',
    contentText: props.work.contentText || '',
    coverUrl: props.work.coverUrl || '',
    images: props.work.images ? [...props.work.images] : [],
    tags: props.work.tags ? [...props.work.tags] : [],
    platform: props.work.platform || 'xiaohongshu',
  })
  workStore.setActiveWork(draft.id)
}

const VIRAL_TYPE_LABELS: Record<string, string> = {
  collect_driven: '收藏驱动',
  share_driven: '分享驱动',
  comment_driven: '评论驱动',
  like_driven: '点赞驱动',
  balanced: '均衡型',
}

const viralTypeLabel = computed(() => {
  if (!props.work?.viralType) return ''
  return VIRAL_TYPE_LABELS[props.work.viralType] || props.work.viralType
})

const platformLabel = computed(() =>
  props.work ? workStore.getPlatformLabel(props.work.platform) : ''
)

const contentTypeLabel = computed(() =>
  props.work ? workStore.getContentTypeLabel(props.work.contentType) : ''
)

function fmtNum(n: number): string {
  return workStore.formatNumber(n)
}

function formatDate(d: string): string {
  try {
    return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return d
  }
}

function onImageError(e: Event, originalUrl: string) {
  const img = e.target as HTMLImageElement
  const currentSrc = img.src

  if (!currentSrc.includes('/api/proxy/image')) {
    if (originalUrl && (originalUrl.includes('xhscdn.com') ||
        originalUrl.includes('xiaohongshu.com') ||
        originalUrl.includes('picasso-static') ||
        originalUrl.includes('douyinvod.com') ||
        originalUrl.includes('bytedanceimg.com') ||
        originalUrl.includes('bilibili.com') ||
        originalUrl.startsWith('http'))) {
      img.src = '/api/proxy/image?url=' + encodeURIComponent(originalUrl)
      return
    }
  }

  img.style.display = 'none'
}

watch(() => props.work?.id, () => {
  if (isDraft.value) {
    activeTab.value = ''
  } else if (isPublished.value) {
    activeTab.value = 'preview'
  } else {
    activeTab.value = 'preview'
  }
  showImportPanel.value = false
})
</script>

<style scoped>
.wdp {
  height: 100%;
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.wdp-header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
}
.wdp-header-info {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}
.wdp-header-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wdp-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: none;
  border-radius: 8px;
  color: #888;
  cursor: pointer;
  flex-shrink: 0;
}
.wdp-close:hover {
  background: rgba(0,0,0,0.05);
  color: #333;
}

.wdp-tabs {
  flex: none;
  display: flex;
  gap: 2px;
  padding: 0 10px 0;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.wdp-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 7px 8px 9px;
  font-size: 11.5px;
  color: #888;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
  user-select: none;
  white-space: nowrap;
}
.wdp-tab:hover {
  color: #555;
}
.wdp-tab-active {
  color: #1a1a1a;
  font-weight: 600;
  border-bottom-color: #1a1a1a;
}

.wdp-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px 12px 16px;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.12) transparent;
}
.wdp-body::-webkit-scrollbar { width: 3px; }
.wdp-body::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 2px; }

.wdp-gallery {
  position: relative;
  margin: 0 -12px 0;
  background: #f5f5f5;
  border-radius: 8px;
  padding-bottom: 4px;
}
.wdp-gallery-track {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding: 8px 10px;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.25) rgba(0,0,0,0.06);
  align-items: center;
}
.wdp-gallery-track::-webkit-scrollbar {
  height: 6px;
}
.wdp-gallery-track::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.25);
  border-radius: 3px;
}
.wdp-gallery-track::-webkit-scrollbar-thumb:hover {
  background: rgba(0,0,0,0.4);
}
.wdp-gallery-track::-webkit-scrollbar-track {
  background: rgba(0,0,0,0.06);
  border-radius: 3px;
}
.wdp-gallery-card {
  flex: 0 0 auto;
  width: 120px;
  height: 160px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(0,0,0,0.08);
  scroll-snap-align: start;
  background: #fff;
}
.wdp-gallery-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  cursor: pointer;
  transition: transform 0.15s;
}
.wdp-gallery-img:hover {
  transform: scale(1.02);
}
.wdp-gallery-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(255,255,255,0.9);
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
  color: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2;
  transition: opacity 0.2s, transform 0.15s;
}
.wdp-gallery-nav:hover { background: #fff; transform: translateY(-50%) scale(1.1); }
.wdp-gallery-prev { left: 6px; }
.wdp-gallery-next { right: 6px; }
.wdp-gallery-nav-hidden { opacity: 0; pointer-events: none; }
.wdp-gallery-indicator {
  position: absolute;
  bottom: 8px;
  right: 12px;
  font-size: 9.5px;
  color: #fff;
  background: rgba(0,0,0,0.45);
  padding: 2px 6px;
  border-radius: 8px;
}

/* ── 草稿横向图文画廊 ── */
.wdp-draft-gallery {
  position: relative;
  padding: 10px 0;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.wdp-draft-gallery-track {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 0 10px;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.25) rgba(0,0,0,0.06);
}
.wdp-draft-gallery-track::-webkit-scrollbar {
  height: 6px;
}
.wdp-draft-gallery-track::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.25);
  border-radius: 3px;
}
.wdp-draft-gallery-track::-webkit-scrollbar-thumb:hover {
  background: rgba(0,0,0,0.4);
}
.wdp-draft-gallery-track::-webkit-scrollbar-track {
  background: rgba(0,0,0,0.06);
  border-radius: 3px;
}
.wdp-draft-gallery-card {
  flex: 0 0 auto;
  width: 120px;
  height: 160px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(0,0,0,0.08);
  scroll-snap-align: start;
}
.wdp-draft-gallery-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.wdp-draft-gallery-indicator {
  position: absolute;
  bottom: 12px;
  right: 12px;
  font-size: 9.5px;
  color: #fff;
  background: rgba(0,0,0,0.45);
  padding: 2px 6px;
  border-radius: 8px;
}
.wdp-draft-gallery-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 10px;
  color: #aaa;
  font-size: 12px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}

/* ── 草稿 HTML iframe 预览 ── */
.wdp-draft-html-preview {
  padding: 10px 0;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.wdp-draft-iframe {
  width: 1080px;
  height: 1440px;
  transform: scale(0.16);
  transform-origin: top left;
  border: none;
  pointer-events: none;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

/* ── 发布平台网格 ── */
.wdp-publish-platforms {
  margin-top: auto;
  border-top: 1px solid rgba(0,0,0,0.06);
  padding-top: 10px;
}
.wdp-platform-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.wdp-platform-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 3px;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
  transition: all 0.15s;
}
.wdp-platform-btn:hover {
  border-color: rgba(0,0,0,0.15);
  background: #f0f0f0;
  transform: translateY(-1px);
}
.wdp-platform-icon {
  font-size: 20px;
  line-height: 1;
}
.wdp-platform-name {
  font-size: 10.5px;
  color: #555;
  font-weight: 500;
}

.wdp-original-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: #3b82f6;
  text-decoration: none;
  word-break: break-all;
  padding: 3px 0;
}
.wdp-original-link:hover {
  color: #2563eb;
  text-decoration: underline;
}
</style>