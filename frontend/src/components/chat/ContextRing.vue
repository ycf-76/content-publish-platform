<template>
  <div class="ctx-ring" :class="{ 'ctx-ring-warn': ctxStore.contextRingWarn }">
    <svg class="ctx-ring-svg" viewBox="0 0 36 36">
      <circle class="ctx-ring-bg" cx="18" cy="18" r="15.9155" />
      <circle
        class="ctx-ring-fill"
        cx="18" cy="18" r="15.9155"
        :stroke-dasharray="dashArray"
        :stroke="ringColor"
      />
    </svg>
    <span class="ctx-ring-pct">{{ pctDisplay }}%</span>
    <span class="ctx-ring-label">{{ tokenDisplay }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatContextStore } from '@/stores/chatContext'

const ctxStore = useChatContextStore()

const pct = computed(() => Math.round(ctxStore.contextRingRatio * 100))
const pctDisplay = computed(() => pct.value)
const tokenDisplay = computed(() => {
  const t = ctxStore.estimatedTokenCount
  if (t >= 1000) return `${(t / 1000).toFixed(1)}k`
  return String(t)
})

const dashArray = computed(() => {
  const fill = ctxStore.contextRingRatio * 100
  return `${fill} ${100 - fill}`
})

const ringColor = computed(() => {
  if (pct.value >= 90) return '#e67e22'
  if (pct.value >= 70) return '#f0a050'
  return '#3b82f6'
})
</script>

<style scoped>
.ctx-ring {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}
.ctx-ring-svg {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  transform: rotate(-90deg);
}
.ctx-ring-bg {
  fill: none;
  stroke: rgba(0, 0, 0, 0.06);
  stroke-width: 3;
}
.ctx-ring-fill {
  fill: none;
  stroke: #3b82f6;
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 0.3s, stroke 0.3s;
}
.ctx-ring-pct {
  font-size: 12px;
  font-weight: 600;
  color: #333;
  min-width: 28px;
}
.ctx-ring-label {
  font-size: 10px;
  color: #888;
}
.ctx-ring-warn .ctx-ring-pct {
  color: #e67e22;
}
.ctx-ring-warn .ctx-ring-label {
  color: #e67e22;
}
</style>