<template>
  <div class="wdp-preview" v-if="hasContent">
    <div class="wdp-section">
      <div class="wdp-section-title">作品预览</div>
    </div>

    <div class="wdp-preview-images" v-if="displayImages.length">
      <div class="wdp-preview-gallery">
        <button
          class="wdp-preview-nav wdp-preview-prev"
          v-if="displayImages.length > 1"
          @click="scrollPrev"
          :class="{ 'wdp-preview-nav-hidden': !canScrollPrev }"
        >
          ‹
        </button>
        <div class="wdp-preview-track" ref="trackRef" @scroll="onScroll">
          <div
            v-for="(img, i) in displayImages"
            :key="i"
            class="wdp-preview-slide"
          >
            <img :src="img" :alt="`预览图 ${i + 1}`" class="wdp-preview-img" @error="onImgError($event, img)" />
          </div>
        </div>
        <button
          class="wdp-preview-nav wdp-preview-next"
          v-if="displayImages.length > 1"
          @click="scrollNext"
          :class="{ 'wdp-preview-nav-hidden': !canScrollNext }"
        >
          ›
        </button>
        <span class="wdp-preview-indicator" v-if="displayImages.length > 1">
          {{ currentIndex + 1 }} / {{ displayImages.length }}
        </span>
      </div>
    </div>

    <div class="wdp-preview-card-pngs" v-if="cardPngs.length">
      <div class="wdp-preview-card-grid">
        <div v-for="(url, i) in cardPngs" :key="i" class="wdp-preview-card-item">
          <img :src="url" :alt="`卡片 ${i + 1}`" class="wdp-preview-card-img" />
        </div>
      </div>
    </div>

    <div class="wdp-preview-card-html" v-if="cardHtmlPages.length">
      <div class="wdp-preview-card-grid" ref="cardGridRef">
        <div v-for="(page, i) in cardHtmlPages" :key="page.id || i" class="wdp-preview-card-item">
          <div class="wdp-preview-card-iframe-wrap">
            <iframe
              sandbox="allow-same-origin"
              :srcdoc="page.htmlContent"
              class="wdp-preview-card-iframe"
              loading="lazy"
            ></iframe>
          </div>
        </div>
      </div>
    </div>

    <div class="wdp-preview-title-row" v-if="work.title && work.title !== '未命名创作'">
      <span class="wdp-preview-title">{{ work.title }}</span>
    </div>

    <div class="wdp-preview-text" v-if="displayText">
      <div class="wdp-preview-text-label">{{ textLabel }}</div>
      <div class="wdp-preview-text-body">{{ displayText }}</div>
    </div>

    <div class="wdp-preview-tags" v-if="work.tags?.length">
      <span class="wdp-tag" v-for="tag in work.tags.slice(0, 10)" :key="tag">#{{ tag }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import './panel-shared.css'
import { computed, ref, onMounted, onUpdated, onUnmounted } from 'vue'
import type { WorkItem } from '@/stores/work'

const CARD_W = 1080
const CARD_H = 1440

const props = defineProps<{
  work: WorkItem
}>()

const trackRef = ref<HTMLElement | null>(null)
const cardGridRef = ref<HTMLElement | null>(null)
const canScrollPrev = ref(false)
const canScrollNext = ref(false)
const currentIndex = ref(0)
let _resizeObs: ResizeObserver | null = null

function fitCardIframes() {
  const grid = cardGridRef.value
  if (!grid) return
  const panelBody = grid.closest<HTMLElement>('.wdp-body')
  const maxAvailH = panelBody ? panelBody.clientHeight * 0.75 : 380
  const items = grid.querySelectorAll<HTMLElement>('.wdp-preview-card-item')
  items.forEach((item) => {
    const containerW = item.clientWidth
    if (containerW <= 0) return
    const scaleByW = containerW / CARD_W
    const scaleByH = maxAvailH / CARD_H
    const scale = Math.min(scaleByW, scaleByH)
    const wrap = item.querySelector<HTMLElement>('.wdp-preview-card-iframe-wrap')
    const iframe = item.querySelector<HTMLIFrameElement>('.wdp-preview-card-iframe')
    if (wrap && iframe) {
      wrap.style.width = `${Math.round(CARD_W * scale)}px`
      wrap.style.height = `${Math.round(CARD_H * scale)}px`
      iframe.style.width = `${CARD_W}px`
      iframe.style.height = `${CARD_H}px`
      iframe.style.transform = `scale(${scale})`
      iframe.style.transformOrigin = 'top left'
    }
    item.style.height = `${Math.round(CARD_H * scale)}px`
  })
}

onMounted(() => {
  requestAnimationFrame(fitCardIframes)
  if (cardGridRef.value) {
    _resizeObs = new ResizeObserver(() => requestAnimationFrame(fitCardIframes))
    _resizeObs.observe(cardGridRef.value)
  }
})
onUpdated(() => { requestAnimationFrame(fitCardIframes) })
onUnmounted(() => { _resizeObs?.disconnect() })

