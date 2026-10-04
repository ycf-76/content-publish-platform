<template>
  <div class="ccd-card">
    <div class="ccd-header">
      <span class="ccd-badge">卡片</span>
      <span class="ccd-title">{{ draftTitle }}</span>
      <span class="ccd-count">{{ pageCount }}页</span>
    </div>

    <div class="ccd-previews">
      <div
        v-for="(page, i) in previewPages"
        :key="page.id || i"
        class="ccd-thumb-wrap"
        @click="openLightbox(i)"
      >
        <img
          v-if="page.imageUrl"
          :src="page.imageUrl"
          class="ccd-thumb"
          loading="lazy"
          @error="onThumbError($event, page.imageUrl)"
        />
        <div v-else-if="page.htmlContent" class="ccd-thumb-iframe-wrap">
          <iframe
            sandbox="allow-same-origin"
            :srcdoc="page.htmlContent"
            class="ccd-thumb-iframe"
            loading="lazy"
            :style="thumbIframeStyle"
          ></iframe>
        </div>
        <div v-else class="ccd-thumb-placeholder">
          <span>{{ page.type === 'cover' ? '封面' : page.type === 'end' ? '结尾' : `P${i + 1}` }}</span>
        </div>
        <div class="ccd-thumb-overlay">
          <ZoomIn :size="18" />
        </div>
      </div>
    </div>

    <div class="ccd-actions">
      <button class="ccd-btn ccd-btn-view" @click="openLightbox(0)">
        <Eye :size="14" />
        <span>查看大图</span>
      </button>
      <button class="ccd-btn ccd-btn-edit" @click="openStudio">
        <Edit3 :size="14" />
        <span>编辑</span>
      </button>
    </div>

    <Teleport to="body">
      <Transition name="clb-fade">
        <div v-if="lightboxOpen" class="clb-overlay" @click.self="closeLightbox">
          <div class="clb-container">
            <button class="clb-close" @click="closeLightbox">
              <X :size="20" />
            </button>

            <button
              v-if="pageCount > 1"
              class="clb-nav clb-prev"
              :class="{ 'clb-nav-disabled': currentIndex === 0 }"
              @click="prevPage"
            >
              <ChevronLeft :size="24" />
            </button>

            <div class="clb-content">
              <img
                v-if="currentPage?.imageUrl"
                :src="currentPage.imageUrl"
                class="clb-img"
                @error="onImgError($event, currentPage.imageUrl)"
              />
              <div
                v-else-if="currentPage?.htmlContent"
                class="clb-iframe-wrapper"
                :style="lightboxWrapperStyle"
              >
                <iframe
                  sandbox="allow-same-origin"
                  :srcdoc="currentPage.htmlContent"
                  class="clb-iframe"
                  :style="lightboxIframeStyle"
                ></iframe>
              </div>
              <div v-else class="clb-empty">无预览内容</div>
            </div>

            <button
              v-if="pageCount > 1"
              class="clb-nav clb-next"
              :class="{ 'clb-nav-disabled': currentIndex === pageCount - 1 }"
              @click="nextPage"
            >
              <ChevronRight :size="24" />
            </button>

            <div class="clb-footer">
              <span class="clb-page-info">{{ currentIndex + 1 }} / {{ pageCount }}</span>
              <span v-if="currentPageTitle" class="clb-page-title">{{ currentPageTitle }}</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ZoomIn, Eye, Edit3, X, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import type { NormalizedCardDraft } from '@/composables/cardDraft'

const props = defineProps<{
  cardDraft: NormalizedCardDraft
  workId?: string
}>()

const emit = defineEmits<{
  openStudio: [workId?: string]
}>()

const lightboxOpen = ref(false)
const currentIndex = ref(0)

const CARD_NATIVE_W = 1080
const CARD_NATIVE_H = 1440
const THUMB_W = 160
const THUMB_H = Math.round(THUMB_W * (CARD_NATIVE_H / CARD_NATIVE_W))

const thumbScale = THUMB_W / CARD_NATIVE_W
const thumbIframeStyle = {
  width: `${CARD_NATIVE_W}px`,
  height: `${CARD_NATIVE_H}px`,
  transform: `scale(${thumbScale})`,
  transformOrigin: 'top left',
}

const lightboxSize = computed(() => {
  const maxW = Math.min(window.innerWidth * 0.85, 540)
  const maxH = window.innerHeight * 0.85
  const scaleW = maxW / CARD_NATIVE_W
  const scaleH = maxH / CARD_NATIVE_H
  const scale = Math.min(scaleW, scaleH)
  return {
    w: Math.round(CARD_NATIVE_W * scale),
    h: Math.round(CARD_NATIVE_H * scale),
    scale,
  }
})

const lightboxIframeStyle = computed(() => {
  const { scale } = lightboxSize.value
  return {
    width: `${CARD_NATIVE_W}px`,
    height: `${CARD_NATIVE_H}px`,
    transform: `scale(${scale})`,
    transformOrigin: 'top left',
  }
})

const lightboxWrapperStyle = computed(() => {
  const { w, h } = lightboxSize.value
  return {
    width: `${w}px`,
    height: `${h}px`,
  }
})

