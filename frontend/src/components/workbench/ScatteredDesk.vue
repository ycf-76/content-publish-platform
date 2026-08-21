<template>
  <div class="scattered-desk" ref="deskRef" @mousemove="onDeskMouseMove" @mouseleave="onDeskMouseLeave">
    <div
      v-for="(item, i) in items"
      :key="item.workflow_id"
      class="scatter-card"
      :style="scatterStyle(i)"
      @click="$emit('card-click', item)"
    >
      <div class="scatter-card-pin"></div>
      <!-- 图片区：展示 image_gen 生成的图 -->
      <div class="scatter-card-img-wrap">
        <img
          v-if="item.cover_image"
          class="scatter-card-img"
          :src="item.cover_image"
          :alt="item.title || item.topic"
          loading="lazy"
        />
        <div v-else class="scatter-card-placeholder">
          <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
        </div>
      </div>

      <!-- 图文内容区：标题 + 文案摘要 -->
      <div class="scatter-card-info">
        <div class="scatter-card-title">{{ item.title || item.topic || '未命名创作' }}</div>
        <div v-if="item.content_snippet" class="scatter-card-snippet">{{ item.content_snippet }}</div>
        <div class="scatter-card-meta">
          <span class="scatter-card-status" :style="{ color: statusColor(item.status) }">{{ statusLabel(item.status) }}</span>
          <span class="scatter-card-sep">·</span>
          <span>{{ formatRelativeTime(item.completed_at || item.updated_at || item.created_at) }}</span>
        </div>
      </div>

      <div v-if="item.likes" class="scatter-card-badge">
        <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7Z"/></svg>
        {{ item.likes }}
      </div>
    </div>

    <div v-if="items.length === 0" class="scatter-empty-canvas">
      <div class="empty-canvas-frame">
        <div class="empty-canvas-cursor"></div>
        <span class="empty-canvas-hint">你的第一件作品将出现在这里</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

export interface ShowcaseItem {
  workflow_id: string
  topic: string
  status: string
  cover_image?: string
  title?: string
  content_snippet?: string
  completed_at?: string
  updated_at?: string
  created_at: string
  likes?: number
}

const props = defineProps<{
  items: ShowcaseItem[]
}>()

defineEmits<{
  'card-click': [item: ShowcaseItem]
}>()

const deskRef = ref<HTMLElement | null>(null)

function scatterStyle(index: number) {
  const direction = index % 2 === 0 ? -1 : 1
  const rotateBase = 2.5 + (index % 4) * 1.2
  const rotate = direction * rotateBase
  const yOffset = direction * (3 + (index % 3) * 2.5)
  const mid = Math.floor(props.items.length / 2)
  const z = 10 - Math.abs(index - mid)
  const delay = index * 80 + 200
  const dealRotate = direction * (12 + index * 2.5)

  return {
    '--scatter-rotate': `${rotate}deg`,
    '--scatter-y': `${yOffset}px`,
    '--scatter-z': z,
    '--scatter-delay': `${delay}ms`,
    '--scatter-deal-rotate': `${dealRotate}deg`,
  }
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  completed: { label: '已完成', color: '#2B52E0' },
  passed: { label: '已通过', color: '#10B981' },
  running: { label: '执行中', color: '#FF2442' },
  error: { label: '出错', color: '#EF4444' },
  failed: { label: '失败', color: '#EF4444' },
  terminated: { label: '已终止', color: '#6B7280' },
  suspended: { label: '待审核', color: '#F59E0B' },
}

function statusLabel(status: string) {
  return STATUS_MAP[status]?.label || status
}

function statusColor(status: string) {
  return STATUS_MAP[status]?.color || '#6B7280'
}

function formatRelativeTime(dateStr?: string) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}小时前`
  const diffD = Math.floor(diffH / 24)
  if (diffD < 30) return `${diffD}天前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function onDeskMouseMove(e: MouseEvent) {
  const desk = deskRef.value
  if (!desk) return
  const rect = desk.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  const cards = desk.querySelectorAll('.scatter-card') as NodeListOf<HTMLElement>
  cards.forEach((card) => {
    const cr = card.getBoundingClientRect()
    const cx = cr.left + cr.width / 2 - rect.left
    const cy = cr.top + cr.height / 2 - rect.top
    const dx = cx - mx
    const dy = cy - my
    const dist = Math.sqrt(dx * dx + dy * dy)
    const maxDist = 160

    if (dist < maxDist && dist > 0) {
      const force = (1 - dist / maxDist) * 8
      const pushX = (dx / dist) * force
      const pushY = (dy / dist) * force
      card.style.setProperty('--push-x', `${pushX}px`)
      card.style.setProperty('--push-y', `${pushY}px`)
    } else {
      card.style.setProperty('--push-x', '0px')
      card.style.setProperty('--push-y', '0px')
    }
  })
}

function onDeskMouseLeave() {
  const desk = deskRef.value
  if (!desk) return
  const cards = desk.querySelectorAll('.scatter-card') as NodeListOf<HTMLElement>
  cards.forEach((card) => {
    card.style.setProperty('--push-x', '0px')
    card.style.setProperty('--push-y', '0px')
  })
}
</script>