const displayImages = computed(() => {
  const imgs = props.work.images?.filter(Boolean) || []
  if (imgs.length > 0) return imgs
  if (props.work.coverUrl) return [props.work.coverUrl]
  return []
})

const cardPngs = computed(() => {
  return props.work.cardDraft?.pngUrls?.filter(Boolean) || []
})

const cardHtmlPages = computed(() => {
  const pages = props.work.cardDraft?.pages || []
  return pages
    .filter((p: any) => p?.htmlContent)
    .map((p: any) => ({
      ...p,
      htmlContent: p.htmlContent.replace(
        /<meta\s+name=["']viewport["'][^>]*>/gi,
        '<meta name="viewport" content="width=1080,initial-scale=1">'
      ),
    })) as any[]
})

const displayText = computed(() => {
  return props.work.contentText || props.work.scriptText || ''
})

const textLabel = computed(() => {
  if (props.work.scriptText) return '脚本'
  return '正文'
})

const hasContent = computed(() => {
  return (
    displayImages.value.length > 0 ||
    cardPngs.value.length > 0 ||
    cardHtmlPages.value.length > 0 ||
    (props.work.title && props.work.title !== '未命名创作') ||
    displayText.value.length > 0 ||
    (props.work.tags && props.work.tags.length > 0)
  )
})

function scrollPrev() {
  const el = trackRef.value
  if (!el) return
  el.scrollBy({ left: -el.clientWidth * 0.85, behavior: 'smooth' })
}

function scrollNext() {
  const el = trackRef.value
  if (!el) return
  el.scrollBy({ left: el.clientWidth * 0.85, behavior: 'smooth' })
}

function onScroll() {
  const el = trackRef.value
  if (!el) return
  canScrollPrev.value = el.scrollLeft > 2
  canScrollNext.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 2
  const slideWidth = el.firstElementChild
    ? (el.firstElementChild as HTMLElement).offsetWidth + 8
    : 1
  currentIndex.value = Math.round(el.scrollLeft / slideWidth)
}

function onImgError(e: Event, originalUrl: string) {
  const img = e.target as HTMLImageElement
  const currentSrc = img.src
  if (!currentSrc.includes('/api/proxy/image') && originalUrl && originalUrl.startsWith('http')) {
    img.src = '/api/proxy/image?url=' + encodeURIComponent(originalUrl)
    return
  }
  img.style.display = 'none'
}
</script>

<style scoped>
.wdp-preview {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}

.wdp-preview-images {
  margin-bottom: 10px;
}

.wdp-preview-gallery {
  position: relative;
  background: #f5f5f5;
  border-radius: 8px;
  overflow: hidden;
}

.wdp-preview-track {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding: 8px;
  scrollbar-width: none;
  align-items: center;
}
.wdp-preview-track::-webkit-scrollbar {
  display: none;
}

.wdp-preview-slide {
  flex: 0 0 auto;
  scroll-snap-align: start;
  max-width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wdp-preview-img {
  max-height: 320px;
  max-width: 100%;
  width: auto;
  height: auto;
  border-radius: 6px;
  object-fit: contain;
  background: #eee;
  display: block;
}

.wdp-preview-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(255,255,255,0.9);
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
  color: #333;
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2;
  transition: opacity 0.2s;
}
.wdp-preview-prev { left: 6px; }
.wdp-preview-next { right: 6px; }
.wdp-preview-nav-hidden { opacity: 0; pointer-events: none; }

.wdp-preview-indicator {
  position: absolute;
  bottom: 10px;
  right: 12px;
  font-size: 10px;
  color: #fff;
  background: rgba(0,0,0,0.45);
  padding: 2px 6px;
  border-radius: 6px;
}

.wdp-preview-card-pngs {
  margin-bottom: 10px;
}

.wdp-preview-card-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.wdp-preview-card-item {
  border-radius: 6px;
  overflow: hidden;
  background: #f5f5f5;
}

.wdp-preview-card-img {
  width: 100%;
  display: block;
  border-radius: 6px;
}

.wdp-preview-card-html {
  margin-bottom: 10px;
}

.wdp-preview-card-item {
  position: relative;
}

.wdp-preview-card-iframe {
  border: none;
  border-radius: 6px;
  display: block;
  background: #fff;
  transform-origin: top left;
}

.wdp-preview-card-iframe-wrap {
  overflow: hidden;
  border-radius: 6px;
}

.wdp-preview-title-row {
  margin-bottom: 8px;
}

.wdp-preview-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
  line-height: 1.4;
}

.wdp-preview-text {
  margin-bottom: 8px;
}

.wdp-preview-text-label {
  font-size: 10px;
  font-weight: 600;
  color: #999;
  letter-spacing: 0.3px;
  margin-bottom: 4px;
}

.wdp-preview-text-body {
  font-size: 12px;
  line-height: 1.6;
  color: #444;
  max-height: 160px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 8px 10px;
  background: #f9f9fa;
  border-radius: 6px;
}

.wdp-preview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>