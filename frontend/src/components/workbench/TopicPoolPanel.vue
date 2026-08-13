<template>
  <div class="page-container tp-panel">
    <div class="mint-hero mint-glass">
      <div>
        <h1 class="font-cal mint-hero-title">选题池</h1>
        <p class="mint-hero-sub">爆款内容抓取、监控、筛选与管理</p>
      </div>
    </div>

    <div class="mint-workflow-cards tp-scroll-area">
      <div class="tp-embed-body">
        <TopicPoolView @start-workflow="(ref) => emit('start-workflow', ref)" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import TopicPoolView from '@/views/TopicPoolView.vue'

const emit = defineEmits<{
  'start-workflow': [reference: Record<string, unknown>]
}>()
</script>

<style scoped>
.tp-panel {
  height: 100%;
  overflow: hidden;
}

.tp-scroll-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 2px 4px 0;
}

.tp-embed-body {
  min-height: 100%;
}

.tp-embed-body :deep(.tp-page) {
  min-width: unset;
  min-height: unset;
  height: auto;
  background: transparent;
  flex-direction: column;
  overflow: visible;
}

.tp-embed-body :deep(.tp-topbar) {
  display: none;
}

.tp-embed-body :deep(.tp-container) {
  max-width: unset;
  padding: 4px 6px 16px;
  gap: 16px;
  overflow: visible;
}

.tp-embed-body :deep(.tp-stats) {
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.tp-embed-body :deep(.tp-stat-card) {
  padding: 16px 20px;
  gap: 12px;
}

.tp-embed-body :deep(.tp-stat-icon) {
  width: 38px;
  height: 38px;
}

.tp-embed-body :deep(.tp-stat-num) {
  font-size: 22px;
}

.tp-embed-body :deep(.tp-fetch) {
  padding: 14px 18px;
}

.tp-embed-body :deep(.tp-platform-tabs) {
  gap: 2px;
  padding: 3px;
}

.tp-embed-body :deep(.tp-filters) {
  padding: 12px 16px;
  gap: 12px;
}

.tp-embed-body :deep(.tp-list) {
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.tp-embed-body :deep(.tp-pagination) {
  position: relative;
  padding: 10px 0;
  border-top: none;
  background: transparent;
}

.tp-embed-body :deep(.tp-card) {
  border-radius: 10px;
  overflow: hidden;
}
</style>