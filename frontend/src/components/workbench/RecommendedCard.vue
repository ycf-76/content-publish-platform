<template>
  <div class="mint-wf-card wf-node-card wf-node-recommended">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            推荐热点
            <code class="wf-node-key">recommended</code>
          </div>
        </div>
      </div>
      <button class="wf-aux-refresh" @click="loadRecommended" :disabled="auxLoading" title="刷新推荐">
        <i data-lucide="refresh-cw" style="width:14px; height:14px;"></i>
      </button>
    </div>

    <div class="wf-node-body">
      <div class="wf-aux-scroll">
        <div v-if="auxLoading" class="wf-aux-placeholder">加载推荐中...</div>
        <div v-else-if="recommendedItems.length === 0" class="wf-aux-placeholder">暂无推荐，去选题池抓取内容试试</div>
        <div
          v-for="item in recommendedItems"
          :key="item.id"
          class="wf-aux-card"
        >
          <div v-if="item.cover_img" class="wf-aux-cover">
            <img
              :src="coverSrc(item.cover_img)"
              :alt="item.title"
              loading="lazy"
              referrerpolicy="no-referrer"
              @error="onAuxCoverError($event, item)"
            />
          </div>
          <div class="wf-aux-content">
            <div class="wf-aux-card-title">{{ item.title || '无标题' }}</div>
            <div class="wf-aux-actions">
              <button class="wf-aux-btn wf-aux-btn-primary" @click="$emit('start-from-topic', item)">
                <i data-lucide="zap" style="width:11px; height:11px;"></i>
                发起分析
              </button>
              <button class="wf-aux-btn wf-aux-btn-outline" @click="$emit('search-similar', item.source_keyword || item.title || '')">
                <i data-lucide="search" style="width:11px; height:11px;"></i>
                搜索同款
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { createIcons, icons } from 'lucide'
import { topicPoolApi, type TopicPoolItem } from '@/api/topic_pool'

const emit = defineEmits<{
  'start-from-topic': [item: TopicPoolItem]
  'search-similar': [keyword: string]
}>()

const recommendedItems = ref<TopicPoolItem[]>([])
const recommendedKeywords = ref<string[]>([])
const auxLoading = ref(false)

async function loadRecommended() {
  auxLoading.value = true
  try {
    const data = await topicPoolApi.recommended(10)
    recommendedItems.value = data.items || []
    recommendedKeywords.value = data.keywords || []
  } catch (e) {
    console.warn('[RecommendedCard] loadRecommended failed:', e)
  } finally {
    auxLoading.value = false
    nextTick(() => createIcons({ icons }))
  }
}

onMounted(() => {
  loadRecommended()
})

/** 封面图代理 */
function coverSrc(cover: string): string {
  const needsProxy = cover.includes('xhscdn.com') ||
    cover.includes('xiaohongshu.com') ||
    cover.includes('picasso-static')
  return needsProxy ? '/api/proxy/image?url=' + encodeURIComponent(cover) : cover
}

/** 平台配色 */
function letterColor(platform: string) {
  const palette: Record<string, { bg: string; fg: string }> = {
    hackernews: { bg: '#FF6600', fg: '#FFFFFF' },
    reddit: { bg: '#FF4500', fg: '#FFFFFF' },
    xiaohongshu: { bg: '#FF2442', fg: '#FFFFFF' },
    builtin: { bg: '#FF2442', fg: '#FFFFFF' },
    tavily: { bg: '#2563EB', fg: '#FFFFFF' },
  }
  return palette[platform] || { bg: '#6B7280', fg: '#FFFFFF' }
}

/** 平台简称 */
function platformLabel(platform: string): string {
  const map: Record<string, string> = {
    hackernews: 'HN',
    reddit: 'RD',
    xiaohongshu: '小红书',
    builtin: '热门',
    tavily: '全网',
  }
  return map[platform] || platform.slice(0, 4)
}

/** 字母色块标签 */
function letterLabel(platform: string, url: string, title: string): string {
  const palette: Record<string, string> = {
    hackernews: 'HN',
    reddit: 'RD',
    xiaohongshu: 'XHS',
    builtin: '热门',
  }
  if (palette[platform]) return palette[platform]
  let letter = '?'
  try {
    const u = new URL(url)
    const host = u.hostname.replace(/^www./, '')
    letter = host.charAt(0).toUpperCase() || '?'
  } catch {
    letter = (title || '?').charAt(0).toUpperCase()
  }
  return letter
}

/** 封面加载失败 */
function onAuxCoverError(e: Event, item: TopicPoolItem) {
  const img = e.target as HTMLImageElement
  const color = letterColor(item.platform)
  const label = letterLabel(item.platform, item.url || '', item.title)
  const fallback = document.createElement('div')
  fallback.className = 'wf-aux-cover-letter'
  fallback.style.background = color.bg
  fallback.style.color = color.fg
  fallback.innerHTML = `<span>${label}</span>`
  img.outerHTML = fallback.outerHTML
}

watch(() => recommendedItems.value, () => {
  nextTick(() => createIcons({ icons }))
}, { deep: true })
</script>