const draftTitle = computed(() => props.cardDraft.title || '小红书卡片')

function fixViewport(html: string): string {
  return html.replace(
    /<meta\s+name=["']viewport["'][^>]*>/gi,
    '<meta name="viewport" content="width=1080,initial-scale=1">'
  )
}

const previewPages = computed(() => {
  const pages = props.cardDraft.pages || []
  const pngUrls = props.cardDraft.pngUrls || []
  if (pages.length > 0) {
    return pages.map((p: any) => ({
      ...p,
      htmlContent: p.htmlContent ? fixViewport(p.htmlContent) : p.htmlContent,
    }))
  }
  return pngUrls.map((url: string, i: number) => ({
    id: `png_${i}`,
    type: i === 0 ? 'cover' : 'content',
    title: `卡片 ${i + 1}`,
    imageUrl: url,
    htmlContent: '',
  }))
})

const pageCount = computed(() => previewPages.value.length)

const currentPage = computed(() => previewPages.value[currentIndex.value] || null)

const currentPageTitle = computed(() => {
  const page = currentPage.value
  if (!page) return ''
  return page.title || (page.type === 'cover' ? '封面页' : page.type === 'end' ? '结尾页' : '')
})

function openLightbox(index: number) {
  currentIndex.value = Math.min(index, pageCount.value - 1)
  lightboxOpen.value = true
  document.body.style.overflow = 'hidden'
}

function closeLightbox() {
  lightboxOpen.value = false
  document.body.style.overflow = ''
}

function prevPage() {
  if (currentIndex.value > 0) currentIndex.value--
}

function nextPage() {
  if (currentIndex.value < pageCount.value - 1) currentIndex.value++
}

function openStudio() {
  emit('openStudio', props.workId)
}

function onThumbError(e: Event, originalUrl: string) {
  const img = e.target as HTMLImageElement
  if (!img.src.includes('/api/proxy/image') && originalUrl?.startsWith('http')) {
    img.src = '/api/proxy/image?url=' + encodeURIComponent(originalUrl)
    return
  }
  img.style.display = 'none'
}

function onImgError(e: Event, originalUrl: string) {
  const img = e.target as HTMLImageElement
  if (!img.src.includes('/api/proxy/image') && originalUrl?.startsWith('http')) {
    img.src = '/api/proxy/image?url=' + encodeURIComponent(originalUrl)
    return
  }
}

function onKeydown(e: KeyboardEvent) {
  if (!lightboxOpen.value) return
  if (e.key === 'Escape') closeLightbox()
  if (e.key === 'ArrowLeft') prevPage()
  if (e.key === 'ArrowRight') nextPage()
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  if (lightboxOpen.value) {
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
.ccd-card {
  background: #f0f9ff;
  border: 1px solid #93c5fd;
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 8px;
}

.ccd-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.ccd-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
  background: #3b82f6;
}

.ccd-title {
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ccd-count {
  font-size: 11px;
  color: #64748b;
  background: #e2e8f0;
  padding: 1px 6px;
  border-radius: 3px;
}

.ccd-previews {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
}

.ccd-thumb-wrap {
  position: relative;
  flex: 0 0 160px;
  height: 213px;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid #e2e8f0;
  background: #fff;
  transition: transform 0.15s, box-shadow 0.15s;
  contain: layout;
}

.ccd-thumb-wrap:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.ccd-thumb-wrap:hover .ccd-thumb-overlay {
  opacity: 1;
}

.ccd-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ccd-thumb-iframe-wrap {
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: none;
}

.ccd-thumb-iframe {
  border: none;
}

.ccd-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 500;
}

.ccd-thumb-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  opacity: 0;
  transition: opacity 0.15s;
}

.ccd-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.ccd-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 6px;
  border: none;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.ccd-btn-view {
  background: #3b82f6;
  color: #fff;
}

.ccd-btn-view:hover {
  background: #2563eb;
}

.ccd-btn-edit {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.ccd-btn-edit:hover {
  background: #e2e8f0;
}

/* Lightbox */
.clb-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
}

.clb-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.clb-close {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.15);
  border: none;
  border-radius: 8px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;
}

.clb-close:hover {
  background: rgba(255, 255, 255, 0.3);
}

.clb-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  border-radius: 50%;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;
}

.clb-nav:hover:not(.clb-nav-disabled) {
  background: rgba(255, 255, 255, 0.25);
}

.clb-nav-disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.clb-prev {
  left: 12px;
}

.clb-next {
  right: 12px;
}

.clb-content {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.clb-img {
  max-width: min(85vw, 540px);
  max-height: 85vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.clb-iframe {
  border: none;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  background: #fff;
}

.clb-iframe-wrapper {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.clb-empty {
  color: #94a3b8;
  font-size: 14px;
}

.clb-footer {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
}

.clb-page-info {
  background: rgba(255, 255, 255, 0.15);
  padding: 3px 10px;
  border-radius: 4px;
}

.clb-page-title {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.clb-fade-enter-active,
.clb-fade-leave-active {
  transition: opacity 0.2s ease;
}

.clb-fade-enter-from,
.clb-fade-leave-to {
  opacity: 0;
}
</style>